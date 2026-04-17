"""
BRASA Briefing Bot — Entry point (Vercel Serverless Function)
Trigger: ClickUp taskStatusUpdated → "em progresso mkt"
"""

from http.server import BaseHTTPRequestHandler
import json
import threading
import hmac
import hashlib
import os
import sys

# Adiciona o diretório raiz ao path para importar lib/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.pipeline import run_pipeline

# ID do status "em progresso mkt" no espaço Comun
TARGET_STATUS_ID = "sc901105543313_huc4fCr2"
TARGET_STATUS_NAME = "em progresso mkt"

# ID do espaço Comun — só processa tasks daqui
COMUN_SPACE_ID = "90111669766"


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_length)

            # 1. Valida assinatura do webhook (segurança)
            secret = os.environ.get("CLICKUP_WEBHOOK_SECRET", "")
            if secret:
                sig = hmac.new(
                    secret.encode(), body_bytes, hashlib.sha256
                ).hexdigest()
                received_sig = self.headers.get("X-Signature", "")
                if not hmac.compare_digest(sig, received_sig):
                    self._respond(401, "Unauthorized")
                    return

            body = json.loads(body_bytes)

            # 2. Responde 200 imediatamente — ClickUp tem timeout de 3s
            self._respond(200, "ok")

            # 3. Filtra: só taskStatusUpdated → "em progresso mkt"
            if body.get("event") != "taskStatusUpdated":
                return

            triggered = False
            for item in body.get("history_items", []):
                if item.get("field") != "status":
                    continue
                after = item.get("after", {})
                # Aceita por ID ou por nome (case-insensitive)
                if (
                    after.get("id") == TARGET_STATUS_ID
                    or after.get("status", "").lower() == TARGET_STATUS_NAME
                ):
                    triggered = True
                    break

            if not triggered:
                return

            task_id = body.get("task_id")
            if not task_id:
                return

            # 4. Roda a pipeline em thread separada — não bloqueia o response
            thread = threading.Thread(
                target=run_pipeline,
                args=(task_id,),
                daemon=True,
            )
            thread.start()

        except Exception as e:
            # Nunca deixa o webhook falhar silenciosamente
            print(f"[webhook] Erro inesperado: {e}")

    def _respond(self, status_code, message):
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(message.encode())

    def log_message(self, format, *args):
        # Silencia logs padrão do BaseHTTPRequestHandler
        pass
