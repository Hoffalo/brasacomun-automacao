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
│                             valida assinatura HMAC, responde 200 imediatamente,
│                             dispara pipeline em thread separada.
├── lib/
│   ├── pipeline.py         ← Orquestra as 5 etapas. Entry point síncrono
│                             que chama asyncio.run(_pipeline()).
│   ├── clickup.py          ← REST API ClickUp direto (não MCP). Usa
│                             ?include_markdown_description=true para obter
│                             rich text com links embutidos preservados.
│   ├── slack_client.py     ← Busca mensagens relevantes (allowlist de canais)
│                             + lookup de cargo dos assignees via bio do Slack.
│   ├── drive_client.py     ← Busca Google Drive via Service Account JWT.
│   ├── canva_client.py     ← Extrai design_id de URL Canva no markdown_description
│                             e lê o conteúdo do slide referenciado.
│   ├── briefing.py         ← Chama Claude API com prompt completo.
│                             Legenda + Orientação Design: rascunho pronto.
│                             Outros campos: direcionamentos + perguntas norteadoras.
│   ├── editorial.py        ← Linha editorial, prefixos, paletas por produto
│                             (Manual de ID Visual BRASA, seção 1.3).
│   └── alerts.py           ← Gera alertas automáticos (data, tags, campos).
├── requirements.txt        ← aiohttp, anthropic, cryptography
├── vercel.json             ← maxDuration: 60s, runtime: python3.12
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
CLICKUP_API_TOKEN           # pk_... (ClickUp Settings → Apps)
CLICKUP_WEBHOOK_SECRET      # Gerado ao criar o webhook no ClickUp
SLACK_TOKEN                 # xoxp-... (token pessoal, fase 1)
                            # xoxb-... (bot dedicado, fase 2)
GOOGLE_SERVICE_ACCOUNT_JSON # JSON minificado da Service Account
ANTHROPIC_API_KEY           # sk-ant-...
CANVA_API_TOKEN             # Token da integração Canva
```

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
   → get_canva_context(markdown_desc) → lê slide referenciado
   → _get_related_tasks(tags, task_id) → tasks com mesmas tags

   ETAPA 4 — Geração via Claude API
   → claude-sonnet-4-5, max_tokens=1800
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
| Drive: Slides/Sheets não são legíveis diretamente | Loga como "○" no contexto | Exportar como texto via Drive export endpoint |
| Timeout Vercel: 60s plano gratuito | Pipeline paralela (~15-20s no total) | Migrar para AWS Lambda (15min) se necessário |

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
export ANTHROPIC_API_KEY="sk-ant-..."
export CANVA_API_TOKEN="..."

# Rodar pipeline diretamente (sem webhook)
python3 -c "
from lib.pipeline import run_pipeline
run_pipeline('868j9tryh')  # ID de uma task real para teste
"
```

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

5. **O webhook responde 200 antes de processar.** A pipeline roda em thread separada
   via `threading.Thread(daemon=True)`. Isso é intencional — o ClickUp tem timeout de 3s.

6. **Paletas do manual de ID visual** estão em `lib/editorial.py` no dict
   `PALETA_POR_PRODUTO`. O cruzamento com tags da task é feito em `pipeline.py`
   na função `_get_paleta()`.

7. **Formato do briefing** é definido no `SYSTEM_PROMPT` em `lib/briefing.py`.
   Legenda e Orientação Design = rascunho pronto.
   MKT, Público-alvo, Foco Emocional = direcionamentos + perguntas norteadoras.
