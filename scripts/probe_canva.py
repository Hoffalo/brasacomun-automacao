"""
Probe na Canva Connect API — testa o que a integration consegue acessar.
Uso:
  . .\scripts\load_env.ps1
  python scripts/probe_canva.py DAHEgH1dK6c
"""

import asyncio
import json
import sys
import aiohttp

sys.path.insert(0, ".")

from lib.canva_client import _get_access_token


async def main(design_id: str):
    token = await _get_access_token()
    if not token:
        print("Sem access token — verifica env vars.")
        return

    print(f"✓ Access token obtido (len={len(token)})")
    print()

    headers = {"Authorization": f"Bearer {token}"}
    base = "https://api.canva.com/rest/v1"

    endpoints = [
        ("GET metadata", f"{base}/designs/{design_id}"),
        ("GET pages", f"{base}/designs/{design_id}/pages"),
        ("LIST designs (primeiros 3)", f"{base}/designs?limit=3"),
    ]

    async with aiohttp.ClientSession() as session:
        for label, url in endpoints:
            print(f"── {label} ──")
            print(f"   {url}")
            try:
                async with session.get(url, headers=headers) as resp:
                    body = await resp.text()
                    print(f"   Status: {resp.status}")
                    try:
                        parsed = json.loads(body)
                        print(json.dumps(parsed, indent=2, ensure_ascii=False)[:1500])
                    except Exception:
                        print(body[:500])
            except Exception as e:
                print(f"   Erro: {e}")
            print()


if __name__ == "__main__":
    design_id = sys.argv[1] if len(sys.argv) > 1 else "DAHEgH1dK6c"
    asyncio.run(main(design_id))
