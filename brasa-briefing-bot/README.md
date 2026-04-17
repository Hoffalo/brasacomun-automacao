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

### 2. Variáveis de ambiente no Vercel (~5 min)

Em **Settings → Environment Variables**, adicione:

| Variável | Onde encontrar |
|---|---|
| `CLICKUP_API_TOKEN` | ClickUp → Settings → Apps → API Token (`pk_...`) |
| `CLICKUP_WEBHOOK_SECRET` | Gerado no passo 3 abaixo |
| `SLACK_TOKEN` | Slack → perfil → Preferências → (ou token OAuth pessoal `xoxp-...`) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google Cloud Console → Service Accounts → JSON key (minificado) |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys (`sk-ant-...`) |
| `CANVA_API_TOKEN` | canva.com/developers → Create Integration → Token |

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

### 5. Google Drive Service Account (~15 min)

```
1. console.cloud.google.com → New Project → Enable Drive API
2. IAM & Admin → Service Accounts → Create → Download JSON key
3. Compartilhe o Drive da BRASA com o email da Service Account (viewer)
4. Minifique o JSON: python3 -c "import json,sys; print(json.dumps(json.load(open('key.json'))))"
5. Cole o resultado em GOOGLE_SERVICE_ACCOUNT_JSON
```

### 6. Canva API Token (~5 min)

```
1. canva.com/developers → Create Integration
2. Scopes necessários: design:content:read
3. Gerar token e salvar em CANVA_API_TOKEN
```

---

## Estrutura do projeto

```
brasa-briefing-bot/
├── api/
│   └── webhook.py          ← Entry point (Vercel Serverless)
├── lib/
│   ├── pipeline.py         ← Orquestra as 5 etapas
│   ├── clickup.py          ← REST API ClickUp (rich text)
│   ├── slack_client.py     ← Busca Slack + cargos dos assignees
│   ├── drive_client.py     ← Busca Google Drive
│   ├── canva_client.py     ← Lê slides do Canva via link na descrição
│   ├── briefing.py         ← Claude API — gera o briefing
│   ├── editorial.py        ← Linha editorial + prefixos + paletas
│   └── alerts.py           ← Alertas automáticos
├── requirements.txt
└── vercel.json
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
    ┌─────┴──────────────────────────┐
    ↓     (paralelo)                 ↓
ClickUp rich text          Slack + Drive + Canva
(com links embutidos)      (contexto relevante)
    └─────┬──────────────────────────┘
          ↓
    Claude API gera briefing
    (Legenda + Design: rascunho pronto)
    (MKT + Público + Emocional: direcionamentos)
          ↓
    ClickUp atualiza descrição
    (alertas no topo + conteúdo original preservado)
```

---

## Fase 2 (roadmap)

- [ ] Trocar `SLACK_TOKEN` por bot dedicado (`xoxb-...`)
- [ ] Campo "Arte" nas listas de conferência para link Canva estruturado
- [ ] Suporte a múltiplos design_ids na mesma descrição
- [ ] Dashboard de monitoramento de briefings gerados
