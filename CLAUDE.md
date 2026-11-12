# Procedimento: ArestAgência · dashboards e relatórios mensais

> **Fluxo atual (nov/2026):** cada cliente tem um **dashboard** fixo atualizado pelo robô (seção "Dashboards")
> e, no fim do mês, recebe um **PDF** gerado manualmente no chat (seção "Relatórios mensais em PDF").
> As páginas mensais de entrega (seções seguintes) são o fluxo antigo: as já publicadas continuam no ar,
> mas não se criam novas, e o painel de pedidos/tarefa agendada não são mais usados.

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
   Ex.: arquivos dentro de `01. Universa - Janeiro.26` são da entrega de Janeiro/2026, mesmo que criados em maio.
   Estrutura do Drive (espelho do Notion, desde nov/2026):
   `1. Clientes Ativos / NN. Cliente / 01. Entregas / MM. Cliente - Mês.AA`
   (eventos do Sarau: `MM. Sarau Convida - Detalhe - Mês.AA`, ou subpastas de evento dentro do mês).
   O nome da pasta do mês, sem o prefixo `MM. `, é exatamente o nome da página no Notion.
   Pastas antigas no formato `01. Janeiro` ainda valem: leia o mês do nome e o ano da pasta-mãe/contexto.
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

## Dashboards de clientes (atualização automática)

Cada cliente tem um dashboard fixo em `https://entregas.arestagencia.com.br/<cliente>/` com todos os vídeos e
fotos do Drive, filtros por Cliente, Mês e tipo. Config em `paineis/<cliente>.json`:
`slug` (ex.: `universa`), `titulo`, `marca` (nome grande da capa), `drive_raiz` (id da pasta raiz no Drive),
`cliente_unico` (opcional: use quando a raiz já contém as pastas de mês, sem subpastas de marca),
`clientes` (ordem dos filtros) e `itens` (preenchido pelo robô).

Estrutura esperada no Drive: `raiz / [NN. ]Marca / N. Marca - Mês.AA / arquivos` (subpastas como `Fotos`
são lidas). **Carrosséis:** uma subpasta cujo nome começa com "Carrossel" vira UM item `tipo: "carrossel"` com
`slides` (fotos e/ou vídeos) na ordem natural do nome dos arquivos (1, 2, … 10). No dashboard abre um player
deslizante (arrastar/setas, baixar slide atual) e há o filtro "Carrosséis"; no PDF ganha seção própria. Pastas de mês fora do padrão são ignoradas e aparecem como AVISO no log.

**Robô:** `.github/workflows/atualizar-paineis.yml` roda de hora em hora (minuto 17) e também sob demanda
(REST: `gh api -X POST repos/arestaagencia-cloud/entregas/actions/workflows/atualizar-paineis.yml/dispatches -f ref=main -f 'inputs[forcar]=true'`). Ele executa `atualizar_painel.py` para cada `paineis/*.json` e só
faz commit se o Drive mudou. Lê o Drive pela API oficial se o segredo `GDRIVE_API_KEY` existir no repositório;
sem ele, usa a listagem pública das pastas (precisam estar como "qualquer pessoa com o link").

**Novo cliente:** criar `paineis/<cliente>.json` com slug, titulo, marca e drive_raiz, rodar
`python3 atualizar_painel.py paineis/<cliente>.json --forcar` (ou o workflow com "forcar"), conferir e publicar.

Dashboards no ar: `universa` (9 marcas, raiz = pasta Universa) `niso` (Niso Engenharia) e `faber` (Clínica Faber), os dois com
`cliente_unico` e raiz = pasta do cliente. Ao criar um novo, atualize também `relatorios/clientes.json` (campo `painel`).

Layout: `painel_template.html` + `gerar_painel.py`. Endereço antigo `/painel-universa-k7q2/` redireciona para `/universa/`.

## Relatórios mensais em PDF

Fluxo **manual**, feito no chat no fim de cada mês (sem robô nem fila). A equipe pede no chat, por exemplo:
"gera o PDF da Vitrinni de outubro, 2 diárias: 03/10 das 8h às 12h30 no Lago Sul, 17/10 das 14h às 17h45.
Obs: …". Se faltar cliente, mês ou as diárias, pergunte antes de gerar.

Vale para **todos os clientes da pasta "Clientes Ativos"** do Drive (`1Xr_yQthvOFYcNoVwMxeBOHLC5VrKoZH2`,
com "1. Clientes Recorrentes" e "2. Clientes Freelancers"). A lista com as pastas de cada um fica em
`relatorios/clientes.json`; se o cliente pedido não estiver lá, procure-o em Clientes Ativos e adicione.

1. Ache o cliente em `relatorios/clientes.json`:
   - com `painel` (ex.: clientes da Universa): o pedido leva `painel` e `mes`;
   - sem painel: ache no Drive (search_files com parentId) a pasta do mês dentro de `entregas`
     (padrão "N. Cliente - Mês.AA") e passe o ID em `pastas: [...]`. Clientes por projeto (sem meses, ex.:
     Tuiuti "Segunda Leva de Conteúdos"): passe a pasta do projeto em `pastas` e o nome em `periodo`
     (`mes` pode faltar). Se não ficar claro qual pasta usar, pergunte.
2. Escreva `relatorios/pedidos/<cliente-slug>-<AAAA-MM ou projeto>.json` com `id, cliente, mes/periodo,
   painel ou pastas, diarias[{data, entrada, saida, local}]` e `obs`. Commit + push.
3. O push dispara `.github/workflows/gerar-pdf.yml`: atualiza o painel com o Drive, baixa as capas e imprime
   o PDF (`gerar_pdf.py` + `relatorio_template.html`) em `docs/relatorios/<cliente>-<mes>-<4 hex>.pdf`.
   Acompanhe: `gh api "repos/arestaagencia-cloud/entregas/actions/workflows/gerar-pdf.yml/runs?per_page=1"`
   (API REST; GraphQL não funciona). No log, "PDF: …" = ok; "FALHOU" = mês sem conteúdo ou erro.
4. `git pull` e leia o pedido: agora tem `link_pdf`, `pdf` e `resumo`. Envie o arquivo no chat (SendUserFile)
   e o link `link_pdf`.

O PDF: capa (mosaico + cliente + mês), resumo (números, diárias, observações), vídeos (15 por página),
fotos (até 20, "+N no seu painel"), página final com QR code para o dashboard (ou, sem dashboard, para a pasta da entrega no Drive). Cada miniatura é um link
invisível que abre o arquivo no player do Drive (`/file/d/<id>/view`).
