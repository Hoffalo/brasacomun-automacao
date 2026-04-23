"""
BRASA Briefing Bot — Cliente Google Drive
Usa Service Account com acesso de leitura ao Drive da BRASA.
"""

import os
import json
import aiohttp


DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


async def search_drive(tags: list, task_name: str) -> str:
    """
    Busca documentos relevantes no Drive da BRASA.
    Sempre inclui o Manual de Comunicação no topo dos resultados.
    Estratégia: Service Account primeiro; se falhar auth OU retornar vazio,
    tenta OAuth (token do usuário, herda acesso pessoal às Shared Drives).
    """
    import asyncio

    keywords = _build_query(tags, task_name)

    token = await _get_sa_access_token()
    if not token:
        token = await _get_oauth_access_token()
    if not token:
        return ""

    # Busca o manual de comunicação e os docs da task em paralelo
    manual_result, task_result = await asyncio.gather(
        _search_with_token(token, "manual de comunicação BRASA", max_results=1),
        _search_with_token(token, keywords, max_results=4),
    )

    parts = []
    if manual_result:
        parts.append("📘 MANUAL DE COMUNICAÇÃO:\n" + manual_result)
    if task_result:
        parts.append("📁 DOCUMENTOS RELACIONADOS:\n" + task_result)
    return "\n\n".join(parts)


async def _search_with_token(token: str, keywords: str, max_results: int = 4) -> str:
    try:
        query = f"fullText contains '{keywords}' and trashed = false"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "q": query,
            "pageSize": max_results + 1,
            "orderBy": "modifiedTime desc",
            "fields": "files(id,name,modifiedTime,webViewLink,mimeType)",
            "includeItemsFromAllDrives": "true",
            "supportsAllDrives": "true",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{DRIVE_API_BASE}/files",
                params=params,
                headers=headers,
            ) as resp:
                data = await resp.json()

        files = data.get("files", [])
        if not files:
            return ""

        lines = []
        for f in files[:max_results]:
            name = f.get("name", "")
            link = f.get("webViewLink", "")
            mime = f.get("mimeType", "")
            readable = "✓" if "document" in mime or "spreadsheet" in mime else "○"
            lines.append(f"{readable} [{name}]({link})")

        return "\n".join(lines)

    except Exception as e:
        print(f"[drive] Exceção na busca: {e}")
        return ""


async def _get_sa_access_token() -> str | None:
    """Access token via Service Account JWT."""
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not creds_json:
        return None

    try:
        import time
        import base64
        import json
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend

        creds = json.loads(creds_json)
        client_email = creds["client_email"]
        private_key_str = creds["private_key"]
        token_uri = creds.get("token_uri", "https://oauth2.googleapis.com/token")

        now = int(time.time())
        claim = {
            "iss": client_email,
            "scope": " ".join(DRIVE_SCOPES),
            "aud": token_uri,
            "iat": now,
            "exp": now + 3600,
        }

        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        payload = b64url(json.dumps(claim).encode())
        signing_input = f"{header}.{payload}".encode()

        private_key = serialization.load_pem_private_key(
            private_key_str.encode(), password=None, backend=default_backend()
        )
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        jwt = f"{header}.{payload}.{b64url(signature)}"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": jwt,
                },
            ) as resp:
                token_data = await resp.json()
                return token_data.get("access_token")

    except Exception as e:
        print(f"[drive] SA token falhou: {e}")
        return None


async def _get_oauth_access_token() -> str | None:
    """Access token via OAuth refresh token (conta pessoal BRASA)."""
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    refresh_token = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN", "")

    if not (client_id and client_secret and refresh_token):
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            ) as resp:
                data = await resp.json()
                return data.get("access_token")
    except Exception as e:
        print(f"[drive] OAuth token falhou: {e}")
        return None


def _build_query(tags: list, task_name: str) -> str:
    """Constrói string de busca a partir de tags e nome da task."""
    import re
    # Remove prefixos
    name = re.sub(
        r"^(POST Inn|Corp|REDE|EDU|Stories|Reels|CAM|VÍDEO|Institucional|Newsletter|Takeover)[:\s]*",
        "", task_name, flags=re.IGNORECASE
    ).strip()
    # Pega as palavras mais significativas
    words = [w for w in (tags[:2] + name.split()[:3]) if len(w) > 3]
    return " ".join(words[:4]) if words else task_name[:30]
