
# ---- ajustes de tamanho (multiplicadores em variáveis CSS) + pré-visualização na configuração
GRUPOS = [
    ("logo",   [r"\.p-marca img\.ag", r"\.p-marca img\.parc", r"\.p-marca \.x"]),
    ("marca",  [r"\.marca-agua img\.ag", r"\.marca-agua img\.parc", r"\.marca-agua \.x"]),
    ("texto",  [r"\.p-baile", r"\.p-chamada \.k", r"\.p-chamada b", r"\.p-chamada \.sub", r"\.oferta \.k", r"\.oferta b",
                r"\.oferta p", r"\.qr b", r"\.qr p", r"\.prox"]),
    ("qr",     [r"\.qr \.q"]),
    ("num",    [r"\.num-video"]),
]
PROPS = ("height", "width", "max-width", "font-size")


def escalar(css):
    linhas = []
    for linha in css.split("\n"):
        m = re.match(r"^(\s*)([^{}]+)\{(.*)\}\s*$", linha)
        if m:
            sel = m.group(2).strip()
            for grupo, sels in GRUPOS:
                if not any(re.fullmatch(x, sel) for x in sels):
                    continue
                def troca_decl(d, grupo=grupo):
                    k, _, v = d.partition(":")
                    if k.strip() not in PROPS:
                        return d
                    return k + ":" + re.sub(r"(\d*\.?\d+)(cqw|cqh|cqmin)",
                                            lambda x: "calc(%s%s*var(--k-%s,1))" % (x.group(1), x.group(2), grupo), v)
                linha = "%s%s{%s}" % (m.group(1), m.group(2), ";".join(troca_decl(d) for d in m.group(3).split(";")))
                break
        linhas.append(linha)
    return "\n".join(linhas)


ini_css = s.index("/* ---------- telão ----------")
fim_css = s.index("</style>")
s = s[:ini_css] + escalar(s[ini_css:fim_css]) + s[fim_css:]
s = troca(s, "grid-template-columns:minmax(0,1fr) 38cqw;container:quadro / size}",
          "grid-template-columns:minmax(0,1fr) calc(38cqw*var(--k-painel,1));container:quadro / size}")
s = troca(s, ".telao.vid-h .quadro{grid-template-columns:minmax(0,1fr) 32cqw}",
          ".telao.vid-h .quadro{grid-template-columns:minmax(0,1fr) calc(32cqw*var(--k-painel,1))}")
s = troca(s, "gap:1.4cqw;margin:0;width:24cqw;align-self:start}", "gap:1.4cqw;margin:0;width:calc(24cqw*var(--k-qr,1));align-self:start}")
for g in ("logo", "marca", "texto", "qr", "num"):
    assert "var(--k-%s" % g in s, g

HTML_AJ_TXT = (AQUI_GER / "telao_ajustes.html").read_text()
CSS_AJ_TXT = (AQUI_GER / "telao_ajustes.css").read_text()
JS_AJ_TXT = (AQUI_GER / "telao_ajustes.js").read_text()
INICIO_TXT = (AQUI_GER / "telao_inicio.js").read_text().strip()
s = troca(s, '    <div class="fila"><table>', HTML_AJ_TXT + '\n    <div class="fila"><table>')
s = troca(s, '  td.st{color:var(--muted)', CSS_AJ_TXT + '\n  td.st{color:var(--muted)')
s = troca(s, '// ---------- reprodução ----------', JS_AJ_TXT + '\n// ---------- reprodução ----------')
s = troca(s, '''  t.classList.toggle("sem-oferta", !COM_OFERTA);
}''', '''  t.classList.toggle("sem-oferta", !COM_OFERTA);
  if (typeof aplicarEscalas === "function") aplicarEscalas();
}''')
s = troca(s, 'carregarBailes().catch((e) => aviso(e.message));', INICIO_TXT)
s = troca(s, 'function salvarBaile(aj) {', 'function salvarBaile(aj) {\n  if (new URLSearchParams(location.search).has("previa")) return;')
s = troca(s, '''document.addEventListener("keydown", (e) => {
  if ($("#telao").hidden) return;''', '''document.addEventListener("keydown", (e) => {
  if ($("#telao").hidden || document.body.classList.contains("modo-previa")) return;''')
