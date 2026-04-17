"""
BRASA Briefing Bot — Cliente Canva
Extrai links do Canva do markdown_description da task
e lê o conteúdo do slide referenciado.
"""

import os
import re
import aiohttp

CANVA_API_BASE = "https://api.canva.com/rest/v1"

# Regex para extrair design_id de URLs do Canva
# Formatos: /design/DAGZYat8Egk/... ou /d/abc123...
CANVA_ID_PATTERN = re.compile(
    r"canva\.com/(?:design|d)/([A-Za-z0-9_-]{11})"
)

# Regex para extrair número de slide da instrução na descrição
SLIDE_NUMBER_PATTERN = re.compile(
    r"slide[s]?\s+(\d+)", re.IGNORECASE
)


async def get_canva_context(markdown_desc: str) -> str:
    """
    1. Extrai design_id do markdown_description da task
    2. Detecta número do slide mencionado (ex: "slide 21")
    3. Lê o conteúdo daquele slide via API do Canva
    Retorna string com o conteúdo encontrado, ou "" se não houver.
    """
    if not markdown_desc:
        return ""

    # Extrai design_id
    match = CANVA_ID_PATTERN.search(markdown_desc)
    if not match:
        return ""
    design_id = match.group(1)

    # Extrai número do slide (default: lê slide 1 se não especificado)
    slide_match = SLIDE_NUMBER_PATTERN.search(markdown_desc)
    page_number = int(slide_match.group(1)) if slide_match else 1

    try:
        token = await _get_access_token()
        if not token:
            print("[canva] Sem token (CANVA_API_TOKEN ou CANVA_REFRESH_TOKEN)")
            return ""

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Lê o conteúdo do slide específico
        url = f"{CANVA_API_BASE}/designs/{design_id}/content"
        payload = {
            "content_types": ["richtexts"],
            "pages": [page_number],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    print(f"[canva] Erro ao ler design {design_id}: {resp.status}")
                    return ""
                data = await resp.json()

        # Extrai o texto do slide
        content = _extract_text(data)
        if content:
            return f"[Canva — slide {page_number} do design {design_id}]:\n{content}"
        return ""

    except Exception as e:
        print(f"[canva] Exceção ao ler design: {e}")
        return ""


async def _get_access_token() -> str:
    """
    Devolve um access token do Canva.
    Preferência:
      1. CANVA_API_TOKEN (legado / direto — bearer estático)
      2. OAuth refresh flow: CANVA_CLIENT_ID + CANVA_CLIENT_SECRET + CANVA_REFRESH_TOKEN
    """
    direct = os.environ.get("CANVA_API_TOKEN", "")
    if direct:
        return direct

    client_id = os.environ.get("CANVA_CLIENT_ID", "")
    client_secret = os.environ.get("CANVA_CLIENT_SECRET", "")
    refresh_token = os.environ.get("CANVA_REFRESH_TOKEN", "")
    if not (client_id and client_secret and refresh_token):
        return ""

    try:
        import base64

        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CANVA_API_BASE}/oauth/token",
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            ) as resp:
                data = await resp.json()
                return data.get("access_token", "")
    except Exception as e:
        print(f"[canva] Erro refresh token: {e}")
        return ""


def _extract_text(api_response: dict) -> str:
    """Extrai texto legível da resposta da API do Canva."""
    try:
        items = api_response.get("items", []) or api_response.get("richtexts", [])
        texts = []
        for item in items:
            # Suporta diferentes formatos de resposta
            text = (
                item.get("text")
                or item.get("content")
                or item.get("value")
                or ""
            )
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
        return "\n".join(texts) if texts else str(api_response)[:500]
    except Exception:
        return str(api_response)[:500]
