"""Gera o painel interno com todos os dashboards de clientes.

Uso: python3 gerar_hub.py
Lê paineis/*.json e escreve docs/<caminho>/index.html (caminho em hub.json; vazio = raiz do site).
Roda sozinho no robô depois de atualizar os dashboards.

Os dados vão criptografados (AES-GCM, chave derivada da senha com PBKDF2-SHA256): sem a senha, nem o
código da página mostra quem são os clientes. Senha na variável de ambiente HUB_SENHA (segredo no GitHub).
Sem senha, o painel não é gerado (para nunca publicar a lista aberta por engano).
"""
import base64, json, os, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).parent


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
    return {
        "nome": cfg.get("nome_hub") or (cfg["marca"] if len(cfg["clientes"]) > 1 else cfg["clientes"][0]),
        "url": f"/{cfg['slug']}/", "total": len(itens), "videos": conta("video"), "fotos": conta("foto"),
        "carrosseis": conta("carrossel"), "primeiro": meses[0], "ultimo": meses[-1], "meses": len(meses),
        "capas": capas, "marcas": [m for m in marcas if m["total"]],
    }


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
    paineis = [r for p in sorted((RAIZ / "paineis").glob("*.json")) if (r := resumo(json.loads(p.read_text())))]
    html = (RAIZ / "hub_template.html").read_text()
    logo = (RAIZ / "assets/logo-mark.b64").read_text().strip()
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
    html = (html.replace("{{LOGO}}", logo).replace("{{ATUALIZADO}}", agora)
                .replace("/*__DATA__*/null", json.dumps(cifrar(paineis, senha), separators=(",", ":"))))
    destino = RAIZ / "docs" / hub.get("caminho", "") / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html)
    print(f"{destino} — {len(paineis)} painéis: " + ", ".join(f"{p['nome']} ({p['total']})" for p in paineis))


if __name__ == "__main__":
    main()
