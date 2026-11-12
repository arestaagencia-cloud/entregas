"""Gera o relatório mensal em PDF de um cliente.

Uso: python3 gerar_pdf.py relatorios/pedidos/<id>.json
Pedido: {id, cliente: "Vitrinni", mes: "2026-10", diarias: [{data, entrada, saida, local}], obs: "",
         painel: "universa"          -> cliente com dashboard: lê paineis/<painel>.json
         ou pastas: ["<id Drive>"]   -> cliente sem dashboard: lê direto as pastas da entrega
         periodo: "Segunda leva"     -> opcional; clientes por projeto podem vir sem "mes"}
Baixa as capas do Drive,
monta o HTML (relatorio_template.html) e imprime em PDF com o Chromium (playwright).
Saída: docs/relatorios/<arquivo>.pdf e o pedido atualizado com "pdf" (caminho) e "resumo".
"""
import base64, html, json, re, secrets, sys, unicodedata, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))
from gerar_painel import titulo  # noqa: E402

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
         "Outubro", "Novembro", "Dezembro"]
DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MAX_FOTOS = 20
SITE = "https://entregas.arestagencia.com.br"
esc = html.escape


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def thumb(fid, w):
    url = f"https://drive.google.com/thumbnail?id={fid}&sz=w{w}"
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read()
                tipo = r.headers.get_content_type()
            if tipo.startswith("image/") and len(data) > 500:
                return f"data:{tipo};base64,{base64.b64encode(data).decode()}"
        except Exception:  # noqa: BLE001
            pass
    return None


def minutos(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def dur(entrada, saida):
    d = minutos(saida) - minutos(entrada)
    return d + 24 * 60 if d < 0 else d  # passou da meia-noite


def fmt_dur(m):
    h, r = divmod(m, 60)
    return f"{h}h{r:02d}" if r else f"{h}h"


def qr_svg(texto):
    import qrcode, qrcode.image.svg
    img = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, border=0)
    svg = img.to_string(encoding="unicode")
    return re.sub(r"<\?xml[^>]*>", "", svg)


def main(caminho):
    ped_path = RAIZ / caminho
    ped = json.loads(ped_path.read_text())
    cli = ped["cliente"]
    mes = ped.get("mes")  # "AAAA-MM"; clientes por projeto podem vir sem mês, com "periodo"
    if mes:
        ano, m = mes.split("-")
        mes_txt = f"{MESES[int(m) - 1]} {ano}"
        chamada = f"em {MESES[int(m) - 1].lower()}"
    else:
        mes_txt = ped.get("periodo") or "Entrega"
        chamada = f"<br>{esc(mes_txt.lower())}" if ped.get("periodo") else "para você"
    if ped.get("periodo") and mes:
        mes_txt = f"{ped['periodo']} · {mes_txt}"
    painel = None
    if ped.get("painel"):  # cliente com dashboard: lê o que o robô mantém em paineis/<painel>.json
        painel = json.loads((RAIZ / "paineis" / f"{ped['painel']}.json").read_text())
        itens = [i for i in painel["itens"] if i["cliente"] == cli and i["mes"] == mes]
    else:  # cliente sem dashboard: lê direto a(s) pasta(s) da entrega no Drive
        from atualizar_painel import coletar
        itens = []
        for pasta in ped["pastas"]:
            coletar(pasta, cli, mes or "", itens)
    videos = sorted([i for i in itens if i["tipo"] == "video"], key=lambda i: titulo(i["nome"], cli).lower())
    fotos = sorted([i for i in itens if i["tipo"] == "foto"], key=lambda i: i["nome"])
    if not itens:
        raise SystemExit(f"Nenhum conteúdo de {cli} em {mes_txt}.")

    fotos_pdf = fotos[:MAX_FOTOS]
    pedidos_thumb = [(v["id"], 600) for v in videos] + [(f["id"], 500) for f in fotos_pdf]
    with ThreadPoolExecutor(8) as ex:
        imgs = dict(zip([p[0] for p in pedidos_thumb], ex.map(lambda p: thumb(*p), pedidos_thumb)))
    sem_capa = [i for i, v in imgs.items() if not v]

    logo = (RAIZ / "assets/logo-mark.b64").read_text().strip()
    brand = f'<div class="brand"><img src="data:image/png;base64,{logo}" alt=""><span>ARESTAGÊNCIA</span></div>'
    foot = lambda n: f'<div class="foot"><span>{esc(cli)} · {mes_txt}</span><span>{n}</span></div>'
    bg = lambda fid: f"background-image:url('{imgs[fid]}')" if imgs.get(fid) else ""
    link = lambda fid: f"https://drive.google.com/file/d/{fid}/view"  # abre direto no player do Drive
    paginas = []

    # capa
    mos_ids = ([v["id"] for v in videos] + [f["id"] for f in fotos_pdf])
    mos_ids = [i for i in mos_ids if imgs.get(i)] or [None]
    mos = "".join(f'<div style="{bg(mos_ids[k % len(mos_ids)]) if mos_ids[0] else ""}"></div>' for k in range(25))
    tam = 120 if len(cli) <= 9 else 96 if len(cli) <= 13 else 74
    paginas.append(f'''<section class="page cover"><div class="mos">{mos}</div><div class="in">{brand}
      <div><div class="eyebrow">Relatório de produção</div><h1>{esc(cli)}</h1>
      <h2>Tudo o que <em>criamos</em> {chamada}</h2></div></div></section>''')

    # resumo
    diarias = [d for d in ped.get("diarias", []) if d.get("entrada") and d.get("saida")]
    total = sum(dur(d["entrada"], d["saida"]) for d in diarias)
    nums = [(len(videos), "vídeos entregues" if len(videos) != 1 else "vídeo entregue", "gold"), (len(fotos), "fotos entregues" if len(fotos) != 1 else "foto entregue", "")]
    if diarias:
        nums += [(len(diarias), "diárias de captação" if len(diarias) > 1 else "diária de captação", ""),
                 (fmt_dur(total), "em captação", "")]
    nums = [x for x in nums if x[0] not in (0, "0h")]
    nums_html = "".join(f'<div class="num {c}"><b>{n}</b><span>{l}</span></div>' for n, l, c in nums)
    tabela = ""
    if diarias:
        linhas = ""
        for d in sorted(diarias, key=lambda d: (d.get("data") or "", d["entrada"])):
            dt = ""
            if d.get("data"):
                x = datetime.strptime(d["data"], "%Y-%m-%d")
                dt = f"{x:%d/%m} · {DIAS[x.weekday()]}"
            local = f' <span style="color:var(--muted)">· {esc(d["local"])}</span>' if d.get("local") else ""
            linhas += (f'<tr><td><b>{dt or "—"}</b>{local}</td><td>{d["entrada"]}</td><td>{d["saida"]}</td>'
                       f'<td><b>{fmt_dur(dur(d["entrada"], d["saida"]))}</b></td></tr>')
        linhas += f'<tr class="total"><td>Total</td><td></td><td></td><td>{fmt_dur(total)}</td></tr>'
        tabela = (f'<div class="kick">Captação</div><table><tr><th>Diária</th><th>Entrada</th><th>Saída</th>'
                  f'<th>Tempo</th></tr>{linhas}</table>')
    obs = f'<div class="kick">Observações</div><div class="obs">{esc(ped["obs"].strip())}</div>' if ped.get("obs", "").strip() else ""
    paginas.append(f'''<section class="page">{brand}<div class="kick">Resumo do mês</div>
      <div class="h">{mes_txt}</div><div class="nums">{nums_html}</div>{tabela}{obs}{{FOOT}}</section>''')

    # produção: vídeos (15 por página) e fotos (até 20)
    def bloco_videos(lote, primeiro):
        cab = (f'<div class="kick">Produção</div><div class="h">Vídeos <em>({len(videos)})</em></div>' if primeiro
               else '<div class="kick">Vídeos · continuação</div>')
        cards = "".join(f'<a class="it" href="{link(v["id"])}"><div class="th" style="{bg(v["id"])}"><i></i></div>'
                        f'<p>{esc(titulo(v["nome"], cli))}</p></a>' for v in lote)
        return f'<section class="page">{brand}{cab}<div class="grid v">{cards}</div>{{FOOT}}</section>'

    for k in range(0, len(videos), 15):
        paginas.append(bloco_videos(videos[k:k + 15], k == 0))
    if fotos_pdf:
        cards = "".join(f'<a class="it" href="{link(f["id"])}"><div class="th" style="{bg(f["id"])}"></div></a>' for f in fotos_pdf)
        resto = len(fotos) - len(fotos_pdf)
        mais = f'<div class="more">+ {resto} fotos no seu painel.</div>' if resto > 0 else ""
        paginas.append(f'''<section class="page">{brand}<div class="kick">Produção</div>
          <div class="h">Fotos <em>({len(fotos)})</em></div><div class="grid f">{cards}</div>{mais}{{FOOT}}</section>''')

    # final
    if painel:
        link = f"{SITE}/{painel['slug']}/" + (f"#cliente={cli}" if len(painel["clientes"]) > 1 else "")
        link = link.replace(" ", "%20")
        link_vis = link.replace("https://", "")
        kick, h, txt = ("Seu painel", "Tudo em <em>um só lugar</em>",
                        "Assista, filtre por mês e baixe todos os conteúdos que produzimos para você, sempre atualizados.")
    else:  # sem dashboard: o QR leva à pasta da entrega no Drive
        link = f"https://drive.google.com/drive/folders/{ped['pastas'][0]}"
        link_vis = "Pasta da entrega no Google Drive"
        kick, h, txt = ("Seus arquivos", "Tudo em <em>um só lugar</em>",
                        "Assista e baixe em alta qualidade todos os conteúdos desta entrega.")
    paginas.append(f'''<section class="page end">{brand}<div class="kick" style="margin-top:20mm">{kick}</div>
      <div class="h">{h}</div>
      <p>{txt}</p>
      <a href="{link}" class="qr">{qr_svg(link)}</a><div class="link"><a href="{link}" style="color:inherit;text-decoration:none">{esc(link_vis)}</a></div>
      <div class="contato">ArestAgência · (61) 99128-3546 · arestagencia.com.br</div></section>''')

    total_pag = len(paginas)
    paginas = [p.replace("{FOOT}", foot(f"{i + 1:02d} / {total_pag:02d}")) for i, p in enumerate(paginas)]
    doc = (RAIZ / "relatorio_template.html").read_text()
    doc = (doc.replace("{{TITLE}}", f"{cli} · {mes_txt} · ArestAgência").replace("{{TAM_MARCA}}", str(tam))
              .replace("{{PAGINAS}}", "\n".join(paginas)))

    nome = ped.get("arquivo") or f"{slugify(cli)}-{mes or slugify(mes_txt)}-{secrets.token_hex(2)}"
    saida = RAIZ / "docs" / "relatorios" / f"{nome}.pdf"
    saida.parent.mkdir(parents=True, exist_ok=True)
    tmp_html = RAIZ / "relatorios" / "tmp.html"
    tmp_html.parent.mkdir(parents=True, exist_ok=True)
    tmp_html.write_text(doc)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        import os
        exe = os.environ.get("CHROME_PATH")
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        pg = b.new_page()
        pg.goto(tmp_html.resolve().as_uri(), wait_until="networkidle")
        pg.wait_for_timeout(800)
        pg.pdf(path=str(saida), format="A4", print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        b.close()
    tmp_html.unlink()

    ped["arquivo"] = nome
    ped["pdf"] = f"docs/relatorios/{nome}.pdf"
    ped["link_pdf"] = f"{SITE}/relatorios/{nome}.pdf"
    ped["resumo"] = {"videos": len(videos), "fotos": len(fotos), "diarias": len(diarias), "minutos": total,
                     "paginas": total_pag, "sem_capa": len(sem_capa)}
    ped["gerado_em"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ped_path.write_text(json.dumps(ped, ensure_ascii=False, indent=1))
    print(f"PDF: {saida} — {len(videos)} vídeos, {len(fotos)} fotos, {len(diarias)} diárias, {total_pag} páginas,"
          f" {len(sem_capa)} sem capa")


if __name__ == "__main__":
    main(sys.argv[1])
