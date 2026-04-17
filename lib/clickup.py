"""
BRASA Briefing Bot — Cliente ClickUp
Usa a REST API diretamente (não o MCP) para ter acesso ao rich text.
"""

import os
import aiohttp


CLICKUP_API_BASE = "https://api.clickup.com/api/v2"


def _headers() -> dict:
    return {"Authorization": os.environ["CLICKUP_API_TOKEN"]}


async def get_task_rich(task_id: str) -> dict | None:
    """
    Busca a task com markdown_description=true para preservar links embutidos.
    Isso é essencial para extrair links do Canva da descrição.
    """
    url = f"{CLICKUP_API_BASE}/task/{task_id}"
    params = {
        "include_markdown_description": "true",
        "custom_fields": "true",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=_headers()) as resp:
                if resp.status != 200:
                    print(f"[clickup] Erro ao buscar task {task_id}: {resp.status}")
                    return None
                return await resp.json()
    except Exception as e:
        print(f"[clickup] Exceção ao buscar task {task_id}: {e}")
        return None


async def update_task_description(task_id: str, description: str) -> bool:
    """
    Atualiza a descrição da task no ClickUp como rich text.
    Usa markdown_content (ClickUp renderiza markdown → rich text).
    """
    url = f"{CLICKUP_API_BASE}/task/{task_id}"
    payload = {"markdown_content": description}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(
                url, json=payload, headers=_headers()
            ) as resp:
                if resp.status not in (200, 204):
                    body = await resp.text()
                    print(f"[clickup] Erro ao atualizar task {task_id}: {resp.status} — {body}")
                    return False
                return True
    except Exception as e:
        print(f"[clickup] Exceção ao atualizar task {task_id}: {e}")
        return False


async def post_task_comment(task_id: str, comment: str) -> bool:
    """
    Posta um comentário na task. Preserva a descrição original intacta.
    comment_text aceita markdown básico (títulos, bold, listas, links).
    """
    url = f"{CLICKUP_API_BASE}/task/{task_id}/comment"
    payload = {"comment_text": comment, "notify_all": False}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers={**_headers(), "Content-Type": "application/json"}
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    print(f"[clickup] Erro ao postar comentário {task_id}: {resp.status} — {body}")
                    return False
                return True
    except Exception as e:
        print(f"[clickup] Exceção ao postar comentário {task_id}: {e}")
        return False


async def get_task_comments(task_id: str) -> list:
    """Lista comentários da task. Usado pra checar anti-duplicata."""
    url = f"{CLICKUP_API_BASE}/task/{task_id}/comment"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_headers()) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("comments", [])
    except Exception as e:
        print(f"[clickup] Exceção ao buscar comentários {task_id}: {e}")
        return []
