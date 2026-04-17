"""
BRASA Briefing Bot — Cliente Slack
Usa as credenciais do usuário autenticado (fase 1).
Fase 2: trocar SLACK_TOKEN pelo token do bot dedicado.
"""

import os
import aiohttp

SLACK_API_BASE = "https://slack.com/api"

# Canais autorizados (allowlist — IDs reais do workspace BRASA)
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


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['SLACK_TOKEN']}",
        "Content-Type": "application/json",
    }


async def search_slack(tags: list, task_name: str) -> str:
    """
    Busca mensagens relevantes nos canais autorizados.
    Retorna string formatada com o contexto encontrado.
    """
    keywords = _extract_keywords(tags, task_name)
    if not keywords:
        return ""

    try:
        async with aiohttp.ClientSession() as session:
            params = {
                "query": keywords,
                "count": 15,
                "sort": "timestamp",
                "sort_dir": "desc",
            }
            async with session.get(
                f"{SLACK_API_BASE}/search.messages",
                params=params,
                headers=_headers(),
            ) as resp:
                data = await resp.json()

        if not data.get("ok"):
            print(f"[slack] Erro na busca: {data.get('error')}")
            return ""

        messages = data.get("messages", {}).get("matches", [])

        # Filtra só canais permitidos
        filtered = [
            m for m in messages
            if m.get("channel", {}).get("id") in ALLOWED_CHANNELS
        ][:8]

        if not filtered:
            return ""

        lines = []
        for m in filtered:
            channel = m.get("channel", {}).get("name", "?")
            user = m.get("username", "?")
            text = m.get("text", "")[:200].replace("\n", " ")
            lines.append(f"[#{channel}] {user}: {text}")

        return "\n".join(lines)

    except Exception as e:
        print(f"[slack] Exceção na busca: {e}")
        return ""


async def get_assignee_roles(assignees: list) -> list:
    """
    Busca o cargo de cada assignee via perfil do Slack (campo title).
    Retorna lista de dicts com name, title, team.
    """
    roles = []
    try:
        async with aiohttp.ClientSession() as session:
            for a in assignees:
                email = a.get("email", "")
                if not email:
                    roles.append({
                        "name": a.get("username", ""),
                        "title": "(cargo não encontrado)",
                        "team": "desconhecido",
                    })
                    continue

                params = {"email": email}
                async with session.get(
                    f"{SLACK_API_BASE}/users.lookupByEmail",
                    params=params,
                    headers=_headers(),
                ) as resp:
                    data = await resp.json()

                if not data.get("ok"):
                    roles.append({
                        "name": a.get("username", ""),
                        "title": "(cargo não encontrado)",
                        "team": "desconhecido",
                    })
                    continue

                profile = data.get("user", {}).get("profile", {})
                title = profile.get("title", "")
                team = "comun" if "COMUN" in title.upper() else "externo"

                roles.append({
                    "name": a.get("username", ""),
                    "title": title,
                    "team": team,
                    "slack_id": data["user"]["id"],
                })

    except Exception as e:
        print(f"[slack] Exceção ao buscar cargos: {e}")

    return roles


def _extract_keywords(tags: list, task_name: str) -> str:
    """Extrai keywords relevantes da task para a busca no Slack."""
    # Remove prefixos comuns do nome
    import re
    prefixes = [
        r"^POST Inn:\s*", r"^Corp:\s*", r"^REDE:\s*", r"^EDU:\s*",
        r"^Stories:\s*", r"^Reels:\s*", r"^CAM:\s*", r"^VÍDEO\s*",
        r"^Institucional:\s*", r"^Newsletter:\s*", r"^Takeover\s*",
    ]
    name = task_name
    for p in prefixes:
        name = re.sub(p, "", name, flags=re.IGNORECASE).strip()

    parts = tags[:3] + name.split()[:4]
    return " ".join(parts)
