"""
One-time: pega refresh token OAuth do Google pra usar no drive_client.py.

Pré-requisito:
  1. Google Cloud Console → APIs & Services → Credentials →
     Create Credentials → OAuth client ID → Desktop app
  2. Exporte as envs:
        export GOOGLE_OAUTH_CLIENT_ID="..."
        export GOOGLE_OAUTH_CLIENT_SECRET="..."

Uso:
  python scripts/get_refresh_token.py

Autentique com a conta BRASA no browser. O refresh_token aparece no terminal.
Cole no Vercel como GOOGLE_OAUTH_REFRESH_TOKEN.
"""

import http.server
import json
import os
import secrets
import socketserver
import urllib.parse
import urllib.request
import webbrowser

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

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


def main():
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Erro: defina GOOGLE_OAUTH_CLIENT_ID e GOOGLE_OAUTH_CLIENT_SECRET")
        return

    state = secrets.token_urlsafe(16)
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )

    print(f"Abrindo browser... se não abrir, acesse:\n{auth_url}\n")
    webbrowser.open(auth_url)

    with socketserver.TCPServer(("localhost", REDIRECT_PORT), CallbackHandler) as httpd:
        while _captured["code"] is None:
            httpd.handle_request()

    if _captured["state"] != state:
        print("Erro: state mismatch (possível CSRF). Abortando.")
        return

    data = urllib.parse.urlencode(
        {
            "code": _captured["code"],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    ).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=data, method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        tokens = json.loads(resp.read().decode())

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("Erro: refresh_token não retornado. Resposta:")
        print(json.dumps(tokens, indent=2))
        print("\nDica: revogue o app em https://myaccount.google.com/permissions "
              "e rode de novo — Google só manda refresh_token na primeira autorização.")
        return

    print("\n" + "=" * 60)
    print("REFRESH TOKEN (cole no Vercel como GOOGLE_OAUTH_REFRESH_TOKEN):")
    print("=" * 60)
    print(refresh_token)
    print("=" * 60)


if __name__ == "__main__":
    main()
