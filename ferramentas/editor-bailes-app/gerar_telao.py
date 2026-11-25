# Gera Resources/telao.html (telão dentro do app) a partir de bailes_telao_template.html do site.
import re, sys
from pathlib import Path
src = (Path(__file__).resolve().parents[2] / "bailes_telao_template.html").read_text()
out = Path(__file__).resolve().parent / "Editor de Bailes.app/Contents/Resources/telao.html"

def troca(s, a, b, n=1):
    assert s.count(a) >= 1, a[:80]
    return s.replace(a, b) if n == 0 else s.replace(a, b, n)

s = src
# ---- cabeçalho: sem internet (fontes do sistema), recursos locais
s = re.sub(r'<link rel="icon".*?\n', '<link rel="icon" href="/recursos/mark.png">\n', s, count=1)
s = re.sub(r'<link rel="preconnect".*?\n', '', s)
s = re.sub(r'<link href="https://fonts.googleapis.com.*?\n', '', s)
s = troca(s, '<script src="/bailes/qrcode.min.js"></script>', '<script src="/recursos/qrcode.min.js"></script>')
s = troca(s, '<title>Telão · Bailes ArestAgência</title>', '<title>Telão · Editor de Bailes</title>')
s = troca(s, '--sans:"Inter Tight","Helvetica Neue"', '--sans:-apple-system,BlinkMacSystemFont,"Inter Tight","Helvetica Neue"')
s = troca(s, '/bailes/logo-mark.png', '/recursos/mark.png')
s = s.replace('/bailes/logo-aresta-completa.png', '/recursos/aresta.png')
# vídeo final já tem as logos: sem marca d'água por cima
s = troca(s, '  .telao.sem-oferta .marca-agua{display:flex}', '  .telao.sem-oferta .marca-agua{display:flex}\n  .telao.ja-tem-logo .marca-agua{display:none}\n  .fonte .on{}\n  td.st{color:var(--muted);font-size:12px} td.st.ok{color:#57c47b} tr.fora td{opacity:.45}')

# ---- configuração: baile da pasta, link da galeria e preço salvos no baile, fonte dos vídeos
ini = s.index('<section class="config" id="config">'); fim = s.index('<!-- ========== telão ========== -->')
config = '''<section class="config" id="config">
  <div class="config-in">
    <div class="marca"><img src="/recursos/mark.png" alt=""><span>ARESTAGÊNCIA</span></div>
    <h1>Telão do <em>baile</em></h1>

    <div class="grade">
      <div class="caixa">
        <h2>Baile e oferta</h2>
        <p class="sub">Funciona sem internet. O QR leva para o "Me avise" da galeria (quem escaneia usa a internet do celular).</p>
        <label class="campo"><span>Baile</span><select id="cEv"></select></label>
        <label class="campo"><span>Link da galeria deste baile</span><input id="cLink" list="galerias" placeholder="https://entregas.arestagencia.com.br/bailes/..."></label>
        <datalist id="galerias"></datalist>
        <div class="campo"><span>Logo do parceiro (versão branca, PNG sem fundo)</span>
          <div style="display:flex;align-items:center;gap:12px;min-height:44px"><img id="cParcImg" alt="" style="height:44px;max-width:160px;object-fit:contain;display:none"><span id="cParcTxt" class="sub" style="margin:0">Sem logo do parceiro: o telão mostra só a ArestAgência.</span>
          <label class="btn sec" for="cParcArq" style="margin-left:auto">Escolher PNG</label><input type="file" id="cParcArq" accept="image/png" hidden></div></div>
        <div class="duas">
          <label class="campo"><span>Preço do código (R$)</span><input id="cPreco" inputmode="decimal" placeholder="35"></label>
          <label class="campo"><span>Segundos por vídeo</span><input id="cSeg" inputmode="numeric" value="20"></label>
        </div>
        <label class="campo"><span>Preço "de" riscado na oferta (R$, opcional)</span><input id="cCheio" inputmode="decimal" placeholder="ex.: 5"></label>
        <label class="campo"><span>Frase da oferta</span><input id="cOferta" maxlength="80" value="Fale com a nossa equipe e garanta o seu código"></label>
        <div class="campo"><span>Formato do telão</span><div class="formato" id="cFormato"><button type="button" data-f="horizontal" class="on">TV deitada</button><button type="button" data-f="vertical">TV em pé</button></div>
          <div class="formato lado" id="cLado"><button type="button" data-l="esq">TV girada para a esquerda ↺</button><button type="button" data-l="dir">TV girada para a direita ↻</button></div>
          <div class="formato" id="cComOferta" style="margin-top:8px"><button type="button" data-o="1" class="on">Com oferta e QR</button><button type="button" data-o="0">Só vídeos (logos por cima)</button></div></div>
      </div>
      <div class="caixa">
        <h2>Vídeos</h2>
        <p class="sub">O telão lê a pasta 1. Brutos do baile sozinho: cada vídeo novo entra na fila em poucos segundos, com o mesmo número da edição.</p>
        <div class="campo"><span>O que passa no telão</span>
          <div class="formato fonte" id="cFonte"><button type="button" data-fonte="brutos" class="on">Todos os brutos, assim que chegam</button><button type="button" data-fonte="prontos">Só os já editados</button></div></div>
        <p class="sub" id="cResumo" style="margin-top:10px"></p>
        <button class="btn ouro" type="button" id="cIniciarTopo" disabled style="width:100%;margin-top:14px;padding:14px 18px;font-size:15px">Iniciar telão em tela cheia</button>
      </div>
    </div>

    <div class="fila"><table><thead><tr><th>Nº</th><th>Arquivo</th><th>Duração</th><th>Situação</th><th></th></tr></thead><tbody id="cFila"></tbody></table></div>

    <div class="dicas">
      <b>No telão:</b> <kbd>espaço</kbd> pausa · <kbd>←</kbd> <kbd>→</kbd> vídeo anterior / próximo · <kbd>F</kbd> tela cheia · <kbd>R</kbd> inverte o giro da TV em pé · <kbd>O</kbd> liga/desliga a oferta · <kbd>S</kbd> volta para esta tela (o telão continua de onde parou).
      <br>Arraste esta janela para a TV antes de iniciar.
    </div>
  </div>
</section>

'''
s = s[:ini] + config + s[fim:]

# ---- script: troca a parte de bailes/fila (Supabase + arquivos escolhidos) pela leitura da pasta do baile
ini = s.index('// Telão do baile: toca vídeos locais')
fim = s.index('let FORMATO = ler("telao-formato", "horizontal");')
js = r'''// Telão do baile dentro do Editor de Bailes: lê a pasta do baile pelo editor (127.0.0.1), sem internet.
// A numeração é a mesma da edição (numeracao.csv): o Nº 07 do telão é o F. 07 / P. 07.
const GALERIAS = {{GALERIAS}};

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
const reais = (c) => (c / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: c % 100 ? 2 : 0 });
const dois = (n) => String(n).padStart(2, "0");
const mmss = (s) => s ? `${Math.floor(s / 60)}:${dois(Math.round(s % 60))}` : "";
const enc = encodeURIComponent;
const guardar = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };
const ler = (k, d) => { try { return JSON.parse(localStorage.getItem(k) || "null") ?? d; } catch { return d; } };
function aviso(t) { const el = $("#toast"); el.textContent = t; el.style.display = "block"; clearTimeout(aviso.t); aviso.t = setTimeout(() => (el.style.display = "none"), 2600); }
async function api(caminho, corpo) {
  const op = corpo === undefined ? {} : { method: "POST", headers: { "X-Editor": "1", "Content-Type": "application/json" }, body: JSON.stringify(corpo) };
  const r = await fetch(caminho, op); const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.erro || "Erro"); return d;
}

// ---------- bailes (pastas do editor) ----------
let BAILES = [], DADOS = null, TEM_PARCEIRO = false;
$("#galerias").innerHTML = GALERIAS.map((g) => `<option value="${esc(g.url)}">${esc(g.nome)}</option>`).join("");
async function carregarBailes() {
  const d = await api("/api/inicio");
  BAILES = d.bailes;
  const sel = $("#cEv"), pedido = new URLSearchParams(location.search).get("baile");
  sel.innerHTML = BAILES.map((b) => `<option>${esc(b)}</option>`).join("") || `<option value="">Nenhum baile na pasta</option>`;
  if (pedido && BAILES.includes(pedido)) sel.value = pedido; else if (d.baile_atual) sel.value = d.baile_atual;
  await aoTrocarBaile();
}
const baileNome = () => $("#cEv").value;
const nomeExibido = () => baileNome().replace(/^\d{4}-\d{2}-\d{2}\s*-?\s*/, "");
async function aoTrocarBaile() {
  if (!baileNome()) return;
  await lerBaile();
  const a = DADOS.ajustes;
  // link e preço guardados no baile; na primeira vez, tenta achar a galeria pelo nome do baile
  let link = a.url_galeria || "", preco = a.preco_codigo || 0, cheio = a.preco_cheio || 0;
  if (!link) {
    const n = nomeExibido().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]/g, "");
    const g = GALERIAS.find((g) => n.includes(g.chave) || g.chave.includes(n));
    if (g) { link = g.url; if (!preco) preco = g.preco; if (!cheio) cheio = g.cheio || 0; salvarBaile({ url_galeria: link, preco_codigo: preco, preco_cheio: cheio }); }
  }
  $("#cLink").value = link;
  $("#cPreco").value = preco ? (preco / 100).toLocaleString("pt-BR") : "";
  $("#cCheio").value = cheio ? (cheio / 100).toLocaleString("pt-BR") : "";
  FONTE = a.telao_fonte || "brutos"; marcarFonte();
  const of = ler("telao-oferta", null); if (of) $("#cOferta").value = of;
  const sg = ler("telao-seg", null); if (sg) $("#cSeg").value = sg;
  FORA = new Set(ler(`telao-fora-${baileNome()}`, []));
  verParceiro();
  montarFila();
}
function verParceiro() {
  const src = `/api/imagem?baile=${enc(baileNome())}&tipo=parceiro&v=${Date.now()}`, im = new Image();
  im.onload = () => { TEM_PARCEIRO = true; $("#cParcImg").src = src; $("#cParcImg").style.display = ""; $("#cParcTxt").style.display = "none"; };
  im.onerror = () => { TEM_PARCEIRO = false; $("#cParcImg").style.display = "none"; $("#cParcTxt").style.display = ""; };
  im.src = src;
}
$("#cParcArq").addEventListener("change", (e) => {
  const f = e.target.files[0]; e.target.value = ""; if (!f) return;
  const fr = new FileReader();
  fr.onload = async () => { try { await api("/api/upload-json", { baile: baileNome(), tipo: "parceiro", dados: String(fr.result).split(",")[1] }); verParceiro(); aviso("Logo do parceiro salvo."); } catch (er) { aviso(er.message); } };
  fr.readAsDataURL(f);
});
async function lerBaile() { DADOS = await api(`/api/baile?nome=${enc(baileNome())}`); }
function salvarBaile(aj) { api("/api/ajustes", { baile: baileNome(), ajustes: aj }).catch((e) => aviso(e.message)); }
$("#cEv").addEventListener("change", () => { FILA = []; ATUAL = -1; aoTrocarBaile(); });
$("#cLink").addEventListener("change", () => salvarBaile({ url_galeria: $("#cLink").value.trim() }));
$("#cCheio").addEventListener("change", () => { const c = Math.round(Number(String($("#cCheio").value).replace(/\./g, "").replace(",", ".")) * 100); salvarBaile({ preco_cheio: c > 0 ? c : 0 }); });
$("#cPreco").addEventListener("change", () => { const c = Math.round(Number(String($("#cPreco").value).replace(/\./g, "").replace(",", ".")) * 100); salvarBaile({ preco_codigo: c > 0 ? c : 0 }); });

// ---------- fila: vem da pasta do baile ----------
let FILA = [];   // { nome, num, dur, h, url, pronto }
let FORA = new Set();
let FONTE = "brutos";
function marcarFonte() { $("#cFonte").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.fonte === FONTE)); }
$("#cFonte").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; FONTE = b.dataset.fonte; marcarFonte(); salvarBaile({ telao_fonte: FONTE }); montarFila(); });
function montarFila() {
  if (!DADOS) return;
  const novos = [];
  for (const b of DADOS.brutos) {
    if (FONTE === "prontos" && !b.final) continue;
    const pronto = FONTE === "prontos";
    const url = pronto ? `/api/video?baile=${enc(baileNome())}&num=${b.num}&tipo=final` : `/api/video?baile=${enc(baileNome())}&arquivo=${enc(b.arquivo)}`;
    const velho = FILA.find((x) => x.url === url);
    novos.push(velho || { nome: b.arquivo, num: b.num, dur: b.duracao, h: pronto ? false : b.deitado, url, pronto, ok: null });
  }
  const atual = tocaveis()[ATUAL];
  FILA = novos.sort((a, b) => a.num - b.num);
  if (atual) { const i = tocaveis().indexOf(atual); if (i >= 0) ATUAL = i; }
  desenharFila();
}
function desenharFila() {
  if (!DADOS) return;
  const prontos = DADOS.brutos.filter((b) => b.final).length;
  $("#cResumo").textContent = `${DADOS.brutos.length} vídeo${DADOS.brutos.length === 1 ? "" : "s"} na pasta · ${prontos} já editado${prontos === 1 ? "" : "s"}`;
  $("#cFila").innerHTML = FILA.length ? FILA.map((x, i) => `<tr class="${FORA.has(x.nome) ? "fora" : ""}">
      <td>${dois(x.num)}</td>
      <td>${esc(x.nome)}${x.ok === false ? ` <span class="ruim">· não tocou</span>` : ""}</td>
      <td>${mmss(x.dur)}</td>
      <td class="st ${x.pronto ? "ok" : ""}">${x.pronto ? "editado" : (DADOS.brutos.find((b) => b.arquivo === x.nome) || {}).final ? "bruto · já editado" : "bruto"}</td>
      <td><button class="x" type="button" data-tirar="${i}">${FORA.has(x.nome) ? "voltar" : "tirar"}</button></td></tr>`).join("")
    : `<tr><td colspan="5" class="vazio">${FONTE === "prontos" ? "Nenhum vídeo editado ainda." : "Nenhum vídeo em 1. Brutos ainda. Copie os arquivos do cartão para essa pasta."}</td></tr>`;
  $("#cIniciarTopo").disabled = !tocaveis().length;
}
$("#cFila").addEventListener("click", (e) => {
  const i = e.target.dataset.tirar; if (i == null) return;
  const n = FILA[i].nome; FORA.has(n) ? FORA.delete(n) : FORA.add(n);
  guardar(`telao-fora-${baileNome()}`, [...FORA]); desenharFila();
});
// vídeos novos entram sozinhos (a cada 5 s)
setInterval(async () => { if (!baileNome()) return; try { await lerBaile(); montarFila(); } catch {} }, 5000);
'''
s = s[:ini] + js + s[fim:]

# ---- reprodução: lista tocável respeita "tirar"; painel com logo do parceiro do baile
s = troca(s, 'const tocaveis = () => FILA.filter((x) => x.ok !== false);', 'const tocaveis = () => FILA.filter((x) => x.ok !== false && !FORA.has(x.nome));')
ini = s.index('function montarPainel() {'); fim = s.index('async function iniciar() {')
s = s[:ini] + r'''function montarPainel() {
  const parc = TEM_PARCEIRO ? `<span class="x">×</span><img class="parc" src="/api/imagem?baile=${enc(baileNome())}&tipo=parceiro" alt="">` : "";
  $("#tMarca").innerHTML = `<img class="ag" src="/recursos/aresta.png" alt="ArestAgência">${parc}`;
  $("#tMarcaAgua").innerHTML = `<img class="ag" src="/recursos/aresta.png" alt="">${parc}`;
  aplicarModo();
  $("#tBaile").textContent = nomeExibido();
  const c = Math.round(Number(String($("#cPreco").value).replace(/\./g, "").replace(",", ".")) * 100);
  $("#tPreco").textContent = c > 0 ? reais(c) : "";
  const ch = Math.round(Number(String($("#cCheio").value).replace(/\./g, "").replace(",", ".")) * 100) || 0;
  $("#tDe").innerHTML = ch > c && c > 0 ? `de <s>${reais(ch)}</s> ` : "";
  $("#tOferta").textContent = $("#cOferta").value;
  QR_ATUAL = "";
  if (ITEM_ATUAL) situacao(ITEM_ATUAL);
  else { try { const q = qrcode(0, "M"); q.addData(`${baseGaleria()}/avise/`); q.make(); $("#tQR").innerHTML = q.createSvgTag({ cellSize: 4, margin: 0, scalable: true }); } catch {} }
  lerDisponiveis();
}

''' + s[fim:]
s = troca(s, 'const filtroEvento = () => { const e = baile(); return e ? `slug=eq.${encodeURIComponent(e.slug)}` : ""; };',
  'const filtroEvento = () => { const u = ($("#cLink").value || "").trim().replace(/\\/+$/, ""); return u ? `or=(url_galeria.eq.${encodeURIComponent(u)},url_galeria.eq.${encodeURIComponent(u + "/")})` : ""; };')
i0 = s.index("const baseGaleria = () => {"); i1 = s.index("\n", s.index("return String(e.url_galeria", i0))
s = s[:i0] + 'const baseGaleria = () => ($("#cLink").value.trim() || "https://entregas.arestagencia.com.br/bailes").replace(/\\/+$/, "");' + s[i1:]
s = troca(s, "    $(\"#telao\").classList.toggle(\"vid-h\", !!item.h);", "    $(\"#telao\").classList.toggle(\"vid-h\", !!item.h);\n    $(\"#telao\").classList.toggle(\"ja-tem-logo\", !!item.pronto);")
s = troca(s, 'carregarBailes().then(desenharFila);', 'carregarBailes().catch((e) => aviso(e.message));')
import json, unicodedata
AQUI_GER = Path(__file__).resolve().parent
exec((AQUI_GER / "telao_ajustes.py").read_text())
def chave(n): return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFD", n.lower()).encode("ascii", "ignore").decode())
GAL = [{"nome": "I Dá-lhe Samba", "chave": chave("I Dá-lhe Samba"), "url": "https://entregas.arestagencia.com.br/bailes/idalhesamba", "preco": 3500},
       {"nome": "Baile Teste - Aula de Samba Planet", "chave": chave("Aula de Samba Planet"), "url": "https://entregas.arestagencia.com.br/bailes/planet-teste", "preco": 200, "cheio": 500}]
assert "{{GALERIAS}}" in s
s = s.replace("{{GALERIAS}}", json.dumps(GAL, ensure_ascii=False))
# com internet, acrescenta bailes novos cadastrados no site (guardados para usar offline depois)
s = troca(s, '$("#galerias").innerHTML = GALERIAS.map(', """try { for (const g of JSON.parse(localStorage.getItem("telao-galerias") || "[]")) if (!GALERIAS.some((x) => x.url === g.url)) GALERIAS.push(g); } catch {}
fetch("https://jlogxdjttufiiikiezfe.supabase.co/rest/v1/eventos?select=nome,url_galeria,preco_codigo_centavos,preco_cheio_centavos&url_galeria=not.is.null",
  { headers: { apikey: "sb_publishable_ilWt8PPFiHuOBCmiCcsZ3A_CTmqyjmR" } }).then((r) => r.ok ? r.json() : []).then((ev) => {
  const lista = ev.map((e) => ({ nome: e.nome, chave: e.nome.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]/g, ""), url: e.url_galeria, preco: e.preco_codigo_centavos || 0, cheio: e.preco_cheio_centavos || 0 }));
  guardar("telao-galerias", lista);
  for (const g of lista) if (!GALERIAS.some((x) => x.url === g.url)) GALERIAS.push(g);
  $("#galerias").innerHTML = GALERIAS.map((g) => `<option value="${esc(g.url)}">${esc(g.nome)}</option>`).join("");
}).catch(() => {});
$("#galerias").innerHTML = GALERIAS.map(""")
out.write_text(s)
print("ok", len(s))
