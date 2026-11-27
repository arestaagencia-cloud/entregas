// ---------- iPad: tocar num vídeo troca o telão NA HORA; depois volta para a sequência normal ----------
// (sem fila: cada toque substitui o anterior). O iPad fala com este Mac pela rede local (/ipad).
let PED_ID = -1, ITEM_IPAD = null, VOLTAR_PARA = null;
const _proximoNormal = proximo;
proximo = function (passo) {
  ITEM_IPAD = null;
  if (VOLTAR_PARA !== null) { ATUAL = VOLTAR_PARA; VOLTAR_PARA = null; }   // volta para o vídeo que foi interrompido
  return _proximoNormal(passo);
};
async function lerPedidoIpad() {
  let d;
  try { const r = await fetch(`/api/controle/pedido?baile=${enc(baileNome())}`, { cache: "no-store" }); d = await r.json(); } catch { return; }
  if (PED_ID < 0) { PED_ID = d.id; return; }        // pedidos de antes de abrir o telão não contam
  if (d.id === PED_ID) return;
  PED_ID = d.id;
  if ($("#telao").hidden || Date.now() / 1000 - d.quando > 15) return;
  const L = tocaveis(), i = L.findIndex((x) => Number(x.num) === Number(d.num));
  if (i < 0) return;
  if (VOLTAR_PARA === null) VOLTAR_PARA = ATUAL - 1;  // proximo(1) volta exatamente para o interrompido
  if (pausado) { pausado = false; $("#tPausa").hidden = true; }
  ITEM_IPAD = L[i];
  tocar(L[i], L[(i + 1) % L.length]);
}
setInterval(lerPedidoIpad, 500);
