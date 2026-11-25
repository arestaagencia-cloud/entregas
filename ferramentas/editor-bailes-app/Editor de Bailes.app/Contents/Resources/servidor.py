#!/usr/bin/env python3
# Editor de Bailes · ArestAgência
# Servidor local (só neste Mac, 127.0.0.1) que gerencia a edição dos vídeos brutos dos bailes:
#   F. NN.mp4 (1080x1920, logos embaixo) e P. NN.mp4 (720x1280, logos + PNG "prévia" com fade).
# Compatível com o Python 3.9 que vem com as ferramentas de linha de comando da Apple.

import base64
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
}


def nfc(s):
    return unicodedata.normalize("NFC", s)


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


def config():
    c = ler_json(CONF, {})
    if not c.get("pasta_bailes"):
        doc = os.path.join(HOME, "Documents", "Bailes")
        c["pasta_bailes"] = doc if os.path.isdir(doc) else os.path.join(HOME, "Movies", "Bailes")
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


def saida(baile, num, tipo):
    p = pastas(baile)
    nn = "%02d" % num
    return os.path.join(p["finais"], "F. %s.mp4" % nn) if tipo == "final" else os.path.join(p["previas"], "P. %s.mp4" % nn)


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
    return {"nome": baile, "caminho": p["baile"], "ajustes": ajustes(baile), "brutos": lista,
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


def cadeia(origem, W, H, aj, idx_logo, idx_previa, nome, fade=True):
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
        f += ";[a%s][p%s]overlay=0:0:shortest=1,format=yuv420p[o%s]" % (nome, nome, nome)
    else:
        f += ";[a%s]format=yuv420p[o%s]" % (nome, nome)
    return f


TAMANHOS = {"final": (1080, 1920), "previa": (720, 1280)}


def montar_filtro(inf, aj, saidas, fade=True):
    """Uma leitura do bruto, duas saídas: o vídeo 4K é decodificado uma vez só."""
    g = giro(inf, aj)
    n = len(saidas)
    f = "[0:v]%s%s" % (g, ("split=%d" % n) + "".join("[s%d]" % i for i in range(n)) + ";" if n > 1 else "null[s0];")
    f += "[1:v]" + (("split=%d" % n) + "".join("[lg%d]" % i for i in range(n)) if n > 1 else "null[lg0]") + ";"
    partes = []
    for i, tipo in enumerate(saidas):
        W, H = TAMANHOS[tipo]
        partes.append(cadeia("s%d" % i, W, H, aj, "lg%d" % i, "2:v" if tipo == "previa" else None, str(i), fade))
    return f + ";".join(partes)


# ---------------------------------------------------------------- fila
FILA = []
TRAVA = threading.Lock()
EVENTO = threading.Event()
ATUAL = {"proc": None, "job": None}
ULTIMO_ACESSO = [time.time()]


def job_publico(j):
    return {k: j[k] for k in ("id", "baile", "arquivo", "num", "saidas", "estado", "etapa", "pct", "eta",
                              "velocidade", "erro", "criado", "inicio", "fim", "duracao")}


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
        for s in j["saidas"]:
            orig = saida(baile, j["num"], s)
            if not os.path.isfile(orig):
                continue
            d = os.path.join(destino, "Finais" if s == "final" else "Prévias")
            os.makedirs(d, exist_ok=True)
            alvo = os.path.join(d, os.path.basename(orig))
            if j["refazer"] or not os.path.isfile(alvo) or os.path.getsize(alvo) != os.path.getsize(orig):
                shutil.copyfile(orig, alvo + ".copiando")
                os.replace(alvo + ".copiando", alvo)
    j["estado"] = "concluido"
    j["etapa"] = "Concluído" if fazer else "Já estava pronto"


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
    jpg = os.path.join(d, "%s-%d.jpg" % (re.sub(r"[^\w.-]", "_", nfc(arquivo)), int(st.st_mtime)))
    if not os.path.isfile(jpg):
        with TRAVA_IMG:
            inf = info_video(bruto)
            t = min(3.0, max(0.0, inf["duracao"] / 3))
            hw = ["-hwaccel", "videotoolbox"] if VT else []
            subprocess.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y"] + hw + ["-ss", "%.2f" % t, "-i", bruto,
                            "-frames:v", "1", "-vf", giro(inf, ajustes(baile)) + "scale=-2:320", "-q:v", "4", jpg],
                           timeout=120)
    with open(jpg, "rb") as f:
        return f.read()


def amostra(baile, arquivo, t, tipo):
    """Um quadro do vídeo com as logos (e a prévia já visível), com os ajustes atuais."""
    p = preparar_recursos(baile)
    aj = ajustes(baile)
    alvo = [a for a in arquivos_brutos(baile) if nfc(a) == nfc(arquivo)]
    if not alvo:
        raise ValueError("Arquivo não encontrado")
    bruto = os.path.join(p["brutos"], alvo[0])
    inf = info_video(bruto)
    t = max(0.0, min(float(t), max(0.0, inf["duracao"] - 0.5)))
    out = os.path.join(CONF_DIR, "amostra-%s.jpg" % tipo)
    os.makedirs(CONF_DIR, exist_ok=True)
    ent = ["-ss", "%.2f" % t, "-i", bruto, "-i", os.path.join(p["rec"], "logos-baixo.png")]
    if tipo == "previa":
        ent += ["-loop", "1", "-framerate", "30", "-i", os.path.join(p["rec"], "previa.png")]
    filtro = montar_filtro(inf, aj, [tipo], fade=False)
    with TRAVA_IMG:
        hw = ["-hwaccel", "videotoolbox"] if VT else []
        r = subprocess.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y"] + hw + ent +
                           ["-filter_complex", filtro, "-map", "[o0]", "-frames:v", "1", "-q:v", "3", out],
                           capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "erro").strip().splitlines()[-1][:300])
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

    def erro(self, e, codigo=400):
        self.responder(codigo, {"erro": str(e)})

    def do_GET(self):
        ULTIMO_ACESSO[0] = time.time()
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                with open(os.path.join(AQUI, "index.html"), "rb") as f:
                    return self.responder(200, f.read(), "text/html; charset=utf-8")
            if u.path.startswith("/recursos/") and re.match(r"^/recursos/[\w.-]+\.(png|svg)$", u.path):
                with open(os.path.join(REC_APP, u.path.split("/")[-1]), "rb") as f:
                    return self.responder(200, f.read(), "image/png", cache=True)
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
                                                   "previa" if q.get("tipo") == "previa" else "final"), "image/jpeg")
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
        n = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(n) if n else b""
        try:
            if u.path == "/api/upload-json":
                d = json.loads(corpo.decode("utf-8") or "{}")
                q = {"baile": d.get("baile", ""), "tipo": d.get("tipo", "")}
                corpo = base64.b64decode(d.get("dados", ""))
                u = u._replace(path="/api/upload")
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


def desligar():
    time.sleep(0.5)
    SERVIDOR["s"].shutdown()


def vigia():
    # fecha sozinho depois de 20 min sem a janela aberta e sem nada na fila
    while True:
        time.sleep(30)
        if not fila_ocupada() and time.time() - ULTIMO_ACESSO[0] > 20 * 60:
            desligar()
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
    s = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    s.daemon_threads = True
    SERVIDOR["s"] = s
    threading.Thread(target=trabalhador, daemon=True).start()
    threading.Thread(target=vigia, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *a: threading.Thread(target=desligar, daemon=True).start())
    print("Editor de Bailes em http://127.0.0.1:%d/ (ffmpeg: %s, videotoolbox: %s)" % (porta, FFMPEG, VT), flush=True)
    s.serve_forever()
    if ATUAL["proc"]:
        try:
            ATUAL["proc"].terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
