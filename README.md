# BRASA Briefing Bot

Automação de briefings de marketing para a diretoria Comun da BRASA.

**Trigger:** Status da task muda para "Em Progresso MKT" no ClickUp  
**Output:** Briefing completo na descrição da task (~20 segundos)

---

## Setup (~50 min total)

### 1. Deploy no Vercel (~10 min)

```bash
# 1. Fork/clone este repositório para o seu GitHub
# 2. Acesse vercel.com → Add New Project → Import do GitHub
# 3. Deploy (sem configurar nada ainda)
# 4. Copie a URL gerada: https://brasa-briefing.vercel.app
```

⚠️ **Configurações importantes no Vercel:**
- **Framework Preset:** `Other` (NÃO "Python" — Python preset tenta detectar
  Flask/Django; Other trata arquivos em `api/` como Serverless Functions).
- **Root Directory:** vazio ou `./` (ou o subpath correto se o projeto não
  estiver na raiz do repo).
- **Não especifique `runtime`** no `vercel.json` — o Vercel auto-detecta pelo
  `requirements.txt` + `runtime.txt` (python-3.12).
- **Plano Hobby** tem timeout de 10s — insuficiente pra pipeline completa
  (~15-20s). Use **Pro** ($20/mês) pra 60s, ou migre pra Cloud Run / Railway.

### 2. Variáveis de ambiente no Vercel (~5 min)

Em **Settings → Environment Variables**, adicione:

| Variável | Onde encontrar |
|---|---|
| `CLICKUP_API_TOKEN` | ClickUp → Settings → Apps → API Token (`pk_...`) |
| `CLICKUP_WEBHOOK_SECRET` | Gerado no passo 3 abaixo |
| `SLACK_TOKEN` | Slack → perfil → Preferências → (ou token OAuth pessoal `xoxp-...`) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google Cloud Console → Service Accounts → JSON key (minificado) |
| `GOOGLE_OAUTH_CLIENT_ID` | *(opcional, fallback)* OAuth Client ID — ver passo 5b |
| `GOOGLE_OAUTH_CLIENT_SECRET` | *(opcional, fallback)* OAuth Client Secret — ver passo 5b |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | *(opcional, fallback)* gerado via `scripts/get_refresh_token.py` |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys (`sk-ant-...`) |
| `CANVA_CLIENT_ID` | canva.com/developers → Integration → Configuration |
| `CANVA_CLIENT_SECRET` | canva.com/developers → Integration → Configuration |
| `CANVA_REFRESH_TOKEN` | gerado via `scripts/get_canva_token.py` — ver passo 6 |

### 3. Webhook no ClickUp (~5 min)

```
ClickUp → Settings → Integrations → Webhooks → Add Webhook

URL:    https://brasa-briefing.vercel.app/api/webhook
Evento: taskStatusUpdated
Espaço: Comun (ID: 90111669766)
```

Copie o **secret gerado** → cole em `CLICKUP_WEBHOOK_SECRET` no Vercel.

### 4. Slack Token (~5 min)

Por ora, usar token pessoal:
```
slack.com → Seu perfil → Preferências → Advanced → Legacy token
OU
api.slack.com/apps → Create App → OAuth & Permissions → xoxp-...
```

**Fase 2:** substituir por bot dedicado (`xoxb-...`) com escopos:
`channels:history`, `groups:history`, `users:read`, `search:read`

### 5a. Google Drive — Service Account (~15 min, via primário)

```
1. console.cloud.google.com → New Project → Enable Drive API
2. IAM & Admin → Service Accounts → Create → Download JSON key
3. Compartilhe o Drive da BRASA com o email da Service Account (viewer)
4. Minifique o JSON: python3 -c "import json,sys; print(json.dumps(json.load(open('key.json'))))"
5. Cole o resultado em GOOGLE_SERVICE_ACCOUNT_JSON
```

### 5b. Google Drive — OAuth fallback (opcional, ~10 min)

Use quando não der pra compartilhar as Shared Drives com a Service Account
(ex: você não é Manager). O bot autentica como você e herda seu acesso.

```
1. Google Cloud Console (mesmo projeto da SA):
   - APIs & Services → OAuth consent screen → configurar (External ou Internal)
     Scope: .../auth/drive.readonly. Test users: seu email BRASA
   - APIs & Services → Credentials → Create → OAuth client ID
     Application type: Desktop app → Create → baixar JSON

2. Rodar script local uma vez:
   export GOOGLE_OAUTH_CLIENT_ID="..."
   export GOOGLE_OAUTH_CLIENT_SECRET="..."
   python scripts/get_refresh_token.py
   → abre browser, você loga com a conta BRASA
   → refresh_token aparece no terminal

3. Colar no Vercel (Environment Variables):
   - GOOGLE_OAUTH_CLIENT_ID
   - GOOGLE_OAUTH_CLIENT_SECRET
   - GOOGLE_OAUTH_REFRESH_TOKEN
```

O bot usa SA primeiro; se SA falhar autenticação ou retornar zero resultados,
cai no OAuth automaticamente.

### 6. Canva OAuth (~10 min)

A Canva Connect API usa OAuth 2.0 com PKCE — não tem token estático.
O bot precisa de Client ID, Client Secret e um refresh token inicial.

```
1. canva.com/developers → Create Integration (Team ou Public)
   - Scopes: design:content:read (mínimo), design:meta:read, asset:read
   - Configuration: copie Client ID e Client Secret
   - Authentication → Authorized redirects → adicione:
       http://127.0.0.1:8765/callback

2. Rodar script local uma vez:
   $env:CANVA_CLIENT_ID = "..."
   $env:CANVA_CLIENT_SECRET = "..."
   python scripts/get_canva_token.py
   → abre browser, você autoriza com conta Canva da BRASA
   → refresh_token aparece no terminal

3. Colar no Vercel:
   - CANVA_CLIENT_ID
   - CANVA_CLIENT_SECRET
   - CANVA_REFRESH_TOKEN
```

**Como o bot usa o Canva:** quando a descrição da task tem um link
`canva.com/design/{id}`, o bot pega metadata + exporta o slide em PNG alta-res
via `POST /exports` (job assíncrono), baixa e passa pro Claude Vision. A IA
"vê" o slide e extrai título, texto, tema — usa isso pra gerar o briefing.

⚠️ **Rotação de refresh token:** Canva invalida o refresh token a cada uso e
retorna um novo. Em dev, `canva_client.py` salva automaticamente o novo em
`secrets/.env.local`. Em produção (Vercel), o refresh token fica só em memória
dentro da invocação — ou seja, duas invocações próximas podem falhar. Pra
produção em alto volume, considere Upstash Redis pra persistir.

---

## Desenvolvimento local

### Setup (uma vez)

```powershell
pip install -r requirements.txt
Copy-Item .env.local.example secrets/.env.local
# Edite secrets/.env.local preenchendo os valores reais
```

Coloque também o JSON da Service Account em `secrets/` (qualquer nome com
`service` ou prefixo `automacao-clickup-`).

### Em cada sessão

```powershell
# Carrega todas as env vars + Service Account JSON do disco
. .\scripts\load_env.ps1

# Rodar pipeline direto pra uma task (sem precisar de webhook)
python -c "from lib.pipeline import run_pipeline; run_pipeline('TASK_ID')"

# Forçar re-geração ignorando o marcador anti-duplicata
python -c "from lib.pipeline import run_pipeline; run_pipeline('TASK_ID', force=True)"
```

### Scripts úteis

| Script | O que faz |
|---|---|
| `scripts/load_env.ps1` | Carrega `secrets/.env.local` + Service Account JSON na sessão PowerShell |
| `scripts/get_refresh_token.py` | Gera `GOOGLE_OAUTH_REFRESH_TOKEN` (browser + callback) |
| `scripts/get_canva_token.py` | Gera `CANVA_REFRESH_TOKEN` via OAuth + PKCE |
| `scripts/probe_canva.py <design_id>` | Diagnóstico da API Canva — lista metadata, pages e designs |

---

## Estrutura do projeto

```
brasa-briefing-bot/
├── api/
│   └── webhook.py          ← Entry point (Vercel Serverless)
├── lib/
│   ├── pipeline.py         ← Orquestra as 5 etapas
│   ├── clickup.py          ← REST API ClickUp (rich text + markdown_content)
│   ├── slack_client.py     ← Busca Slack + cargos dos assignees
│   ├── drive_client.py     ← Google Drive (SA primário + OAuth fallback)
│   ├── canva_client.py     ← Canva OAuth + exports PNG pro Claude Vision
│   ├── briefing.py         ← Claude API (Sonnet 4.5 + Vision) — gera briefing
│   ├── editorial.py        ← Linha editorial + prefixos + paletas por produto
│   └── alerts.py           ← Alertas automáticos
├── scripts/
│   ├── load_env.ps1        ← Carrega secrets/.env.local na sessão PowerShell
│   ├── get_refresh_token.py ← One-shot: gera GOOGLE_OAUTH_REFRESH_TOKEN
│   ├── get_canva_token.py  ← One-shot: gera CANVA_REFRESH_TOKEN (OAuth+PKCE)
│   └── probe_canva.py      ← Diagnóstico da API Canva
├── secrets/                ← Chaves locais (gitignored)
│   ├── .env.local
│   └── *service*.json
├── .env.local.example      ← Template do .env.local
├── requirements.txt        ← aiohttp, anthropic, cryptography
├── runtime.txt             ← python-3.12
├── vercel.json             ← maxDuration: 60s (runtime auto-detectado)
└── .gitignore              ← secrets/, .env*, *-service-account*.json, etc
```

---

## Como funciona

```
Analista muda status → "Em Progresso MKT"
          ↓
ClickUp dispara POST webhook
          ↓
Vercel Function acorda → responde 200 → dispara pipeline em thread
          ↓
    ┌─────┴────────────────────────────────┐
    ↓     (paralelo)                       ↓
ClickUp rich text          Slack + Drive + Canva (export PNG)
(com links embutidos)      (contexto + imagem do slide)
    └─────┬────────────────────────────────┘
          ↓
    Claude Sonnet 4.5 (+ Vision se houver slide)
    aplica ID visual BRASA e filtro de público
    (Legenda + Design: rascunho pronto)
    (MKT + Público + Emocional: direcionamentos)
          ↓
    ClickUp atualiza descrição
    (alertas no topo + conteúdo original preservado + marcador)
```

---

## Fase 2 (roadmap)

- [ ] Trocar `SLACK_TOKEN` por bot dedicado (`xoxb-...`)
- [ ] Campo "Arte" nas listas de conferência para link Canva estruturado
- [ ] Suporte a múltiplos design_ids na mesma descrição
- [ ] Dashboard de monitoramento de briefings gerados
