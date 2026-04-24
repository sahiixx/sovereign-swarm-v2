from ..config import *

class SwarmBridge:
    def __init__(self, crm_endpoint: str = "http://localhost:18792", omni_endpoint: str = "http://localhost:18790"):
        self.crm = crm_endpoint; self.omni = omni_endpoint

    async def _post(self, url: str, payload: Dict) -> Dict:
        if not aiohttp: return {"error": "aiohttp missing"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return {"status": resp.status, "body": await resp.json() if resp.status < 300 else await resp.text()}
        except Exception as e: return {"error": str(e)}

    async def crm_lead(self, lead_data: Dict) -> Dict: return await self._post(f"{self.crm}/lead", lead_data)
    async def crm_pipeline(self) -> Dict: return await self._post(f"{self.crm}/pipeline", {})
    async def omni_message(self, target: str, message: str) -> Dict: return await self._post(f"{self.omni}/message", {"target": target, "message": message})
    async def omni_status(self) -> Dict: return await self._post(f"{self.omni}/status", {})
    def report(self) -> Dict: return {"crm": self.crm, "omni": self.omni, "aiohttp": aiohttp is not None}


