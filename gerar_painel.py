"""Gera o painel de conteúdos da Universa e parceiros.

Uso: python3 gerar_painel.py paineis/universa.json
O JSON traz: slug, titulo, marca (nome grande da capa), eyebrow (opcional),
clientes (ordem dos filtros), itens[{id, nome, tipo, cliente, mes, pasta}].
Serve para qualquer cliente: com um só cliente o filtro de Cliente mostra só ele.
"""
import base64, json, random, re, sys, unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path

RAIZ = Path(__file__).parent
CORES = ["#F6AD03", "#C8463F", "#7FB7A4", "#B79CE0", "#E7895A", "#6FA8DC", "#D6C27A", "#E58FB2", "#9BC46B", "#A3A3A3"]


def titulo(nome, cliente):
    t = unicodedata.normalize("NFC", nome)
    t = re.sub(r"\.(mov|mp4|m4v|jpe?g|png|heic|webp)$", "", t, flags=re.I)
    t = re.sub(r"^[FP]\.\s*", "", t)
    # tira o nome do cliente do começo ("Vitrinni - ", "Vitrinni. ", "Universa - ")
    for alvo in [cliente, cliente.split()[0], "Vitrini"]:
        t = re.sub(rf"^{re.escape(alvo)}\s*[-.]\s*", "", t, flags=re.I)
    for _ in range(3):
        t = re.sub(r"[\s.\-]*[Vv]\.?\s?\d+(\(\d+\))?\s*$", "", t)  # versão no fim
        t = re.sub(r"[\s.\-]+(Andressa|Gabi|Gabriela|Marcus|Luiz)\s*$", "", t, flags=re.I)  # apresentador
        t = re.sub(rf"\s*-\s*{re.escape(cliente)}\s*$", "", t, flags=re.I)  # cliente no fim
        t = t.strip(" -.")
    if re.fullmatch(r"[A-Z]{1,3}\d{4,}|IMG_\d+|DSC\d+|[\d._]+|.*\bFotos?(_\d+)?|Gabi \d+", t) or not t:
        t = "Foto"
    return t


def main(caminho):
    cfg = json.loads(Path(caminho).read_text())
    rnd = random.Random(7)
    cores = {c: CORES[i % len(CORES)] for i, c in enumerate(cfg["clientes"])}
    itens = []
    for x in cfg["itens"]:
        itens.append({
            "id": x["id"], "tipo": x["tipo"], "cliente": x["cliente"], "mes": x["mes"], "pasta": x["pasta"],
            "arquivo": x["nome"], "titulo": titulo(x["nome"], x["cliente"]), "r": rnd.random(),
        })
    dados = {"clientes": cfg["clientes"], "cores": cores, "itens": itens}
    html = (RAIZ / "painel_template.html").read_text()
    logo = (RAIZ / "assets/logo-mark.b64").read_text().strip()
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
    html = (html.replace("{{TITLE}}", cfg["titulo"]).replace("{{LOGO}}", logo)
                .replace("{{MARCA}}", cfg.get("marca", cfg["clientes"][0]).upper())
                .replace("{{EYEBROW}}", cfg.get("eyebrow", "Painel de conteúdos"))
                .replace("{{ATUALIZADO}}", agora)
                .replace("/*__DATA__*/null", json.dumps(dados, ensure_ascii=False, separators=(",", ":"))))
    destino = RAIZ / "docs" / cfg["slug"] / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html)
    print(f"{destino} — {len(itens)} itens")
    from collections import Counter
    for (c, t), n in sorted(Counter((i["cliente"], i["tipo"]) for i in itens).items()):
        print(f"  {c:18} {t:5} {n}")
    print("Amostra de títulos:", sorted({i['titulo'] for i in itens if i['tipo'] == 'video'})[:40])


if __name__ == "__main__":
    main(sys.argv[1])
