"""Gera as páginas dos bailes.

Uso: python3 gerar_bailes.py
- docs/bailes/index.html          ← bailes_publico_template.html (Hub PÚBLICO dos bailes: lista as galerias, campo de código)
- docs/bailes/painel/index.html   ← bailes_template.html  (Hub de Bailes INTERNO: métricas e códigos, login Google)
- docs/bailes/telao/index.html    ← bailes_telao_template.html (telão do baile: vídeos locais em loop + oferta + QR do Me avise)
- docs/bailes/<pasta>/index.html   ← galeria_template.html (galeria pública de cada baile, uma por item de bailes.json)

Nenhuma página leva dados: tudo vem ao vivo do Supabase (projeto arestagencia-bailes).
Galeria nova: acrescente {"pasta", "evento" (slug no Supabase), "parceiro": {"nome","logo"} opcional} em bailes.json,
ponha o logo do cliente em docs/bailes/<pasta>/ e grave a url em eventos.url_galeria no Supabase.
"""
import html, json
from pathlib import Path

RAIZ = Path(__file__).parent
DOCS = RAIZ / "docs" / "bailes"
logo = (RAIZ / "assets/logo-mark.b64").read_text().strip()

galerias = json.loads((RAIZ / "bailes.json").read_text())["galerias"]

hub = (RAIZ / "bailes_template.html").read_text().replace("{{LOGO}}", logo)
(DOCS / "painel").mkdir(parents=True, exist_ok=True)
(DOCS / "painel" / "index.html").write_text(hub)
print(DOCS / "painel" / "index.html")

mapa = {g["evento"]: {"pasta": g["pasta"],
                      "logo": f'/bailes/{g["pasta"]}/{g["parceiro"]["logo"]}' if (g.get("parceiro") or {}).get("logo") else None}
        for g in galerias}
publico = (RAIZ / "bailes_publico_template.html").read_text().replace(
    "{{GALERIAS}}", json.dumps(mapa, ensure_ascii=False).replace("</", "<\\/"))
(DOCS / "index.html").write_text(publico)
print(DOCS / "index.html")

telao = (RAIZ / "bailes_telao_template.html").read_text().replace(
    "{{GALERIAS}}", json.dumps(mapa, ensure_ascii=False).replace("</", "<\\/"))
(DOCS / "telao").mkdir(parents=True, exist_ok=True)
(DOCS / "telao" / "index.html").write_text(telao)
print(DOCS / "telao" / "index.html")

modelo = (RAIZ / "galeria_template.html").read_text()
for g in galerias:
    p = g.get("parceiro") or {}
    parceiro = ""
    if p.get("logo"):
        parceiro = (f'<span class="x" aria-hidden="true">×</span>'
                    f'<img class="parceiro" src="{html.escape(p["logo"])}" alt="{html.escape(p.get("nome", ""))}">')
    destino = DOCS / g["pasta"] / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(modelo.replace("{{EVENTO}}", g["evento"]).replace("{{PARCEIRO}}", parceiro))
    print(destino, "→ evento", g["evento"])
