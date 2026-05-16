#!/usr/bin/env python3
"""Telegram Bot for Dubai RE Voice Agent — scripts/telegram_bot.py
Runs on port 18802. Receives /start, /dsl, /find, /status.
Routes /find to n8n-lite webhook POST /webhook/dsl-mission.
Sends Telegram responses via Bot API.
"""
import os
import sys
import json
import time
import logging
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Load secrets from .hermes/secrets.env if TOKEN not in environment
if not os.getenv("TELEGRAM_BOT_TOKEN"):
    secrets_path = os.path.join(os.path.expanduser("~"), ".hermes", "secrets.env")
    if os.path.exists(secrets_path):
        with open(secrets_path) as f:
            for line in f:
                if line.strip().startswith("TELEGRAM_BOT_TOKEN="):
                    os.environ["TELEGRAM_BOT_TOKEN"] = line.strip().split("=", 1)[1]
                    break

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
N8N_WEBHOOK = "http://127.0.0.1:5678/webhook/dsl-mission"
DSL_STATUS_URL = "http://127.0.0.1:18800/api/v1/status"
PORT = int(os.getenv("TELEGRAM_BOT_PORT", "18802"))

HELP_TEXT = (
    "🏠 *Dubai RE Voice Agent*\n"
    "Commands:\n"
    "`/start` — show this help\n"
    "`/find <query>` — search properties (routes to n8n-lite)\n"
    "`/dsl <goal>` — send a DSL mission\n"
    "`/status` — system health check"
)


def tg_post(method: str, payload: dict) -> dict:
    url = f"{TELEGRAM_API}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log.warning("Telegram API call failed: %s", e)
        return {"ok": False, "error": str(e)}


def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    tg_post("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": parse_mode})


def route_to_n8n(goal: str, chat_id: int) -> dict:
    payload = {"goal": goal, "source": "telegram", "chat_id": chat_id}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(N8N_WEBHOOK, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log.warning("n8n-lite call failed: %s", e)
        return {"ok": False, "error": str(e)}


def dsl_status() -> str:
    try:
        req = urllib.request.Request(DSL_STATUS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return json.dumps(data, indent=2)
    except Exception as e:
        return f"DSL unreachable: {e}"


def handle_command(text: str, chat_id: int):
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/start":
        send_message(chat_id, HELP_TEXT)
        return

    if cmd == "/status":
        status = dsl_status()
        send_message(chat_id, f"⚙️ Status:\n```\n{status}\n```")
        return

    if cmd == "/dsl":
        if not arg:
            send_message(chat_id, "Usage: `/dsl <goal>`")
            return
        threading.Thread(target=_dsl_async, args=(arg, chat_id), daemon=True).start()
        send_message(chat_id, f"🚀 DSL mission queued: `{arg[:80]}`")
        return

    if cmd == "/find":
        if not arg:
            send_message(chat_id, "Usage: `/find 2 bedroom apartment in Dubai Marina under 3M`")
            return
        threading.Thread(target=_find_async, args=(arg, chat_id), daemon=True).start()
        send_message(chat_id, f"🔍 Searching: `{arg[:80]}` …")
        return

    send_message(chat_id, f"Unknown command: `{cmd}`")


def _dsl_async(goal: str, chat_id: int):
    result = route_to_n8n(goal, chat_id)
    if result.get("ok"):
        msg = f"✅ DSL result for `{goal[:60]}`:\n```\n{json.dumps(result.get('result', result), indent=2)[:3800]}\n```"
    else:
        msg = f"❌ DSL mission failed:\n```\n{json.dumps(result, indent=2)[:3800]}\n```"
    send_message(chat_id, msg)


def _find_async(query: str, chat_id: int):
    result = route_to_n8n(f"search Dubai properties for: {query}", chat_id)
    ok = result.get("ok")
    if ok:
        res = result.get("result", result)
        msg = f"🔍 *Find Results for:* `{query[:60]}`\n```\n{json.dumps(res, indent=2)[:3800]}\n```"
    else:
        msg = f"❌ Find failed:\n```\n{json.dumps(result, indent=2)[:3800]}\n```"
    send_message(chat_id, msg)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class BotHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info(fmt % args)

    def _json(self, data: dict, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def do_GET(self):
        if self.path in ("/", "/health", "/status"):
            healthy = bool(TOKEN)
            self._json({"ok": healthy, "bot": "DubaiREBot", "token_configured": healthy})
        else:
            self._json({"error": "unknown"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else "{}"
        try:
            update = json.loads(body)
        except json.JSONDecodeError:
            return self._json({"error": "invalid json"}, 400)

        message = update.get("message", {})
        text = message.get("text", "")
        chat = message.get("chat", {})
        chat_id = chat.get("id")

        if not text or not chat_id:
            return self._json({"ok": True, "status": "no-op"})

        handle_command(text, chat_id)
        self._json({"ok": True, "handled": text[:50]})


def main():
    if not TOKEN:
        log.error("TELEGRAM_BOT_TOKEN not set. Export it first.")
        sys.exit(1)
    server = ThreadedHTTPServer(("0.0.0.0", PORT), BotHandler)
    log.info("Dubai RE Telegram Bot on port %s", PORT)
    log.info("Webhook target: Telegram /webhook → this server POST /")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log.info("Bot stopped.")


if __name__ == "__main__":
    main()
