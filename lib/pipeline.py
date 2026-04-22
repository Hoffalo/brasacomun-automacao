"""
BRASA Briefing Bot — Pipeline principal
Etapas: leitura → validação → contexto (paralelo) → geração → output
"""

import asyncio
import traceback

from lib.clickup import get_task_rich, update_task_description, get_task_comments
from lib.slack_client import search_slack, get_assignee_roles
from lib.drive_client import search_drive
from lib.canva_client import get_canva_context
from lib.briefing import generate_briefing
from lib.editorial import identify_prefix, validate_date, PALETA_POR_PRODUTO
from lib.alerts import build_alerts

COMUN_SPACE_ID = "90111669766"
BRIEFING_MARKER = "<!-- briefing-gerado -->"
COMMENT_MARKER = "🤖 BRIEFING AUTOMÁTICO"
FALLBACK_PREFIX = "⚠ Não foi possível gerar"


def run_pipeline(task_id: str, force: bool = False):
    """Entry point síncrono chamado pelo webhook (sync) ou CLI."""
    try:
        asyncio.run(_pipeline(task_id, force=force))
    except Exception as e:
        print(f"[pipeline] Erro na task {task_id}: {type(e).__name__}: {e}")
        print(f"[pipeline] Traceback: {traceback.format_exc()}")


async def _pipeline(task_id: str, force: bool = False):
    print(f"[pipeline] Iniciando task {task_id}")

    # ── ETAPA 1: Leitura da task (rich text) ──────────────────────────────
    task = await get_task_rich(task_id)
    if not task:
        print(f"[pipeline] Task {task_id} não encontrada")
        return

    # Guard: só roda no espaço Comun
    if task.get("space", {}).get("id") != COMUN_SPACE_ID:
        print(f"[pipeline] Task fora do espaço Comun — ignorando")
        return

    desc = task.get("markdown_description") or task.get("description") or ""

    # Guard: anti-duplicata (bypass com force=True)
    if BRIEFING_MARKER in desc and not force:
        print(f"[pipeline] Briefing já gerado — ignorando (use force=True pra refazer)")
        return

    name = task.get("name", "")
    tags = [t["name"] for t in task.get("tags", [])]
    due_date_ms = task.get("due_date")
    date_created_ms = task.get("date_created")
    list_name = task.get("list", {}).get("name", "")
    custom_fields = task.get("custom_fields", [])
    assignees_raw = task.get("assignees", [])

    # Identifica tipo de conteúdo pelo prefixo
    content_type, platform_type = identify_prefix(name)

    # Paleta de cores por produto (cruza tags com manual de ID visual)
    paleta = _get_paleta(tags, list_name)

    # ── ETAPA 2: Cargos dos assignees via Slack ───────────────────────────
    assignee_roles = await get_assignee_roles(assignees_raw)
    is_cross_team = any(r.get("team") != "comun" for r in assignee_roles)

    # ── ETAPA 2b: Validação de data e alertas ─────────────────────────────
    alerts = build_alerts(
        name=name,
        tags=tags,
        due_date_ms=due_date_ms,
        date_created_ms=date_created_ms,
        custom_fields=custom_fields,
        content_type=content_type,
        list_name=list_name,
    )

    # ── ETAPA 3: Coleta de contexto em paralelo ───────────────────────────
    keywords = " ".join(tags) + " " + name
    slack_ctx, drive_ctx, canva_ctx, related_tasks, raw_comments = await asyncio.gather(
        search_slack(tags, name),
        search_drive(tags, name),
        get_canva_context(desc),        # extrai design_id do markdown_description
        _get_related_tasks(tags, task_id),
        get_task_comments(task_id),
    )
    comments_ctx = _format_comments(raw_comments)

    # ── ETAPA 4: Geração do briefing via Claude API ───────────────────────
    briefing = await generate_briefing(
        task_name=name,
        content_type=content_type,
        platform_type=platform_type,
        list_name=list_name,
        tags=tags,
        assignee_roles=assignee_roles,
        is_cross_team=is_cross_team,
        existing_desc=desc,
        slack_ctx=slack_ctx,
        drive_ctx=drive_ctx,
        canva_ctx=canva_ctx,
        related_tasks=related_tasks,
        comments_ctx=comments_ctx,
        paleta=paleta,
        alerts=alerts,
    )

    # ── ETAPA 5: Output na descrição da task ──────────────────────────────
    is_fallback = (briefing or "").lstrip().startswith(FALLBACK_PREFIX)
    new_desc = _build_output(
        existing_desc=desc,
        alerts=alerts,
        briefing=briefing,
        include_marker=not is_fallback,
    )
    await update_task_description(task_id, new_desc)
    if is_fallback:
        print(f"[pipeline] Fallback escrito — próximo trigger fará retry (sem marcador)")
    else:
        print(f"[pipeline] Briefing gerado com sucesso para task {task_id}")


def _format_comments(comments: list) -> str:
    """Formata lista de comentários do ClickUp para texto legível pelo Claude.
    Prefere markdown_description (rich text com links) sobre comment_text (plain)."""
    if not comments:
        return ""
    lines = []
    for c in comments[:20]:  # máx 20 comentários
        user = c.get("user", {}).get("username") or c.get("user", {}).get("email", "?")
        text = (c.get("markdown_description") or c.get("comment_text", "")).strip()
        if text:
            lines.append(f"[{user}]: {text}")
    return "\n".join(lines)


def _get_paleta(tags: list, list_name: str) -> str:
    """Cruza tags e nome da lista com o manual de ID visual (seção 1.3)."""
    for tag in tags:
        tag_lower = tag.lower()
        for produto, paleta in PALETA_POR_PRODUTO.items():
            if produto in tag_lower:
                return paleta
    # Fallback: infere pelo nome da lista
    list_lower = list_name.lower()
    for produto, paleta in PALETA_POR_PRODUTO.items():
        if produto in list_lower:
            return paleta
    return PALETA_POR_PRODUTO.get("default", "Verde escuro #03571A + Amarelo #FFCC02 + Azul vívido #065FD8")


async def _get_related_tasks(tags: list, current_task_id: str) -> str:
    """Busca tasks relacionadas pelas mesmas tags nos últimos 3 meses."""
    if not tags:
        return ""
    try:
        import aiohttp
        import os
        from datetime import datetime, timedelta

        token = os.environ["CLICKUP_API_TOKEN"]
        three_months_ago = int((datetime.now() - timedelta(days=90)).timestamp() * 1000)

        url = "https://api.clickup.com/api/v2/team/9011435781/task"
        params = {
            "space_ids[]": "90111669766",
            "tags[]": tags[:2],  # máx 2 tags para não sobre-filtrar
            "due_date_gt": three_months_ago,
            "include_closed": "true",
            "page": 0,
        }
        headers = {"Authorization": token}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                data = await resp.json()
                tasks = data.get("tasks", [])
                # Remove a task atual
                tasks = [t for t in tasks if t.get("id") != current_task_id][:5]
                if not tasks:
                    return ""
                lines = []
                for t in tasks:
                    status = t.get("status", {}).get("status", "")
                    lines.append(f"- [{status}] {t['name']}")
                return "\n".join(lines)
    except Exception as e:
        print(f"[pipeline] Erro ao buscar tasks relacionadas: {e}")
        return ""


def _build_output(
    existing_desc: str, alerts: list, briefing: str, include_marker: bool = True
) -> str:
    """Monta a descrição final com alertas + conteúdo original + briefing.

    include_marker=False quando o briefing é fallback de erro, pra permitir
    retry automático na próxima mudança de status.
    """
    parts = []

    if alerts:
        parts.append("⚠️ ALERTAS AUTOMÁTICOS")
        parts.append("─" * 40)
        for alert in alerts:
            parts.append(alert)
        parts.append("")

    # Preserva conteúdo original MAS remove briefings gerados anteriores
    # (impede acúmulo quando retries acontecem).
    original = _strip_prior_briefing(existing_desc or "").strip()
    if original:
        parts.append(original)
        parts.append("")

    parts.append("─" * 40)
    parts.append("BRIEFING GERADO AUTOMATICAMENTE")
    parts.append("─" * 40)
    parts.append(briefing)

    if include_marker:
        parts.append("")
        parts.append(BRIEFING_MARKER)

    return "\n".join(parts)


def _strip_prior_briefing(desc: str) -> str:
    """Remove a seção 'BRIEFING GERADO AUTOMATICAMENTE' e qualquer marcador
    de uma descrição anterior, pra evitar empilhar briefings a cada retry."""
    if not desc:
        return desc
    markers = [
        "⚠️ ALERTAS AUTOMÁTICOS",
        "─" * 40 + "\nBRIEFING GERADO AUTOMATICAMENTE",
        "BRIEFING GERADO AUTOMATICAMENTE",
    ]
    for m in markers:
        idx = desc.find(m)
        if idx != -1:
            desc = desc[:idx]
    # Remove marcador HTML oculto se estiver solto
    desc = desc.replace(BRIEFING_MARKER, "")
    return desc
