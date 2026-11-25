carregarBailes().then(() => {
  if (!PREVIA) return;
  // pré-visualização (dentro do iframe da configuração): mostra o telão direto, sem tela cheia
  document.body.classList.add("modo-previa");
  montarPainel(); aplicarEscalas();
  $("#config").hidden = true; $("#telao").hidden = false;
  pausado = false; ATUAL = -1;
  (function espera() { if (tocaveis().length) proximo(1); else setTimeout(espera, 2000); })();
}).catch((e) => aviso(e.message));
