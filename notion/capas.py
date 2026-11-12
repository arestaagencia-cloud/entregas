"""Capas das páginas de "Conteúdos" no Notion + lista do que ainda não está no Drive.

Uso: python3 notion/capas.py            -> PRÉVIA: só verifica e gera a lista (notion/sem-drive.csv)
     python3 notion/capas.py --aplicar  -> baixa as miniaturas para docs/capas/ e põe como capa no Notion
     python3 notion/capas.py --auto     -> modo do robô: igual a --aplicar, só para páginas ainda sem capa

Capa = miniatura do arquivo do Link (vídeo: quadro do Google; pasta/carrossel: 1º arquivo da pasta).
Se na mesma pasta existir uma imagem com o mesmo nome do vídeo (ex.: "Tema - V.2.jpg"), ela vira a capa.
A imagem fica em https://entregas.arestagencia.com.br/capas/<id>.jpg (não depende do Drive depois).
Só põe capa em página SEM capa (não sobrescreve capa escolhida à mão).
"""
import csv, io, json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(AQUI))
from sync_conteudos import DB, api, todas, titulo_de, prop, id_drive, norm  # noqa: E402
from atualizar_painel import listar_publico, tipo, ordem_natural  # noqa: E402

APLICAR = "--aplicar" in sys.argv or "--auto" in sys.argv
AUTO = "--auto" in sys.argv
SITE = "https://entregas.arestagencia.com.br/capas"
PASTA = RAIZ / "docs" / "capas"


def baixar_thumb(fid, w=720):
    try:
        req = urllib.request.Request(f"https://drive.google.com/thumbnail?id={fid}&sz=w{w}",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            d, t = r.read(), r.headers.get_content_type()
        return d if t.startswith("image/") and len(d) > 800 else None
    except Exception:  # noqa: BLE001
        return None


def capas_personalizadas():
    """{id do vídeo: id da imagem com o mesmo nome na mesma pasta}, a partir dos painéis."""
    mapa = {}
    for p in (RAIZ / "paineis").glob("*.json"):
        itens = json.loads(p.read_text()).get("itens", [])
        fotos = {(i["pasta"], norm(i["nome"])): i["id"] for i in itens if i["tipo"] == "foto"}
        for i in itens:
            if i["tipo"] == "video" and (i["pasta"], norm(i["nome"])) in fotos:
                mapa[i["id"]] = fotos[(i["pasta"], norm(i["nome"]))]
            if i["tipo"] == "carrossel":
                mapa[i["id"]] = i["slides"][0]["id"]
    return mapa


def primeiro_da_pasta(pid):
    try:
        arqs = [x for x in listar_publico(pid) if not x["pasta"] and tipo(x["nome"], x.get("mime", ""))]
    except Exception:  # noqa: BLE001
        return None
    arqs.sort(key=lambda x: ordem_natural(x["nome"]))
    return arqs[0]["id"] if arqs else None


def main():
    paginas = todas(DB["conteudos"])
    clientes = {c["id"]: titulo_de(c) for c in todas(DB["clientes"])}
    servicos = {s["id"]: titulo_de(s) for s in todas(DB["servicos"])}
    pers = capas_personalizadas()
    print(f"{len(paginas)} páginas em Conteúdos")

    def avaliar(p):
        link = prop(p, "Link") or ""
        tem_capa = bool(p.get("cover"))
        if AUTO and tem_capa:
            return p, "ok_com_capa", None, None
        fid = id_drive(link)
        if not link:
            return p, "sem_link", None, None
        if not fid or "drive.google" not in link:
            return p, "link_fora_do_drive", None, None
        origem = pers.get(fid) or fid
        img = baixar_thumb(origem)
        if img is None and "/folders/" in link:  # pasta: usa o 1º arquivo
            primeiro = primeiro_da_pasta(fid)
            img = baixar_thumb(primeiro) if primeiro else None
            if img is None:
                return p, "pasta_vazia_ou_sem_acesso", None, None
        if img is None:
            return p, "arquivo_sem_acesso_ou_apagado", None, None
        return p, ("ok_com_capa" if tem_capa else "ok"), fid, img

    with ThreadPoolExecutor(10) as ex:
        res = list(ex.map(avaliar, paginas))

    no_drive = [r for r in res if r[1] in ("ok", "ok_com_capa")]
    faltam = [r for r in res if r[1] not in ("ok", "ok_com_capa")]
    por_capa = [r for r in res if r[1] == "ok"]
    motivos = {}
    for r in faltam:
        motivos[r[1]] = motivos.get(r[1], 0) + 1
    print(f"No Drive: {len(no_drive)} | sem capa ainda: {len(por_capa)} | fora do Drive: {len(faltam)} {motivos}")

    # lista do que falta subir para o Drive
    rotulo = {"sem_link": "Sem link", "link_fora_do_drive": "Link não é do Drive",
              "arquivo_sem_acesso_ou_apagado": "Arquivo apagado, privado ou link quebrado",
              "pasta_vazia_ou_sem_acesso": "Pasta vazia ou sem acesso"}
    linhas = []
    for p, motivo, _, _ in faltam:
        linhas.append({"Cliente": ", ".join(clientes.get(x, "?") for x in prop(p, "Clientes") or []) or "(sem cliente)",
                       "Serviço": ", ".join(servicos.get(x, "?") for x in prop(p, "Serviços") or []) or "(sem serviço)",
                       "Conteúdo": titulo_de(p), "Status": prop(p, "Status Conteúdo") or "",
                       "Motivo": rotulo.get(motivo, motivo), "Link atual": prop(p, "Link") or "",
                       "Página no Notion": p["url"]})
    linhas.sort(key=lambda l: (l["Cliente"], l["Serviço"], l["Conteúdo"]))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(linhas[0].keys()) if linhas else ["Cliente"])
    w.writeheader()
    w.writerows(linhas)
    (AQUI / "sem-drive.csv").write_text(buf.getvalue())
    if not AUTO:
        print("=====CSV=====")
        print(buf.getvalue())
        print("=====FIM=====")

    if not APLICAR:
        return
    PASTA.mkdir(parents=True, exist_ok=True)
    feitos, erros = 0, 0
    for p, _, fid, img in por_capa:
        (PASTA / f"{fid}.jpg").write_bytes(img)
        try:
            api("PATCH", f"pages/{p['id']}", {"cover": {"type": "external", "external": {"url": f"{SITE}/{fid}.jpg"}}})
            feitos += 1
        except Exception as e:  # noqa: BLE001
            erros += 1
            print("ERRO", titulo_de(p), e)
        time.sleep(0.35)
    print(f"CAPAS: {feitos} aplicadas, {erros} erros")


if __name__ == "__main__":
    main()
