#!/usr/bin/env python3
"""DSL Daemon - lightweight HTTP API for the Deterministic Sovereign Loop."""

import asyncio, json, signal, sys, time, traceback
from pathlib import Path
from typing import Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sovereign_swarm.dsl import DeterministicSovereignLoop
from sovereign_swarm.dsl.mission import Mission


class StorableDict(dict):
    def __init__(self, path: str):
        super().__init__()
        self._path = Path(path)
        if self._path.exists():
            try:
                with open(self._path) as f:
                    self.update(json.load(f))
            except (json.JSONDecodeError, IOError):
                self["status"] = "boot"
        else:
            self["status"] = "boot"

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, 'w') as f:
            json.dump(dict(self), f, indent=2)


class AuditTrail:
    def __init__(self, _: str = ""): pass
    def log(self, *args, **kwargs): pass
    def record_checkpoint(self, *args, **kwargs): pass
    def record_milestone(self, *args, **kwargs): pass


_DATA_DIR = Path.home() / ".dsl_daemo"
_DATA_DIR.mkdir(exist_ok=True)

_mission_loop: Optional[DeterministicSovereignLoop] = None
_missions_store = {}  # mission_id -> result dict
_server: Optional[HTTPServer] = None
_shutdown_event = threading.Event()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    def _json(self, data: dict, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        import json
        self.wfile.write(json.dumps(data, indent=2, default=str).encode())

    def do_GET(self):
        if self.path == "/api/v1/status":
            store = StorableDict(_DATA_DIR / "status.json")
            self._json({
                "ok": True,
                "daemon": "dsl",
                "time": time.time(),
                "missions_completed": len(_missions_store),
                "loop_ready": _mission_loop is not None,
                "status": store.get("status", "unknown")
            })
        elif self.path.startswith("/api/v1/missions"):
            limit = 20
            try:
                from urllib.parse import parse_qs, urlparse
                qs = parse_qs(urlparse(self.path).query)
                limit = int(qs.get("limit", [20])[0])
            except Exception:
                pass
            recent = sorted(_missions_store.items(), key=lambda x: x[1].get("timestamp", 0), reverse=True)[:limit]
            self._json({"ok": True, "missions": [m[1] for m in recent], "count": len(_missions_store)})
        else:
            self._json({"ok": False, "error": f"Unknown path {self.path}"}, 404)

    def do_POST(self):
        import json
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else "{}"
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return self._json({"ok": False, "error": "Invalid JSON"}, 400)

        if self.path == "/api/v1/mission":
            goal = payload.get("goal", "")
            user_id = payload.get("user_id", "api_user")
            if not goal:
                return self._json({"ok": False, "error": "Missing goal"}, 400)

            def _run_async():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(_mission_loop.run(goal, requester_id=user_id))
                    rid = result.checkpoint_id or result.data.get("mission_id") or f"mission_{int(time.time())}"
                    _missions_store[rid] = result.to_dict()
                    store = StorableDict(_DATA_DIR / "status.json")
                    store["last_mission"] = rid
                    store.save()
                except Exception as exc:
                    import traceback as _tb
                    _missions_store[f"error_{int(time.time())}"] = {"ok": False, "error": str(exc), "traceback": _tb.format_exc()}

            t = threading.Thread(target=_run_async, daemon=True)
            t.start()
            self._json({
                "ok": True,
                "status": "accepted",
                "goal": goal,
                "message": "Mission running. Check /api/v1/missions for result."
            })

        elif self.path == "/api/v1/chat":
            message = payload.get("message", "")
            user_id = payload.get("user_id", "chat_user")
            if not message:
                return self._json({"ok": False, "error": "Missing message"}, 400)

            def _chat_async():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(_mission_loop.run(message, requester_id=user_id))
                    rid = result.checkpoint_id or result.data.get("mission_id") or f"chat_{int(time.time())}"
                    _missions_store[rid] = result.to_dict()
                except Exception as exc:
                    _missions_store[f"chat_error_{int(time.time())}"] = {"ok": False, "error": str(exc)}

            t = threading.Thread(target=_chat_async, daemon=True)
            t.start()
            self._json({
                "ok": True,
                "status": "accepted",
                "message": message,
            })

        else:
            self._json({"ok": False, "error": f"Unknown path {self.path}"}, 404)

    def log_message(self, fmt, *args):
        # Suppress server logs for clean output
        pass


def _signal_handler(signum, frame):
    _shutdown_event.set()
    if _server:
        _server.shutdown()


def main():
    global _mission_loop, _server

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Init loop (asyncio not needed for sync run)
    _mission_loop = DeterministicSovereignLoop()

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18800
    _server = ThreadedHTTPServer(("0.0.0.0", port), Handler)
    _server.allow_reuse_address = True
    print(f"[DSL Daemon] Running on port {port}")
    print(f"[DSL Daemon] POST http://localhost:{port}/api/v1/mission")

    # Block until signal
    try:
        _server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _server.server_close()
        print("[DSL Daemon] Shut down.")


class DSLDaemon:
    """Async-friendly daemon wrapper for CLI integration."""

    def __init__(self, port: int = 18800):
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._running = False

    async def start(self):
        self._thread = threading.Thread(target=main, daemon=True)
        self._thread.start()
        self._running = True
        # Wait for server to bind
        import socket
        for _ in range(30):
            try:
                with socket.create_connection(("localhost", self.port), timeout=1):
                    break
            except Exception:
                await asyncio.sleep(0.5)

    async def stop(self):
        _shutdown_event.set()
        if _server:
            _server.shutdown()
        self._running = False


if __name__ == "__main__":
    main()
