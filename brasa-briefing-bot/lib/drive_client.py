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
    Retorna string com títulos e trechos dos documentos encontrados.
    """
    try:
        token = await _get_access_token()
        if not token:
            return ""

        keywords = _build_query(tags, task_name)
        query = f"fullText contains '{keywords}' and trashed = false"

        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "q": query,
            "pageSize": 5,
            "orderBy": "modifiedTime desc",
            "fields": "files(id,name,modifiedTime,webViewLink,mimeType)",
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
        for f in files[:4]:
            name = f.get("name", "")
            link = f.get("webViewLink", "")
            mime = f.get("mimeType", "")
            # Marca documentos que provavelmente não são legíveis (Slides, etc.)
            readable = "✓" if "document" in mime or "spreadsheet" in mime else "○"
            lines.append(f"{readable} [{name}]({link})")

        return "\n".join(lines)

    except Exception as e:
        print(f"[drive] Exceção na busca: {e}")
        return ""


async def _get_access_token() -> str | None:
    """
    Obtém access token via Service Account JWT.
    """
    try:
        import time
        import base64
        import json
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend

        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not creds_json:
            print("[drive] GOOGLE_SERVICE_ACCOUNT_JSON não configurado")
            return None

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

        # Codifica o JWT manualmente
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
        print(f"[drive] Erro ao obter token: {e}")
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
