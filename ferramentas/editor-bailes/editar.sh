#!/bin/bash
# Editor de Bailes · ArestAgência
# Gera, para cada vídeo bruto (um arquivo por casal, Sony A7IV 4K vertical):
#   3. Finais/F. NN.mp4   1080x1920, logos embaixo durante todo o vídeo (alta qualidade)
#   2. Prévias/P. NN.mp4  720x1280, mesmas logos + PNG "prévia" a 35% entrando no segundo 5 (fade de 1,5 s)
# A numeração segue a ordem dos arquivos em "1. Brutos" (a mesma do telão) e fica guardada em numeracao.csv:
# um vídeo novo nunca muda o número dos que já existem.
# Uso: ./editar.sh "/caminho/da/pasta do baile"   (ou dê dois cliques em "Editar baile.command")

set -u
AQUI="$(cd "$(dirname "$0")" && pwd)"
REC="$AQUI/recursos"
source "$AQUI/config.txt"

BAILE="${1:-}"
if [ -z "$BAILE" ] || [ ! -d "$BAILE" ]; then echo "Pasta do baile não encontrada: $BAILE"; exit 1; fi
BAILE="$(cd "$BAILE" && pwd)"
BRUTOS="$BAILE/1. Brutos"; PREVIAS="$BAILE/2. Prévias"; FINAIS="$BAILE/3. Finais"; NUMS="$BAILE/numeracao.csv"
if [ ! -d "$BRUTOS" ]; then echo "Não achei a pasta \"1. Brutos\" dentro de $BAILE"; exit 1; fi
mkdir -p "$PREVIAS" "$FINAIS"

FFMPEG="$(command -v ffmpeg || true)"; FFPROBE="$(command -v ffprobe || true)"
for c in /opt/homebrew/bin /usr/local/bin; do
  [ -z "$FFMPEG" ] && [ -x "$c/ffmpeg" ] && FFMPEG="$c/ffmpeg"
  [ -z "$FFPROBE" ] && [ -x "$c/ffprobe" ] && FFPROBE="$c/ffprobe"
done
if [ -z "$FFMPEG" ] || [ -z "$FFPROBE" ]; then
  echo "O FFmpeg não está instalado. Abra o Terminal e rode:  brew install ffmpeg   (veja o LEIA-ME)"; exit 1
fi

# Codificador: o do próprio Mac (rápido) quando existe; senão o x264.
if "$FFMPEG" -hide_banner -encoders 2>/dev/null | grep -q h264_videotoolbox; then
  ENC_FINAL=(-c:v h264_videotoolbox -b:v 16M -maxrate 22M -profile:v high)
  ENC_PREVIA=(-c:v h264_videotoolbox -b:v 3M -maxrate 4M -profile:v high)
else
  ENC_FINAL=(-c:v libx264 -preset veryfast -crf 18 -profile:v high)
  ENC_PREVIA=(-c:v libx264 -preset veryfast -crf 26 -profile:v high)
fi

# ---------- numeração ----------
touch "$NUMS"
maior=$(awk -F';' 'BEGIN{m=0} $1+0>m{m=$1+0} END{print m}' "$NUMS")
novos=0
while IFS= read -r arq; do
  nome="$(basename "$arq")"
  if ! awk -F';' -v n="$nome" '$2==n{f=1} END{exit !f}' "$NUMS"; then
    maior=$((maior+1)); echo "$maior;$nome" >> "$NUMS"; novos=$((novos+1))
  fi
done < <(find "$BRUTOS" -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' \) ! -name '._*' | sort)
total=$(grep -c ';' "$NUMS" || true)
echo "Baile: $(basename "$BAILE")"
echo "Vídeos brutos: $total ($novos novos na numeração)"

# ---------- filtros ----------
# girar: os vídeos verticais da A7IV podem vir "deitados" (sem a marcação de rotação). Se o quadro sair na
# horizontal, gira conforme GIRAR_HORIZONTAIS do config.txt (direita | esquerda | nao).
giro() {
  local w h r
  w=$("$FFPROBE" -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$1")
  h=$("$FFPROBE" -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$1")
  r=$("$FFPROBE" -v error -select_streams v:0 -show_entries stream_side_data=rotation -of csv=p=0 "$1" | head -n1 | tr -d ' -')
  if [ "${r:-0}" = "90" ] || [ "${r:-0}" = "270" ]; then local t=$w; w=$h; h=$t; fi   # o FFmpeg já gira sozinho
  if [ "${w:-0}" -gt "${h:-0}" ]; then
    case "$GIRAR_HORIZONTAIS" in direita) echo "transpose=1,";; esquerda) echo "transpose=2,";; *) echo "";; esac
  fi
}
# logos: largura proporcional ao quadro; margem de baixo de 4% da altura
filtro() { # $1=W $2=H $3=giro $4=com_previa(0/1)
  local W=$1 H=$2 lw=$(( $1 * LOGO_LARGURA_PCT / 100 )) mb=$(( $2 * 3 / 100 ))
  local f="[0:v]${3}scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2,setsar=1[v];"
  f+="[1:v]scale=${lw}:-1,format=rgba,colorchannelmixer=aa=${LOGO_OPACIDADE}[l];"
  f+="[v][l]overlay=(W-w)/2:H-h-${mb}[a]"
  if [ "$4" = "1" ]; then
    f+=";[2:v]scale=${W}:${H},format=rgba,colorchannelmixer=aa=${PREVIA_OPACIDADE},fade=t=in:st=${PREVIA_INICIO}:d=${PREVIA_FADE}:alpha=1[p];"
    f+="[a][p]overlay=0:0:shortest=1,format=yuv420p[o]"
  else
    f+=";[a]format=yuv420p[o]"
  fi
  echo "$f"
}

# ---------- render ----------
feitos=0; pulados=0; erros=0; i=0
while IFS=';' read -r num nome; do
  [ -z "$num" ] && continue
  i=$((i+1))
  bruto="$BRUTOS/$nome"; NN=$(printf '%02d' "$num")
  if [ ! -f "$bruto" ]; then echo "  [$NN] $nome não está mais em 1. Brutos (pulando)"; continue; fi
  F="$FINAIS/F. $NN.mp4"; P="$PREVIAS/P. $NN.mp4"
  if [ -s "$F" ] && [ -s "$P" ]; then pulados=$((pulados+1)); continue; fi
  g="$(giro "$bruto")"
  echo "  [$NN/$total] $nome"
  if [ ! -s "$F" ]; then
    printf '        final 1080x1920 ... '
    if "$FFMPEG" -nostdin -hide_banner -loglevel error -y -i "$bruto" -i "$REC/logos-baixo.png" \
        -filter_complex "$(filtro 1080 1920 "$g" 0)" -map "[o]" -map "0:a?" "${ENC_FINAL[@]}" \
        -c:a aac -b:a 192k -movflags +faststart "$FINAIS/.F. $NN.tmp.mp4"; then
      mv "$FINAIS/.F. $NN.tmp.mp4" "$F"; echo "ok"
    else echo "ERRO"; rm -f "$FINAIS/.F. $NN.tmp.mp4"; erros=$((erros+1)); continue; fi
  fi
  if [ ! -s "$P" ]; then
    printf '        prévia 720x1280 ... '
    if "$FFMPEG" -nostdin -hide_banner -loglevel error -y -i "$bruto" -i "$REC/logos-baixo.png" \
        -loop 1 -framerate 30 -i "$REC/previa.png" \
        -filter_complex "$(filtro 720 1280 "$g" 1)" -map "[o]" -map "0:a?" "${ENC_PREVIA[@]}" \
        -c:a aac -b:a 128k -movflags +faststart "$PREVIAS/.P. $NN.tmp.mp4"; then
      mv "$PREVIAS/.P. $NN.tmp.mp4" "$P"; echo "ok"
    else echo "ERRO"; rm -f "$PREVIAS/.P. $NN.tmp.mp4"; erros=$((erros+1)); continue; fi
  fi
  feitos=$((feitos+1))
done < <(sort -t';' -k1,1n "$NUMS")

# ---------- cópia para o Google Drive (opcional) ----------
copiados=0
if [ -f "$BAILE/.destino-drive" ]; then
  DEST="$(cat "$BAILE/.destino-drive")"
  if [ -d "$DEST" ]; then
    DP="$DEST/Prévias"; DF="$DEST/Finais"; mkdir -p "$DP" "$DF"
    for f in "$PREVIAS"/P.\ *.mp4; do [ -f "$f" ] || continue; [ -s "$DP/$(basename "$f")" ] || { cp "$f" "$DP/"; copiados=$((copiados+1)); }; done
    for f in "$FINAIS"/F.\ *.mp4;  do [ -f "$f" ] || continue; [ -s "$DF/$(basename "$f")" ] || { cp "$f" "$DF/"; copiados=$((copiados+1)); }; done
  else
    echo "A pasta do Drive guardada não existe mais: $DEST"
  fi
fi

echo ""
echo "Pronto: $feitos editados agora, $pulados já estavam prontos, $erros com erro, $copiados arquivos copiados para o Drive."
[ "$erros" -gt 0 ] && exit 2
exit 0
