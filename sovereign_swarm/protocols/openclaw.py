from ..config import *

class OpenClawGateway:
    def __init__(self, host: str = "http://localhost:18789", token: str = ""):
        self.host = host; self.token = token or os.getenv("OPENCLAW_GATEWAY_TOKEN", ""); self.hooks = {f"hook_{i}": None for i in range(1, 8)}

    def register_hook(self, hook_id: int, handler: Callable):
        if 1 <= hook_id <= 7: self.hooks[f"hook_{hook_id}"] = handler

    async def _request(self, method: str, path: str, payload: Optional[Dict] = None) -> Dict:
        if not aiohttp: return {"error": "aiohttp missing"}
        url = f"{self.host}{path}"; headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        return {"status": resp.status, "body": await resp.json() if resp.status < 300 else await resp.text()}
                elif method == "POST":
                    async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        return {"status": resp.status, "body": await resp.json() if resp.status < 300 else await resp.text()}
        except Exception as e: return {"error": str(e)}

    async def status(self) -> Dict: return await self._request("GET", "/status")
    async def send_message(self, channel: str, target: str, message: str) -> Dict: return await self._request("POST", "/message", {"channel": channel, "target": target, "message": message})
    async def trigger_hook(self, hook_id: int, context: Dict) -> Dict:
        handler = self.hooks.get(f"hook_{hook_id}")
        if handler:
            try:
                if asyncio.iscoroutinefunction(handler): return await handler(context)
                return handler(context)
            except Exception as e: return {"hook": hook_id, "error": str(e)}
        return {"hook": hook_id, "status": "no_handler"}

    def report(self) -> Dict:
        return {"host": self.host, "token_set": bool(self.token), "hooks_registered": [k for k, v in self.hooks.items() if v is not None]}


