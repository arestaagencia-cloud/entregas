"""Gera o Hub de Bailes (docs/bailes/index.html) a partir de bailes_template.html.

Uso: python3 gerar_bailes.py
A página não leva dados: os números vêm ao vivo da função `painel-bailes` (Supabase, projeto
arestagencia-bailes), que só responde para quem entra com Google e tem acesso à "Chave do Hub".
"""
from pathlib import Path

RAIZ = Path(__file__).parent
html = (RAIZ / "bailes_template.html").read_text()
logo = (RAIZ / "assets/logo-mark.b64").read_text().strip()
destino = RAIZ / "docs" / "bailes" / "index.html"
destino.parent.mkdir(parents=True, exist_ok=True)
destino.write_text(html.replace("{{LOGO}}", logo))
print(destino)
