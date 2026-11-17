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


ACENTOS = {"a": "aáàâã", "e": "eéê", "i": "ií", "o": "oóôõ", "u": "uúü", "c": "cç"}


def sem_acento(palavra):
    """Regex que casa a palavra com ou sem acento."""
    base = unicodedata.normalize("NFKD", palavra).encode("ascii", "ignore").decode()
    return "".join(f"[{ACENTOS[ch.lower()]}{ACENTOS[ch.lower()].upper()}]" if ch.lower() in ACENTOS else re.escape(ch)
                   for ch in base)


def titulo(nome, cliente):
    nome = re.sub(r"[\u2028\u2029\u200b\ufeff]", "", nome)
    t = unicodedata.normalize("NFC", nome)
    t = re.sub(r"\.(mov|mp4|m4v|jpe?g|png|heic|webp)$", "", t, flags=re.I)
    t = re.sub(r"^[FPQ](\.\s*|\s+|-\s*)(?=\S)", "", t)
    t = re.sub(r"\s*-\s*C\.\s*Faber\s*-\s*", " - ", t)  # "Dra. Laís - C. Faber - Tema"
    # tira o nome do cliente do começo ("Vitrinni - ", "Vitrinni. ", "Universa - ")
    alvos = [cliente, cliente.replace(" ", "")] + [w for w in cliente.split() if len(w) >= 4] + [cliente.split()[0], "Vitrini"]
    for _ in range(3):  # "Clinica Faber - Dr Jorge", "Faber - Alinhador": tira mesmo sem acento
        for alvo in alvos:
            t = re.sub(rf"^(\w{{1,2}}\.\s*)?{sem_acento(alvo)}(\s+Eng(enharia)?\.?)?\s*[-.]\s*", "", t, flags=re.I)  # "Niso Eng - "
    for _ in range(3):
        t = re.sub(r"[\s.\-]*[Vv]\.?\s?\d+(\.\d+)?(\(\d+\))?\s*$", "", t)  # versão no fim
        t = re.sub(r"\s+-\s*[Vv]\.?\s*$", "", t)  # "- V" sem número
        t = re.sub(r"[\s.\-]+(Andressa|Gabi|Gabriela|Marcus|Luiz)\s*$", "", t, flags=re.I)  # apresentador
        t = re.sub(rf"\s*-\s*{re.escape(cliente)}\s*$", "", t, flags=re.I)  # cliente no fim
        t = t.strip(" -.")
    if not t:  # o nome era só o cliente (ex.: "F. Raul & Paola - V.3")
        return cliente
    if re.fullmatch(r"[A-Z]{1,3}\d{4,}|IMG_\d+|DSC\d+|[\d._]+|(?:\S+\s)?Fotos?(?:[_\s]*\d+)?|(?:.*[\s_-])?(?:[A-Z]{1,3}\d{4,}|IMG_\d+|DSC\d+)|Gabi \d+|[\d.\-_ ]*[Vv]?[\d.\-_ ]*", t):
        t = "Foto"
    return t


def norm_l(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower().strip()


def categoria(titulo_item, cat):
    """(categoria, como): como = 'inicio' (padrão), 'meio' (achou o nome fora do começo), 'nenhum' (foi para Gerais)."""
    nomes = {norm_l(n): n for n in cat["lista"]}
    nomes.update({norm_l(a): n for a, n in cat.get("apelidos", {}).items()})
    gerais = {norm_l(g) for g in cat.get("geral_apelidos", ["Geral"])}
    titulo_item = re.sub(r"^\s*T\.\s*", "", titulo_item)  # "T. ..." = thumbnail do vídeo
    partes = [norm_l(p) for p in re.split(r"\s*-\s*|\.\s+", titulo_item) if p.strip()]
    if partes and partes[0] in nomes:
        return nomes[partes[0]], "inicio"
    if partes and partes[0] in gerais:
        return cat["geral"], "inicio"
    t = " " + re.sub(r"[^a-z0-9.]+", " ", norm_l(titulo_item)) + " "
    achados = {n for k, n in nomes.items() if f" {k} " in t}
    if len(achados) == 1:
        return achados.pop(), "meio"
    t2 = " " + re.sub(r"[^a-z0-9%]+", " ", norm_l(titulo_item)) + " "
    for nome, chaves in cat.get("palavras", {}).items():  # por palavra-chave, na ordem de prioridade
        if any(re.search(r"\s" + re.escape(norm_l(k)), t2) for k in chaves):
            return nome, "palavra"
    return cat["geral"], "nenhum"


def corretores(titulo_item, cfg_cor):
    """Lista de corretores citados no título (pode ter mais de um: "Raquel e Escobar")."""
    t = " " + re.sub(r"[^a-z0-9]+", " ", norm_l(titulo_item)) + " "
    nomes = {norm_l(n): n for n in cfg_cor["lista"]}
    nomes.update({norm_l(a): n for a, n in cfg_cor.get("apelidos", {}).items()})
    achados = []
    for k, n in nomes.items():
        if " " + re.sub(r"[^a-z0-9]+", " ", k).strip() + " " in t and n not in achados:
            achados.append(n)
    return [n for n in cfg_cor["lista"] if n in achados]


def montar(cfg):
    """DATA do painel (itens já com título, categoria, corretor...). Usado também pelo painel interno."""
    rnd = random.Random(7)
    cores = {c: CORES[i % len(CORES)] for i, c in enumerate(cfg["clientes"])}
    itens = []
    for x in cfg["itens"]:
        itens.append({
            "id": x["id"], "tipo": x["tipo"], "cliente": x["cliente"], "mes": x["mes"], "pasta": x["pasta"],
            "arquivo": x["nome"], "titulo": titulo(x["nome"], x["cliente"]), "r": rnd.random(),
        })
        if x.get("fmt") == "h":  # horizontal (16:9); sem a chave = vertical (9:16)
            itens[-1]["fmt"] = "h"
        if x["tipo"] == "carrossel":
            itens[-1]["slides"] = x["slides"]
            itens[-1]["capa"] = x["slides"][0]["id"]
            itens[-1]["titulo"] = re.sub(r"^carross[eé]l\s*\d*\s*[-.:]?\s*", "", x["nome"], flags=re.I).strip() or "Carrossel"
    dados = {"clientes": cfg["clientes"], "cores": cores, "itens": itens}
    if cfg.get("agrupar_por") == "edicao":  # ex.: Sarau: agrupa por edição (pasta) e filtra por linha do evento
        linhas_cfg = cfg.get("linhas", [])
        for it, x in zip(itens, cfg["itens"]):
            ed = re.sub(r"\s*\(.*?\)\s*$", "", x.get("servico") or x["cliente"])  # "… - Janeiro.26 (Não participamos)"
            linha = ed.split(" - ")[0].strip()
            linha = next((l for l in linhas_cfg if norm_l(l) == norm_l(linha)), linha)
            detalhe = " - ".join(ed.split(" - ")[1:-1]) if ed.count(" - ") >= 2 else ""
            it["cliente"] = linha
            it["mes"] = f"{x['mes']}|{linha + (' · ' + detalhe if detalhe else '')}"  # chave ordena por data
        presentes = {it["cliente"] for it in itens}
        ordem = [l for l in linhas_cfg if l in presentes] + sorted(presentes - set(linhas_cfg))
        dados.update({"clientes": ordem, "cores": {c: CORES[i % len(CORES)] for i, c in enumerate(ordem)},
                      "modo": "edicao", "rotulo_clientes": cfg.get("rotulo_clientes", "Tipo")})
    if cfg.get("categorias"):  # ex.: Equipe Prime: filtro por empreendimento, lido do começo do nome do arquivo
        cat = cfg["categorias"]
        for it in itens:
            it["cliente"] = categoria(it["titulo"], cat)[0]
        presentes = {it["cliente"] for it in itens}
        ordem = [l for l in cat["lista"] if l in presentes] + ([cat["geral"]] if cat["geral"] in presentes else [])
        dados.update({"clientes": ordem, "cores": {c: CORES[i % len(CORES)] for i, c in enumerate(ordem)},
                      "modo": "categoria", "rotulo_clientes": cat.get("rotulo", "Categoria")})
        if cat.get("regioes"):  # 1º escolhe a região, depois aparecem os empreendimentos dela
            reg_de = {e: r for r, es in cat["regioes"].items() for e in es}
            for it in itens:
                it["reg"] = reg_de.get(it["cliente"], cat["geral"])
            regs = [{"nome": r, "emps": [e for e in es if e in presentes]} for r, es in cat["regioes"].items()]
            regs = [r for r in regs if r["emps"]]
            if cat["geral"] in presentes:
                regs.append({"nome": cat["geral"], "emps": []})
            dados["regioes"] = regs
    if cfg.get("corretores"):  # filtro extra por corretor, lido do nome do arquivo
        for it in itens:
            cs = corretores(it["titulo"], cfg["corretores"])
            if cs:
                it["cor"] = cs
        presentes = {c for it in itens for c in it.get("cor", [])}
        dados.update({"corretores": [c for c in cfg["corretores"]["lista"] if c in presentes],
                      "rotulo_corretores": cfg["corretores"].get("rotulo", "Corretor")})
    for k in ("destaque", "destaque_titulo", "zip"):  # vídeo(s) em destaque acima da grade
        if cfg.get(k):
            dados[k] = cfg[k]
    if cfg.get("capa"):  # id de uma foto do Drive para usar como capa no lugar do mosaico
        dados["capa"] = cfg["capa"]
    return dados


def main(caminho):
    cfg = json.loads(Path(caminho).read_text())
    dados = montar(cfg)
    itens = dados["itens"]
    html = (RAIZ / "painel_template.html").read_text()
    logo = (RAIZ / "assets/logo-mark.b64").read_text().strip()
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
    html = (html.replace("{{TITLE}}", cfg["titulo"]).replace("{{LOGO}}", logo)
                .replace("{{MARCA}}", cfg.get("marca", cfg["clientes"][0]).upper())
                .replace("{{MARCA_CLASSE}}", "longo" if len(cfg.get("marca", cfg["clientes"][0])) > 9 else "")
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
