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
import html, json, os, re, struct, sys, time, unicodedata, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
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


ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago|agos", "set", "out", "nov", "dez"]


def mes_da_pasta(nome, ano_padrao=None):
    """'N. Cliente - Março.26' -> '2026-03'. Aceita abreviação ('Agos.24') e, sem ano no nome, o da pasta do ano."""
    t = nfc(nome).lower()
    a = re.search(r"\.(\d{2})\s*$", t) or re.search(r"(20\d{2})\s*$", t) or re.search(r"\b[a-zç]+\.(\d{2})\b", t)
    ano = (a.group(1) if a else None) or ano_padrao
    if not ano:
        return None
    ano = ano if len(ano) == 4 else "20" + ano
    # vale o mês mais à direita: "Sarau Secreto - Rio de Janeiro - Outubro.25" é outubro
    for lista, padrao in ((MESES, r"\b{}\b"), (ABREV, r"\b(?:{})\b")):
        achados = [(x.start(), i) for i, m in enumerate(lista) for x in re.finditer(padrao.format(m), t)]
        if achados:
            return f"{ano}-{max(achados)[1] + 1:02d}"
    return None


def nome_cliente(nome):
    return re.sub(r"^\s*\d+\s*[.\-]\s*", "", nfc(nome)).strip()


def ordem_natural(nome):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", nome)]


def eh_carrossel(nome):
    return bool(re.match(r"\s*carross[eé]is?\b|\s*carrossel", unicodedata.normalize("NFC", nome), re.I))


ZIPS = []


def medir(fid):
    """'h' se a miniatura do Drive for horizontal (mais perto de 16:9), 'v' se vertical (mais perto de 9:16).
    None se o Drive ainda não gerou miniatura: tenta de novo na próxima rodada."""
    try:
        req = urllib.request.Request(f"https://drive.google.com/thumbnail?id={fid}&sz=w200",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            d = r.read()
        if d[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", d[16:24])
        elif d[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(d):
                if d[i] != 0xFF:
                    i += 1
                    continue
                if d[i + 1] in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", d[i + 5:i + 9])
                    break
                i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
            else:
                return None
        else:
            return None
        return "h" if w > h else "v"
    except Exception:  # noqa: BLE001
        return None


def formatos(itens, antigos):
    """Grava it["fmt"] em cada vídeo/foto. Reaproveita o que já foi medido; só mede arquivos novos."""
    ja = {a["id"]: a["fmt"] for a in antigos if a.get("fmt")}
    falta = []
    for it in itens:
        if it["tipo"] == "carrossel":
            continue
        if it["id"] in ja:
            it["fmt"] = ja[it["id"]]
        else:
            falta.append(it)
    if falta:
        with ThreadPoolExecutor(16) as ex:
            for it, f in zip(falta, ex.map(lambda x: medir(x["id"]), falta)):
                if not f:  # sem miniatura ainda: usa o nome do arquivo como pista
                    n = it["nome"].lower()
                    f = "h" if "horizontal" in n else "v" if "vertical" in n else None
                if f:
                    it["fmt"] = f
        print(f"  formatos medidos: {sum(1 for x in falta if x.get('fmt'))}/{len(falta)} novos")


def coletar(pasta, cliente, mes, destino, prof=0, servico=None):
    for x in listar(pasta):
        if x["pasta"] and eh_carrossel(x["nome"]):  # pasta "Carrossel ..." vira um item só, slides na ordem do nome
            slides = []
            for f in sorted(listar(x["id"]), key=lambda f: ordem_natural(f["nome"])):
                t = None if f["pasta"] else tipo(f["nome"], f.get("mime", ""))
                if t:
                    slides.append({"id": f["id"], "tipo": t})
            if slides:
                destino.append({"id": x["id"], "nome": x["nome"], "tipo": "carrossel", "cliente": cliente, "mes": mes,
                                "servico": servico, "pasta": pasta, "slides": slides})
            continue
        if x["pasta"]:
            if prof < 2:
                coletar(x["id"], cliente, mes, destino, prof + 1,
                        nome_cliente(x["nome"]) if mes_da_pasta(x["nome"]) else servico)  # subpasta de evento
            continue
        if prof == 0 and x["nome"].lower().endswith(".zip"):  # zip na pasta do mês = botão "Baixar tudo"
            ZIPS.append({"id": x["id"], "nome": x["nome"]})
            continue
        t = tipo(x["nome"], x.get("mime", ""))
        if t:
            destino.append({"id": x["id"], "nome": x["nome"], "tipo": t, "cliente": cliente, "mes": mes,
                            "servico": servico, "pasta": pasta})


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
        meses = []
        for m in listar(c["id"]):
            if not m["pasta"]:
                continue
            ano = re.fullmatch(r"\D*?(20\d{2})\s*", nfc(m["nome"]))  # pasta de ano, ex.: "Sarau 2026"
            if ano and not mes_da_pasta(m["nome"]):
                meses += [(mm, ano.group(1)) for mm in listar(m["id"]) if mm["pasta"]]
            else:
                meses.append((m, None))
        for m, ano in meses:
            mes = mes_da_pasta(m["nome"], ano)
            if not mes:
                avisos.append(f"Pasta fora do padrão ignorada: {cliente} / {m['nome']}")
                continue
            coletar(m["id"], cliente, mes, itens, servico=nome_cliente(m["nome"]))  # nome da pasta = página do Notion
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
    formatos(itens, antigos)
    zip_novo = None
    if len(ZIPS) == 1:  # só faz sentido com uma entrega; vários zips = ignora
        zip_novo = dict(ZIPS[0])
        if (cfg.get("zip") or {}).get("id") == zip_novo["id"] and cfg["zip"].get("bytes"):
            zip_novo["bytes"] = cfg["zip"]["bytes"]
    elif len(ZIPS) > 1:
        avisos.append(f"{len(ZIPS)} arquivos .zip encontrados; botão Baixar tudo só aparece com um")
    mudou = forcar or ordem != cfg.get("clientes") or itens != antigos or zip_novo != cfg.get("zip")
    for a in avisos:
        print("AVISO:", a)
    if not mudou:
        print(f"SEM MUDANÇAS ({len(itens)} arquivos)")
        return
    novos = len({i["id"] for i in itens} - {i["id"] for i in antigos})
    removidos = len({i["id"] for i in antigos} - {i["id"] for i in itens})
    cfg["clientes"], cfg["itens"] = ordem, itens
    if zip_novo:
        cfg["zip"] = zip_novo
    else:
        cfg.pop("zip", None)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    sys.path.insert(0, str(RAIZ))
    import gerar_painel
    gerar_painel.main(caminho)
    print(f"ATUALIZADO: {len(itens)} arquivos (+{novos} / -{removidos})")


if __name__ == "__main__":
    main(sys.argv[1], "--forcar" in sys.argv)
