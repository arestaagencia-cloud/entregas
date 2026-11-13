"""Sincroniza os conteúdos entregues (Drive, via paineis/*.json) com a database "Conteúdos" do Notion.

Uso: python3 notion/sync_conteudos.py            -> PRÉVIA (não altera nada), grava notion/relatorio-sync.md
     python3 notion/sync_conteudos.py --aplicar  -> aplica as mudanças e grava o relatório

Regras (combinadas com a equipe em nov/2026):
- Entram vídeos e carrosséis (fotos avulsas ficam só no painel).
- Casamento: 1) ID do arquivo do Drive no "Link"; 2) nome igual (sem extensão, acento e caixa), se único.
- Propriedades: Nome (= nome do arquivo sem extensão), Link (arquivo; carrossel = pasta), Clientes,
  Serviços ("Cliente - Mês.AA"; marcas da Universa também "Universa - Mês.AA"), SubCategorias Universa,
  Tipo de Conteúdo (Reels | Vídeo Horizontal | Carrossel, mantendo outras opções já marcadas) e
  Status Conteúdo = "Entregue e Aprovado" quando estiver vazio ou em etapa de produção.
- Nunca apaga páginas. Formato, Data de Publicação e Desenvolveu não são tocados.
Precisa da variável NOTION_TOKEN (integração "Robô ArestAgência").
"""
import json, os, re, struct, sys, time, unicodedata, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
APLICAR = "--aplicar" in sys.argv
AUTO = "--auto" in sys.argv  # modo do robô: aplica sozinho, sem lixeira e com limite de segurança
LIMITE_AUTO = 60
DB = {"conteudos": "2f274a51-c09f-8017-9d90-d6e858355881",
      "servicos": "2f074a51-c09f-80f3-9064-de717b8d4f27",
      "clientes": "2f074a51-c09f-80dc-9bdb-d78b219f934b"}
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
         "Novembro", "Dezembro"]
CONCLUIDOS = {"Legenda", "Finalizado", "Entregue e Aprovado", "Programado", "Publicado", "Cancelado"}
FORMATOS = {"Reels", "Vídeo Horizontal", "Carrossel"}
EXT = re.compile(r"\.(mov|mp4|m4v|avi|mkv|webm|jpe?g|png|heic|webp)$", re.I)


# ---------------------------------------------------------------- Notion API
def api(metodo, caminho, corpo=None, tentativa=0):
    req = urllib.request.Request(f"https://api.notion.com/v1/{caminho}", method=metodo,
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503, 504) and tentativa < 5:
            time.sleep(2 + 3 * tentativa)
            return api(metodo, caminho, corpo, tentativa + 1)
        raise RuntimeError(f"{metodo} {caminho}: {e.code} {e.read().decode()[:400]}")


def todas(db):
    linhas, cursor = [], None
    while True:
        r = api("POST", f"databases/{db}/query", {"page_size": 100} | ({"start_cursor": cursor} if cursor else {}))
        linhas += r["results"]
        if not r.get("has_more"):
            return linhas
        cursor = r["next_cursor"]


def titulo_de(p):
    for v in p["properties"].values():
        if v["type"] == "title":
            return "".join(t["plain_text"] for t in v["title"]).strip()
    return ""


def prop(p, nome):
    v = p["properties"].get(nome)
    if not v:
        return None
    t = v["type"]
    if t == "url":
        return v["url"]
    if t == "relation":
        return [x["id"] for x in v["relation"]]
    if t == "multi_select":
        return [x["name"] for x in v["multi_select"]]
    if t == "status":
        return v["status"]["name"] if v["status"] else None
    if t == "title":
        return titulo_de(p)
    return None


# ---------------------------------------------------------------- utilidades
def norm(s):
    s = unicodedata.normalize("NFKD", EXT.sub("", s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def id_drive(link):
    m = re.search(r"/(?:file/d|folders)/([\w-]{20,})", link or "") or re.search(r"[?&]id=([\w-]{20,})", link or "")
    return m.group(1) if m else None


def mes_titulo(ym):
    a, m = ym.split("-")
    return f"{MESES[int(m) - 1]}.{a[2:]}"


def proporcao(fid):
    """'h' se a capa do vídeo for horizontal, 'v' se vertical, None se não deu para medir."""
    try:
        req = urllib.request.Request(f"https://drive.google.com/thumbnail?id={fid}&sz=w320",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            d = r.read()
        if d[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", d[16:24])
        else:  # JPEG: procura o marcador SOF
            i = 2
            while i < len(d):
                if d[i] != 0xFF:
                    i += 1
                    continue
                marca = d[i + 1]
                if marca in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", d[i + 5:i + 9])
                    break
                i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
            else:
                return None
        return "h" if w > h * 1.1 else "v"
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- dados do Drive (painéis)
def conteudos_do_drive():
    itens = []
    for p in sorted((RAIZ / "paineis").glob("*.json")):
        cfg = json.loads(p.read_text())
        universa = cfg["slug"] == "universa"
        for i in cfg.get("itens", []):
            if i["tipo"] not in ("video", "carrossel"):
                continue
            itens.append({**i, "painel": cfg["slug"], "universa": universa})
    return itens


# ---------------------------------------------------------------- principal
def main():
    if not TOKEN:
        raise SystemExit("NOTION_TOKEN não definido.")
    drive = conteudos_do_drive()
    print(f"Drive: {len(drive)} vídeos/carrosséis nos painéis")

    clientes = todas(DB["clientes"])
    servicos = todas(DB["servicos"])
    conteudos = todas(DB["conteudos"])
    print(f"Notion: {len(clientes)} clientes, {len(servicos)} serviços, {len(conteudos)} conteúdos")
    cli_por_nome = {norm(titulo_de(c)): c["id"] for c in clientes}
    serv_por_nome = {}
    for s in servicos:
        serv_por_nome.setdefault(norm(titulo_de(s)), []).append(s["id"])
    nome_cli = {c["id"]: titulo_de(c) for c in clientes}
    nome_serv = {s["id"]: titulo_de(s) for s in servicos}

    # índices das páginas existentes
    por_id, por_nome = {}, {}
    for c in conteudos:
        fid = id_drive(prop(c, "Link"))
        if fid:
            por_id.setdefault(fid, []).append(c)
        por_nome.setdefault(norm(titulo_de(c)), []).append(c)

    # proporção dos vídeos (Reels x Vídeo Horizontal)
    vids = [i["id"] for i in drive if i["tipo"] == "video"]
    with ThreadPoolExecutor(12) as ex:
        orient = dict(zip(vids, ex.map(proporcao, vids)))

    usados, plano, avisos, sem_cliente, sem_servico = set(), [], [], set(), set()
    arquivar = {}
    criado = lambda c: c["created_time"]

    # 1ª passada: casa pelo ID do arquivo no Link (vale para todos os itens antes de olhar nomes)
    casamento = {}
    for it in drive:
        nome_arq = EXT.sub("", it["nome"]).strip()
        cands = [c for c in por_id.get(it["id"], []) if c["id"] not in usados]
        if cands:
            cands.sort(key=lambda c: (norm(titulo_de(c)) != norm(nome_arq), criado(c)))
            casamento[it["id"]] = (cands[0], "link")
            usados.add(cands[0]["id"])
            if len(cands) > 1:
                avisos.append(f"{len(cands)} páginas apontam para o mesmo arquivo **{nome_arq}** "
                              f"({it['cliente']} · {mes_titulo(it['mes'])}); atualizei \"{titulo_de(cands[0])}\" e "
                              "deixei as outras sem mexer (confira à mão): "
                              + ", ".join(f"[{titulo_de(c)}]({c['url']})" for c in cands[1:]))
    # 2ª passada: casa pelo nome; com duplicatas, atualiza a mais antiga e manda as outras para a lixeira
    for it in drive:
        if it["id"] in casamento:
            continue
        nome_arq = EXT.sub("", it["nome"]).strip()
        cands = sorted([c for c in por_nome.get(norm(nome_arq), []) if c["id"] not in usados], key=criado)
        if cands:
            casamento[it["id"]] = (cands[0], "nome")
            usados.add(cands[0]["id"])
            for c in cands[1:]:
                arquivar[c["id"]] = (c, nome_arq)

    for it in drive:
        cli = it["cliente"]
        nome_arq = EXT.sub("", it["nome"]).strip()
        alvo_cli, alvo_serv, sub = [], [], []
        nomes_cli = (["Universa", cli] if it["universa"] else [cli])
        for n in nomes_cli:
            cid = cli_por_nome.get(norm(n))
            if cid:
                alvo_cli.append(cid)
            elif not (it["universa"] and n == cli):
                sem_cliente.add(n)
            nserv = f"{n} - {mes_titulo(it['mes'])}"
            sids = serv_por_nome.get(norm(nserv), [])
            pasta_serv = it.get("servico")  # nome da pasta do mês, ex.: "Sarau Convida - Letícia Fialho - Abril.26"
            if not it["universa"] and pasta_serv and serv_por_nome.get(norm(pasta_serv)):
                nserv, sids = pasta_serv, serv_por_nome[norm(pasta_serv)]
            if sids:
                alvo_serv.append(sids[0])
                if len(sids) > 1:
                    avisos.append(f"Serviço duplicado no Notion: **{nserv}** ({len(sids)} páginas). Usei a primeira.")
            else:
                sem_servico.add(nserv)
        if it["universa"]:
            sub = [cli]
        if it["tipo"] == "carrossel":
            formato, link = "Carrossel", f"https://drive.google.com/drive/folders/{it['id']}"
        else:
            nn = norm(it["nome"])
            if re.search(r"\bhorizontal\b|\b16 ?x ?9\b", nn):
                formato = "Vídeo Horizontal"
            elif re.search(r"\bvertical\b|\b9 ?x ?16\b", nn):
                formato = "Reels"
            else:
                formato = "Vídeo Horizontal" if orient.get(it["id"]) == "h" else "Reels"
            link = f"https://drive.google.com/file/d/{it['id']}/view"

        desejado = {"Nome": nome_arq, "Link": link, "Clientes": sorted(alvo_cli), "Serviços": sorted(alvo_serv),
                    "SubCategorias Universa": sub}
        pag, como = casamento.get(it["id"], (None, ""))
        if pag is None:
            desejado["Tipo de Conteúdo"] = [formato]
            desejado["Status Conteúdo"] = "Entregue e Aprovado"
            plano.append({"acao": "criar", "item": it, "props": desejado})
            continue
        mud = {}  # o Nome das páginas existentes não é alterado (a equipe padroniza no Notion)
        if id_drive(prop(pag, "Link")) != it["id"] or not (prop(pag, "Link") or "").startswith(link):
            mud["Link"] = (prop(pag, "Link"), link)
        for k in ("Clientes", "Serviços"):
            atual = sorted(prop(pag, k) or [])
            if atual != desejado[k] and desejado[k]:
                mud[k] = (atual, desejado[k])
        if sorted(prop(pag, "SubCategorias Universa") or []) != sorted(sub):
            mud["SubCategorias Universa"] = (prop(pag, "SubCategorias Universa") or [], sub)
        tipos = prop(pag, "Tipo de Conteúdo") or []
        novo_tipos = sorted([t for t in tipos if t not in FORMATOS] + [formato])
        if sorted(tipos) != novo_tipos:
            mud["Tipo de Conteúdo"] = (tipos, novo_tipos)
        st = prop(pag, "Status Conteúdo")
        if st not in CONCLUIDOS:
            mud["Status Conteúdo"] = (st, "Entregue e Aprovado")
        if mud:
            plano.append({"acao": "atualizar", "pagina": pag, "item": it, "mud": mud, "como": como})

    # ---------------- relatório
    criar = [p for p in plano if p["acao"] == "criar"]
    atual = [p for p in plano if p["acao"] == "atualizar"]
    ok = len(drive) - len(criar) - len(atual)
    fmt = lambda v: ", ".join(nome_cli.get(x) or nome_serv.get(x) or x for x in v) if isinstance(v, list) else (v or "vazio")
    L = [f"# Sincronização Drive → Notion ({'APLICADA' if (APLICAR or AUTO) else 'PRÉVIA, nada foi alterado'})", "",
         f"- Conteúdos no Drive (vídeos e carrosséis dos painéis): **{len(drive)}**",
         f"- Já corretos no Notion: **{ok}**", f"- Páginas a corrigir: **{len(atual)}**",
         f"- Páginas a criar: **{len(criar)}**", f"- Duplicatas para a lixeira: **{len(arquivar)}**",
         f"- Avisos: **{len(avisos)}**",
         f"- Vídeos horizontais detectados: **{sum(1 for v in orient.values() if v == 'h')}**"
         f" (não medidos: {sum(1 for v in orient.values() if v is None)}, ficam como Reels)", ""]
    if sem_cliente:
        L += ["## Clientes sem página no Notion", "", *[f"- {n}" for n in sorted(sem_cliente)], ""]
    if sem_servico:
        L += ["## Serviços (Cliente - Mês.AA) que não existem no Notion",
              "Os conteúdos desses meses ficam sem a relação com o Serviço até a página ser criada.", "",
              *[f"- {n}" for n in sorted(sem_servico)], ""]
    if arquivar:
        L += ["## Duplicatas que vão para a lixeira do Notion (fica a mais antiga)", "",
              *[f"- [{titulo_de(c)}]({c['url']}) · criada em {c['created_time'][:10]}" for c, _ in arquivar.values()], ""]
    if avisos:
        L += ["## Avisos", "", *[f"- {a}" for a in avisos], ""]
    resumo = {}
    for p in atual:
        for k in p["mud"]:
            resumo[k] = resumo.get(k, 0) + 1
    if resumo:
        L += ["## O que muda nas páginas existentes", "", *[f"- {k}: {n} páginas" for k, n in sorted(resumo.items())], ""]
    por_painel = {}
    for p in plano:
        por_painel.setdefault(p["item"]["painel"], []).append(p)
    for painel, ps in sorted(por_painel.items()):
        L += [f"## Painel {painel}", ""]
        for p in sorted(ps, key=lambda p: (p["item"]["mes"], p["item"]["cliente"], p["item"]["nome"])):
            it = p["item"]
            if p["acao"] == "criar":
                pr = p["props"]
                L.append(f"- **CRIAR** · {it['cliente']} · {mes_titulo(it['mes'])} · {pr['Nome']} · "
                         f"{pr['Tipo de Conteúdo'][0]} · serviços: {fmt(pr['Serviços']) or '—'}")
            else:
                ch = "; ".join(f"{k}: {fmt(a)} → {fmt(b)}" for k, (a, b) in p["mud"].items())
                L.append(f"- **CORRIGIR** · [{titulo_de(p['pagina'])}]({p['pagina']['url']}) · {ch}")
        L.append("")
    (RAIZ / "notion" / "relatorio-sync.md").write_text("\n".join(L))
    print("=====RELATORIO=====")
    print("\n".join(L))
    print("=====FIM=====")

    if AUTO:
        if arquivar:
            print(f"AUTO: {len(arquivar)} duplicatas encontradas; o robô não manda nada para a lixeira (rode à mão).")
            arquivar.clear()
        if len(plano) > LIMITE_AUTO:
            print(f"::warning::AUTO: {len(plano)} mudanças de uma vez (limite {LIMITE_AUTO}). Nada aplicado; "
                  "rode a prévia à mão e confira antes.")
            return
    if not (APLICAR or AUTO):
        return
    # ---------------- aplicar
    def props_api(d):
        o = {}
        if "Nome" in d:
            o["Nome"] = {"title": [{"text": {"content": d["Nome"]}}]}
        if "Link" in d:
            o["Link"] = {"url": d["Link"]}
        for k in ("Clientes", "Serviços"):
            if k in d:
                o[k] = {"relation": [{"id": x} for x in d[k]]}
        for k in ("SubCategorias Universa", "Tipo de Conteúdo"):
            if k in d:
                o[k] = {"multi_select": [{"name": x} for x in d[k]]}
        if "Status Conteúdo" in d:
            o["Status Conteúdo"] = {"status": {"name": d["Status Conteúdo"]}}
        return o

    feitos, erros = 0, []
    for p in plano:
        try:
            if p["acao"] == "criar":
                api("POST", "pages", {"parent": {"database_id": DB["conteudos"]}, "properties": props_api(p["props"])})
            else:
                api("PATCH", f"pages/{p['pagina']['id']}",
                    {"properties": props_api({k: b for k, (a, b) in p["mud"].items()})})
            feitos += 1
        except Exception as e:  # noqa: BLE001
            erros.append(f"{p['item']['nome']}: {e}")
        time.sleep(0.35)  # limite da API do Notion (~3 req/s)
    for c, _ in arquivar.values():
        try:
            api("PATCH", f"pages/{c['id']}", {"archived": True})  # vai para a lixeira (recuperável por 30 dias)
            feitos += 1
        except Exception as e:  # noqa: BLE001
            erros.append(f"lixeira {titulo_de(c)}: {e}")
        time.sleep(0.35)
    print(f"APLICADO: {feitos} de {len(plano) + len(arquivar)}; erros: {len(erros)}")
    for e in erros[:30]:
        print("ERRO", e)
    with open(RAIZ / "notion" / "relatorio-sync.md", "a") as f:
        f.write(f"\n## Resultado\n\n- Aplicadas: {feitos} de {len(plano)}\n- Erros: {len(erros)}\n"
                + "".join(f"  - {e}\n" for e in erros))


if __name__ == "__main__":
    main()
