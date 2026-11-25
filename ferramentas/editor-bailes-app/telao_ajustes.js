// ---------- tamanhos + pré-visualização ----------
var PADRAO_ESC = { logo: 0.65, texto: 0.85, qr: 1, painel: 1.16, marca: 0.75, num: 1.8 }; // padrão escolhido pela Aresta (25/11/2026)
var ESC = Object.assign({}, PADRAO_ESC, ler("telao-escalas", {}));
function aplicarEscalas() { if (!ESC) return; const t = $("#telao"); for (const k in ESC) t.style.setProperty(`--k-${k}`, ESC[k]); }
function marcarEscalas() {
  document.querySelectorAll("[data-esc]").forEach((i) => { i.value = ESC[i.dataset.esc]; i.nextElementSibling.value = Math.round(ESC[i.dataset.esc] * 100) + "%"; });
}
document.querySelectorAll("[data-esc]").forEach((i) => i.addEventListener("input", () => {
  ESC[i.dataset.esc] = Number(i.value); i.nextElementSibling.value = Math.round(i.value * 100) + "%"; guardar("telao-escalas", ESC); aplicarEscalas();
}));
$("#cEscPadrao").onclick = () => { ESC = Object.assign({}, PADRAO_ESC); guardar("telao-escalas", ESC); marcarEscalas(); aplicarEscalas(); };
marcarEscalas();
const PREVIA = new URLSearchParams(location.search).has("previa");
function estadoPrevia() {
  return { baile: baileNome(), link: $("#cLink").value, preco: $("#cPreco").value, cheio: $("#cCheio").value, oferta: $("#cOferta").value,
    formato: FORMATO, lado: LADO, comOferta: COM_OFERTA, esc: ESC, fonte: FONTE, parceiro: TEM_PARCEIRO, fora: [...FORA] };
}
let ultimoEstado = "", ultimoTam = "";
function sincronizarPrevia() {
  const f = $("#prev"); if (!f || !baileNome()) return;
  const caixa = $("#prevCaixa"), vert = FORMATO === "vertical";
  caixa.classList.toggle("vert", vert);
  const W = caixa.clientWidth, H = caixa.clientHeight;
  // o iframe desenha a tela do Mac (1280x720); na TV em pé, gira de volta para ficar como quem olha a TV
  const esc = vert ? Math.min(W / 720, H / 1280) : Math.min(W / 1280, H / 720);
  const giro = vert ? (LADO === "dir" ? -90 : 90) : 0;
  const tam = `translate(-50%,-50%) rotate(${giro}deg) scale(${esc})`;
  if (tam !== ultimoTam) { f.style.transform = tam; ultimoTam = tam; }
  $("#prevNota").textContent = vert ? "TV em pé, como o público vê" : "TV deitada";
  if (!f.getAttribute("src")) { f.src = `/telao?previa=1&baile=${enc(baileNome())}`; ultimoEstado = ""; }
  const est = JSON.stringify(estadoPrevia());
  if (est === ultimoEstado) return;
  try { if (f.contentWindow && f.contentWindow.receberPrevia && f.contentWindow.receberPrevia(JSON.parse(est))) ultimoEstado = est; } catch {}
}
if (!PREVIA) setInterval(() => { if (!$("#config").hidden) sincronizarPrevia(); }, 400);
$("#cEv").addEventListener("change", () => { const f = $("#prev"); if (f) { f.removeAttribute("src"); ultimoEstado = ""; } });
// dentro do iframe: recebe o estado da configuração e redesenha (devolve true quando aplicou)
window.receberPrevia = (d) => {
  if (!PREVIA || !DADOS || d.baile !== baileNome()) return false;
  $("#cLink").value = d.link; $("#cPreco").value = d.preco; $("#cCheio").value = d.cheio; $("#cOferta").value = d.oferta;
  FORMATO = d.formato; LADO = d.lado; COM_OFERTA = d.comOferta; ESC = d.esc; FORA = new Set(d.fora);
  if (FONTE !== d.fonte) { FONTE = d.fonte; montarFila(); }
  if (d.parceiro !== TEM_PARCEIRO) verParceiro();
  montarPainel(); aplicarEscalas();
  if (tocaveis().length && ATUAL < 0) proximo(1);
  return true;
};
