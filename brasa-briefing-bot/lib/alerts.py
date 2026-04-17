"""
BRASA Briefing Bot — Alertas automáticos
Valida data, tags, campos obrigatórios e regra corp.
"""

from datetime import datetime, timedelta
from lib.editorial import validate_date, DAY_NAMES


def build_alerts(
    name: str,
    tags: list,
    due_date_ms,
    date_created_ms,
    custom_fields: list,
    content_type: str,
    list_name: str,
) -> list[str]:
    """
    Retorna lista de strings de alerta para exibir no topo da descrição.
    """
    alerts = []

    # 1. Tags faltando
    if not tags:
        alerts.append(
            "⚠ Tags não adicionadas — lembre de adicionar campanha e tipo de post"
        )

    # 2. Validação de dia da semana
    day_alert = validate_date(due_date_ms, content_type, list_name)
    if day_alert:
        alerts.append(day_alert)

    # 3. Regra corp — margem mínima de 2 semanas
    if "corp" in tags and due_date_ms and date_created_ms:
        created_dt = datetime.fromtimestamp(int(date_created_ms) / 1000)
        due_dt = datetime.fromtimestamp(int(due_date_ms) / 1000)
        if (due_dt - created_dt).days < 14:
            alerts.append(
                "⚠ Tag 'corp' — margem mínima de 2 semanas não respeitada"
            )

    # 4. Custom fields vazios (lista @gobrasa)
    important_fields = {"Channel", "Data de postagem", "Design", "Marketing"}
    empty = [
        cf["name"]
        for cf in custom_fields
        if cf.get("name") in important_fields and not cf.get("value")
    ]
    if empty:
        alerts.append(f"⚠ Custom fields vazios: {', '.join(empty)}")

    # 5. Data no passado
    if due_date_ms:
        due_dt = datetime.fromtimestamp(int(due_date_ms) / 1000)
        if due_dt < datetime.now():
            alerts.append(
                f"⚠ Data de entrega {due_dt.strftime('%d/%m')} já passou"
            )

    return alerts
