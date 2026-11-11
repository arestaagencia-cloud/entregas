# Entregas ArestAgência

Páginas de entrega de vídeos e fotos para clientes, publicadas em `entregas.arestagencia.com.br`.

## Como funciona

- `template.html`: layout único. Se adapta sozinho a entregas mistas, só de vídeos ou só de fotos.
- `clientes/<slug>.json`: dados de cada entrega (nome do cliente, pasta do Drive, vídeos, fotos e o .zip).
- `gerar.py`: monta a página do cliente em `docs/<slug>/index.html`.
- `docs/`: o que vai ao ar pelo GitHub Pages.

Gerar uma página:

```
python3 gerar.py clientes/universa-n3p0.json
```

## Regras da pasta no Drive

- Vídeos soltos na pasta do cliente
- Fotos dentro de uma subpasta chamada `Fotos`
- O `.zip` da entrega final na pasta do cliente (vira o botão "Baixar tudo")
- A pasta precisa estar compartilhada como "Qualquer pessoa com o link"
