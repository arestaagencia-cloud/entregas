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

- Favicon da ArestAgência (logo branca em quadrado escuro) em todas as páginas: arquivos `docs/favicon.ico`, `docs/favicon-32.png` e `docs/apple-touch-icon.png`, já referenciados no `<head>` de `template.html`, `painel_template.html` e `hub_template.html`. Página nova = usar esses templates (ou copiar as 3 tags `<link rel="icon">`).

- Tema escuro, logo no topo, mosaico de fotos + capas de vídeo na capa.
- Detecta sozinho: misto, só vídeos ou só fotos.
- "Fale com a gente" abre o WhatsApp (61) 99128-3546 com a mensagem pronta.
- Vídeos tocam pelo player do Drive (1080p) e baixam o original.

## Nunca

- Apagar páginas publicadas ou arquivos do Drive.
- Mudar o slug de uma entrega já publicada (o cliente já tem o link).
- Marcar "Página no Ar" sem confirmar que o deploy terminou com sucesso.

## Dashboards

**Rodapé e WhatsApp:** rodapé de todas as páginas (HUB, painéis, páginas de entrega antigas) = "ArestAgência - Produção de Conteúdo". Painéis e páginas de entrega têm botão flutuante do WhatsApp (canto inferior direito, wa.me/5561991283546 com mensagem pronta); o HUB interno não tem.

**Abertura dos painéis:** sempre 80% da altura da tela (`height:80svh`), mosaico ou foto (foto em `object-fit:cover` com degradê para o texto). Título e números se ajustam à altura. No lightbox aparecem só o título e o nome do arquivo (a linha cliente · mês fica escondida).

**Revisão de design dos painéis (nov/2026):** miniaturas da grade e do mosaico vêm do próprio site (`/m/<id>.jpg`, 360px, geradas por `miniaturas()` em gerar_hub.py para TODOS os conteúdos dos painéis; até 600 downloads do Drive por rodada, `MINI_LIMITE`); se faltar, a página cai no thumbnail do Drive. No celular a barra fixa mostra só busca + botão "Filtros" (com contador); os filtros abrem por cima ao tocar. Título do card sem repetir categoria/pessoa da linha de baixo (`tituloCurto()`); selo só para Foto e Carrossel. No celular a abertura mostra só conteúdos, vídeos e meses. Meses, números e títulos na fonte sem serifa (a serifada só na frase "Tudo o que já criamos juntos"). Foco visível, lightbox prende o Tab e devolve o foco ao card, destaque abre pelo teclado.

**Exceções por painel (JSON):** `"layout": "tipo"` troca a separação por mês por colunas por tipo (vídeos à esquerda, fotos à direita; carrosséis numa terceira se houver), mais recentes primeiro, mês como filtro e na linha de baixo do card; escolher Vídeos ou Fotos mostra uma coluna só. `"hero": {"altura": 90, "compacto": true}` muda a altura da abertura (% da tela) e diminui o texto. `"edicoes": {"rotulo": "Edição", "anos": ["2025","2026"]}` adiciona filtro por ano (edição) com os anos listados + qualquer ano que apareça nos meses (2027 entra sozinho). `"capa_pos": "center 100%"` = object-position da foto de capa. Usado no Samba ao Quadrado (no Drive só há conteúdo de 2026; 2025 aparece com 0).

**Player no celular (painel_template.html):** o iframe do Drive é desenhado em 540x960 (vertical) ou 960x540 (horizontal) e reduzido para caber. Botão grande "Tela cheia" (só no celular, vídeo e foto): usa a tela cheia do navegador (Android, gira para paisagem em vídeo horizontal); no iPhone, que não tem tela cheia para isso, a caixa ocupa a tela inteira e o vídeo horizontal com o celular em pé gira 90°. Botão de sair no canto e o X também sai da tela cheia antes de fechar. de clientes (atualização automática)

Cada cliente tem um dashboard fixo em `https://entregas.arestagencia.com.br/<cliente>/` com todos os vídeos e
fotos do Drive, filtros por Cliente, Mês e tipo. Config em `paineis/<cliente>.json`:
`slug` (ex.: `universa`), `titulo`, `marca` (nome grande da capa), `drive_raiz` (id da pasta raiz no Drive),
`cliente_unico` (opcional: use quando a raiz já contém as pastas de mês, sem subpastas de marca),
`clientes` (ordem dos filtros), `capa` (opcional: id de foto do Drive ou caminho no site, ex. `/capas/raul-paola-capa.jpg`; substitui o mosaico,
mostrada inteira, sem corte, com o nome logo abaixo; **sempre horizontal**, nunca foto vertical, porque fica ruim no notebook), `destaque` (opcional: lista de ids de vídeos 16:9 mostrados grandes, com player, acima da grade e fora
dela) com `destaque_titulo` opcional (sem ele, só o vídeo) e
`itens` (preenchido pelo robô). `agrupar_por: "edicao"` (Sarau): agrupa pela pasta da edição em vez do mês e troca o filtro de cliente
pelo de linha (`linhas`, rótulo em `rotulo_clientes`), tirando a linha do começo do nome da pasta
("After Secreto - Tonhão - Janeiro.24"). Painel com um mês só (freelancer) esconde sozinho o período, o filtro e o título de mês.

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

Dashboards no ar: `universa` (9 marcas, raiz = pasta Universa) `niso` (Niso Engenharia), `faber` (Clínica Faber), `equipe-prime`, `sarau` (Sarau Secreto) e `raul-paola` (freelancer, pedido de noivado), todos com
`cliente_unico` e raiz = pasta do cliente. Ao criar um novo, atualize também `relatorios/clientes.json` (campo `painel`).

**Painel interno** (raiz `https://entregas.arestagencia.com.br/`): lista todos os dashboards, com busca e
"Copiar link". Gerado por `gerar_hub.py` + `hub_template.html` a partir de `paineis/*.json` (caminho em `hub.json`).
Protegido por senha da equipe: os dados vão criptografados (AES-GCM/PBKDF2) e só abrem com a senha, que fica
no segredo `HUB_SENHA` do repositório. O robô regera o painel quando algum dashboard muda; sem o segredo, ele
não regera (mantém a versão publicada). Para regerar à mão: `HUB_SENHA=... python3 gerar_hub.py`.
Novo dashboard aparece sozinho no painel interno. Nunca publique o painel interno sem senha.

Layout: `painel_template.html` + `gerar_painel.py`. Endereço antigo `/painel-universa-k7q2/` redireciona para `/universa/`.

## Relatórios mensais em PDF

> Os PDFs são feitos em chats próprios, com a skill "relatorio-mensal-pdf". O chat de gestão da plataforma
> (painéis, robô, painel interno, Notion) não gera PDFs. Mudanças no fluxo do PDF: atualize esta seção E a skill.

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

## Notion · sincronização de Conteúdos com o Drive

Integração "Robô ArestAgência" (segredo `NOTION_TOKEN`) com acesso às databases Conteúdos, Serviços e Clientes.
Script `notion/sync_conteudos.py`, workflow "Notion · sincronizar conteúdos" (`notion-sync.yml`, input `aplicar`):
sem `aplicar` só gera a prévia no log (entre `=====RELATORIO=====` e `=====FIM=====`); com `aplicar` cria/corrige.
Regras: vídeos e carrosséis dos painéis (fotos não); casa pelo ID do Drive no Link e depois pelo nome; não renomeia
páginas existentes; ajusta Link, Clientes, Serviços ("Cliente - Mês.AA", marcas da Universa também "Universa - Mês.AA"),
SubCategorias Universa, Tipo de Conteúdo (Reels | Vídeo Horizontal pela proporção da capa | Carrossel) e Status
("Entregue e Aprovado" se vazio/em produção). Duplicatas pelo nome: fica a mais antiga, as outras vão para a lixeira.
Nunca mexe em Formato, Data de Publicação e Desenvolveu. Rode sempre a prévia antes de aplicar.
**Automático:** o robô dos painéis roda `sync_conteudos.py --auto` toda vez que o Drive muda (de hora em hora):
cria/corrige páginas sozinho, mas nunca manda duplicatas para a lixeira e não aplica nada se houver mais de 60
mudanças de uma vez (fica um aviso no log; aí rode a prévia à mão).
Primeira sincronização (12/11/2026): 154 criadas, 169 corrigidas, 8 duplicatas na lixeira; 392/392 corretos.

**Capas e lista do que falta no Drive:** `notion/capas.py` (workflow "Notion · capas dos conteúdos", `notion-capas.yml`)
põe como capa de cada página de Conteúdos a miniatura do arquivo do Link (pasta/carrossel: 1º arquivo; imagem com
o mesmo nome do vídeo na pasta tem prioridade), publicada em `docs/capas/<id do Drive>.jpg`. Troca só capas
genéricas (vazia, placeholder "Novo_Conteúdo" do modelo, galeria do Notion); capas enviadas à mão ficam.
Páginas cujo arquivo não abre no Drive vão para a lista "sem Drive" (CSV no log, entre `=====CSV=====`).
O robô roda `capas.py --auto` junto com a sincronização. 12/11/2026: 174 capas; 274 páginas fora do Drive.

## Botão "Baixar tudo" (zip)
Se a pasta do mês tiver UM arquivo .zip (direto na pasta, não em subpasta), o robô grava `"zip": {"id","nome"}` no JSON do painel e o painel mostra o botão "Baixar tudo" no topo (link direto de download do Drive). `bytes` é opcional (mostra o tamanho) e é preservado enquanto o id for o mesmo. Zips nunca entram na grade. Mais de um zip = aviso, sem botão.

## Formato de cada conteúdo (vertical x horizontal)
O robô mede a miniatura de cada vídeo/foto no Drive e grava `"fmt": "h"` ou `"v"` no item (só mede arquivos novos; reaproveita o resto). Sem miniatura ainda, usa "horizontal"/"vertical" no nome como pista, senão tenta na próxima rodada. No painel, dentro de cada mês/edição os verticais aparecem primeiro e depois os horizontais numa grade própria em 16:9 (padrão de todo o sistema: vertical antes de horizontal); o player do lightbox abre em 16:9 para os horizontais. Carrosséis ficam sempre na grade vertical.

## Filtro por categoria (ex.: Equipe Prime por empreendimento)
`"categorias": {"rotulo","lista","apelidos","geral","geral_apelidos"}` no JSON do painel. A categoria vem do 1º trecho do título (antes do " - "), sem acento; "Geral" vai para `geral` ("Gerais"). Se o nome aparecer no meio do título (ex.: "Cada Detalhe - Rubi - Fábio"), classifica mesmo assim; sem nenhum nome, vai para Gerais. Só muda a exibição (DATA); o JSON, o Notion e os PDFs continuam com o cliente original. Para listar os fora do padrão: `categoria(titulo, cfg["categorias"])` em gerar_painel.py retorna (categoria, "inicio"|"meio"|"nenhum").

## Filtro por corretor (Equipe Prime)
`"corretores": {"rotulo","lista","apelidos"}` no JSON. Procura cada nome/apelido (sem acento, palavra inteira) em qualquer parte do título; um vídeo pode ter mais de um corretor ("Raquel e Escobar") e aparece nos dois. Item ganha `cor: [...]` no DATA; o card mostra "Empreendimento · Corretor". Corretor novo = acrescentar na `lista` (apelido curto, ex.: "Poli", em `apelidos`). Funções: `corretores(titulo, cfg["corretores"])` em gerar_painel.py.
Com `categorias.regioes` ({"Sudoeste":[...], ...}) o filtro vira dois níveis: linha "Região" (Todos, regiões com conteúdo, Gerais) e, ao escolher uma região, a linha "Empreendimento" só com os dela. Região sem conteúdo não aparece (ex.: Águas Claras até sair vídeo do Montana). Empreendimento novo = colocar na `lista` e na região certa.

## Clínica Faber: Tópico + Quem grava
Mesmo mecanismo (`categorias` com rotulo "Tópico" e `corretores` com rotulo "Quem grava"). Faber tem também `categorias.palavras`: {tópico: [palavras-chave]} em ordem de prioridade, usado quando o 1º trecho do nome não é um tópico (ex.: "Ranger dos dentes" → Bruxismo). Sem nada → Gerais.

## HUB (painel interno) · layout "Sala de Projeção" (18/11/2026)
Duas áreas, com menu fixo (Upload, Painéis): **Upload** no topo ("Produção da casa" com KPIs e mix logo abaixo do título, e os números sobem na hora a cada arquivo enviado pelo Hub; upload à esquerda com cliente e mês pesquisáveis por texto; calendário de uploads à direita com a foto de quem enviou, lida do dono do arquivo no Drive via login Google, por pasta de mês conhecida em `pastas.meses`; sem login aparece "Mostrar quem enviou") e depois **Painéis** ( os gráficos por mês/cliente e a lista de últimos uploads foram removidos a pedido). Antes eram quatro: **Painéis** (cards Recorrentes x Freelancers, sem sigla, sem selo e sem prévia de filtros; recorrentes usam o mosaico da capa do painel, freelancers a foto horizontal da capa; "Último mês", Abrir em nova aba), **Upload**, **Métricas** e **Calendário**. Tudo vem do JSON cifrado gerado por `gerar_hub.py` (`{"paineis", "metricas", "gh", "gerado"}`).
- **Acesso (login Google):** o HUB abre com "Entrar com Google". A página lê o documento "Chave do Hub" (id em `hub.json` → `chave_drive`, pasta 1p6SaxjeKDNJZRnDT1E2InNCWBz7IFsLx, dono aresta.agencia@gmail.com) pela API do Drive com a conta da pessoa; o texto do documento é a senha que decifra os dados (igual ao segredo HUB_SENHA). Quem entra = quem tem o documento compartilhado (e está nos usuários de teste do Google Cloud). O mesmo login libera o Upload. A senha continua valendo como "senha de emergência" (link no login; sessão de 1 h, sem upload). Sessão sempre com Google: nada fica salvo no aparelho (só sessionStorage da aba, para sobreviver ao recarregar); quando o token do Google vence (1 h) ou dá 401, o HUB fecha e volta para o login (espera terminar um envio em andamento). Foto da conta no canto superior direito com menu Trocar de conta / Sair (Sair revoga o token). Para tirar alguém: remover o compartilhamento do documento E trocar a senha (novo texto no documento + novo segredo HUB_SENHA + rodar o robô com forcar), porque a pessoa pode ter guardado a chave no navegador. `client_id` e `chave_drive` ficam visíveis na página (não são segredo).
- **Pasta Indefinido (padrão do upload):** `1. Clientes Ativos / 0. Cliente Indefinido / 00. Mês Indefinido` (id em `hub.json` → `pasta_indefinido`). O upload começa com "Cliente indefinido" e "Mês indefinido": sem cliente, o arquivo vai com o nome original; com cliente e sem mês, vai com o nome no padrão do cliente. Nada lá entra nos painéis (o robô não lê essa pasta), não sobe os números nem dispara o Atualizar. O Hub mostra quantos arquivos aguardam organização. Organizar = mover para a pasta certa (hoje à mão no Drive).
- **Abertura:** seção "Hub de entregas" no topo, com mosaico animado das capas (`capas`) de todos os painéis intercaladas e as métricas (conteúdos entregues, painéis ativos e barra com quantidades de fotos/vídeos/carrosséis). O card "Produção da casa" saiu da seção de upload. Ao escolher um cliente no upload, o mês já vem no mês atual (existente ou "+ criar pasta"); Indefinido só é padrão para "Cliente indefinido".
- **Criar cliente e mês pelo upload:** digitar um cliente que não existe oferece "+ Criar cliente em Recorrentes/Freelancers" (`hub.json` → `pastas_tipo`); a pasta "Cliente" é criada no envio (se já existir com o mesmo nome, usa a existente). O mês lista do mês passado até 2 à frente como "criar pasta" e aceita digitar qualquer mês ("fev 27"). Com login, o Hub lê as pastas de mês direto do Drive (pega as criadas depois da última atualização) e lista clientes que existem no Drive sem painel ("sem painel"). Cliente novo só aparece nos Painéis depois de criar o `paineis/<slug>.json`.
- **Nova versão de um vídeo (upload):** o Hub lê os arquivos da pasta de destino e compara pelo nome sem versão (`semVersao()`: tira só a ÚLTIMA marca "V.N" do fim ou antes de " - Pessoa", o "F." e as palavras do nome do cliente; "Apresentações V.10 Manda" e "V.11" continuam diferentes). Se o vídeo já existe, sugere a próxima versão e mostra "Nova versão de X"; depois de enviar, manda a anterior para a LIXEIRA do Drive (recuperável por 30 dias), a não ser que marquem "Manter a versão anterior também". Nova versão não soma nos números. A busca de versões olha também as subpastas do mês (até 3 níveis, ex.: Apresentações/Magrão Verticais) e a nova versão é enviada para a mesma subpasta da anterior. A versão escrita no arquivo original ("… - V.3") é mantida. Sem `categorias`, se o título já começa pela 1ª palavra do cliente ("Sarau Junho…", "Niso - …"), o nome não repete o cliente. Abertura voltou para ~80% da altura (pedido da Aresta). No Notion, `sync_conteudos.py` tem uma 3ª passada: vídeo novo sem página casa com a página cujo Link aponta para um arquivo que saiu do Drive e tem o mesmo nome sem versão (só se for única) e troca o Link, sem criar página nova (o Nome da página não muda).
- **Sistema visual (revisão de design, nov/2026):** dourado só para a ação principal (Escolher arquivos/Enviar), o que está ativo (menu, dia de hoje) e avisos; "Atualizar sistema" é botão discreto (fica dourado só rodando). Títulos só na sans (a serifada saiu). Abertura com ~56% da altura e mosaico pausado fora da tela ou com o mouse em cima. Upload e calendário em cards iguais. Calendário: cada cliente tem cor e sigla (`sigla()` em gerar_hub.py; uma palavra = 3 letras, "UNI"), legenda embaixo e clique no dia abre a lista completa. Acessibilidade: foco visível dourado, aviso com aria-live, menu da conta com Esc/aria-expanded, campos de cliente/mês como combobox ARIA, `color-scheme: dark`, alvos de 44px no celular.
- **Topo:** uma linha só e fixa: Atualizar sistema (+ "Atualizado em") · logo ARESTAGÊNCIA · menu Início/Upload/Painéis · foto da conta. Mosaico da abertura usa `mosaico` (até 24 capas por painel), 14 colunas no desktop. **Miniaturas do HUB são servidas pelo próprio site** (`docs/m/<id>.jpg` 240px; `docs/m/c/<id>.jpg` 640px para capa de card de freelancer), geradas por `miniaturas()` em gerar_hub.py (reaproveita `docs/capas/` ou baixa do Drive devagar, até 400 por rodada; apaga as que não são mais usadas; precisa de Pillow no workflow). O Drive bloqueia (429) quando a página pede centenas de miniaturas de uma vez; sem miniatura local o HUB cai no thumbnail do Drive. `qualidade()` avalia cada miniatura (cache `docs/m/_qualidade.json`): evita quase lisas, pretas, estouradas/brancas (desvio < 20, média fora de 24–205, >45% quase branco ou >85% quase preto) e marca rosto (OpenCV haarcascade, `opencv-python-headless<5` no workflow). Card usa as 8 boas mais recentes; mosaico usa só as boas, com rostos primeiro. Rodapé: só "ArestAgência · Brasília".
- **Upload:** envio direto ao Drive pelo navegador (Google Identity Services, escopo `drive`, ID do cliente OAuth em `hub.json` → `google_client_id`; app no Google Cloud em modo Teste, só usuários de teste entram; projeto "Hub Entregas" da conta aresta.agencia@gmail.com, origem autorizada https://entregas.arestagencia.com.br). Escolhe cliente e mês; se o mês não tem pasta, cria "NN. Cliente - Mês.AA" (numeração igual às existentes; antes procura uma pasta do mesmo mês para não duplicar). Renomeia no ato: com `categorias` → `F. Categoria - Título - Pessoa - V.N` (região sozinha = "Sudoeste · Geral"); sem → `F. Cliente - Título - V.N`; fotos com o mesmo título ganham número (`Título 1`, `Título 2`); .zip e outros mantêm o nome. Bloqueia nome repetido na lista ou já existente na pasta. Envio retomável em pedaços de 16 MB. Ao terminar sem erro, dispara o "Atualizar sistema". Opções de nome vêm de `nomes` (gerado por `nomes_upload()` em gerar_hub.py). Carrosséis continuam pelo Drive. O robô grava `pastas` ({clientes:[{nome,id}], meses:[{cliente,mes,id,nome}]}) em cada `paineis/*.json`.
- **Métricas:** totais, mix de formatos, conteúdos por mês da pasta de entrega (últimos 12) e por cliente.
- **Calendário:** dias de upload. Cada item tem `up` (AAAA-MM-DD): o robô grava a data do dia em que o arquivo apareceu no Drive (arquivos novos); itens criados desde 01/08/2026 foram preenchidos com o `createdTime` do Drive. Antes disso não há data. Em 17/11 aparece o pico da reorganização de Faber e Equipe Prime (arquivos reenviados).
- **Atualizar sistema:** mostra "Sincronizado há X" pela API pública do GitHub (repo público). Com o segredo `HUB_GH_TOKEN` (token fine-grained só deste repo, permissão Actions: read and write), o botão dispara `atualizar-paineis.yml`, acompanha e recarrega a página; sem o segredo, abre a página do workflow no GitHub para clicar em "Run workflow". O token vai dentro dos dados cifrados (só abre com a senha).

## Painel interno: subcategorias
`gerar_hub.grupos(cfg)` usa `gerar_painel.montar(cfg)` (o mesmo DATA do painel) e mostra no card de cada cliente as subcategorias com link já filtrado: Marcas (Universa), Tipo de Sarau, Região/Empreendimento/Corretor (Equipe Prime), Tópico/Quem grava (Faber). Qualquer filtro novo num painel aparece aqui sozinho.
Painel interno dividido em duas áreas: "Clientes Recorrentes" e "Clientes Freelancers". Padrão = recorrente; para freelancer, `"tipo_cliente": "freelancer"` no JSON do painel (ex.: raul-paola). Busca e ordenação valem para as duas áreas.

## Universidade Tuiuti
Drive: "Contrato N" (pasta-contêiner, o robô entra nela) > "NN. Tuiuti - Contrato N - Primeira Leva - Mês.AA" > (Verticais/Horizontais opcionais). Painel `tuiuti`: `filtro_pasta` {"rotulo":"Contrato","regex":"contrato\\s*\\d+"} lê o contrato do nome da pasta; `remover_titulo` tira "Tuiuti 2.2 - " do título. No Notion o cliente é "Universidade Tuiuti" e cada leva é um Serviço com o nome da pasta.
Equipe Prime: nome começando pela região ("Sudoeste - ...") vira "Sudoeste · Geral" (aparece dentro da região); "Geral" em qualquer trecho do nome = Gerais. Faber ganhou o tópico Periodontia.
Freelancers (`tipo_cliente: freelancer`): capa do painel com uma imagem só (`capa`; sem ela, usa a miniatura do vídeo horizontal mais recente) e o card no painel interno mostra essa mesma imagem em vez do mosaico.

## Hub de Bailes (desde 24/11/2026)
Duas páginas, geradas por `python3 gerar_bailes.py`:
- **Pública `/bailes/`** (`bailes_publico_template.html`): mosaico, bailes com galeria aberta (`eventos.aberto`) do mais
  recente ao mais antigo, separados por ano; cada card abre a galeria do baile (`eventos.url_galeria`), com o logo do
  parceiro (de `bailes.json`). Campo "Comprou um código no baile?" (e `?codigo=` do QR): confere o código e leva à
  galeria do baile para o qual ele foi vendido. **Sem nenhuma métrica.**
- **Interna `/bailes/painel/`** (`bailes_template.html`, login Google igual ao HUB): métricas e códigos. Aparece no HUB
  como card na coluna **Freelancers**, vindo de `hub.json` → `extras` (url `/bailes/painel/`; `gerar_hub.py` leva a
  lista para os dados cifrados e `cardExtra()` em `hub_template.html` desenha o card). Capa do card: `docs/bailes/capa.jpg`.
- **Números ao vivo:** função `painel-bailes` do Supabase (projeto `arestagencia-bailes`, id `jlogxdjttufiiikiezfe`).
  A página manda o token Google no cabeçalho `x-google-token`; a função só responde se essa conta abre a
  "Chave do Hub" no Drive (mesmo controle de acesso do HUB). Devolve totais e, por baile: vídeos publicados,
  vendas, vídeos vendidos, arrecadado (bruto), Pix x cartão x dinheiro, vendas por dia, checkouts, downloads,
  estornos, mais vendidos, últimas vendas, códigos vendidos/a resgatar e alerta de venda paga sem e-mail enviado.
- **Galerias públicas de cada baile:** `https://entregas.arestagencia.com.br/bailes/<pasta>/` (ex.: `/bailes/idalhesamba/`),
  geradas a partir de `galeria_template.html` e da lista `bailes.json`
  (`pasta`, `evento` = slug no Supabase, `parceiro` opcional com `nome` e `logo`, arquivo em `docs/bailes/<pasta>/`;
  o logo aparece ao lado da marca, "ARESTAGÊNCIA × logo"; **sempre a versão toda branca do logo, PNG com fundo
  transparente, sem quadro nem fundo** (pedido da Aresta, 24/11/2026). Se o cliente só tiver o logo colorido, peça a versão branca). A galeria lê eventos/vídeos pela chave pública, abre a
  compra (função `criar-checkout`), mostra a confirmação (`?pedido=`) e o download (`?baixar=`). O Supabase guarda o
  endereço em `eventos.url_galeria`: é para lá que o Mercado Pago devolve o cliente e para onde aponta o link do e-mail.
  O endereço antigo `videos.arestagencia.com.br` (repo `arestaagencia-cloud/videos`) só redireciona para cá.
- **Códigos de resgate (genéricos desde 24/11/2026):** vendidos no baile, mais baratos, trocados depois por UM vídeo.
  **Valem para qualquer baile:** o código nasce sem baile (`codigos.evento_id` nulo) e o baile é escolhido NA VENDA;
  valor e métricas somam para esse baile e o resgate só vale para vídeos dele. Cartão que sobra serve no próximo baile.
  Tabela `codigos` (8 caracteres sem 0/O/1/I/L, exibidos `XXXX-XXXX`; status disponivel → vendido → resgatado;
  "Desfazer" volta para o estoque e limpa o baile). Painel interno, seção **Códigos de resgate** → "Vender e gerenciar":
  baile da venda (padrão: o mais recente aberto), código do cartão, valor (preço do baile em
  `eventos.preco_codigo_centavos`), Pix/Cartão/Dinheiro/Cortesia, nome e contato opcionais, mensagem pronta para
  WhatsApp (link direto da galeria do baile); preço por baile; gerar lote; **imprimir cartões** (A4, 10 por folha,
  "VALE 1 VÍDEO", QR para `https://entregas.arestagencia.com.br/bailes/?codigo=XXXXXXXX`, lib `docs/bailes/qrcode.min.js`);
  copiar lista; filtro por situação e por baile. Função `codigos-admin` (mesmo acesso Google). **Código não marcado como
  vendido não resgata.** Galeria: `?codigo=` mostra o aviso (ou redireciona para a galeria do baile certo); na janela do
  vídeo, "Tenho um código" troca a compra pelo resgate (função pública `resgatar-codigo`, até 8 erros por IP a cada
  15 min, resgate atômico na função SQL `resgatar_codigo`). O resgate cria um pedido `origem: codigo`, valor 0, pago, e
  manda o e-mail de sempre. Métricas: vendas e arrecadado somam códigos vendidos (pelo valor da venda), sem contar o resgate.
  Primeiro lote: 25 códigos (24/11/2026), preço no I Dá-lhe Samba R$ 35.
- **"Me avise" (desde 24/11/2026):** na galeria, enquanto não há vídeos, aparece o formulário "Quer saber quando o seu
  vídeo chegar?" (nome + WhatsApp e/ou e-mail); `?avise=1` (QR do telão) rola até ele. Função pública `avise-me`
  (até 60 cadastros por IP/hora; mesmo baile + mesmo e-mail/WhatsApp atualiza em vez de duplicar) grava na tabela
  `avisos` (sem acesso público). Painel interno: linha "Pediram aviso" e botão **Interessados** em cada baile:
  lista, "Enviar e-mail a quem falta" (só funciona com vídeos publicados; marca `email_avisado_em`), botão "Enviar"
  por pessoa no WhatsApp (mensagem pronta; marca `whatsapp_avisado_em`) e copiar lista. Ações `avisos`,
  `avisar_email`, `whats_avisado` na função `codigos-admin`.
- **Telão `/bailes/telao/`** (`bailes_telao_template.html`, sem login): no MacBook, escolhe o baile, adiciona a pasta
  do cartão (ou arquivos, ou arrasta) e toca cada vídeo N segundos (padrão 20, a partir do meio do vídeo), em loop,
  com número do vídeo, oferta do código (preço do baile, editável) e QR para `<url_galeria>/?avise=1`. Os arquivos
  não saem do computador. Numeração: novas levas continuam a contagem; números ficam guardados por baile no
  navegador (recarregar a página e reescolher a pasta mantém os números); número editável por vídeo. **A edição usa
  os mesmos números (P. 07 / F. 07).** Teclas: espaço pausa, ← → anterior/próximo, F tela cheia, S configuração.
- **Novo baile** = criar o evento no Supabase (tabela `eventos`, com `url_galeria`, `aberto` e o preço do código),
  acrescentar em `bailes.json`, rodar `gerar_bailes.py` e cadastrar os vídeos; ele aparece sozinho na página pública
  (se `aberto`), no painel interno e na lista de bailes da venda de códigos.
