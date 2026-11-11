# Procedimento: páginas de entrega ArestAgência

Este repositório publica as páginas de entrega de vídeos e fotos dos clientes em
`https://entregas.arestagencia.com.br/<slug>/` (GitHub Pages, pasta `docs/`, branch `main`).

## Onde as coisas ficam

| O quê | Onde |
|---|---|
| Painel de pedidos (fila) | Artifact `205ea829-f10d-4dc7-ae2a-ebba998d5c2f`, coleção `pedidos` (ferramentas db_query / db_get / db_write) |
| Entregas no Notion | Database "Serviços", data source `collection://2f074a51-c09f-807d-8047-000b2020bb69` |
| Campos do Notion | `Entrega` (status: Não iniciada → Pronta para Entrega → **Página no Ar**) e `Link da Entrega` (url) |
| Arquivos | Google Drive da agência (conector Google Drive) |
| Código | `template.html` (layout único), `gerar.py` (gera `docs/<slug>/index.html`), `clientes/<slug>.json` (dados) |

## Como um pedido chega

1. **Pelo painel:** documento em `pedidos` com `status: "na_fila"`. Campos: `tipo` (`nova` | `atualizacao`),
   `notion_nome`, `notion_url`, `drive`, `obs`, `link` (em atualizações), `criado_em`.
2. **Pelo chat:** "Finalizamos a entrega de <mês> do cliente X, link Y". Nesse caso, crie você mesmo o
   documento em `pedidos` (para aparecer no painel) e siga o mesmo procedimento.

## Progresso no painel

Atualize o pedido com `db_write` (op `merge`, sempre com `ifVersion` da última leitura) a cada etapa:

| status | progresso | quando |
|---|---|---|
| `lendo_drive` | 25 | ao começar a ler a pasta |
| `gerando` | 50 | ao montar o JSON e rodar o gerador |
| `publicando` | 75 | ao fazer commit e push |
| `concluido` | 100 | página no ar e Notion atualizado; preencher `link`, `slug`, `mensagem` (resumo) |
| `atencao` | mantém | algo impede seguir; preencher `etapa` (onde parou) e `mensagem` (o que a equipe deve fazer) |

Sempre atualize `atualizado_em` (ISO, UTC).

## Passo a passo: nova entrega

1. **Ler a pasta do Drive** (`search_files` com `parentId = '<id da pasta>'`, paginando até o fim).
   - Vídeos: arquivos de vídeo soltos na pasta do cliente.
   - Fotos: arquivos de imagem dentro da subpasta `Fotos`.
   - Zip: arquivo `.zip` na pasta do cliente vira o botão "Baixar tudo" (`"zip": {"id", "bytes"}`).
   - Pasta sem vídeos e sem fotos → `atencao`: "A pasta está vazia. Confira se os arquivos estão na pasta certa."
   - Arquivos precisam estar como "Qualquer pessoa com o link" (`get_file_permissions` em um arquivo).
     Se não estiverem → `atencao` explicando como compartilhar.
2. **Mês de referência = nome das pastas no Drive**, nunca a data de criação dos arquivos.
   Ex.: arquivos dentro de `01. Janeiro` são da entrega de Janeiro, mesmo que criados em maio.
3. **Achar a página no Notion.** Use `notion_url` do pedido. Se vier vazio (pedido pelo chat), procure na
   data source pelo nome no padrão **`Cliente - Mês.AA`** (mês por extenso, ano com 2 dígitos), ex.:
   "Universa Digital - Janeiro.26", "Niso Engenharia - Novembro.26". Eventos com detalhe seguem
   `Cliente - Detalhe - Mês.AA` (ex.: "Sarau Convida - Magrão - Junho.26").
   "Universa" e "Universa Digital" são páginas diferentes. Mais de uma candidata ou nenhuma → `atencao`
   listando as opções. Nunca chute.
4. **Montar `clientes/<slug>.json`.** Slug = nome do cliente em minúsculas, sem acento, com hífens,
   + `-` + 4 caracteres aleatórios `[a-z0-9]` (ex.: `universa-n3p0`). Campos:
   `slug, cliente, projeto ("Entrega de <Mês>"), data ("<Mês> de <Ano>"), mes_referencia ("AAAA-MM"),
   pasta (link da pasta), capa (id da primeira foto, se houver), zip (ou null), videos[{id, arquivo, bytes}],
   fotos[{id, arquivo, bytes}]`. Fotos ordenadas pelo nome; vídeos na ordem do nome.
   O nome do cliente na página é o nome comercial curto (ex.: "Universa"), sem "Digital - Janeiro.2026".
5. **Gerar:** `python3 gerar.py clientes/<slug>.json`. Confira a lista de títulos que ele imprime.
6. **Publicar:** commit com mensagem curta em português e push para `main`
   (`git -c user.name="ArestAgência" -c user.email="aresta.agencia@gmail.com" commit ...`).
   Confirme o deploy: `gh api "repos/arestaagencia-cloud/entregas/actions/runs?per_page=1"` até
   `conclusion: success`.
7. **Notion:** `Entrega` = "Página no Ar" e `Link da Entrega` = `https://entregas.arestagencia.com.br/<slug>/`.
8. **Painel:** `concluido`, 100, `link`, `slug`, `mensagem` (ex.: "4 vídeos, 12 fotos e .zip de 1,6 GB").
9. **Responder** com o link pronto para enviar ao cliente.

## Passo a passo: atualização

1. Descubra o slug pelo `link` do pedido (ou pelo `Link da Entrega` no Notion). O slug **não muda**.
2. Releia a pasta (a de `drive`, se veio preenchida; senão a `pasta` do JSON existente).
3. Reescreva `videos`, `fotos`, `capa` e `zip` no mesmo `clientes/<slug>.json`, mantendo `slug`, `cliente`,
   `projeto`, `data` e `mes_referencia`.
4. Gere, publique e marque o pedido como `concluido`. O Notion já está com o link; só garanta "Página no Ar".

## Regras de layout (já no template, não mexer sem pedido)

- Tema escuro, logo no topo, mosaico de fotos + capas de vídeo na capa.
- Detecta sozinho: misto, só vídeos ou só fotos.
- "Fale com a gente" abre o WhatsApp (61) 99128-3546 com a mensagem pronta.
- Vídeos tocam pelo player do Drive (1080p) e baixam o original.

## Nunca

- Apagar páginas publicadas ou arquivos do Drive.
- Mudar o slug de uma entrega já publicada (o cliente já tem o link).
- Marcar "Página no Ar" sem confirmar que o deploy terminou com sucesso.
