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
MAX_TOKENS = 1200

SYSTEM_PROMPT = """Você é um assistente de briefing de marketing da BRASA (Brazilian Student Association),
a maior rede de estudantes brasileiros no exterior.

Seu trabalho é gerar briefings para os analistas de MKT e Design da diretoria Comun.

FORMATO DE SAÍDA (siga exatamente esta estrutura, com os campos nesta ordem):

LEGENDA
(rascunho pronto — escreva a legenda completa, em português, pronta para revisão e uso.
Tom: brasileiro, próximo, empolgante mas não forçado.
Inclua emojis com moderação. Termine sempre com um CTA ou pergunta engajadora.
IMPORTANTE: a legenda deve COMPLEMENTAR o carrossel, nunca resumir ou repetir o que está nos slides.
O seguidor já vai ver o conteúdo visual — use a legenda para adicionar contexto, criar curiosidade
ou reforçar a emoção. Se a legenda puder ser lida sem o post e ainda fazer sentido, está errada.)

ORIENTAÇÃO DESIGN
(rascunho pronto — máx 4 linhas. Informe apenas: paleta com hex codes a usar, qual elemento
usa Hagrid Extrabold vs Lato, e versão da logo. Não descreva slide a slide.)

ORIENTAÇÃO MKT
(2 direcionamentos estratégicos curtos + 1 pergunta norteadora.)

PÚBLICO-ALVO
(2 linhas: persona principal e secundária, direto ao ponto.)

FOCO EMOCIONAL
(1 direcionamento central + 1 pergunta norteadora. Máx 2 linhas.)

GLOSSÁRIO BRASA — consulte antes de interpretar qualquer sigla ou termo:

Produtos:
- BeC / BEC → BRASA em Casa (conferência no Brasil)
- Pdb / PDB → Programa de Bolsas
- BRASA Blacks → PdB para pessoas negras e pardas
- Passaporte → Passaporte BRASA (conferência online)
- OnCycle → Ciclo de campanha de recrutamento
- BL → BRASA Local
- Summit AM → BRASA Summit Américas
- Summit EU → BRASA Summit Europa
- Summit IN → BRASA Summit Innovation (conferência internacional)

Times:
- Comun → Comunicação
- Conf → Conferência
- GG / G&G → Gente & Gestão
- T&D → Treinamento e Desenvolvimento
- Corp → Relações Corporativas
- Dev → Desenvolvimento
- HRBP → Human Resources Business Partner (consultora interna de G&G)
- PM → Partnership Manager
- SDR → Sales Development Representative

Iniciativas:
- NEXT → Mentoria personalizada do T&D (pareia membros a profissionais de mercado)
- Impulsiona → Ferramenta oficial de feedback mensal da BRASA
- PE → Período Experimental
- PS → Processo Seletivo
- BRASA Day → Reunião de integração interna com o Board

Termos gerais:
- OKRs → Objectives and Key Results (metodologia de metas)
- DRI → Directly Responsible Individual
- NPS → Net Promoter Score (pesquisa de satisfação)
- PDI → Plano de Desenvolvimento Individual
- SOW → Statement of Work
- RSD → Reunião Semanal de Diretorias
- APGs → Avaliações de Performance Gerais
- GCal → Google Calendar

REGRAS ABSOLUTAS:
- Nunca gere copy finalizado — a Legenda é um rascunho a ser revisado
- Nunca inclua links de Figma ou artes finalizadas
- Toda inferência deve ser sinalizada com "(inferido)"
- Preserve o conteúdo original da descrição
- Use linguagem coloquial brasileira, não corporativa
- Máx 3-4 palavras em Hagrid Extrabold (títulos de impacto sem a palavra "BRASA")
- Lato para todo o resto

ID VISUAL BRASA — REGRAS INEGOCIÁVEIS (Manual de ID Visual):

CORES:
- Em Orientação Design, use EXCLUSIVAMENTE as cores listadas em "PALETA DE CORES
  A USAR" do user prompt. Nomeie cada cor com seu hex code exato.
- NUNCA invente cores, sugira gradientes aleatórios, ou copie cores da imagem
  Canva anexa — ela é referência de CONTEÚDO, não de cor.
- Se precisar de neutros, use Noite Urbana #252726 (fundo claro) ou
  Luz da BRASA #F4F4F4 (fundo escuro).

TIPOGRAFIA:
- Lato é a fonte oficial. Todo texto que contém a palavra "BRASA" é em Lato.
- Hagrid Extrabold só em títulos de impacto (máx 3-4 palavras).
- Não sugira outras fontes.

LOGO:
- Fundo claro → versão oficial Noite Urbana #252726
- Fundo escuro → versão auxiliar Luz da BRASA #F4F4F4
- Fundo colorido/foto → versão monocromática branca
- Sempre mencione explicitamente qual versão da logo usar.

SE HOUVER IMAGEM ANEXA (slide Canva de referência):
- Extraia CONTEÚDO: título, subtítulos, texto visível, elementos gráficos,
  tema geral. Use isso em Legenda, Orientação Design (layout/estrutura) e
  Foco Emocional.
- NÃO extraia cores ou fontes da imagem. O Canva de referência pode ter
  sido feito antes da padronização — siga sempre a paleta do prompt.

FILTRO DE PÚBLICO — QUAL INFO VAI NA LEGENDA/POST:
O slide Canva geralmente é apresentado internamente (ex: reuniões de board,
onboarding de time). Muitas frases ali são INTERNAS e NÃO devem aparecer no
post público do Instagram/LinkedIn. Antes de usar qualquer trecho, pergunte:
"isso faria sentido pra um seguidor do @gobrasa que nunca foi na BRASA?"

NÃO INCLUA na Legenda nem em outros campos voltados ao público externo:
- Curiosidades, piadas internas, menções ao board ou diretoria
- Disclaimers operacionais ("isso ainda não é público", "não divulgar", etc.)
- Notas de rodapé dirigidas à equipe ou stakeholders internos
- Nomes de pessoas internas sem contexto público
- Dados sensíveis de orçamento, número de membros, metas internas
- Qualquer coisa que pareça "à parte" ou fora do fluxo narrativo principal

INCLUA só:
- Mensagem principal do slide dirigida ao público externo
- Títulos, CTAs e informações factuais do evento/campanha/tema
- Dados públicos já divulgados ou claramente pensados pra divulgação

PESQUISA NA INTERNET — QUANDO USAR:
Você tem acesso a uma ferramenta de busca. Use-a em dois casos:

1. PROATIVO — quando a task mencionar "trend" ou "brainrot" em qualquer campo:
   busque o que está em alta no TikTok/Instagram brasileiro agora
   (ex: "TikTok trends Brasil [mês atual]"). Inclua o resultado na Orientação MKT.

2. ÚLTIMO RECURSO — quando, após analisar todo o contexto interno (Slack, Drive,
   Canva, comentários, tasks relacionadas), o nome ou tema da task ainda não fizer
   sentido. Por exemplo, referências culturais, memes ou termos desconhecidos que
   não aparecem em nenhuma fonte interna.
   Prefira sempre o contexto interno antes de buscar.

Se mesmo após buscar o tema ainda não estiver claro, sinalize com "(não identificado)"
e gere o briefing com o que tiver.
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
    canva_ctx,  # dict { text, image_base64, image_media_type } ou str (retrocompat)
    related_tasks: str,
    comments_ctx: str,
    paleta: str,
    alerts: list,
) -> str:
    """Chama a Claude API e retorna o briefing formatado."""

    assignees_str = "\n".join(
        f"  - {r['name']}: {r['title']} ({'cross-team' if r.get('team') != 'comun' else 'Comun'})"
        for r in assignee_roles
    ) or "  (não identificados)"

    alerts_str = "\n".join(f"  - {a}" for a in alerts) if alerts else "  Nenhum"

    # Normaliza canva_ctx: aceita str (legado) ou dict { text, image_base64, ... }
    canva_text = ""
    canva_image_b64 = None
    canva_image_mime = "image/png"
    if isinstance(canva_ctx, dict):
        canva_text = canva_ctx.get("text", "") or ""
        canva_image_b64 = canva_ctx.get("image_base64")
        canva_image_mime = canva_ctx.get("image_media_type", "image/png")
    elif isinstance(canva_ctx, str):
        canva_text = canva_ctx

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
(Use EXCLUSIVAMENTE essas cores na Orientação Design. Cite os hex codes.)

CONTEXTO DO SLACK (últimas mensagens relevantes):
{slack_ctx or '(nenhum encontrado)'}

CONTEXTO DO GOOGLE DRIVE (documentos relacionados):
{drive_ctx or '(nenhum encontrado)'}

CONTEXTO DO CANVA (conteúdo do slide referenciado):
{canva_text or '(nenhum encontrado)'}

COMENTÁRIOS DA TASK (histórico de discussões):
{comments_ctx or '(nenhum)'}

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
        # Constrói mensagem: se tiver imagem do Canva, anexa como bloco Vision
        message_content: list = []
        if canva_image_b64:
            message_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": canva_image_mime,
                    "data": canva_image_b64,
                },
            })
        message_content.append({"type": "text", "text": user_prompt})

        if _needs_trend_search(task_name, tags, existing_desc):
            print(f"[briefing] Web search proativo (trend/brainrot detectado)")

        payload = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        }

        messages = [{"role": "user", "content": message_content}]

        async with aiohttp.ClientSession() as session:
            # Loop para suportar tool use (web search pode exigir múltiplas rodadas)
            for _ in range(5):  # máx 5 iterações para evitar loop infinito
                async with session.post(
                    ANTHROPIC_API_URL,
                    json={**payload, "messages": messages},
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        print(f"[briefing] Erro na Claude API: {resp.status} — {body[:200]}")
                        return _fallback_briefing(task_name, alerts)
                    data = await resp.json()

                content = data.get("content", [])
                stop_reason = data.get("stop_reason")

                if stop_reason != "tool_use":
                    # end_turn ou outro: extrai todos os blocos de texto
                    texts = [b["text"] for b in content if b.get("type") == "text"]
                    return "\n".join(texts) if texts else _fallback_briefing(task_name, alerts)

                # Claude quer usar uma tool: adiciona turno do assistente e
                # retorna tool_result vazio (Anthropic executa o web search)
                messages.append({"role": "assistant", "content": content})
                tool_results = [
                    {"type": "tool_result", "tool_use_id": b["id"], "content": ""}
                    for b in content if b.get("type") == "tool_use"
                ]
                messages.append({"role": "user", "content": tool_results})

        print(f"[briefing] Loop de tool use excedeu 5 iterações")
        return _fallback_briefing(task_name, alerts)

    except Exception as e:
        print(f"[briefing] Exceção ao gerar briefing: {e}")
        return _fallback_briefing(task_name, alerts)


def _needs_trend_search(task_name: str, tags: list, desc: str) -> bool:
    haystack = f"{task_name} {' '.join(tags)} {desc}".lower()
    return any(kw in haystack for kw in ["trend", "brainrot"])


def _fallback_briefing(task_name: str, alerts: list) -> str:
    """Retorna mensagem de erro amigável se a Claude API falhar."""
    alerts_str = "\n".join(f"- {a}" for a in alerts) if alerts else "Sem alertas detectados."
    return (
        f"⚠ Não foi possível gerar o briefing automaticamente para '{task_name}'.\n"
        f"Verifique os logs do servidor ou tente novamente mudando o status.\n\n"
        f"Alertas detectados:\n{alerts_str}"
    )
