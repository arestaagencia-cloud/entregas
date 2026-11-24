#!/bin/bash
# Escolha a pasta do baile: o editor gera as prévias e os finais de todos os vídeos de "1. Brutos" que ainda não
# foram editados. Pode rodar quantas vezes quiser durante e depois do baile: só faz o que falta.
AQUI="$(cd "$(dirname "$0")" && pwd)"; source "$AQUI/config.txt"
mkdir -p "$PASTA_BAILES"
B=$(osascript -e "POSIX path of (choose folder with prompt \"Escolha a pasta do baile\" default location POSIX file \"$PASTA_BAILES\")" 2>/dev/null) || exit 0
caffeinate -i "$AQUI/editar.sh" "${B%/}"
st=$?
if [ $st -eq 0 ]; then osascript -e 'display notification "Prévias e finais prontos." with title "Editor de Bailes" sound name "Glass"'
else osascript -e 'display notification "Terminou com erro em algum vídeo. Veja a janela do Terminal." with title "Editor de Bailes" sound name "Basso"'; fi
echo ""; read -n 1 -s -r -p "Pressione qualquer tecla para fechar."
