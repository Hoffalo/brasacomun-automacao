# BRASA Briefing Bot — Contexto para Claude Code

## O que é este projeto

Automação de briefings de marketing para a diretoria **Comun** da BRASA (Brazilian Student Association), a maior rede de estudantes brasileiros no exterior.

Quando um analista de MKT muda o status de uma task no ClickUp para **"Em Progresso MKT"**, uma função serverless é acionada, coleta contexto de múltiplas fontes em paralelo, gera um briefing via Claude API e escreve o resultado diretamente na descrição da task — em ~20 segundos.

---

## Stack

| Componente | Tecnologia |
|---|---|
| Servidor | Vercel Serverless Function (Python 3.12) |
| Trigger | ClickUp Webhook — `taskStatusUpdated` |
| Contexto | Slack API + Google Drive API v3 + Canva API |
| Geração | Anthropic API — `claude-sonnet-4-5` |
| Output | ClickUp REST API — atualiza descrição da task |

---

## Estrutura de arquivos

```
brasa-briefing-bot/
├── api/
│   └── webhook.py          ← Entry point Vercel. Recebe POST do ClickUp,
│                             valida assinatura HMAC, responde 200 imediatamente
│                             (wfile.write esvazia o buffer TCP), e DEPOIS
│                             roda run_pipeline sincronamente no mesmo processo.
│                             Sem thread daemon — serverless mata threads quando
│                             handler retorna. Vercel Pro dá 60s, suficiente.
├── lib/
│   ├── pipeline.py         ← Orquestra as 5 etapas. Entry point síncrono
│                             que chama asyncio.run(_pipeline()).
│   ├── clickup.py          ← REST API ClickUp direto (não MCP). Usa
│                             ?include_markdown_description=true para obter
│                             rich text com links embutidos preservados.
│   ├── slack_client.py     ← Busca mensagens relevantes (allowlist de canais)
│                             + lookup de cargo dos assignees via bio do Slack.
│   ├── drive_client.py     ← Busca Google Drive. Service Account (JWT) como
│                             autenticação primária; se SA não tiver token ou
│                             retornar 0 resultados, cai em OAuth refresh token
│                             (conta pessoal BRASA) como fallback. Inclui
│                             includeItemsFromAllDrives pra buscar em Shared Drives.
│   ├── canva_client.py     ← Extrai design_id + nº de slide do markdown_description.
│                             Usa Canva OAuth (CLIENT_ID/SECRET/REFRESH_TOKEN) —
│                             Canva rotaciona o refresh token a cada uso, o código
│                             persiste o novo em secrets/.env.local automaticamente.
│                             Faz POST /exports pra PNG alta-res da página pedida
│                             (job assíncrono com polling), baixa e retorna
│                             {text, image_base64, image_media_type} pra Vision.
│                             Fallback pra thumbnail 596x335 se export falhar.
│   ├── briefing.py         ← Chama Claude API (Sonnet 4.5) com prompt completo.
│                             Se canva_ctx tem image_base64, anexa como bloco
│                             Vision na mensagem (Claude "vê" o slide).
│                             Legenda + Orientação Design: rascunho pronto.
│                             Outros campos: direcionamentos + perguntas norteadoras.
│                             System prompt aplica ID visual BRASA (cores/fontes)
│                             e filtro de público (remove conteúdo interno/board).
│   ├── editorial.py        ← Linha editorial, prefixos, paletas por produto
│                             (Manual de ID Visual BRASA, seção 1.3).
│   └── alerts.py           ← Gera alertas automáticos (data, tags, campos).
├── scripts/
│   ├── load_env.ps1        ← PowerShell. Lê secrets/.env.local + Service Account
│                              JSON e exporta tudo como env vars na sessão atual.
│                              Rodar com `. .\scripts\load_env.ps1` (dot-source).
│   ├── get_refresh_token.py ← One-shot Google OAuth. Abre browser, usuário
│                              loga com conta BRASA, imprime GOOGLE_OAUTH_REFRESH_TOKEN.
│   ├── get_canva_token.py  ← One-shot Canva OAuth (PKCE + localhost callback).
│                              Imprime CANVA_REFRESH_TOKEN.
│   └── probe_canva.py      ← Diagnóstico da Canva Connect API — testa
│                              /designs/{id}, /pages, /designs?limit.
├── secrets/                ← Pasta local ignorada pelo git.
│   ├── .env.local          ← KEY=VALUE com tokens (fonte-da-verdade em dev;
│                              canva_client atualiza in-place quando o Canva
│                              rotaciona o refresh token).
│   └── *service*.json      ← Service Account JSON (Google).
├── .env.local.example      ← Template vazio do .env.local (commitado).
├── requirements.txt        ← aiohttp>=3.10, anthropic>=0.40, cryptography>=42.
├── vercel.json             ← maxDuration: 60s (runtime auto-detectado).
├── runtime.txt             ← python-3.12
├── .gitignore              ← secrets/, .env, *-service-account*.json, etc.
└── README.md               ← Instruções de setup
```

---

## IDs reais do workspace BRASA

```python
COMUN_SPACE_ID         = "90111669766"
TARGET_STATUS_ID       = "sc901105543313_huc4fCr2"  # "em progresso mkt"
TARGET_STATUS_NAME     = "em progresso mkt"
WORKSPACE_ID           = "9011435781"
```

### Canais Slack autorizados (allowlist)

```python
ALLOWED_CHANNELS = {
    "C087ZGQGDBL",   # #comunicação-2025
    "C08APKCM682",   # #comun-time-1
    "C0946MDKY0Z",   # #adm-comun
    "C093AHRH7LG",   # #comun-design
    "C09QQ393BKR",   # #comun-conf-campanha-summit-in
    "C08JDFT65S5",   # #comun-time-brasacast
    "C09ENQR975E",   # #comun-europa
    "C09J3MQSQS0",   # #comun-na-summit-am
    "C098EHU8A8Z",   # #comun-design-tech
    "C098X90H42G",   # #help-comun-board
    "C0ACNDU63KK",   # #impacto-alcance-brasa-ensina
}
```

---

## Variáveis de ambiente necessárias

```bash
CLICKUP_API_TOKEN             # pk_... (ClickUp Settings → Apps)
CLICKUP_WEBHOOK_SECRET        # Gerado ao criar o webhook no ClickUp
SLACK_TOKEN                   # xoxp-... (token pessoal, fase 1)
                              # xoxb-... (bot dedicado, fase 2)
GOOGLE_SERVICE_ACCOUNT_JSON   # JSON minificado da Service Account (primário)
GOOGLE_OAUTH_CLIENT_ID        # OAuth Client ID (Desktop app) — fallback
GOOGLE_OAUTH_CLIENT_SECRET    # OAuth Client Secret                — fallback
GOOGLE_OAUTH_REFRESH_TOKEN    # Gerado por scripts/get_refresh_token.py — fallback
ANTHROPIC_API_KEY             # sk-ant-...
CANVA_CLIENT_ID               # OAuth Client ID (Canva Connect API)
CANVA_CLIENT_SECRET           # OAuth Client Secret
CANVA_REFRESH_TOKEN           # Gerado por scripts/get_canva_token.py
CANVA_API_TOKEN               # (legado) Bearer estático — só usado se definido
```

As três envs `GOOGLE_OAUTH_*` são opcionais. Se as três estiverem preenchidas,
o bot usa o token OAuth como fallback quando a Service Account não consegue
autenticar ou retorna 0 resultados (típico quando a SA não foi adicionada
como membro das Shared Drives da BRASA).

**Canva — rotação de refresh token:** a API Canva invalida o refresh token a
cada uso. O `canva_client._get_access_token` lê sempre do `secrets/.env.local`
(se existir) pra pegar o token mais recente, e o `_persist_new_refresh_token`
atualiza o arquivo quando a resposta do refresh retorna um novo. Em produção
(Vercel, sem `.env.local`), o novo token fica só em `os.environ` — válido
dentro da mesma invocação; chamadas concorrentes podem bater na rotação e
falhar. Pra alto volume, considerar Upstash Redis ou equivalente.

---

## Fluxo completo da pipeline

```
1. Webhook recebe POST do ClickUp
   → Valida HMAC SHA-256 com CLICKUP_WEBHOOK_SECRET
   → Responde 200 imediatamente (ClickUp tem timeout de 3s)
   → Dispara thread separada com run_pipeline(task_id)

2. pipeline.py: _pipeline(task_id)

   ETAPA 1 — Leitura da task
   → GET /task/{id}?include_markdown_description=true
   → Preserva links embutidos (ex: URL do Canva na descrição)
   → Guard: só roda no espaço Comun (90111669766)
   → Guard: anti-duplicata (checa marcador <!-- briefing-gerado -->)

   ETAPA 2 — Identificação e validação
   → identify_prefix(name) → (content_type, platform_type)
   → get_assignee_roles(assignees) → busca cargo via bio Slack
   → build_alerts() → data, tags, campos, regra corp

   ETAPA 3 — Coleta de contexto (asyncio.gather — paralelo)
   → search_slack(tags, name) → mensagens nos canais autorizados
   → search_drive(tags, name) → documentos relevantes no Drive
   → get_canva_context(markdown_desc) → exporta slide em PNG e retorna
       {text, image_base64, image_media_type} pro Vision
   → _get_related_tasks(tags, task_id) → tasks com mesmas tags

   ETAPA 4 — Geração via Claude API
   → claude-sonnet-4-5, max_tokens=1800
   → Se houver image_base64, anexa como bloco Vision (content: [image, text])
   → System prompt aplica ID visual BRASA (cores da paleta do produto,
     tipografia Lato/Hagrid) e filtro de público (remove conteúdo interno,
     disclaimers, menções a board, dados sensíveis)
   → Legenda: rascunho pronto para revisão
   → Orientação Design: rascunho com paleta, tipografia, versão da logo
   → Orientação MKT: direcionamentos + perguntas norteadoras
   → Público-alvo: 1 parágrafo (personas)
   → Foco Emocional: direcionamentos + perguntas norteadoras

   ETAPA 5 — Output
   → Alertas no topo
   → Conteúdo original preservado
   → Briefing gerado abaixo
   → Marcador <!-- briefing-gerado --> no final
   → PUT /task/{id} com nova descrição
```

---

## Lógica de negócio importante

### Prefixos de task e tipos de conteúdo

```python
PREFIXES = {
    "CAM":           ("campanha",      "post"),
    "Corp":          ("corp",          "post"),
    "Stories":       ("stories",       "story"),
    "Reels":         ("campanha",      "reels"),
    "INN":           ("conferencia",   "post"),
    "POST Inn":      ("conferencia",   "post"),
    "EDU":           ("educativo",     "post"),
    "REDE":          ("rede",          "post"),
    "Institucional": ("institucional", "post"),
    "Newsletter":    ("newsletter",    "newsletter"),
    "Takeover":      ("institucional", "story"),
    "VÍDEO":         ("producao",      "video_horizontal"),
}
```

### Linha editorial @gobrasa (por dia da semana)

```
Segunda (0) → corp
Terça   (1) → institucional
Quarta  (2) → rede
Quinta  (3) → educativo
Sex/Sáb/Dom → produto
```

### Regras de alerta

- **Tags vazias** → sempre alerta
- **Data no dia errado** → alerta com sugestão de data correta
- **Tag `corp` + menos de 2 semanas** → alerta de margem
- **Custom fields vazios** → Channel, Data de postagem, Design, Marketing
- **Data no passado** → alerta

### Identidade visual (Manual de ID Visual BRASA)

Tipografia:
- **Lato** → fonte oficial, todos os casos + qualquer texto com a palavra "BRASA"
- **Hagrid Extrabold** → só títulos de impacto, máx 3-4 palavras, nunca com "BRASA"

Logo:
- Fundo claro → versão oficial (Noite Urbana #252726)
- Fundo escuro → versão auxiliar (Luz da BRASA #F4F4F4)
- Fundo colorido/foto → versão monocromática branca

Paletas por produto (seção 1.3 do manual):
- `passaporte` → Azul escuro #1A2B77 · Azul vívido #065FD8 · Amarelo #FFCC02 · Laranja #FB8C0A
- `innovation` → Azul escuro #1A2B77 · Azul vívido #065FD8 · Azul claro · Laranja #FB8C0A
- `bec` → Laranja #FB8C0A · Amarelo #FFCC02 · Verde folha #00863D
- `pdb` → Verde escuro #03571A · Verde folha #00863D · Verde vívido #4BBF4B
- `summit am` → Azul escuro #1A2B77 · Azul médio · Amarelo claro #F5D566
- `summit eu` → Verde escuro #03571A · Verde folha · Amarelo #FFCC02

### Extração de link Canva do markdown

A descrição da task pode conter links Canva embutidos, que só são visíveis
via `?include_markdown_description=true`. O `canva_client.py` extrai assim:

```python
CANVA_ID_PATTERN = re.compile(r"canva\.com/(?:design|d)/([A-Za-z0-9_-]{11})")
SLIDE_NUMBER_PATTERN = re.compile(r"slide[s]?\s+(\d+)", re.IGNORECASE)
```

Exemplo: descrição `"usar info slide 21 [link](https://www.canva.com/design/DAHEgH1dK6c/edit)"`
→ design_id = `DAHEgH1dK6c`, page = `21`

---

## Contexto do time Comun

**Diretora:** Dalila Figueiras (dalila.messagi@gobrasa.org)

**Subtimes:**
- Subtime 1 (Corp/Institucional): Beatriz Guell Teixeira (gerente)
- Subtime 2 (Campanhas): Ana Marina Landmann (gerente)
- Subtime 3 (Conferências): Leticia Pacheco (diretora conf)

**Analistas recorrentes:**
- Larissa Thaty de Melo Medeiros — MKT @gobrasa (U091LFCJNMS)
- Clara Saullu — Design Conferências (U091LFC52N8)
- Sophia de Luna — Design Institucional
- Domênica Augusta Corradi — MKT Time 1
- Lorenzo Hoffmann — Audiovisual (U091LFB4BC4)

**Cargo de assignee:** sempre verificar via bio do Slack (`users.lookupByEmail`),
campo `profile.title`. Formato: "COMUN | Cargo — Subtime"

**Cross-team:** assignee com `title` sem "COMUN" = externo (ex: Ana Clara Cardoso
= Gerente de Alcance do time de Impacto).

---

## Listas ativas no espaço Comun

```
@gobrasa          (901105543313) — Instagram principal
LinkedIn & Newsletter (901106135245)
TikTok            (901106135274)
IG Summit Innovation (901106135849)
IG Summit Americas (a confirmar)
IG Summit Europa  (a confirmar)
IG BeC            (901106164735)
Tasks             (901109622288) — tasks gerais sem lista específica
```

---

## Limitações conhecidas e soluções

| Limitação | Situação atual | Solução futura |
|---|---|---|
| Slack: só vê canais do usuário autenticado | `SLACK_TOKEN` = token pessoal | Bot dedicado (`xoxb-`) com `channels:history` em todos os canais Comun |
| ClickUp MCP não retorna rich text | Pipeline usa REST API direta com `include_markdown_description=true` | — (já resolvido) |
| Canva: links só visíveis no rich text | `canva_client.py` extrai via regex do `markdown_description` | Campo "Arte" (URL) nas listas para alternativa estruturada |
| Canva: refresh token rotaciona a cada uso | Em dev, salva novo em `secrets/.env.local`. Em produção, só em `os.environ` da invocação | Upstash Redis ou Vercel KV pra persistir entre invocações |
| Canva: endpoint `/content` não existe na Connect API | Usa `/exports` (job assíncrono de PNG) + Vision pra "ler" o slide | — (já resolvido) |
| Drive: SA não tem acesso às Shared Drives da BRASA (só Manager adiciona membro) | Fallback OAuth: bot autentica como usuário BRASA via refresh token | Pedir pra COO/Dir Tech adicionar SA como Viewer nas Shared Drives relevantes |
| Drive: Slides/Sheets não são legíveis diretamente | Loga como "○" no contexto | Exportar como texto via Drive export endpoint |
| Vercel Hobby: timeout de 10s mata a pipeline | Plano Hobby não suporta briefing completo (~15-20s) | Upgrade Pro ($20/mês, 60s) OU migrar pra Cloud Run/Railway |
| Vercel: thread daemon morre quando handler retorna 200 | Em Vercel Serverless, background thread é terminada ao fim da invocação | Fazer handler síncrono (aguardar pipeline) com Pro plan, ou usar fila externa |

---

## Roadmap (Fase 2)

- [ ] Substituir `SLACK_TOKEN` por bot dedicado (`xoxb-`) — setup ~20min
- [ ] Adicionar campo "Arte" (URL) nas listas de conferência para link Canva estruturado
- [ ] Suporte a múltiplos design_ids na mesma descrição
- [ ] Testes automatizados com tasks reais como fixtures
- [ ] Logging estruturado (Vercel logs ou Datadog)
- [ ] Dashboard de monitoramento de briefings gerados

---

## Como testar localmente

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
export CLICKUP_API_TOKEN="pk_..."
export SLACK_TOKEN="xoxp-..."
export GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
# Opcional: OAuth fallback quando SA não tem acesso às Shared Drives
export GOOGLE_OAUTH_CLIENT_ID="..."
export GOOGLE_OAUTH_CLIENT_SECRET="..."
export GOOGLE_OAUTH_REFRESH_TOKEN="..."  # gerado por scripts/get_refresh_token.py
export ANTHROPIC_API_KEY="sk-ant-..."
export CANVA_CLIENT_ID="..."
export CANVA_CLIENT_SECRET="..."
export CANVA_REFRESH_TOKEN="..."  # gerado por scripts/get_canva_token.py

# Rodar pipeline diretamente (sem webhook)
python3 -c "
from lib.pipeline import run_pipeline
run_pipeline('868j9tryh')                  # respeitando anti-duplicata
run_pipeline('868j9tryh', force=True)      # força, ignora marcador <!-- briefing-gerado -->
"
```

**No Windows / PowerShell**, use o helper:
```powershell
# cada sessão nova
. .\scripts\load_env.ps1
python -c "from lib.pipeline import run_pipeline; run_pipeline('868j9tryh', force=True)"
```

O `load_env.ps1` lê `secrets/.env.local` (KEY=VALUE uma linha por var) e
também carrega o Service Account JSON direto do disco. Canva rotaciona o
refresh token a cada uso, então o `canva_client` atualiza o `.env.local`
in-place — a próxima chamada na mesma sessão não precisa de reload.

---

## Observações para Claude Code

1. **Não usar o MCP do ClickUp** para leitura de tasks na pipeline — ele retorna
   texto plano e perde links. Usar sempre `lib/clickup.py` que chama a REST API diretamente.

2. **Todas as chamadas externas são assíncronas** (`aiohttp`). Nunca usar `requests`
   síncrono — causaria bloqueio no event loop e timeout no Vercel.

3. **O campo `markdown_description`** é o campo crítico. Sem ele, links Canva
   embutidos na descrição ficam invisíveis.

4. **Anti-duplicata:** sempre checar `<!-- briefing-gerado -->` antes de gerar.
   A mudança de status pode ser triggerada múltiplas vezes.

5. **O webhook responde 200 antes de processar.** `self._respond(200, "ok")` é
   chamado primeiro (envia TCP, ClickUp recebe); DEPOIS `run_pipeline(task_id)`
   roda sincronamente no mesmo processo. Vercel Pro (60s maxDuration) aguenta.
   NÃO usar thread daemon — serverless mata threads quando handler retorna.

6. **Paletas do manual de ID visual** estão em `lib/editorial.py` no dict
   `PALETA_POR_PRODUTO`. O cruzamento com tags da task é feito em `pipeline.py`
   na função `_get_paleta()`.

7. **Formato do briefing** é definido no `SYSTEM_PROMPT` em `lib/briefing.py`.
   Legenda e Orientação Design = rascunho pronto.
   MKT, Público-alvo, Foco Emocional = direcionamentos + perguntas norteadoras.

8. **Drive — SA vs OAuth:** `drive_client.py` tenta Service Account primeiro
   (`_get_sa_access_token`). Se falhar OU retornar 0 arquivos, cai em OAuth
   (`_get_oauth_access_token`) usando refresh token do usuário BRASA.
   A SA só funciona em pastas/Shared Drives onde foi adicionada como membro —
   o fallback OAuth herda acesso completo do usuário.

9. **Secrets ficam em `secrets/`** (ignorado pelo git). Nunca commitar chaves
   Service Account, OAuth client JSONs, ou tokens. O `.gitignore` cobre
   `secrets/`, `.env*`, `*-service-account*.json`.

10. **Vercel config:** Framework Preset deve ser **"Other"** (não "Python").
    Python preset tenta detectar Flask/Django; Other trata arquivos em `api/`
    como Serverless Functions individuais. `vercel.json` NÃO deve especificar
    `runtime` — o Vercel auto-detecta pelo `requirements.txt` + `runtime.txt`.

11. **Canva via Vision:** o endpoint `/designs/{id}/content` **não existe** na
    Canva Connect API (foi tentativa/erro histórico). O fluxo correto é:
    GET `/designs/{id}` (metadata) + POST `/exports` (PNG alta-res assíncrono
    com polling) → download da S3 pré-assinada → passa como `type: "image"`
    pro Claude Sonnet 4.5 com Vision. Fallback pra thumbnail 596x335 se o
    export demorar >20s ou falhar.

12. **Filtro de público no briefing:** o system prompt de `briefing.py` tem uma
    seção FILTRO DE PÚBLICO que remove conteúdo interno do slide Canva
    (curiosidades pro board, disclaimers operacionais, dados sensíveis) antes
    de gerar Legenda/copy. Se aparecer vazamento, adicionar exemplo negativo
    explícito nessa seção — não confia só em regra genérica.

13. **ID visual é INEGOCIÁVEL no prompt:** o bloco "ID VISUAL BRASA — REGRAS
    INEGOCIÁVEIS" força o Claude a usar **só** hex codes da paleta do produto
    (vindos de `PALETA_POR_PRODUTO` em `editorial.py`), ignorando as cores
    que aparecem no slide Canva de referência. Sem esse bloco, Vision tende
    a "herdar" cores da imagem.

14. **Local dev workflow (Windows/PS):** `secrets/.env.local` é source of truth.
    `scripts/load_env.ps1` exporta pra sessão. `canva_client` lê sempre do
    `.env.local` pra refresh token (não do `os.environ`) porque Canva rotaciona
    — dois `python -c ...` seguidos sem reload do PS ainda funcionam.


SEMPRE atualizar esse arquivo (CLAUDE.md) quando fizer uma mudança importante