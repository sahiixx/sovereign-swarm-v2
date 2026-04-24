from ..config import *

class HermesMessenger:
    PROTOCOLS = ["mcp", "a2a", "openclaw", "internal"]
    def __init__(self):
        self.routes: Dict[str, Callable] = {}; self.stats: Dict[str, int] = {p: 0 for p in self.PROTOCOLS}

    def register(self, protocol: str, handler: Callable):
        if protocol in self.PROTOCOLS: self.routes[protocol] = handler

    async def send(self, protocol: str, message: Dict) -> Dict:
        self.stats[protocol] = self.stats.get(protocol, 0) + 1; handler = self.routes.get(protocol)
        if handler:
            try:
                if asyncio.iscoroutinefunction(handler): return await handler(message)
                return handler(message)
            except Exception as e: return {"error": str(e), "protocol": protocol}
        return {"error": "no_handler", "protocol": protocol}

    async def broadcast(self, message: Dict, exclude: list = None) -> Dict:
        exclude = exclude or []; results = {}
        for proto in self.PROTOCOLS:
            if proto not in exclude: results[proto] = await self.send(proto, message)
        return results

    def status(self) -> Dict:
        return {"registered": list(self.routes.keys()), "stats": self.stats, "protocols": self.PROTOCOLS}


