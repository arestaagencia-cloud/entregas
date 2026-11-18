"""Gera o painel interno com todos os dashboards de clientes.

Uso: python3 gerar_hub.py
Lê paineis/*.json e escreve docs/<caminho>/index.html (caminho em hub.json; vazio = raiz do site).
Roda sozinho no robô depois de atualizar os dashboards.

Os dados vão criptografados (AES-GCM, chave derivada da senha com PBKDF2-SHA256): sem a senha, nem o
código da página mostra quem são os clientes. Senha na variável de ambiente HUB_SENHA (segredo no GitHub).
Sem senha, o painel não é gerado (para nunca publicar a lista aberta por engano).
"""
import base64, json, os, secrets
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).parent


def capa_unica(cfg):
    """Freelancers: uma imagem só no card (a mesma capa do painel)."""
    if cfg.get("tipo_cliente") != "freelancer":
        return None
    import gerar_painel
    return gerar_painel.montar(json.loads(json.dumps(cfg))).get("capa")


def grupos(cfg):
    """Subcategorias do painel, com link que já abre filtrado: marcas, tipos de Sarau, regiões, tópicos, corretores."""
    import gerar_painel
    d = gerar_painel.montar(json.loads(json.dumps(cfg)))
    it = d["itens"]
    conta = lambda f: sum(1 for x in it if f(x))
    lk = lambda **kw: "#" + "&".join(f"{k}={quote(v)}" for k, v in kw.items())
    out = []
    if len(d["clientes"]) > 1:
        rot = {"edicao": d.get("rotulo_clientes", "Tipo"), "categoria": d.get("rotulo_clientes", "Categoria")}.get(d.get("modo"), "Marcas")
        if d.get("regioes"):
            out.append({"rotulo": "Região", "itens": [{"nome": r["nome"], "total": conta(lambda x, r=r: x.get("reg") == r["nome"]),
                                                       "link": lk(regiao=r["nome"])} for r in d["regioes"]]})
            out.append({"rotulo": rot, "itens": [{"nome": e, "total": conta(lambda x, e=e: x["cliente"] == e),
                                                  "link": lk(regiao=r["nome"], cliente=e)}
                                                 for r in d["regioes"] for e in r["emps"]]})
        else:
            out.append({"rotulo": rot, "itens": [{"nome": c, "total": conta(lambda x, c=c: x["cliente"] == c),
                                                  "link": lk(cliente=c)} for c in d["clientes"]]})
    if d.get("corretores"):
        out.append({"rotulo": d.get("rotulo_corretores", "Corretor"),
                    "itens": [{"nome": c, "total": conta(lambda x, c=c: c in x.get("cor", [])), "link": lk(corretor=c)}
                              for c in d["corretores"]]})
    if cfg.get("hub_grupos"):  # quais grupos aparecem no card do hub (ex.: só "Empreendimento")
        out = [g for g in out if g["rotulo"] in cfg["hub_grupos"]]
    for g in out:
        g["itens"] = [i for i in g["itens"] if i["total"]]
    return [g for g in out if g["itens"]]


def resumo(cfg):
    itens = cfg.get("itens", [])
    if not itens:
        return None
    meses = sorted({i["mes"] for i in itens})
    # capas: conteúdos mais recentes, vídeos primeiro
    rec = sorted(itens, key=lambda i: (i["mes"], i["tipo"] == "video"), reverse=True)
    capas = []
    for i in rec:
        cid = i["slides"][0]["id"] if i["tipo"] == "carrossel" else i["id"]
        if cid not in capas:
            capas.append(cid)
        if len(capas) == 8:
            break
    conta = lambda t: sum(1 for i in itens if i["tipo"] == t)
    marcas = [{"nome": c, "total": sum(1 for i in itens if i["cliente"] == c)} for c in cfg["clientes"]]
    nome = cfg.get("nome_hub") or (cfg["marca"] if len(cfg["clientes"]) > 1 else cfg["clientes"][0])
    cu = capa_unica(cfg)
    hz = next((i for i in rec if i.get("fmt") == "h" and i["tipo"] != "carrossel"), None)  # capa do card: horizontal
    return {
        "sigla": sigla(nome), "img": cu or (hz["id"] if hz else (capas[0] if capas else None)), "raiz": cfg.get("drive_raiz"),
        "pastas": cfg.get("pastas") or {"clientes": [{"nome": cfg["clientes"][0], "id": cfg.get("drive_raiz")}], "meses": []},
        "nome": cfg.get("nome_hub") or (cfg["marca"] if len(cfg["clientes"]) > 1 else cfg["clientes"][0]),
        "url": f"/{cfg['slug']}/", "total": len(itens), "videos": conta("video"), "fotos": conta("foto"),
        "carrosseis": conta("carrossel"), "primeiro": meses[0], "ultimo": meses[-1], "meses": len(meses),
        "capas": capas, "marcas": [m for m in marcas if m["total"]], "grupos": grupos(cfg),
        "capa": capa_unica(cfg), "nomes": nomes_upload(cfg),
        "tipo": "freelancer" if cfg.get("tipo_cliente") == "freelancer" else "recorrente",
    }


def nomes_upload(cfg):
    """Opções do upload para montar o nome do arquivo: 'F. Tópico - Título - Pessoa - V.1'."""
    out = {}
    cat = cfg.get("categorias")
    if cat and cat.get("lista"):
        ops = [{"r": c, "v": c} for c in cat["lista"]]
        ops += [{"r": f"{r} · Geral", "v": r} for r in cat.get("regioes", {})]  # "F. Sudoeste - ..." = geral da região
        ops.append({"r": "Geral", "v": "Geral"})
        out["cat"] = {"rotulo": cat.get("rotulo", "Tópico"), "ops": ops}
    pes = cfg.get("corretores")
    if pes and pes.get("lista"):
        out["pes"] = {"rotulo": pes.get("rotulo", "Pessoa"), "lista": pes["lista"]}
    return out


def sigla(nome):
    """'Clínica Faber' -> 'CF', 'Raul & Paola' -> 'R&P', 'Universa' -> 'U'."""
    if nome.lower().startswith("universidade tuiuti"):
        return "UTP"
    ps = [p for p in nome.replace("&", " & ").split() if p == "&" or (len(p) > 2 and p.lower() not in ("das", "dos", "ao"))]
    return "".join("&" if p == "&" else p[0].upper() for p in ps)[:3] or nome[:2].upper()


def metricas(cfgs, paineis):
    """Números da casa para a área de Métricas e o calendário de uploads."""
    hoje = datetime.now(timezone(timedelta(hours=-3)))
    tudo = [(c, i) for c, p in zip(cfgs, paineis) for i in c.get("itens", [])]
    conta = lambda t: sum(1 for _, i in tudo if i["tipo"] == t)
    ult = []
    a, m = hoje.year, hoje.month
    for _ in range(12):
        ult.insert(0, f"{a}-{m:02d}")
        a, m = (a, m - 1) if m > 1 else (a - 1, 12)
    por_mes = [{"ym": ym, "n": sum(1 for _, i in tudo if i["mes"] == ym)} for ym in ult]
    por_cli = sorted([{"nome": p["nome"], "n": p["total"], "tipo": p["tipo"]} for p in paineis], key=lambda x: -x["n"])
    ups = {}
    for c, p in zip(cfgs, paineis):
        for i in c.get("itens", []):
            if not i.get("up"):
                continue
            u = ups.setdefault((i["up"], p["nome"], i["cliente"]), {"d": i["up"], "p": p["nome"], "c": i["cliente"],
                                                                   "url": p["url"], "video": 0, "foto": 0, "carrossel": 0})
            u[i["tipo"]] += 1
    return {"total": len(tudo), "videos": conta("video"), "fotos": conta("foto"), "carrosseis": conta("carrossel"),
            "paineis": len(paineis), "meses": por_mes, "clientes": por_cli,
            "uploads": sorted(ups.values(), key=lambda u: u["d"], reverse=True)}


ITER = 210000


def cifrar(dados, senha):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    sal, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal, iterations=ITER).derive(senha.encode())
    ct = AESGCM(chave).encrypt(iv, json.dumps(dados, ensure_ascii=False).encode(), None)
    b = lambda x: base64.b64encode(x).decode()
    return {"sal": b(sal), "iv": b(iv), "it": ITER, "ct": b(ct)}


def main():
    senha = os.environ.get("HUB_SENHA", "").strip()
    if not senha:
        print("HUB_SENHA não definida: painel interno não foi gerado.")
        return
    hub = json.loads((RAIZ / "hub.json").read_text())
    cfgs, paineis = [], []
    for p in sorted((RAIZ / "paineis").glob("*.json")):
        c = json.loads(p.read_text())
        if (r := resumo(c)):
            cfgs.append(c)
            paineis.append(r)
    dados = {"paineis": paineis, "metricas": metricas(cfgs, paineis),
             "gh": {"repo": "arestaagencia-cloud/entregas", "workflow": "atualizar-paineis.yml",
                    "token": os.environ.get("HUB_GH_TOKEN", "").strip() or None},
             "google": hub.get("google_client_id"),
             "gerado": datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="minutes")}
    html = (RAIZ / "hub_template.html").read_text()
    logo = (RAIZ / "assets/logo-mark.b64").read_text().strip()
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
    html = (html.replace("{{LOGO}}", logo).replace("{{ATUALIZADO}}", agora)
                .replace("/*__DATA__*/null", json.dumps(cifrar(dados, senha), separators=(",", ":"))))
    destino = RAIZ / "docs" / hub.get("caminho", "") / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html)
    print(f"{destino} — {len(paineis)} painéis: " + ", ".join(f"{p['nome']} ({p['total']})" for p in paineis))


if __name__ == "__main__":
    main()
