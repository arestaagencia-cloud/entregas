"""Robô de atualização dos dashboards de clientes.

Lê a pasta raiz do cliente no Google Drive e reconstrói paineis/<cliente>.json:
  raiz / [NN. ]Cliente / N. Cliente - Mês.AA / arquivos (e subpastas como "Fotos")
Se algo mudou, regenera docs/<slug>/index.html com gerar_painel.py.

Uso: python3 atualizar_painel.py paineis/universa.json [--forcar]

Como lê o Drive:
- Com a variável GDRIVE_API_KEY: API oficial do Google Drive (recomendado).
- Sem ela: página pública de listagem de pasta (embeddedfolderview). Funciona porque as
  pastas estão como "qualquer pessoa com o link".
Sai com código 0 e imprime "SEM MUDANÇAS" ou "ATUALIZADO".
"""
import html, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from pathlib import Path

RAIZ = Path(__file__).parent
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]
VIDEO = {"mov", "mp4", "m4v", "avi", "mkv", "webm"}
FOTO = {"jpg", "jpeg", "png", "heic", "webp", "gif", "tif", "tiff"}
FOLDER = "application/vnd.google-apps.folder"
KEY = os.environ.get("GDRIVE_API_KEY", "").strip()
avisos = []


def nfc(s):
    return unicodedata.normalize("NFC", s)


def get(url, tentativas=4):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ArestAgencia-painel"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            if i == tentativas - 1:
                raise
            time.sleep(2 * (i + 1))


def listar_api(pasta):
    itens, token = [], ""
    while True:
        q = urllib.parse.urlencode({
            "q": f"'{pasta}' in parents and trashed = false", "key": KEY, "pageSize": 1000,
            "fields": "nextPageToken,files(id,name,mimeType)", "pageToken": token,
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
        d = json.loads(get(f"https://www.googleapis.com/drive/v3/files?{q}"))
        itens += [{"id": f["id"], "nome": nfc(f["name"]), "pasta": f["mimeType"] == FOLDER, "mime": f["mimeType"]}
                  for f in d.get("files", [])]
        token = d.get("nextPageToken")
        if not token:
            return itens


ENTRY = re.compile(r'<div class="flip-entry" id="entry-([\w-]+)"(.*?)<div class="flip-entry-title">(.*?)</div>', re.S)


def listar_publico(pasta):
    pagina = get(f"https://drive.google.com/embeddedfolderview?id={pasta}")
    itens = []
    for fid, bloco, nome in ENTRY.findall(pagina):
        href = re.search(r'<a href="([^"]+)"', bloco)
        mime = re.search(r'/type/([\w.+-]+/[\w.+-]+)', bloco)  # ícone do Drive traz o tipo do arquivo
        itens.append({"id": fid, "nome": nfc(html.unescape(nome).strip()),
                      "pasta": bool(href and "/folders/" in href.group(1)),
                      "mime": mime.group(1) if mime else ""})
    return itens


listar = listar_api if KEY else listar_publico


RAW = {"arw", "cr2", "cr3", "nef", "dng", "raf", "orf", "rw2"}  # brutos de câmera ficam fora do dashboard


def tipo(nome, mime=""):
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext in RAW:
        return None
    if ext in VIDEO:
        return "video"
    if ext in FOTO:
        return "foto"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("image/") and "raw" not in mime and "sony" not in mime:
        return "foto"
    return None


def mes_da_pasta(nome):
    t = nfc(nome).lower()
    a = re.search(r"\.(\d{2})\s*$", t) or re.search(r"(20\d{2})\s*$", t)
    for i, m in enumerate(MESES):
        if re.search(rf"\b{m}\b", t) and a:
            ano = a.group(1)
            ano = ano if len(ano) == 4 else "20" + ano
            return f"{ano}-{i + 1:02d}"
    return None


def nome_cliente(nome):
    return re.sub(r"^\s*\d+\s*[.\-]\s*", "", nfc(nome)).strip()


def ordem_natural(nome):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", nome)]


def eh_carrossel(nome):
    return bool(re.match(r"\s*carross[eé]is?\b|\s*carrossel", unicodedata.normalize("NFC", nome), re.I))


def coletar(pasta, cliente, mes, destino, prof=0):
    for x in listar(pasta):
        if x["pasta"] and eh_carrossel(x["nome"]):  # pasta "Carrossel ..." vira um item só, slides na ordem do nome
            slides = []
            for f in sorted(listar(x["id"]), key=lambda f: ordem_natural(f["nome"])):
                t = None if f["pasta"] else tipo(f["nome"], f.get("mime", ""))
                if t:
                    slides.append({"id": f["id"], "tipo": t})
            if slides:
                destino.append({"id": x["id"], "nome": x["nome"], "tipo": "carrossel", "cliente": cliente, "mes": mes,
                                "pasta": pasta, "slides": slides})
            continue
        if x["pasta"]:
            if prof < 2:
                coletar(x["id"], cliente, mes, destino, prof + 1)
            continue
        t = tipo(x["nome"], x.get("mime", ""))
        if t:
            destino.append({"id": x["id"], "nome": x["nome"], "tipo": t, "cliente": cliente, "mes": mes, "pasta": pasta})


def main(caminho, forcar=False):
    cfg_path = RAIZ / caminho
    cfg = json.loads(cfg_path.read_text())
    raiz = cfg["drive_raiz"]
    print(f"Lendo Drive ({'API oficial' if KEY else 'listagem pública'}) — pasta {raiz}")
    itens, clientes = [], []
    entradas = listar(raiz)
    pastas_cli = [x for x in entradas if x["pasta"]]
    if cfg.get("cliente_unico"):  # cliente sem subpastas de marca: raiz já tem os meses
        pastas_cli = [{"id": raiz, "nome": cfg["cliente_unico"], "pasta": True}]
    for c in pastas_cli:
        cliente = nome_cliente(c["nome"])
        n0 = len(itens)
        for m in listar(c["id"]):
            if not m["pasta"]:
                continue
            mes = mes_da_pasta(m["nome"])
            if not mes:
                avisos.append(f"Pasta fora do padrão ignorada: {cliente} / {m['nome']}")
                continue
            coletar(m["id"], cliente, mes, itens)
        if len(itens) > n0:
            clientes.append(cliente)
        print(f"  {cliente:20} {len(itens) - n0} arquivos")
    if not itens:
        print("ERRO: nenhum arquivo encontrado — nada foi alterado.")
        sys.exit(1)
    ordem = [c for c in cfg.get("clientes", []) if c in clientes] + [c for c in clientes if c not in cfg.get("clientes", [])]
    chave = lambda i: (i["mes"], i["cliente"], i["id"])
    itens.sort(key=chave)
    antigos = sorted(cfg.get("itens", []), key=chave)
    mudou = forcar or ordem != cfg.get("clientes") or itens != antigos
    for a in avisos:
        print("AVISO:", a)
    if not mudou:
        print(f"SEM MUDANÇAS ({len(itens)} arquivos)")
        return
    novos = len({i["id"] for i in itens} - {i["id"] for i in antigos})
    removidos = len({i["id"] for i in antigos} - {i["id"] for i in itens})
    cfg["clientes"], cfg["itens"] = ordem, itens
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    sys.path.insert(0, str(RAIZ))
    import gerar_painel
    gerar_painel.main(caminho)
    print(f"ATUALIZADO: {len(itens)} arquivos (+{novos} / -{removidos})")


if __name__ == "__main__":
    main(sys.argv[1], "--forcar" in sys.argv)
