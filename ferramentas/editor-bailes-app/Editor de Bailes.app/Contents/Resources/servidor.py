#!/usr/bin/env python3
# Editor de Bailes · ArestAgência
# Servidor local (só neste Mac, 127.0.0.1) que gerencia a edição dos vídeos brutos dos bailes:
#   F. NN.mp4 (1080x1920, logos embaixo) e P. NN.mp4 (720x1280, logos + PNG "prévia" com fade).
# Compatível com o Python 3.9 que vem com as ferramentas de linha de comando da Apple.

import base64
import hashlib
import tempfile
import json
import traceback
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

AQUI = os.path.dirname(os.path.abspath(__file__))
REC_APP = os.path.join(AQUI, "recursos")
HOME = os.path.expanduser("~")
CONF_DIR = os.path.join(HOME, "Library", "Application Support", "Editor de Bailes")
CONF = os.path.join(CONF_DIR, "config.json")
VIDEO_EXT = (".mp4", ".mov", ".m4v")
REC_BAILE = "Recursos do editor"
ESTRUTURA = ("1. Brutos", "2. Prévias", "3. Finais")
EH_MAC = sys.platform == "darwin"

AJUSTES_PADRAO = {
    "logo_largura": 34,       # % da largura do vídeo
    "logo_opacidade": 0.85,
    "logo_margem": 3,         # % da altura, de baixo
    "previa_opacidade": 0.35,
    "previa_inicio": 5.0,     # segundos
    "previa_fade": 1.5,       # segundos
    "girar": "direita",       # vídeo deitado: direita | esquerda | nao
    "destino_drive": "",
    "parceiro_tamanho": 100,
    "url_galeria": "",        # telão: link da galeria do baile (QR do "Me avise")
    "preco_codigo": 0,        # telão: preço do código em centavos
    "preco_cheio": 0,         # telão: preço "de" riscado (centavos), opcional
    "telao_fonte": "brutos",  # telão: brutos | prontos
    "sigla": "",              # nome dos arquivos: vazio = iniciais do nome do baile
    "lut": "",                # filtro (.cube) aplicado na final e na prévia; vazio = sem filtro
    "lut_intensidade": 100,   # %
    "cor_brilho": 0,          # -100..100
    "cor_contraste": 0,       # -100..100
    "cor_saturacao": 0,       # -100..100
    "cor_temperatura": 0,     # -100 (mais frio) .. 100 (mais quente)
}

def nfc(s):
    return unicodedata.normalize("NFC", s)


# ---------------------------------------------------------------- cor: LUTs e ajustes rápidos
LUTS_APP = os.path.join(AQUI, "luts")                       # os que vêm com o editor
LUTS_USUARIO = os.path.join(CONF_DIR, "LUTs")               # os que a equipe adiciona


def listar_luts():
    vistos, out = set(), []
    for pasta, origem in ((LUTS_USUARIO, "seu"), (LUTS_APP, "editor")):
        try:
            nomes = sorted(os.listdir(pasta), key=lambda x: x.lower())
        except OSError:
            continue
        for f in nomes:
            if f.lower().endswith(".cube") and not f.startswith(".") and nfc(f) not in vistos:
                vistos.add(nfc(f))
                out.append({"arquivo": nfc(f), "nome": re.sub(r"^\d+\s+", "", f[:-5]), "origem": origem})
    return out


def caminho_lut(nome):
    nome = os.path.basename(nome or "")
    for pasta in (LUTS_USUARIO, LUTS_APP):
        c = os.path.join(pasta, nome)
        if nome and os.path.isfile(c):
            return c
    return None


def ler_cube(caminho):
    """Lê um .cube 3D: (tamanho, [r,g,b...] com o vermelho variando mais rápido, domínio mín/máx)."""
    n, dados, dmin, dmax = 0, [], (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
    with open(caminho, encoding="utf-8", errors="ignore") as f:
        for linha in f:
            t = linha.strip()
            if not t or t[0] == "#":
                continue
            u = t.upper()
            if u.startswith("LUT_3D_SIZE"):
                n = int(t.split()[1])
            elif u.startswith("DOMAIN_MIN"):
                dmin = tuple(float(x) for x in t.split()[1:4])
            elif u.startswith("DOMAIN_MAX"):
                dmax = tuple(float(x) for x in t.split()[1:4])
            elif t[0] in "-.0123456789":
                p = t.split()
                if len(p) >= 3:
                    dados.append((float(p[0]), float(p[1]), float(p[2])))
    if n < 2 or len(dados) < n ** 3:
        raise ValueError("LUT inválido: %s" % os.path.basename(caminho))
    return n, dados[:n ** 3], dmin, dmax


def amostrar(cube, r, g, b):
    """Interpolação trilinear num LUT 3D."""
    n, d, dmin, dmax = cube
    def idx(v, lo, hi):
        x = (v - lo) / ((hi - lo) or 1) * (n - 1)
        x = 0.0 if x < 0 else (n - 1.0 if x > n - 1 else x)
        i = min(int(x), n - 2)
        return i, x - i
    (ri, rf), (gi, gf), (bi, bf) = idx(r, dmin[0], dmax[0]), idx(g, dmin[1], dmax[1]), idx(b, dmin[2], dmax[2])
    out = [0.0, 0.0, 0.0]
    for db, wb in ((0, 1 - bf), (1, bf)):
        for dg, wg in ((0, 1 - gf), (1, gf)):
            for dr, wr in ((0, 1 - rf), (1, rf)):
                w = wr * wg * wb
                if w:
                    v = d[(ri + dr) + (gi + dg) * n + (bi + db) * n * n]
                    out[0] += v[0] * w; out[1] += v[1] * w; out[2] += v[2] * w
    return out


def lut_combinado(aj, lut, n=65):
    """Um só .cube com tudo junto: brilho, contraste, saturação, temperatura, o filtro escolhido e a intensidade.
    Assim o vídeo passa por um único lut3d (bem mais rápido que vários filtros em sequência).
    Devolve o caminho (sem espaço nem acento, aceito pelo FFmpeg) ou None quando não há nada a aplicar."""
    b, c, sa, te = (float(aj.get(k) or 0) for k in ("cor_brilho", "cor_contraste", "cor_saturacao", "cor_temperatura"))
    cam = caminho_lut(lut) if lut else None
    k = max(0.0, min(1.0, float(aj.get("lut_intensidade", 100)) / 100)) if cam else 0.0
    if not (b or c or sa or te or k):
        return None
    chave = "%s|%s|%.1f|%.1f|%.1f|%.1f|%.3f|%d" % (cam, os.path.getmtime(cam) if cam else 0, b, c, sa, te, k, n)
    d = os.path.join(tempfile.gettempdir(), "editor-bailes-luts")
    os.makedirs(d, exist_ok=True)
    alvo = os.path.join(d, hashlib.sha1(chave.encode()).hexdigest()[:16] + ".cube")
    if os.path.isfile(alvo):
        return alvo
    cube = ler_cube(cam) if k else None
    bb, cc, ss, tt = b / 100 * 0.12, 1 + c / 100 * 0.3, 1 + sa / 100 * 0.5, te / 100 * 0.10
    linhas = ["LUT_3D_SIZE %d" % n]
    for bi in range(n):
        for gi in range(n):
            for ri in range(n):
                r, g, bl = ri / (n - 1), gi / (n - 1), bi / (n - 1)
                # correções (na ordem: temperatura, brilho, contraste, saturação)
                r, bl = r + tt, bl - tt
                r, g, bl = r + bb, g + bb, bl + bb
                r, g, bl = (r - .5) * cc + .5, (g - .5) * cc + .5, (bl - .5) * cc + .5
                y = .2126 * r + .7152 * g + .0722 * bl
                r, g, bl = y + (r - y) * ss, y + (g - y) * ss, y + (bl - y) * ss
                r, g, bl = (min(1.0, max(0.0, v)) for v in (r, g, bl))
                if k:
                    lr, lg, lb = amostrar(cube, r, g, bl)
                    r, g, bl = r + (lr - r) * k, g + (lg - g) * k, bl + (lb - bl) * k
                linhas.append("%.5f %.5f %.5f" % (min(1.0, max(0.0, r)), min(1.0, max(0.0, g)), min(1.0, max(0.0, bl))))
    with open(alvo + ".tmp", "w") as f:
        f.write("\n".join(linhas) + "\n")
    os.replace(alvo + ".tmp", alvo)
    return alvo


def filtro_cor(aj, entrada, saida, lut=None, rapido=True):
    """Cor do vídeo: um único lut3d com correções + filtro + intensidade (ver lut_combinado).
    Roda já em 1080x1920 (depois de reduzir o 4K). No vídeo: LUT de 65 pontos lido sem interpolação, em RGB 8 bits
    (metade do custo do trilinear de 33 pontos, diferença medida de ~46 dB de PSNR, imperceptível).
    Nas miniaturas (rapido=False): 33 pontos com interpolação, que é mais rápido de calcular."""
    cubo = lut_combinado(aj, aj.get("lut") if lut is None else lut, 65 if rapido else 33)
    if not cubo:
        return "[%s]null[%s]" % (entrada, saida)
    if rapido:
        return "[%s]format=rgb24,lut3d=file=%s:interp=nearest,format=yuv420p[%s]" % (entrada, cubo, saida)
    return "[%s]format=rgb24,lut3d=file=%s:interp=tetrahedral[%s]" % (entrada, cubo, saida)


# ---------------------------------------------------------------- ferramentas
def achar(nome):
    for d in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"):
        p = os.path.join(d, nome)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which(nome)


FFMPEG = achar("ffmpeg")
FFPROBE = achar("ffprobe")


def tem_videotoolbox():
    if not FFMPEG:
        return False
    try:
        out = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20).stdout
        return "h264_videotoolbox" in out
    except Exception:
        return False


VT = tem_videotoolbox()


def codificador(tipo):
    if VT:
        return ["-c:v", "h264_videotoolbox", "-profile:v", "high"] + (
            ["-b:v", "16M", "-maxrate", "22M"] if tipo == "final" else ["-b:v", "3M", "-maxrate", "4M"])
    return ["-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high", "-crf", "18" if tipo == "final" else "23"]


# ---------------------------------------------------------------- configuração
def ler_json(caminho, padrao):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return padrao


def gravar_json(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)


def tem_bailes(pasta):
    try:
        return any(os.path.isdir(os.path.join(pasta, n, "1. Brutos")) for n in os.listdir(pasta))
    except OSError:
        return False


def config():
    c = ler_json(CONF, {})
    doc = os.path.join(HOME, "Documents", "Bailes")
    # pasta padrão: Documentos/Bailes. Também corrige quem ficou em Filmes/Bailes vazia (versão anterior sem acesso)
    if not c.get("pasta_bailes") or (not tem_bailes(c["pasta_bailes"]) and c["pasta_bailes"] != doc and tem_bailes(doc)):
        c["pasta_bailes"] = doc if (os.path.isdir(doc) or not os.path.isdir(os.path.join(HOME, "Movies", "Bailes"))) \
            else os.path.join(HOME, "Movies", "Bailes")
    return c


def salvar_config(c):
    gravar_json(CONF, c)


def pasta_bailes():
    p = config()["pasta_bailes"]
    os.makedirs(p, exist_ok=True)
    return p


def listar_bailes():
    base = pasta_bailes()
    out = []
    for n in sorted(os.listdir(base), reverse=True):
        p = os.path.join(base, n)
        if os.path.isdir(p) and os.path.isdir(os.path.join(p, "1. Brutos")):
            out.append(nfc(n))
    return out


def caminho_baile(nome):
    if not nome or "/" in nome or nome.startswith("."):
        raise ValueError("Baile inválido")
    base = pasta_bailes()
    for n in os.listdir(base):
        if nfc(n) == nfc(nome) and os.path.isdir(os.path.join(base, n, "1. Brutos")):
            return os.path.join(base, n)
    raise ValueError("Baile não encontrado: " + nome)


def pastas(baile):
    b = caminho_baile(baile)
    return {
        "baile": b,
        "brutos": os.path.join(b, "1. Brutos"),
        "previas": os.path.join(b, "2. Prévias"),
        "finais": os.path.join(b, "3. Finais"),
        "rec": os.path.join(b, REC_BAILE),
    }


def preparar_recursos(baile):
    p = pastas(baile)
    os.makedirs(p["rec"], exist_ok=True)
    os.makedirs(p["previas"], exist_ok=True)
    os.makedirs(p["finais"], exist_ok=True)
    for arq, padrao in (("logos-baixo.png", "logos-aresta.png"), ("previa.png", "previa.png")):
        if not os.path.isfile(os.path.join(p["rec"], arq)):
            shutil.copyfile(os.path.join(REC_APP, padrao), os.path.join(p["rec"], arq))
    return p


def ajustes(baile):
    p = preparar_recursos(baile)
    a = dict(AJUSTES_PADRAO)
    a.update(ler_json(os.path.join(p["rec"], "ajustes.json"), {}))
    return a


def salvar_ajustes(baile, novos):
    p = preparar_recursos(baile)
    a = ajustes(baile)
    lim = {
        "logo_largura": (5, 100), "logo_opacidade": (0, 1), "logo_margem": (0, 30),
        "previa_opacidade": (0, 1), "previa_inicio": (0, 600), "previa_fade": (0, 30), "parceiro_tamanho": (40, 200),
    }
    for k, (lo, hi) in lim.items():
        if k in novos:
            a[k] = max(lo, min(hi, float(novos[k])))
    if novos.get("girar") in ("direita", "esquerda", "nao"):
        a["girar"] = novos["girar"]
    if "destino_drive" in novos:
        a["destino_drive"] = str(novos["destino_drive"] or "")
    if "url_galeria" in novos:
        a["url_galeria"] = str(novos["url_galeria"] or "").strip()[:300]
    if "preco_codigo" in novos:
        a["preco_codigo"] = max(0, min(100000, int(novos["preco_codigo"] or 0)))
    if "preco_cheio" in novos:
        a["preco_cheio"] = max(0, min(100000, int(novos["preco_cheio"] or 0)))
    if "lut" in novos:
        a["lut"] = os.path.basename(str(novos["lut"] or "")) if (not novos["lut"] or caminho_lut(novos["lut"])) else a["lut"]
    for k, (lo, hi) in {"lut_intensidade": (0, 100), "cor_brilho": (-100, 100), "cor_contraste": (-100, 100),
                        "cor_saturacao": (-100, 100), "cor_temperatura": (-100, 100)}.items():
        if k in novos:
            a[k] = max(lo, min(hi, float(novos[k] or 0)))
    if "sigla" in novos:
        a["sigla"] = re.sub(r"[^A-Z0-9]", "", str(novos["sigla"] or "").upper())[:12]
    if novos.get("telao_fonte") in ("brutos", "prontos"):
        a["telao_fonte"] = novos["telao_fonte"]
    gravar_json(os.path.join(p["rec"], "ajustes.json"), a)
    return a


# ---------------------------------------------------------------- brutos e numeração
def arquivos_brutos(baile):
    d = pastas(baile)["brutos"]
    out = []
    for n in os.listdir(d):
        if n.startswith(".") or n.startswith("._"):
            continue
        if n.lower().endswith(VIDEO_EXT) and os.path.isfile(os.path.join(d, n)):
            out.append(n)
    return sorted(out, key=nfc)


TRAVA_NUM = threading.Lock()


def numeracao(baile):
    """Número estável de cada bruto (mesma regra do telão e do editar.sh): novos entram no fim, em ordem de nome."""
    with TRAVA_NUM:
        csv = os.path.join(pastas(baile)["baile"], "numeracao.csv")
        nums = {}
        maior = 0
        if os.path.isfile(csv):
            with open(csv, "r", encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if ";" not in linha:
                        continue
                    n, nome = linha.split(";", 1)
                    try:
                        n = int(n)
                    except ValueError:
                        continue
                    nums[nfc(nome)] = n
                    maior = max(maior, n)
        novos = [a for a in arquivos_brutos(baile) if nfc(a) not in nums]
        if novos:
            with open(csv, "a", encoding="utf-8") as f:
                for a in novos:
                    maior += 1
                    nums[nfc(a)] = maior
                    f.write("%d;%s\n" % (maior, nfc(a)))
        return nums


CACHE_INFO = {}


def info_video(caminho):
    st = os.stat(caminho)
    chave = (caminho, st.st_size, int(st.st_mtime))
    if chave in CACHE_INFO:
        return CACHE_INFO[chave]
    r = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", caminho],
                       capture_output=True, text=True, timeout=60)
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    rot = 0
    try:
        rot = int(float((v.get("tags") or {}).get("rotate", 0)))
    except ValueError:
        rot = 0
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            try:
                rot = int(float(sd["rotation"]))
            except ValueError:
                pass
    if abs(rot) % 180 == 90:
        w, h = h, w
    try:
        dur = float((d.get("format") or {}).get("duration") or v.get("duration") or 0)
    except ValueError:
        dur = 0.0
    out = {"largura": w, "altura": h, "duracao": dur, "codec": v.get("codec_name", ""),
           "bits": 10 if "10" in (v.get("pix_fmt") or "") else 8}
    CACHE_INFO[chave] = out
    return out


def sigla_auto(nome):
    """Inicial de cada palavra do nome, sem acento (o hífen também separa): "I Dá-lhe Samba" -> IDLS."""
    sem = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    return "".join(w[0] for w in re.split(r"[^A-Za-z0-9]+", sem) if w).upper()[:12] or "BAILE"


def identidade(baile):
    """Data (AAAA-MM-DD) e sigla do baile, tiradas do nome da pasta "AAAA-MM-DD Nome" e dos ajustes."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(.*)$", baile or "")
    data, nome = (m.group(1), m.group(2)) if m else ("", baile or "")
    auto = sigla_auto(nome)
    manual = re.sub(r"[^A-Z0-9]", "", (ler_json(os.path.join(pastas(baile)["rec"], "ajustes.json"), {}).get("sigla") or "").upper())[:12]
    return {"data": data, "sigla": manual or auto, "sigla_auto": auto}


def numero_arquivo(nome):
    base = nome.rsplit(".", 1)[0]
    m = re.search(r"(\d{1,4})\s*$", base)
    return int(m.group(1)) if m else None


def saida(baile, num, tipo):
    """F. IDLS 2026-11-28 - 01.mp4 / P. IDLS 2026-11-28 - 01.mp4.
    Se já existe um arquivo desse número com outro nome (o antigo "F. 01.mp4" ou outra sigla), usa ele."""
    p = pastas(baile)
    pasta, letra = (p["finais"], "F") if tipo == "final" else (p["previas"], "P")
    idt = identidade(baile)
    nome = "%s. %s %s- %02d.mp4" % (letra, idt["sigla"], (idt["data"] + " ") if idt["data"] else "", num)
    novo = os.path.join(pasta, nome)
    if os.path.isfile(novo):
        return novo
    try:
        for f in os.listdir(pasta):
            if f.startswith(letra + ".") and f.lower().endswith(".mp4") and numero_arquivo(f) == num:
                return os.path.join(pasta, f)
    except OSError:
        pass
    return novo


# ---------------------------------------------------------------- tela do iPad (escolher o vídeo do telão)
# O iPad entra pela rede local (hotspot do iPhone, sem precisar de internet): http://<ip do Mac>:8765/ipad
# Pela rede só valem a página do iPad, a lista, as miniaturas e o pedido "tocar". O resto do editor é só no Mac.
CONTROLE = {"baile": "", "visto": 0.0, "pedido": {"id": 0, "num": None, "baile": "", "quando": 0.0}}
LIVRE_NA_REDE_GET = ("/ipad", "/api/controle/lista", "/api/miniatura", "/favicon.ico")
LIVRE_NA_REDE_POST = ("/api/controle/tocar",)


def eh_local(ip):
    return ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def enderecos_rede():
    ips = []
    try:
        import socket
        k = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        k.connect(("10.255.255.255", 1))  # não envia nada; só descobre a interface de saída
        ips.append(k.getsockname()[0]); k.close()
    except Exception:
        pass
    if EH_MAC:
        for itf in ("en0", "en1", "en2", "bridge100"):
            try:
                r = subprocess.run(["ipconfig", "getifaddr", itf], capture_output=True, text=True, timeout=3)
                ip = r.stdout.strip()
                if ip and ip not in ips:
                    ips.append(ip)
            except Exception:
                pass
    return [i for i in ips if i and not i.startswith("127.")]


def lista_controle():
    baile = CONTROLE["baile"] if CONTROLE["baile"] and time.time() - CONTROLE["visto"] < 30 else config().get("baile_atual", "")
    if not baile:
        return {"baile": "", "telao": False, "videos": []}
    p = pastas(baile)
    nums = numeracao(baile)
    vids = []
    for a in arquivos_brutos(baile):
        n = nums.get(nfc(a))
        if not n:
            continue
        try:
            hora = time.strftime("%H:%M", time.localtime(os.path.getmtime(os.path.join(p["brutos"], a))))
        except OSError:
            hora = ""
        vids.append({"num": n, "arquivo": nfc(a), "hora": hora})
    vids.sort(key=lambda x: -x["num"])
    return {"baile": baile, "telao": time.time() - CONTROLE["visto"] < 6, "videos": vids}


def estado_baile(baile):
    p = preparar_recursos(baile)
    nums = numeracao(baile)
    lista = []
    for a in arquivos_brutos(baile):
        cam = os.path.join(p["brutos"], a)
        n = nums.get(nfc(a), 0)
        try:
            inf = info_video(cam)
        except Exception:
            inf = {"duracao": 0, "largura": 0, "altura": 0, "codec": "", "bits": 8}
        f, pv = saida(baile, n, "final"), saida(baile, n, "previa")
        lista.append({
            "arquivo": nfc(a), "num": n, "bytes": os.path.getsize(cam), "duracao": inf["duracao"],
            "deitado": inf["largura"] > inf["altura"], "codec": inf["codec"], "bits": inf["bits"],
            "final": os.path.isfile(f) and os.path.getsize(f) > 0,
            "previa": os.path.isfile(pv) and os.path.getsize(pv) > 0,
        })
    lista.sort(key=lambda x: x["num"])
    idt = identidade(baile)
    idt["exemplo"] = os.path.basename(saida(baile, 999, "final")).replace("999", "01")
    return {"nome": baile, "caminho": p["baile"], "ajustes": ajustes(baile), "brutos": lista, "identidade": idt,
            "versao_recursos": versao_recursos(baile)}


def versao_recursos(baile):
    p = pastas(baile)
    v = 0
    for arq in ("logos-baixo.png", "previa.png"):
        try:
            v += int(os.path.getmtime(os.path.join(p["rec"], arq)))
        except OSError:
            pass
    return v


def criar_baile(nome, data):
    nome = re.sub(r"[/:]", "-", (nome or "").strip())
    if not nome:
        raise ValueError("Dê um nome ao baile")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", data or ""):
        raise ValueError("Data inválida")
    pasta = "%s %s" % (data, nome)
    b = os.path.join(pasta_bailes(), pasta)
    for s in ESTRUTURA:
        os.makedirs(os.path.join(b, s), exist_ok=True)
    preparar_recursos(pasta)
    return pasta


# ---------------------------------------------------------------- filtros de vídeo
def giro(inf, aj):
    if inf["largura"] > inf["altura"]:
        return {"direita": "transpose=1,", "esquerda": "transpose=2,"}.get(aj["girar"], "")
    return ""


def cadeia(origem, W, H, aj, idx_logo, idx_previa, nome, fade=True, fmt="yuv420p"):
    """Filtro para uma saída W x H: logos embaixo e (opcional) PNG da prévia por cima."""
    lw = max(2, int(W * aj["logo_largura"] / 100) // 2 * 2)
    mb = int(H * aj["logo_margem"] / 100)
    f = "[%s]scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1[v%s];" % (
        origem, W, H, W, H, nome)
    f += "[%s]scale=%d:-1,format=rgba,colorchannelmixer=aa=%.3f[l%s];" % (idx_logo, lw, aj["logo_opacidade"], nome)
    f += "[v%s][l%s]overlay=(W-w)/2:H-h-%d[a%s]" % (nome, nome, mb, nome)
    if idx_previa is not None:
        fd = ",fade=t=in:st=%.3f:d=%.3f:alpha=1" % (aj["previa_inicio"], max(0.01, aj["previa_fade"])) if fade else ""
        f += ";[%s]scale=%d:%d,format=rgba,colorchannelmixer=aa=%.3f%s[p%s]" % (
            idx_previa, W, H, aj["previa_opacidade"], fd, nome)
        f += ";[a%s][p%s]overlay=0:0:shortest=1,format=%s[o%s]" % (nome, nome, fmt, nome)
    else:
        f += ";[a%s]format=%s[o%s]" % (nome, fmt, nome)
    return f


TAMANHOS = {"final": (1080, 1920), "previa": (720, 1280)}


def montar_filtro(inf, aj, saidas, fade=True, fmt="yuv420p"):
    """Uma leitura do bruto, duas saídas: o vídeo 4K é decodificado uma vez só."""
    g = giro(inf, aj)
    n = len(saidas)
    # reduz o 4K para 1080x1920 uma vez só, aplica a cor ali e então divide em final e prévia
    f = "[0:v]%sscale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[base];" % g
    f += filtro_cor(aj, "base", "cor") + ";"
    f += "[cor]" + (("split=%d" % n) + "".join("[s%d]" % i for i in range(n)) + ";" if n > 1 else "null[s0];")
    f += "[1:v]" + (("split=%d" % n) + "".join("[lg%d]" % i for i in range(n)) if n > 1 else "null[lg0]") + ";"
    partes = []
    for i, tipo in enumerate(saidas):
        W, H = TAMANHOS[tipo]
        partes.append(cadeia("s%d" % i, W, H, aj, "lg%d" % i, "2:v" if tipo == "previa" else None, str(i), fade, fmt))
    return f + ";".join(partes)


# ---------------------------------------------------------------- fila
FILA = []
TRAVA = threading.Lock()
EVENTO = threading.Event()
ATUAL = {"proc": None, "job": None}
ULTIMO_ACESSO = [time.time()]


def job_publico(j):
    return {k: j.get(k) for k in ("id", "baile", "arquivo", "num", "saidas", "estado", "etapa", "pct", "eta",
                                  "velocidade", "erro", "criado", "inicio", "fim", "duracao", "galeria", "galeria_info")}


def adicionar(baile, arquivos, saidas, refazer):
    saidas = [s for s in ("final", "previa") if s in saidas]
    if not saidas:
        raise ValueError("Escolha final e/ou prévia")
    nums = numeracao(baile)
    novos = []
    with TRAVA:
        ativos = {(j["baile"], j["arquivo"]) for j in FILA if j["estado"] in ("aguardando", "editando", "preparando", "copiando")}
        for a in arquivos:
            a = nfc(a)
            if "/" in a or (baile, a) in ativos:
                continue
            j = {"id": uuid.uuid4().hex[:10], "baile": baile, "arquivo": a, "num": nums.get(a, 0), "saidas": saidas,
                 "refazer": bool(refazer), "estado": "aguardando", "etapa": "Na fila", "pct": 0.0, "eta": None,
                 "velocidade": None, "erro": "", "criado": time.time(), "inicio": None, "fim": None, "duracao": 0,
                 "cancelar": False}
            FILA.append(j)
            novos.append(j["id"])
    EVENTO.set()
    return novos


def cancelar(jid):
    with TRAVA:
        for j in FILA:
            if j["id"] == jid or jid == "todos":
                if j["estado"] == "aguardando":
                    j["estado"], j["etapa"] = "cancelado", "Cancelado"
                elif j["estado"] in ("preparando", "editando", "copiando"):
                    j["cancelar"] = True
        p = ATUAL["proc"]
        if p and ATUAL["job"] and (jid == "todos" or ATUAL["job"]["id"] == jid):
            try:
                p.terminate()
            except Exception:
                pass


def limpar():
    with TRAVA:
        FILA[:] = [j for j in FILA if j["estado"] in ("aguardando", "preparando", "editando", "copiando")]


def rodar_ffmpeg(j, cmd, dur):
    """Roda o FFmpeg lendo o progresso; devolve (ok, mensagem de erro)."""
    log = os.path.join(CONF_DIR, "ultimo-erro.txt")
    os.makedirs(CONF_DIR, exist_ok=True)
    with open(log, "w") as ferr:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=ferr, stdin=subprocess.DEVNULL, text=True)
        ATUAL["proc"] = p
        t0 = time.time()
        for linha in p.stdout:
            linha = linha.strip()
            if linha.startswith("out_time_us=") or linha.startswith("out_time_ms="):
                try:
                    us = int(linha.split("=", 1)[1])
                except ValueError:
                    continue
                if dur > 0 and us > 0:
                    pct = min(99.5, us / 1e6 / dur * 100)
                    j["pct"] = round(pct, 1)
                    gasto = time.time() - t0
                    if pct > 1:
                        j["eta"] = round(gasto * (100 - pct) / pct)
            elif linha.startswith("speed="):
                v = linha.split("=", 1)[1].strip().rstrip("x")
                try:
                    j["velocidade"] = round(float(v), 2)
                except ValueError:
                    pass
        p.wait()
        ATUAL["proc"] = None
    if p.returncode == 0:
        return True, ""
    try:
        with open(log, "r", errors="replace") as f:
            txt = f.read().strip().splitlines()
        return False, (txt[-1] if txt else "FFmpeg terminou com erro %d" % p.returncode)[:300]
    except Exception:
        return False, "FFmpeg terminou com erro %d" % p.returncode


def processar(j):
    baile = j["baile"]
    p = preparar_recursos(baile)
    aj = ajustes(baile)
    bruto = os.path.join(p["brutos"], j["arquivo"])
    if not os.path.isfile(bruto):
        # o nome pode estar em outra normalização de acentos
        alvo = [a for a in arquivos_brutos(baile) if nfc(a) == j["arquivo"]]
        if not alvo:
            raise RuntimeError("O arquivo não está mais em 1. Brutos")
        bruto = os.path.join(p["brutos"], alvo[0])
    j["estado"], j["etapa"] = "preparando", "Lendo o vídeo"
    inf = info_video(bruto)
    j["duracao"] = inf["duracao"]
    j["num"] = numeracao(baile).get(j["arquivo"], j["num"])
    fazer = [s for s in j["saidas"] if j["refazer"] or not os.path.isfile(saida(baile, j["num"], s))]
    if fazer:
        nomes = {"final": "final", "previa": "prévia"}
        j["estado"], j["etapa"], j["pct"] = "editando", "Editando " + " + ".join(nomes[s] for s in fazer), 0.0
        tmps = {s: os.path.join(os.path.dirname(saida(baile, j["num"], s)),
                                ".%s.tmp.mp4" % os.path.basename(saida(baile, j["num"], s))[:-4]) for s in fazer}
        filtro = montar_filtro(inf, aj, fazer)
        base = [FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-progress", "pipe:1", "-nostats"]
        ent = ["-i", bruto, "-i", os.path.join(p["rec"], "logos-baixo.png")]
        if "previa" in fazer:
            ent += ["-loop", "1", "-framerate", "30", "-i", os.path.join(p["rec"], "previa.png")]
        outs = []
        for i, s in enumerate(fazer):
            outs += ["-map", "[o%d]" % i, "-map", "0:a?"] + codificador(s) + [
                "-c:a", "aac", "-b:a", "192k" if s == "final" else "128k", "-movflags", "+faststart", tmps[s]]
        tentativas = [["-hwaccel", "videotoolbox"], []] if VT else [[]]
        ok, erro = False, ""
        for hw in tentativas:
            ok, erro = rodar_ffmpeg(j, base + hw + ent + ["-filter_complex", filtro] + outs, inf["duracao"])
            if ok or j["cancelar"]:
                break
        if not ok:
            for t in tmps.values():
                try:
                    os.remove(t)
                except OSError:
                    pass
            if j["cancelar"]:
                raise InterruptedError()
            raise RuntimeError(erro or "Erro no FFmpeg")
        for s, t in tmps.items():
            os.replace(t, saida(baile, j["num"], s))
    j["pct"] = 100.0
    destino = aj.get("destino_drive") or ""
    if destino:
        if not os.path.isdir(destino):
            raise RuntimeError("A pasta do Drive não foi encontrada: " + destino)
        j["estado"], j["etapa"], j["eta"] = "copiando", "Copiando para o Drive", None
        j["drive_arqs"] = {}
        for s in j["saidas"]:
            orig = saida(baile, j["num"], s)
            if not os.path.isfile(orig):
                continue
            d = os.path.join(destino, "Finais" if s == "final" else "Prévias")
            os.makedirs(d, exist_ok=True)
            alvo = os.path.join(d, os.path.basename(orig))
            j["drive_arqs"][s] = (orig, alvo)
            if j["refazer"] or not os.path.isfile(alvo) or os.path.getsize(alvo) != os.path.getsize(orig):
                shutil.copyfile(orig, alvo + ".copiando")
                os.replace(alvo + ".copiando", alvo)
    j["estado"] = "concluido"
    j["etapa"] = "Concluído" if fazer else "Já estava pronto"
    if destino and "final" in j["saidas"] and "previa" in j["saidas"]:
        j["galeria"], j["galeria_info"], j["tentativas"] = "subindo", "", 0
        threading.Thread(target=acompanhar_galeria, args=(j, aj.get("url_galeria") or ""), daemon=True).start()


SINCRONIZAR = "https://jlogxdjttufiiikiezfe.supabase.co/functions/v1/sincronizar-drive"


# Estado do upload no Google Drive para computador (macOS, File Provider): enviado, enviando, erro.
JXA_DRIVE = r'''ObjC.import("Foundation");
function run(argv) {
  var ks = {up: "NSURLUbiquitousItemIsUploadedKey", ing: "NSURLUbiquitousItemIsUploadingKey", err: "NSURLUbiquitousItemUploadingErrorKey"};
  return JSON.stringify(argv.map(function (p) {
    var u = $.NSURL.fileURLWithPath(p), r = {};
    for (var k in ks) {
      try { var ref = Ref(); u.getResourceValueForKeyError(ref, $(ks[k]), null); var v = ref[0];
        if (v && !v.isNil()) r[k] = k === "err" ? ObjC.unwrap(v.localizedDescription) : ObjC.unwrap(v); } catch (e) {}
    }
    return r;
  }));
}'''


def estado_drive(caminhos):
    """[{up, ing, err}] por arquivo, ou None se não der para saber (fora do Mac, erro do osascript)."""
    if not EH_MAC or not caminhos:
        return None
    try:
        js = os.path.join(CONF_DIR, "estado-drive.js")
        if not os.path.isfile(js) or open(js, encoding="utf-8").read() != JXA_DRIVE:
            with open(js, "w", encoding="utf-8") as f:
                f.write(JXA_DRIVE)
        r = subprocess.run(["osascript", "-l", "JavaScript", js] + list(caminhos), capture_output=True, text=True, timeout=20)
        out = json.loads(r.stdout or "null")
        return out if isinstance(out, list) and len(out) == len(caminhos) else None
    except Exception:
        return None


def recopiar(orig, alvo):
    """Copia de novo para a pasta do Drive: o Drive vê um arquivo novo e tenta subir outra vez."""
    shutil.copyfile(orig, alvo + ".copiando")
    os.replace(alvo + ".copiando", alvo)


def sincronizar_site():
    r = subprocess.run(["curl", "-fsS", "-m", "40", "-X", "POST", "-H", "Content-Type: application/json",
                        "-d", "{}", SINCRONIZAR], capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout or "{}")


MAX_TENTATIVAS = 4


def acompanhar_galeria(j, url_galeria, reenviar_ja=False):
    """Avisa o site que chegou vídeo no Drive e acompanha até ele aparecer na galeria.
    O Drive do Mac sobe o arquivo em segundo plano. Se um arquivo não chega (erro do Drive, como
    "Não foi possível comunicar com um aplicativo auxiliar", ou parado por tempo demais), copia de novo
    sozinho até MAX_TENTATIVAS vezes; depois disso a fila mostra "Tentar de novo"."""
    meu = uuid.uuid4().hex
    j["acomp"] = meu
    codigo = "%02d" % j["num"]
    alvo_url = url_galeria.rstrip("/").lower()
    arqs = j.get("drive_arqs") or {}
    nomes = {"final": "final (F. %s)" % codigo, "previa": "prévia (P. %s)" % codigo}
    enviado = {t: time.time() for t in arqs}

    def reenviar(t, motivo):
        orig, alvo = arqs[t]
        try:
            recopiar(orig, alvo)
        except Exception as e:
            registrar("reenvio falhou %s: %s" % (alvo, e))
            return
        j["tentativas"] = j.get("tentativas", 0) + 1
        enviado[t] = time.time()
        j["galeria"] = "reenviando"
        j["galeria_info"] = "%s O %s foi enviado de novo (%dª tentativa)." % (motivo, nomes[t], j["tentativas"] + 1)
        registrar("reenviado %s (%s)" % (alvo, motivo))

    esperas = (5, 15, 30, 40, 60, 60, 90, 120, 120, 180, 180, 240, 300, 300, 300, 600, 600)
    if not reenviar_ja:
        esperas = (20,) + esperas[2:]
    for n, espera in enumerate(esperas):
        time.sleep(espera)
        if j.get("acomp") != meu:
            return  # um "Tentar de novo" começou outro acompanhamento
        try:
            d = sincronizar_site()
        except Exception:
            j["galeria"], j["galeria_info"] = "sem_internet", ""
            continue
        ev = next((e for e in d.get("resumo", []) if not alvo_url or (e.get("url_galeria") or "").rstrip("/").lower() == alvo_url), None)
        if not ev:
            continue
        if codigo in (ev.get("publicados") or []):
            j["galeria"], j["galeria_info"] = "publicado", ""
            return
        if j.get("galeria") in ("sem_internet", "falhou"):
            j["galeria"], j["galeria_info"] = "subindo", ""
        no_drive = ev.get("no_drive")  # sem ele (leitura pulada), nesta rodada só vale o estado local
        tipos = list(arqs)
        local = estado_drive([arqs[t][1] for t in tipos]) or [{} for _ in tipos]
        for t, st in zip(tipos, local):
            if no_drive is not None and codigo in (no_drive.get("finais" if t == "final" else "previas") or []):
                continue  # o site já enxerga este arquivo
            if no_drive is None and not st.get("err") and not (reenviar_ja and n == 0):
                continue  # sem a leitura do site, só reenvia quando o Drive do Mac acusa erro
            if reenviar_ja and n == 0:
                if j.get("tentativas", 0) < MAX_TENTATIVAS + 3:
                    reenviar(t, "Pedido de novo envio.")
                continue
            orig = arqs[t][0]
            limite = 240 + (os.path.getsize(orig) if os.path.isfile(orig) else 0) / 1.5e6  # ~1,5 MB/s de upload
            if j.get("tentativas", 0) >= MAX_TENTATIVAS:
                continue
            if st.get("err") and time.time() - enviado[t] > 60:
                reenviar(t, "O Drive deu erro ao subir (%s)." % st["err"])
            elif not st.get("ing") and not st.get("up") and time.time() - enviado[t] > limite:
                reenviar(t, "O Drive não subiu o arquivo a tempo.")
            elif st.get("up") and time.time() - enviado[t] > limite + 300:
                reenviar(t, "O Drive diz que subiu, mas o arquivo não apareceu.")
    if j.get("acomp") == meu and j.get("galeria") != "publicado":
        j["galeria"] = "falhou"
        j["galeria_info"] = "Não chegou à galeria depois de %d tentativas. Confira o Google Drive no Mac (ícone na barra de menus) e toque em \"Tentar de novo\"." % (j.get("tentativas", 0) + 1)


def tentar_de_novo(jid):
    with TRAVA:
        j = next((x for x in FILA if x["id"] == jid), None)
    if not j or not j.get("drive_arqs"):
        raise ValueError("Esse vídeo não foi copiado para o Drive")
    j["galeria"], j["galeria_info"] = "reenviando", "Enviando de novo para o Drive…"
    threading.Thread(target=acompanhar_galeria, args=(j, ajustes(j["baile"]).get("url_galeria") or "", True), daemon=True).start()


def trabalhador():
    cafe = None
    while True:
        EVENTO.wait(2)
        EVENTO.clear()
        while True:
            with TRAVA:
                j = next((x for x in FILA if x["estado"] == "aguardando"), None)
            if not j:
                break
            if EH_MAC and cafe is None:
                try:
                    cafe = subprocess.Popen(["caffeinate", "-i"])  # não deixa o Mac dormir durante a fila
                except Exception:
                    cafe = None
            ATUAL["job"] = j
            j["inicio"] = time.time()
            try:
                processar(j)
            except InterruptedError:
                j["estado"], j["etapa"] = "cancelado", "Cancelado"
            except Exception as e:  # noqa
                j["estado"], j["etapa"], j["erro"] = ("cancelado", "Cancelado", "") if j["cancelar"] else (
                    "erro", "Erro", str(e))
            j["fim"], j["eta"] = time.time(), None
            ATUAL["job"] = None
        if cafe is not None:
            cafe.terminate()
            cafe = None
            if EH_MAC and any(x["estado"] == "concluido" and x["fim"] and time.time() - x["fim"] < 10 for x in FILA):
                avisar("Fila concluída", "Prévias e finais prontos.")


def avisar(titulo, texto):
    try:
        subprocess.Popen(["osascript", "-e", 'display notification "%s" with title "Editor de Bailes" subtitle "%s" sound name "Glass"' % (texto, titulo)])
    except Exception:
        pass


def fila_ocupada():
    return any(j["estado"] in ("aguardando", "preparando", "editando", "copiando") for j in FILA)


# ---------------------------------------------------------------- imagens
TRAVA_IMG = threading.Semaphore(2)


def miniatura(baile, arquivo):
    p = preparar_recursos(baile)
    alvo = [a for a in arquivos_brutos(baile) if nfc(a) == nfc(arquivo)]
    if not alvo:
        raise ValueError("Arquivo não encontrado")
    bruto = os.path.join(p["brutos"], alvo[0])
    st = os.stat(bruto)
    d = os.path.join(p["rec"], ".miniaturas")
    os.makedirs(d, exist_ok=True)
    jpg = os.path.join(d, "%s-%d-480.jpg" % (re.sub(r"[^\w.-]", "_", nfc(arquivo)), int(st.st_mtime)))
    if not os.path.isfile(jpg):
        with TRAVA_IMG:
            inf = info_video(bruto)
            t = min(3.0, max(0.0, inf["duracao"] / 3))
            hw = ["-hwaccel", "videotoolbox"] if VT else []
            subprocess.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y"] + hw + ["-ss", "%.2f" % t, "-i", bruto,
                            "-frames:v", "1", "-vf", giro(inf, ajustes(baile)) + "scale=-2:480", "-q:v", "4", jpg],  # 480: o iPad mostra com zoom no rosto
                           timeout=120)
    with open(jpg, "rb") as f:
        return f.read()


def quadro_base(baile, arquivo, t):
    """Um quadro do bruto em 540x960 (guardado), base das miniaturas da galeria de filtros."""
    p = preparar_recursos(baile)
    alvo = [a for a in arquivos_brutos(baile) if nfc(a) == nfc(arquivo)]
    if not alvo:
        raise ValueError("Arquivo não encontrado")
    bruto = os.path.join(p["brutos"], alvo[0])
    st = os.stat(bruto)
    d = os.path.join(CONF_DIR, "quadros")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, hashlib.sha1(("%s|%s|%d|%s" % (baile, alvo[0], st.st_size, t)).encode()).hexdigest()[:16] + ".png")
    if os.path.isfile(out):
        return out
    inf = info_video(bruto)
    tt = max(0.0, min(float(t), max(0.0, inf["duracao"] - 0.5)))
    vf = "%sscale=540:960:force_original_aspect_ratio=decrease,pad=540:960:(ow-iw)/2:(oh-ih)/2,setsar=1" % giro(inf, ajustes(baile))
    for hw in ((["-hwaccel", "videotoolbox"], []) if VT else ([],)):
        r = subprocess.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y"] + list(hw) + ["-ss", "%.2f" % tt, "-i", bruto,
                            "-vf", vf, "-frames:v", "1", out + ".tmp.png"], capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.isfile(out + ".tmp.png"):
            os.replace(out + ".tmp.png", out)
            return out
    raise RuntimeError(((r.stderr or "").strip().splitlines() or ["o FFmpeg não gerou o quadro"])[-1][:300])


def miniatura_lut(baile, arquivo, t, lut):
    """O mesmo quadro com um filtro (e os ajustes de cor atuais), em 270x480."""
    base = quadro_base(baile, arquivo, t)
    aj = ajustes(baile)
    filtro = filtro_cor(aj, "0:v", "c", lut=lut, rapido=False) + ";[c]scale=270:480,format=yuvj420p[o]"
    r = subprocess.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y", "-i", base, "-filter_complex", filtro,
                        "-map", "[o]", "-frames:v", "1", "-q:v", "4", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                       capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError((r.stderr or b"").decode("utf-8", "replace").strip()[-300:] or "falhou")
    return r.stdout


def amostra(baile, arquivo, t, tipo, sem_cor=False):
    """Um quadro do vídeo com as logos (e a prévia já visível), com os ajustes atuais."""
    p = preparar_recursos(baile)
    aj = ajustes(baile)
    if sem_cor:
        aj.update(lut="", cor_brilho=0, cor_contraste=0, cor_saturacao=0, cor_temperatura=0)
    alvo = [a for a in arquivos_brutos(baile) if nfc(a) == nfc(arquivo)]
    if not alvo:
        raise ValueError("Arquivo não encontrado")
    bruto = os.path.join(p["brutos"], alvo[0])
    inf = info_video(bruto)
    t = max(0.0, min(float(t), max(0.0, inf["duracao"] - 0.5)))
    out = os.path.join(CONF_DIR, "amostra-%s%s.jpg" % (tipo, "-antes" if sem_cor else ""))
    os.makedirs(CONF_DIR, exist_ok=True)
    ent = ["-ss", "%.2f" % t, "-i", bruto, "-i", os.path.join(p["rec"], "logos-baixo.png")]
    if tipo == "previa":
        ent += ["-loop", "1", "-framerate", "30", "-i", os.path.join(p["rec"], "previa.png")]
    filtro = montar_filtro(inf, aj, [tipo], fade=False, fmt="yuvj420p")
    erro = ""
    with TRAVA_IMG:
        for hw in ((["-hwaccel", "videotoolbox"], []) if VT else ([],)):
            try:
                os.remove(out)
            except OSError:
                pass
            r = subprocess.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y"] + list(hw) + ent +
                               ["-filter_complex", filtro, "-map", "[o0]", "-frames:v", "1", "-q:v", "3", out],
                               capture_output=True, text=True, timeout=180)
            if r.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 0:
                erro = ""
                break
            erro = ((r.stderr or "").strip().splitlines() or ["o FFmpeg não gerou a imagem"])[-1][:300]
    if erro:
        registrar("amostra falhou: " + erro)
        raise RuntimeError(erro)
    with open(out, "rb") as f:
        return f.read()


def escolher_pasta(prompt, inicial):
    if not EH_MAC:
        raise RuntimeError("Só funciona no Mac")
    script = 'activate\nPOSIX path of (choose folder with prompt "%s" default location POSIX file "%s")' % (
        prompt.replace('"', "'"), inicial.replace('"', ""))
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        return ""
    return r.stdout.strip().rstrip("/")


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "EditorDeBailes/1.0"

    def log_message(self, *a):
        pass

    def responder(self, codigo, corpo, tipo="application/json; charset=utf-8", cache=False):
        if isinstance(corpo, (dict, list)):
            corpo = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        elif isinstance(corpo, str):
            corpo = corpo.encode("utf-8")
        try:
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
            self.end_headers()
            self.wfile.write(corpo)
        except (BrokenPipeError, ConnectionResetError):
            pass  # a janela desistiu do pedido (ex.: trocou o exemplo antes de terminar)

    def video(self, q):
        baile = q.get("baile", "")
        if q.get("tipo") == "final":
            cam = saida(baile, int(q.get("num", "0")), "final")
        else:
            alvo = [a for a in arquivos_brutos(baile) if nfc(a) == nfc(q.get("arquivo", ""))]
            if not alvo:
                return self.erro("vídeo não encontrado", 404)
            cam = os.path.join(pastas(baile)["brutos"], alvo[0])
        if not os.path.isfile(cam):
            return self.erro("vídeo não encontrado", 404)
        total = os.path.getsize(cam)
        ini, fim = 0, total - 1
        faixa = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if faixa:
            if faixa.group(1):
                ini = int(faixa.group(1))
                if faixa.group(2):
                    fim = min(fim, int(faixa.group(2)))
            elif faixa.group(2):
                ini = max(0, total - int(faixa.group(2)))
            if ini > fim:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % total)
                self.end_headers()
                return None
        try:
            self.send_response(206 if faixa else 200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(fim - ini + 1))
            if faixa:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (ini, fim, total))
            self.end_headers()
            with open(cam, "rb") as f:
                f.seek(ini)
                falta = fim - ini + 1
                while falta > 0:
                    bloco = f.read(min(1 << 20, falta))
                    if not bloco:
                        break
                    self.wfile.write(bloco)
                    falta -= len(bloco)
        except (BrokenPipeError, ConnectionResetError):
            pass
        return None

    def erro(self, e, codigo=400):
        self.responder(codigo, {"erro": str(e)})

    def do_GET(self):
        ULTIMO_ACESSO[0] = time.time()
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if not eh_local(self.client_address[0]) and u.path not in LIVRE_NA_REDE_GET and not u.path.startswith("/recursos/"):
            return self.erro("proibido", 403)
        try:
            if u.path == "/ipad":
                with open(os.path.join(AQUI, "ipad.html"), "rb") as f:
                    return self.responder(200, f.read(), "text/html; charset=utf-8")
            if u.path == "/api/controle/lista":
                return self.responder(200, lista_controle())
            if u.path == "/api/controle/pedido":
                # o telão pergunta várias vezes por segundo: diz qual baile está tocando e recebe o último pedido
                CONTROLE["baile"], CONTROLE["visto"] = nfc(q.get("baile", "")), time.time()
                return self.responder(200, CONTROLE["pedido"])
            if u.path == "/api/controle/endereco":
                return self.responder(200, {"ips": enderecos_rede()})
            if u.path in ("/", "/index.html"):
                with open(os.path.join(AQUI, "index.html"), "rb") as f:
                    return self.responder(200, f.read(), "text/html; charset=utf-8")
            if u.path in ("/telao", "/telao/"):
                with open(os.path.join(AQUI, "telao.html"), "rb") as f:
                    return self.responder(200, f.read(), "text/html; charset=utf-8")
            if u.path.startswith("/recursos/") and re.match(r"^/recursos/[\w.-]+\.(png|svg|js)$", u.path):
                tipo = "application/javascript" if u.path.endswith(".js") else "image/png"
                with open(os.path.join(REC_APP, u.path.split("/")[-1]), "rb") as f:
                    return self.responder(200, f.read(), tipo, cache=True)
            if u.path == "/api/video":
                return self.video(q)
            if u.path == "/api/ping":
                return self.responder(200, {"ok": True})
            if u.path == "/api/inicio":
                c = config()
                bailes = listar_bailes()
                atual = c.get("baile_atual") if c.get("baile_atual") in bailes else (bailes[0] if bailes else "")
                return self.responder(200, {"pasta_bailes": c["pasta_bailes"], "bailes": bailes, "baile_atual": atual,
                                            "ffmpeg": bool(FFMPEG and FFPROBE), "videotoolbox": VT,
                                            "mac": EH_MAC})
            if u.path == "/api/baile":
                return self.responder(200, estado_baile(q.get("nome", "")))
            if u.path == "/api/fila":
                with TRAVA:
                    return self.responder(200, {"fila": [job_publico(j) for j in FILA], "ocupada": fila_ocupada()})
            if u.path == "/api/imagem":
                arq = {"logos": "logos-baixo.png", "previa": "previa.png", "parceiro": "parceiro.png"}[q.get("tipo")]
                cam = os.path.join(preparar_recursos(q.get("baile", ""))["rec"], arq)
                if not os.path.isfile(cam):
                    return self.erro("sem imagem", 404)
                with open(cam, "rb") as f:
                    return self.responder(200, f.read(), "image/png")
            if u.path == "/api/miniatura":
                return self.responder(200, miniatura(q.get("baile", ""), q.get("arquivo", "")), "image/jpeg", cache=True)
            if u.path == "/api/amostra":
                return self.responder(200, amostra(q.get("baile", ""), q.get("arquivo", ""), q.get("t", "8"),
                                                   "previa" if q.get("tipo") == "previa" else "final",
                                                   q.get("antes") == "1"), "image/jpeg")
            if u.path == "/api/luts":
                return self.responder(200, {"luts": listar_luts(), "pasta": LUTS_USUARIO})
            if u.path == "/api/lut-amostra":
                return self.responder(200, miniatura_lut(q.get("baile", ""), q.get("arquivo", ""), q.get("t", "8"),
                                                         q.get("lut", "")), "image/jpeg")
            return self.erro("não encontrado", 404)
        except Exception as e:
            traceback.print_exc()
            return self.erro(e)

    def do_POST(self):
        ULTIMO_ACESSO[0] = time.time()
        # bloqueia pedidos de outros sites (o navegador não manda esse cabeçalho sem permissão)
        if self.headers.get("X-Editor") != "1":
            return self.erro("proibido", 403)
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if not eh_local(self.client_address[0]) and u.path not in LIVRE_NA_REDE_POST:
            return self.erro("proibido", 403)
        n = int(self.headers.get("Content-Length") or 0)
        if u.path == "/api/controle/tocar":
            try:
                d = json.loads(self.rfile.read(min(n, 2000)).decode("utf-8") or "{}")
                num = int(d.get("num"))
            except Exception:
                return self.erro("Número inválido")
            ped = CONTROLE["pedido"]
            CONTROLE["pedido"] = {"id": ped["id"] + 1, "num": num, "baile": CONTROLE["baile"], "quando": time.time()}
            return self.responder(200, {"ok": True, "telao": time.time() - CONTROLE["visto"] < 6})
        corpo = self.rfile.read(n) if n else b""
        try:
            if u.path == "/api/upload-json":
                d = json.loads(corpo.decode("utf-8") or "{}")
                q = {"baile": d.get("baile", ""), "tipo": d.get("tipo", "")}
                corpo = base64.b64decode(d.get("dados", ""))
                u = u._replace(path="/api/upload")
            if u.path == "/api/lut-upload":
                nome = os.path.basename(nfc(q.get("nome", "")))
                txt = corpo[:200000].decode("utf-8", "ignore").upper()
                if not nome.lower().endswith(".cube") or "LUT_3D_SIZE" not in txt or len(corpo) > 60_000_000:
                    return self.erro("Envie um arquivo .cube (LUT 3D)")
                os.makedirs(LUTS_USUARIO, exist_ok=True)
                with open(os.path.join(LUTS_USUARIO, nome + ".tmp"), "wb") as f:
                    f.write(corpo)
                os.replace(os.path.join(LUTS_USUARIO, nome + ".tmp"), os.path.join(LUTS_USUARIO, nome))
                return self.responder(200, {"ok": True, "arquivo": nome, "luts": listar_luts()})
            if u.path == "/api/upload":
                tipo = q.get("tipo")
                arq = {"logos": "logos-baixo.png", "previa": "previa.png", "parceiro": "parceiro.png"}.get(tipo)
                if not arq or not corpo.startswith(b"\x89PNG"):
                    return self.erro("Envie um arquivo PNG")
                rec = preparar_recursos(q.get("baile", ""))["rec"]
                with open(os.path.join(rec, arq + ".tmp"), "wb") as f:
                    f.write(corpo)
                os.replace(os.path.join(rec, arq + ".tmp"), os.path.join(rec, arq))
                return self.responder(200, {"ok": True})
            d = json.loads(corpo.decode("utf-8") or "{}") if corpo else {}
            if u.path == "/api/baile-atual":
                c = config()
                c["baile_atual"] = d.get("nome", "")
                salvar_config(c)
                return self.responder(200, {"ok": True})
            if u.path == "/api/criar-baile":
                nome = criar_baile(d.get("nome"), d.get("data"))
                c = config()
                c["baile_atual"] = nome
                salvar_config(c)
                return self.responder(200, {"nome": nome})
            if u.path == "/api/trocar-pasta-bailes":
                c = config()
                novo = escolher_pasta("Escolha a pasta onde ficam os bailes", c["pasta_bailes"])
                if novo:
                    c["pasta_bailes"] = novo
                    c["baile_atual"] = ""
                    salvar_config(c)
                return self.responder(200, {"pasta_bailes": c["pasta_bailes"]})
            if u.path == "/api/ajustes":
                return self.responder(200, salvar_ajustes(d.get("baile", ""), d.get("ajustes", {})))
            if u.path == "/api/escolher-drive":
                baile = d.get("baile", "")
                novo = escolher_pasta("Escolha a pasta deste baile no Google Drive (dentro dela o editor usa Prévias e Finais)",
                                      ajustes(baile).get("destino_drive") or HOME)
                if novo:
                    salvar_ajustes(baile, {"destino_drive": novo})
                return self.responder(200, ajustes(baile))
            if u.path == "/api/fila/adicionar":
                ids = adicionar(d.get("baile", ""), d.get("arquivos", []), d.get("saidas", ["final", "previa"]),
                                d.get("refazer", False))
                return self.responder(200, {"ids": ids})
            if u.path == "/api/fila/reenviar":
                tentar_de_novo(d.get("id", ""))
                return self.responder(200, {"ok": True})
            if u.path == "/api/fila/cancelar":
                cancelar(d.get("id", ""))
                return self.responder(200, {"ok": True})
            if u.path == "/api/fila/limpar":
                limpar()
                return self.responder(200, {"ok": True})
            if u.path == "/api/abrir":
                p = pastas(d.get("baile", ""))
                alvo = p.get(d.get("pasta", "baile"))
                if d.get("pasta") == "drive":
                    alvo = ajustes(d.get("baile", "")).get("destino_drive")
                if d.get("pasta") == "luts":
                    os.makedirs(LUTS_USUARIO, exist_ok=True)
                    alvo = LUTS_USUARIO
                if alvo and os.path.isdir(alvo) and EH_MAC:
                    subprocess.Popen(["open", alvo])
                return self.responder(200, {"ok": True})
            if u.path == "/api/sair":
                cancelar("todos")
                self.responder(200, {"ok": True})
                threading.Thread(target=desligar, daemon=True).start()
                return None
            return self.erro("não encontrado", 404)
        except Exception as e:
            traceback.print_exc()
            return self.erro(e)


SERVIDOR = {}


def registrar(msg):
    print("%s [pid %d] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), os.getpid(), msg), flush=True)


def desligar(motivo="botão Fechar editor"):
    registrar("encerrando: " + motivo)
    time.sleep(0.5)
    SERVIDOR["s"].shutdown()


def vigia(limite):
    # fecha sozinho quando a janela foi fechada (a janela consulta a fila a cada segundo) e não há nada na fila
    while True:
        time.sleep(10)
        if not fila_ocupada() and time.time() - ULTIMO_ACESSO[0] > limite:
            desligar("janela fechada há %d s e fila vazia" % limite)
            return


def limpar_temporarios():
    try:
        for b in listar_bailes():
            p = pastas(b)
            for d in (p["previas"], p["finais"]):
                if os.path.isdir(d):
                    for n in os.listdir(d):
                        if n.startswith(".") and n.endswith(".tmp.mp4"):
                            os.remove(os.path.join(d, n))
    except Exception:
        pass


def separar(log):
    """Sai do grupo de processos do app. Quando o app termina, o macOS (launchd) encerra todos os processos do
    mesmo grupo; sem isto o servidor morria alguns segundos depois de abrir a janela."""
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    os.makedirs(os.path.dirname(log), exist_ok=True)
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    nulo = os.open(os.devnull, os.O_RDONLY)
    os.dup2(nulo, 0)
    os.dup2(fd, 1)
    os.dup2(fd, 2)


def main():
    porta = 8765
    if "--porta" in sys.argv:
        porta = int(sys.argv[sys.argv.index("--porta") + 1])
    if "--separar" in sys.argv:
        separar(os.path.join(HOME, "Library", "Logs", "Editor de Bailes.log"))
    limpar_temporarios()
    # 0.0.0.0: o iPad entra pela rede local (só a página do iPad; ver LIVRE_NA_REDE_*)
    s = ThreadingHTTPServer(("0.0.0.0", porta), Handler)
    s.daemon_threads = True
    SERVIDOR["s"] = s
    threading.Thread(target=trabalhador, daemon=True).start()
    # --app: o servidor é o próprio app (fica aberto enquanto a janela estiver aberta)
    threading.Thread(target=vigia, args=(120 if "--app" in sys.argv else 20 * 60,), daemon=True).start()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda n, f: threading.Thread(target=desligar, args=("recebi o sinal %d do sistema" % n,),
                                                          daemon=True).start())
    registrar("Editor de Bailes em http://127.0.0.1:%d/ (python %s, ffmpeg: %s, videotoolbox: %s, pasta: %s)" % (
        porta, sys.version.split()[0], FFMPEG, VT, config()["pasta_bailes"]))
    try:
        os.listdir(config()["pasta_bailes"])
    except Exception as e:
        registrar("SEM ACESSO à pasta dos bailes: %s" % e)
    s.serve_forever()
    registrar("encerrado")
    if ATUAL["proc"]:
        try:
            ATUAL["proc"].terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
