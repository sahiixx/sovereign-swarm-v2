"""MoltworkerClient — async HTTP client for the Cloudflare Worker messaging gateway.

Connects to the Moltbot gateway for Telegram/Discord/Slack/Web delivery.
"""
from ..config import *

class MoltworkerClient:
    def __init__(self, gateway_url: str = "", token: str = ""):
        self.gateway_url = gateway_url or os.getenv("MOLTBOT_GATEWAY_URL", "http://localhost:8787")
        self.token = token or os.getenv("MOLTBOT_GATEWAY_TOKEN", "")
        self._last_error = None

    def _headers(self) -> Dict:
        h = {"Content-Type": "application/json", "User-Agent": "HermesV2/1.0"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def _request(self, method: str, path: str, payload: Optional[Dict] = None) -> Dict:
        if not aiohttp:
            return {"error": "aiohttp missing"}
        url = f"{self.gateway_url.rstrip('/')}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        body = await resp.json() if resp.status < 300 else await resp.text()
                        return {"status": resp.status, "body": body}
                elif method == "POST":
                    async with session.post(url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=20)) as resp:
                        body = await resp.json() if resp.status < 300 else await resp.text()
                        return {"status": resp.status, "body": body}
                else:
                    return {"error": f"unsupported_method: {method}"}
        except Exception as e:
            self._last_error = str(e)
            return {"error": str(e), "url": url}

    async def status(self) -> Dict:
        return await self._request("GET", "/api/gateway/status")

    async def send(self, platform: str, target: str, message: str) -> Dict:
        return await self._request("POST", "/api/gateway/trigger", {
            "channel": platform,
            "target": target,
            "message": message,
        })

    async def devices(self) -> Dict:
        return await self._request("GET", "/api/devices")

    def report(self) -> Dict:
        return {"gateway_url": self.gateway_url, "token_set": bool(self.token), "last_error": self._last_error}


class MoltworkerMCPBridge:
    """MCP-style tool registry for Moltworker, callable via Hermes internal channel."""

    TOOLS = ["moltworker.send", "moltworker.status", "moltworker.devices"]

    def __init__(self, client: MoltworkerClient):
        self.client = client
        self.handlers = {
            "moltworker.send": self._send,
            "moltworker.status": self._status,
            "moltworker.devices": self._devices,
        }

    async def handle(self, request: Dict) -> Dict:
        tool = request.get("tool"); params = request.get("params", {})
        handler = self.handlers.get(tool)
        if not handler:
            return {"error": "unknown_tool", "tool": tool}
        try:
            result = await handler(**params)
            return {"tool": tool, "result": result, "status": "ok"}
        except Exception as e:
            return {"tool": tool, "error": str(e), "status": "error"}

    async def _send(self, platform: str = "telegram", target: str = "", message: str = "") -> Dict:
        return await self.client.send(platform, target, message)

    async def _status(self) -> Dict:
        return await self.client.status()

    async def _devices(self) -> Dict:
        return await self.client.devices()
