"""
BRASA Briefing Bot — Geração do briefing via Anthropic API
Legenda e Orientação Design: rascunho pronto para correção.
Demais campos: direcionamentos + perguntas norteadoras.
"""

import os
import aiohttp
import json

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1800

SYSTEM_PROMPT = """Você é um assistente de briefing de marketing da BRASA (Brazilian Student Association), 
a maior rede de estudantes brasileiros no exterior.

Seu trabalho é gerar briefings para os analistas de MKT e Design da diretoria Comun.

FORMATO DE SAÍDA (siga exatamente esta estrutura, com os campos nesta ordem):

LEGENDA
(rascunho pronto — escreva a legenda completa, em português, pronta para revisão e uso. 
Tom: brasileiro, próximo, empolgante mas não forçado. 
Inclua emojis com moderação. Termine sempre com um CTA ou pergunta engajadora.)

ORIENTAÇÃO DESIGN
(rascunho pronto — descreva o design completo: formato, número de slides se carrossel, 
o que vai em cada slide, paleta de cores específica com hex codes, tipografia, 
versão da logo. Seja diretivo e específico o suficiente para a Clara começar a produzir sem perguntar.)

ORIENTAÇÃO MKT
(2-3 direcionamentos estratégicos curtos + 1-2 perguntas norteadoras.
Inclua contexto do momento da campanha e ações de pós-postagem.)

PÚBLICO-ALVO
(1 parágrafo identificando persona principal e secundária, sem bullet points.)

FOCO EMOCIONAL
(2-3 direcionamentos sobre a emoção central + 1-2 perguntas norteadoras.)

REGRAS ABSOLUTAS:
- Nunca gere copy finalizado — a Legenda é um rascunho a ser revisado
- Nunca inclua links de Figma ou artes finalizadas
- Toda inferência deve ser sinalizada com "(inferido)"
- Preserve o conteúdo original da descrição
- Use linguagem coloquial brasileira, não corporativa
- Máx 3-4 palavras em Hagrid Extrabold (títulos de impacto sem a palavra "BRASA")
- Lato para todo o resto
"""


async def generate_briefing(
    task_name: str,
    content_type: str,
    platform_type: str,
    list_name: str,
    tags: list,
    assignee_roles: list,
    is_cross_team: bool,
    existing_desc: str,
    slack_ctx: str,
    drive_ctx: str,
    canva_ctx: str,
    related_tasks: str,
    paleta: str,
    alerts: list,
) -> str:
    """Chama a Claude API e retorna o briefing formatado."""

    assignees_str = "\n".join(
        f"  - {r['name']}: {r['title']} ({'cross-team' if r.get('team') != 'comun' else 'Comun'})"
        for r in assignee_roles
    ) or "  (não identificados)"

    alerts_str = "\n".join(f"  - {a}" for a in alerts) if alerts else "  Nenhum"

    user_prompt = f"""TASK:
- Nome: {task_name}
- Tipo de conteúdo: {content_type}
- Plataforma: {list_name} ({platform_type})
- Tags: {', '.join(tags) if tags else '(nenhuma)'}
- Cross-team: {'Sim' if is_cross_team else 'Não'}
- Assignees:
{assignees_str}
- Alertas já detectados:
{alerts_str}

DESCRIÇÃO EXISTENTE (preservar integralmente):
{existing_desc or '(vazia)'}

PALETA DE CORES A USAR (Manual de ID Visual BRASA — seção 1.3):
{paleta}

CONTEXTO DO SLACK (últimas mensagens relevantes):
{slack_ctx or '(nenhum encontrado)'}

CONTEXTO DO GOOGLE DRIVE (documentos relacionados):
{drive_ctx or '(nenhum encontrado)'}

CONTEXTO DO CANVA (conteúdo do slide referenciado):
{canva_ctx or '(nenhum encontrado)'}

TASKS RELACIONADAS (mesmas tags, últimos 3 meses):
{related_tasks or '(nenhuma)'}

Gere o briefing completo seguindo exatamente o formato do system prompt.
Lembre: Legenda e Orientação Design são rascunhos prontos para revisão.
Os demais campos são direcionamentos + perguntas norteadoras."""

    try:
        token = os.environ["ANTHROPIC_API_KEY"]
        headers = {
            "x-api-key": token,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                ANTHROPIC_API_URL, json=payload, headers=headers
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[briefing] Erro na Claude API: {resp.status} — {body[:200]}")
                    return _fallback_briefing(task_name, alerts)
                data = await resp.json()

        return data["content"][0]["text"]

    except Exception as e:
        print(f"[briefing] Exceção ao gerar briefing: {e}")
        return _fallback_briefing(task_name, alerts)


def _fallback_briefing(task_name: str, alerts: list) -> str:
    """Retorna mensagem de erro amigável se a Claude API falhar."""
    return (
        f"⚠ Não foi possível gerar o briefing automaticamente para '{task_name}'.\n"
        f"Verifique os logs do servidor ou tente novamente mudando o status.\n\n"
        f"Alertas detectados:\n" + "\n".join(f"- {a}" for a in alerts)
        if alerts else "Sem alertas detectados."
    )
