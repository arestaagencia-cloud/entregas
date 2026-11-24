#!/bin/bash
# Cria a pasta de um baile com as 3 subpastas: 1. Brutos (cartão da câmera; o telão e o editor leem daqui),
# 2. Prévias e 3. Finais (o editor exporta aqui). Opcional: liga a cópia automática para o Google Drive.
AQUI="$(cd "$(dirname "$0")" && pwd)"; source "$AQUI/config.txt"
nome=$(osascript -e "text returned of (display dialog \"Nome do baile (data + nome, ex.: 2026-11-28 I Dá-lhe Samba)\" default answer \"$(date +%Y-%m-%d) \" with title \"Criar pasta do baile\")" 2>/dev/null) || exit 0
nome="$(echo "$nome" | tr '/:' '--' | sed 's/^ *//; s/ *$//')"
[ -z "$nome" ] && exit 0
B="$PASTA_BAILES/$nome"
mkdir -p "$B/1. Brutos" "$B/2. Prévias" "$B/3. Finais"
r=$(osascript -e 'button returned of (display dialog "Copiar as prévias e os finais automaticamente para a pasta do baile no Google Drive?\n\n(Precisa do Google Drive para computador instalado. Escolha a pasta do baile no Drive: as subpastas Prévias e Finais são criadas sozinhas.)" buttons {"Agora não", "Escolher pasta no Drive"} default button 2 with title "Google Drive")' 2>/dev/null)
if [ "$r" = "Escolher pasta no Drive" ]; then
  d=$(osascript -e 'POSIX path of (choose folder with prompt "Pasta do baile no Google Drive")' 2>/dev/null) && echo "${d%/}" > "$B/.destino-drive"
fi
open "$B"
echo "Pasta criada: $B"
