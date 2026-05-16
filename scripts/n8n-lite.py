"""n8n-lite — FastAPI webhook + workflow engine for Sovereign Swarm DSL.
No npm. No Docker. Just Python. Deployed on port 5678.
"""
import asyncio, json, time, traceback
from pathlib import Path
from typing import Optional, Dict, Any, List
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
import urllib.request
import urllib.parse

DATA_DIR = Path.home() / ".n8n-lite"
DATA_DIR.mkdir(exist_ok=True)

WORKFLOWS: Dict[str, dict] = {}
WEBHOOK_LOG: List[dict] = []

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    def _json(self, data: dict, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, default=str).encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else "{}"
        try:
            return json.loads(body) if body else {}
        except json.JSONDecodeError:
            return {"raw": body}

    def do_GET(self):
        if self.path == "/" or self.path == "/health":
            self._json({"ok": True, "version": "n8n-lite-v1", "workflows": len(WORKFLOWS)})
        elif self.path == "/workflows":
            self._json({"workflows": {k: v["description"] for k, v in WORKFLOFS.items()}})
        elif self.path.startswith("/webhook/"):
            tag = self.path.split("/webhook/")[-1]
            # Trigger workflow by tag
            self._trigger_workflow(tag, {"method": "GET", "query": self.path})
            self._json({"ok": True, "triggered": tag})
        else:
            self._json({"error": "Unknown"}, 404)

    def do_POST(self):
        payload = self._read_body()
        if self.path == "/webhook/dsl-mission":
            self._handle_dsl_mission(payload)
        elif self.path == "/webhook/telegram":
            self._handle_telegram_webhook(payload)
        elif self.path == "/workflow/create":
            self._handle_create_workflow(payload)
        elif self.path == "/workflow/run":
            self._handle_run_workflow(payload)
        else:
            self._json({"error": "Unknown"}, 404)

    def _handle_dsl_mission(self, payload):
        goal = payload.get("goal", "")
        if not goal:
            return self._json({"ok": False, "error": "Missing goal"}, 400)
        try:
            result = self._call_dsl(goal)
            self._json({"ok": True, "mission": goal, "result": result})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

    def _handle_telegram_webhook(self, payload):
        message = payload.get("message", {})
        text = message.get("text", "")
        chat_id = message.get("chat", {}).get("id", "")
        if text.startswith("/dsl "):
            goal = text[5:]
            threading.Thread(target=self._run_async_dsl_then_notify, args=(goal, chat_id), daemon=True).start()
            return self._json({"ok": True, "status": "accepted", "goal": goal})
        self._json({"ok": True, "status": "ignored", "text": text[:50]})

    def _handle_create_workflow(self, payload):
        wf_id = payload.get("id", f"wf_{int(time.time())}")
        WORKFLOWS[wf_id] = payload
        self._json({"ok": True, "workflow_id": wf_id})

    def _handle_run_workflow(self, payload):
        wf_id = payload.get("workflow_id")
        if not wf_id or wf_id not in WORKFLOWS:
            return self._json({"ok": False, "error": "Unknown workflow"}, 404)
        wf = WORKFLOWS[wf_id]
        result = {"status": "ran", "steps": []}
        for step in wf.get("steps", []):
            if step.get("type") == "dsl":
                r = self._call_dsl(step.get("goal"))
                result["steps"].append({"step": step.get("name"), "result": r})
            elif step.get("type") == "notify":
                self._send_telegram(step.get("chat_id"), step.get("message"))
                result["steps"].append({"step": step.get("name"), "result": "sent"})
        self._json({"ok": True, "workflow_result": result})

    def _call_dsl(self, goal: str) -> dict:
        req = urllib.request.Request(
            "http://127.0.0.1:18800/api/v1/mission",
            data=json.dumps({"goal": goal}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    def _run_async_dsl_then_notify(self, goal, chat_id):
        try:
            result = self._call_dsl(goal)
            msg = f"DSL complete: {result.get('status', 'done')} for '{goal[:50]}'"
        except Exception as e:
            msg = f"DSL error for '{goal[:50]}': {str(e)[:100]}"
        self._send_telegram(chat_id, msg)

    def _send_telegram(self, chat_id, message):
        # Stub - requires TELEGRAM_BOT_TOKEN env var
        token = ""
        if not token or not chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = json.dumps({"chat_id": chat_id, "text": message}).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

    def log_message(self, fmt, *args):
        pass


def _load_dubai_re_workflow():
    WORKFLOWS["dubai_re_agent"] = {
        "description": "Dubai Real Estate Voice Agent",
        "steps": [
            {"name": "parse_intent", "type": "dsl", "goal": "parse real estate query into structured search params"},
            {"name": "search_properties", "type": "dsl", "goal": "search Dubai property database for matching listings"},
            {"name": "qualify_lead", "type": "dsl", "goal": "score and qualify potential buyer from query context"},
            {"name": "notify_results", "type": "notify", "message": "Found {count} properties matching your criteria"}
        ]
    }


def main():
    _load_dubai_re_workflow()
    server = ThreadedHTTPServer(("0.0.0.0", 5678), Handler)
    print(f"[n8n-lite] Running on port 5678")
    print(f"[n8n-lite] Webhooks: POST /webhook/dsl-mission, /webhook/telegram")
    print(f"[n8n-lite] Workflows: POST /workflow/run {{workflow_id}}")
    print(f"[n8n-lite] Dubai RE workflow loaded: {list(WORKFLOWS.keys())}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[n8n-lite] Shut down.")


if __name__ == "__main__":
    main()
