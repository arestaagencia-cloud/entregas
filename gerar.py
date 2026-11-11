#!/usr/bin/env python3
"""Gera a página de entrega de um cliente a partir do JSON em clientes/<slug>.json.

Uso: python3 gerar.py clientes/universa.json
Saída: docs/<slug>/index.html
"""
import json, re, sys
from pathlib import Path

BASE = Path(__file__).parent
EXT = re.compile(r"\.(mov|mp4|m4v|avi|mkv|jpe?g|png|heic|tiff?)$", re.I)
VERSAO = re.compile(r"^v\.?\s*\d+$", re.I)


def parse_video(nome, cliente):
    """'F. Universa - 7 Erros - Gabi - V.2.mov' -> titulo, detalhe, versao."""
    base = EXT.sub("", nome).strip()
    partes = [p.strip() for p in re.split(r"\s+-\s+|\.\s+", base) if p.strip()]
    if partes and partes[0].upper() in {"F", "FINAL"}:
        partes = partes[1:]
    if partes and partes[0].lower() == cliente.lower():
        partes = partes[1:]
    versao = None
    if partes and VERSAO.match(partes[-1]):
        versao = re.sub(r"(?i)^v\.?\s*", "V", partes.pop())
    titulo = partes[0] if partes else base
    detalhe = " · ".join(partes[1:])
    return titulo, detalhe, versao


def main(caminho):
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    for v in dados["videos"]:
        t, d, ver = parse_video(v["arquivo"], dados["cliente"])
        v.setdefault("titulo", t)
        v.setdefault("detalhe", d)
        v.setdefault("versao", ver)
        v.setdefault("orientacao", "vertical")
    # "zip": {"id": "...", "bytes": N}  -> botão "Baixar tudo" vira download direto
    dados.setdefault("zip", None)
    tpl = (BASE / "template.html").read_text(encoding="utf-8")
    titulo = f'{dados["cliente"]} · Entrega ArestAgência'
    logo = (BASE / "assets" / "logo-mark.b64").read_text().strip()
    html = tpl.replace("{{TITLE}}", titulo).replace("{{LOGO}}", logo).replace(
        "/*__DATA__*/null", json.dumps(dados, ensure_ascii=False)
    )
    out = BASE / "docs" / dados["slug"] / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(out)
    for v in dados["videos"]:
        print(f'  - {v["titulo"]} | {v["detalhe"]} | {v["versao"]}')


if __name__ == "__main__":
    main(sys.argv[1])
