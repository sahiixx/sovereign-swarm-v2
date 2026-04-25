"""WebhookServer — HTTP listener for n8n and external triggers to feed into Hermes.

Routes:
  POST /webhook/n8n          → Hermes n8n handler
  POST /webhook/generic      → Hermes generic webhook handler
  POST /webhook/lead         → Hermes lead handler
  GET  /health               → Healthcheck
"""
from ..config import *

class WebhookServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 18793, hermes=None):
        self.host = host; self.port = port
        self.hermes = hermes
        self.app = AioWeb.Application() if AioWeb else None
        self.runner = None
        if self.app:
            self.app.router.add_post("/webhook/n8n", self._n8n_handler)
            self.app.router.add_post("/webhook/generic", self._generic_handler)
            self.app.router.add_post("/webhook/lead", self._lead_handler)
            self.app.router.add_get("/health", self._health)

    async def _n8n_handler(self, request):
        try:
            body = await request.json()
            if self.hermes:
                await self.hermes.send("webhook", {"action": "n8n", "payload": body}, sender="n8n")
            return AioWeb.json_response({"status": "accepted", "source": "n8n"})
        except Exception as e:
            return AioWeb.json_response({"error": str(e)}, status=400)

    async def _generic_handler(self, request):
        try:
            body = await request.json()
            event_type = body.get("event_type", "generic")
            if self.hermes:
                await self.hermes.auto_route(event_type, body, sender="webhook")
            return AioWeb.json_response({"status": "accepted", "event_type": event_type})
        except Exception as e:
            return AioWeb.json_response({"error": str(e)}, status=400)

    async def _lead_handler(self, request):
        try:
            body = await request.json()
            if self.hermes:
                await self.hermes.auto_route("lead.new", body, sender="webhook")
            return AioWeb.json_response({"status": "lead_received"})
        except Exception as e:
            return AioWeb.json_response({"error": str(e)}, status=400)

    async def _health(self, request):
        return AioWeb.json_response({"status": "ok", "port": self.port, "hermes_connected": self.hermes is not None})

    async def start(self):
        if not self.app:
            print("[webhook] AioWeb not available"); return None
        self.runner = AioWeb.AppRunner(self.app); await self.runner.setup()
        site = AioWeb.TCPSite(self.runner, self.host, self.port)
        await site.start()
        print(f"[webhook] Server on http://{self.host}:{self.port}")
        return self.runner

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
            self.runner = None

    def report(self) -> Dict:
        return {"host": self.host, "port": self.port, "hermes_connected": self.hermes is not None}
