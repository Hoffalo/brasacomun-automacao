"""
One-time: pega CANVA_REFRESH_TOKEN via OAuth + PKCE.

Pré-requisito (Canva Developers portal → sua integration):
  1. Configuration:
     - Copie o Client ID
     - Generate / copie o Client Secret
  2. Scopes: marque no mínimo design:content:read
  3. Authentication → Authorized redirects → adicione:
        http://127.0.0.1:8765/callback

Uso:
  export CANVA_CLIENT_ID="..."
  export CANVA_CLIENT_SECRET="..."
  python scripts/get_canva_token.py

Autentique com sua conta Canva no browser. Copie o refresh_token do terminal
e cole no Vercel como CANVA_REFRESH_TOKEN (junto com CANVA_CLIENT_ID e SECRET).
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import socketserver
import urllib.parse
import urllib.request
import webbrowser

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"
SCOPES = ["design:content:read", "design:meta:read", "asset:read"]

_captured = {"code": None, "state": None}


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            _captured["code"] = params["code"][0]
            _captured["state"] = params.get("state", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h1>Pronto! Pode fechar essa aba e voltar ao terminal.</h1>"
            )
        else:
            self.send_response(400)
            self.end_headers()
            err = params.get("error", ["sem code"])[0]
            self.wfile.write(f"Erro: {err}".encode())

    def log_message(self, *_args):
        pass


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def main():
    client_id = os.environ.get("CANVA_CLIENT_ID")
    client_secret = os.environ.get("CANVA_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Erro: defina CANVA_CLIENT_ID e CANVA_CLIENT_SECRET")
        return

    code_verifier = b64url(secrets.token_bytes(32))
    code_challenge = b64url(hashlib.sha256(code_verifier.encode()).digest())
    state = secrets.token_urlsafe(16)

    auth_url = "https://www.canva.com/api/oauth/authorize?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "code_challenge": code_challenge,
            "code_challenge_method": "s256",
            "state": state,
        }
    )

    print(f"Abrindo browser... se não abrir, acesse:\n{auth_url}\n")
    webbrowser.open(auth_url)

    with socketserver.TCPServer(("127.0.0.1", REDIRECT_PORT), CallbackHandler) as httpd:
        while _captured["code"] is None:
            httpd.handle_request()

    if _captured["state"] != state:
        print("Erro: state mismatch (possível CSRF). Abortando.")
        return

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": _captured["code"],
            "code_verifier": code_verifier,
            "redirect_uri": REDIRECT_URI,
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.canva.com/rest/v1/oauth/token",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Erro HTTP {e.code}: {e.read().decode()}")
        return

    refresh = tokens.get("refresh_token")
    if not refresh:
        print("Erro: refresh_token não retornado. Resposta:")
        print(json.dumps(tokens, indent=2))
        return

    print("\n" + "=" * 60)
    print("CANVA_REFRESH_TOKEN (cole no Vercel):")
    print("=" * 60)
    print(refresh)
    print("=" * 60)
    print("\nLembre de também adicionar CANVA_CLIENT_ID e CANVA_CLIENT_SECRET no Vercel.")


if __name__ == "__main__":
    main()
