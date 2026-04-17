"""
BRASA Briefing Bot — Cliente Canva
Extrai links do Canva do markdown_description da task, pega metadata + thumbnail
da página referenciada e entrega um contexto pronto pro briefing (texto + imagem
pra Claude Vision).
"""

import base64
import os
import re
import aiohttp

CANVA_API_BASE = "https://api.canva.com/rest/v1"

CANVA_ID_PATTERN = re.compile(r"canva\.com/(?:design|d)/([A-Za-z0-9_-]{11})")
SLIDE_NUMBER_PATTERN = re.compile(r"slide[s]?\s+(\d+)", re.IGNORECASE)


async def get_canva_context(markdown_desc: str) -> dict:
    """
    Extrai design_id e número de slide, exporta página específica em alta
    resolução (PNG via job assíncrono da Canva) e devolve a imagem pra Vision.

    Fluxo:
      GET /designs/{id}            → metadata (título, total de páginas)
      POST /exports                → cria job de export PNG da página pedida
      GET /exports/{id}            → polling até status=success
      download da URL              → base64 pra Claude

    Se export falhar, cai pra thumbnail de baixa resolução (fallback).
    """
    empty = {"text": "", "image_base64": None, "image_media_type": "image/png"}
    if not markdown_desc:
        return empty

    match = CANVA_ID_PATTERN.search(markdown_desc)
    if not match:
        return empty
    design_id = match.group(1)

    slide_match = SLIDE_NUMBER_PATTERN.search(markdown_desc)
    page_number = int(slide_match.group(1)) if slide_match else 1

    token = await _get_access_token()
    if not token:
        print("[canva] Sem token (CANVA_API_TOKEN ou CANVA_REFRESH_TOKEN)")
        return empty

    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with aiohttp.ClientSession() as session:
            # 1. Metadata
            async with session.get(
                f"{CANVA_API_BASE}/designs/{design_id}", headers=headers
            ) as resp:
                if resp.status != 200:
                    print(f"[canva] GET design {design_id} falhou: {resp.status}")
                    return empty
                meta = await resp.json()
            title = meta.get("design", {}).get("title", "")

            # 2. Pages (pra validar nº de página + fallback de thumbnail)
            async with session.get(
                f"{CANVA_API_BASE}/designs/{design_id}/pages", headers=headers
            ) as resp:
                pages_data = await resp.json() if resp.status == 200 else {}
                pages = pages_data.get("items", [])

            if pages:
                valid_indices = [p.get("index") for p in pages]
                if page_number not in valid_indices:
                    page_number = valid_indices[0]

            # 3. Export de alta resolução da página pedida
            image_b64 = await _export_page_png(
                session, headers, design_id, page_number
            )

            # 3b. Fallback: thumbnail se export falhou
            if not image_b64 and pages:
                target = next(
                    (p for p in pages if p.get("index") == page_number), pages[0]
                )
                thumb_url = target.get("thumbnail", {}).get("url", "")
                if thumb_url:
                    async with session.get(thumb_url) as img_resp:
                        if img_resp.status == 200:
                            image_b64 = base64.standard_b64encode(
                                await img_resp.read()
                            ).decode()
                            print("[canva] Usando thumbnail (baixa res) como fallback")

        total_pages = len(pages) if pages else "?"
        text = (
            f"Design Canva: \"{title}\" (id {design_id})\n"
            f"Referência no briefing: slide {page_number} de {total_pages}.\n"
            f"Imagem da página anexada para análise visual."
            if image_b64
            else f"Design Canva: \"{title}\" (id {design_id}) — slide {page_number} solicitado, sem imagem disponível."
        )
        return {
            "text": text,
            "image_base64": image_b64,
            "image_media_type": "image/png",
        }

    except Exception as e:
        print(f"[canva] Exceção ao ler design: {e}")
        return empty


async def _export_page_png(
    session: aiohttp.ClientSession,
    headers: dict,
    design_id: str,
    page_number: int,
    max_wait_seconds: int = 20,
) -> str | None:
    """
    Cria job de export PNG, faz polling até completar, baixa e devolve base64.
    Retorna None se falhar.
    """
    import asyncio

    # 1. Cria job
    payload = {
        "design_id": design_id,
        "format": {
            "type": "png",
            "pages": [page_number],
            "export_quality": "regular",
        },
    }
    try:
        async with session.post(
            f"{CANVA_API_BASE}/exports",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        ) as resp:
            body = await resp.text()
            if resp.status not in (200, 201, 202):
                print(f"[canva] POST /exports falhou {resp.status}: {body[:200]}")
                return None
            import json as _json
            data = _json.loads(body)
            job = data.get("job", {})
            job_id = job.get("id", "")
            status = job.get("status", "")
            urls = job.get("urls", [])
    except Exception as e:
        print(f"[canva] Exceção no POST /exports: {e}")
        return None

    if not job_id:
        print(f"[canva] Job sem ID: {data}")
        return None

    # 2. Polling (se já não estiver pronto)
    elapsed = 0.0
    interval = 1.0
    while status in ("in_progress", "pending", "") and elapsed < max_wait_seconds:
        await asyncio.sleep(interval)
        elapsed += interval
        try:
            async with session.get(
                f"{CANVA_API_BASE}/exports/{job_id}", headers=headers
            ) as resp:
                if resp.status != 200:
                    print(f"[canva] GET export {job_id} falhou: {resp.status}")
                    return None
                data = await resp.json()
                job = data.get("job", {})
                status = job.get("status", "")
                urls = job.get("urls", [])
        except Exception as e:
            print(f"[canva] Exceção no polling: {e}")
            return None

    if status != "success" or not urls:
        print(f"[canva] Export não concluiu (status={status}, urls={len(urls)})")
        return None

    # 3. Download (S3 pré-assinado)
    try:
        async with session.get(urls[0]) as img_resp:
            if img_resp.status != 200:
                print(f"[canva] Download export falhou: {img_resp.status}")
                return None
            raw = await img_resp.read()
            print(f"[canva] Export PNG baixado ({len(raw)} bytes, slide {page_number})")
            return base64.standard_b64encode(raw).decode()
    except Exception as e:
        print(f"[canva] Exceção no download: {e}")
        return None


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
    # Cadeia de source-of-truth pro refresh token (Canva rotaciona a cada uso):
    #   1. Upstash Redis (produção com rotação persistente)
    #   2. secrets/.env.local (dev — arquivo atualizado in-place)
    #   3. os.environ.CANVA_REFRESH_TOKEN (bootstrap inicial)
    refresh_token = (
        await _get_refresh_from_redis()
        or _read_refresh_from_env_file()
        or os.environ.get("CANVA_REFRESH_TOKEN", "")
    )
    missing = [
        name for name, val in [
            ("CANVA_CLIENT_ID", client_id),
            ("CANVA_CLIENT_SECRET", client_secret),
            ("CANVA_REFRESH_TOKEN", refresh_token),
        ] if not val
    ]
    if missing:
        print(f"[canva] Env vars faltando: {', '.join(missing)}")
        return ""

    try:
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
                body = await resp.text()
                if resp.status != 200:
                    print(f"[canva] Refresh falhou {resp.status}: {body[:200]}")
                    return ""
                import json as _json
                data = _json.loads(body)
                token = data.get("access_token", "")
                new_refresh = data.get("refresh_token", "")
                if new_refresh and new_refresh != refresh_token:
                    await _persist_new_refresh_token(new_refresh)
                if not token:
                    print(f"[canva] Resposta sem access_token: {body[:200]}")
                return token
    except Exception as e:
        print(f"[canva] Erro refresh token: {e}")
        return ""


def _env_local_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "secrets",
        ".env.local",
    )


def _read_refresh_from_env_file() -> str:
    """Em dev, lê CANVA_REFRESH_TOKEN diretamente do .env.local (fonte da verdade
    depois de rotações). Retorna "" se arquivo não existe (caso de produção)."""
    path = _env_local_path()
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("CANVA_REFRESH_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


CANVA_REDIS_KEY = "canva_refresh_token"


def _redis_config() -> tuple[str, str]:
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
    return url, token


async def _get_refresh_from_redis() -> str:
    """Lê CANVA_REFRESH_TOKEN do Upstash (se configurado). '' se não configurado
    ou se a chave ainda não existe."""
    url, token = _redis_config()
    if not (url and token):
        return ""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{url}/get/{CANVA_REDIS_KEY}",
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                if resp.status != 200:
                    print(f"[canva] Upstash GET falhou: {resp.status}")
                    return ""
                data = await resp.json()
                return data.get("result") or ""
    except Exception as e:
        print(f"[canva] Upstash GET exceção: {e}")
        return ""


async def _save_refresh_to_redis(new_token: str) -> bool:
    """Escreve novo refresh token no Upstash. Retorna True se gravou."""
    url, token = _redis_config()
    if not (url and token):
        return False
    try:
        async with aiohttp.ClientSession() as session:
            # POST /set/{key} com o valor no body — seguro pra strings longas
            async with session.post(
                f"{url}/set/{CANVA_REDIS_KEY}",
                headers={"Authorization": f"Bearer {token}"},
                data=new_token.encode("utf-8"),
            ) as resp:
                if resp.status == 200:
                    print("[canva] Refresh token rotacionado — Upstash atualizado")
                    return True
                body = await resp.text()
                print(f"[canva] Upstash SET falhou {resp.status}: {body[:200]}")
                return False
    except Exception as e:
        print(f"[canva] Upstash SET exceção: {e}")
        return False


async def _persist_new_refresh_token(new_token: str) -> None:
    """
    Canva rotaciona a cada uso: cada refresh_token só pode ser usado UMA vez.
    Persiste o novo em:
      1. Upstash Redis (se configurado) — produção
      2. secrets/.env.local (se existir) — dev
      3. os.environ (sempre) — válido dentro do processo corrente
    """
    os.environ["CANVA_REFRESH_TOKEN"] = new_token

    # Tenta Redis primeiro (produção)
    if await _save_refresh_to_redis(new_token):
        return

    env_path = _env_local_path()
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("CANVA_REFRESH_TOKEN="):
                lines[i] = f"CANVA_REFRESH_TOKEN={new_token}\n"
                updated = True
                break
        if updated:
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            print("[canva] Refresh token rotacionado — .env.local atualizado")
    except Exception as e:
        print(f"[canva] Aviso: não consegui persistir novo refresh token: {e}")
