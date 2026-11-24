"""Gera as páginas dos bailes.

Uso: python3 gerar_bailes.py
- docs/bailes/index.html          ← bailes_template.html  (Hub de Bailes, interno, login Google)
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

hub = (RAIZ / "bailes_template.html").read_text().replace("{{LOGO}}", logo)
DOCS.mkdir(parents=True, exist_ok=True)
(DOCS / "index.html").write_text(hub)
print(DOCS / "index.html")

modelo = (RAIZ / "galeria_template.html").read_text()
for g in json.loads((RAIZ / "bailes.json").read_text())["galerias"]:
    p = g.get("parceiro") or {}
    parceiro = ""
    if p.get("logo"):
        parceiro = (f'<span class="x" aria-hidden="true">×</span>'
                    f'<img class="parceiro" src="{html.escape(p["logo"])}" alt="{html.escape(p.get("nome", ""))}">')
    destino = DOCS / g["pasta"] / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(modelo.replace("{{EVENTO}}", g["evento"]).replace("{{PARCEIRO}}", parceiro))
    print(destino, "→ evento", g["evento"])
