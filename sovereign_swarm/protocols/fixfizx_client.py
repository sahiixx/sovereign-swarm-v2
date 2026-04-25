"""FixfizxClient — async HTTP client for the Dubai platform (NOWHERE.AI / Fixfizx).

Endpoints covered: leads, campaigns, bookings, analytics.
"""
from ..config import *

class FixfizxClient:
    def __init__(self, base_url: str = "", jwt_token: str = ""):
        self.base_url = base_url or os.getenv("NOWHERE_AI_URL", "http://localhost:8001")
        self.jwt_token = jwt_token or os.getenv("NOWHERE_AI_JWT", "")
        self._last_error = None

    def _headers(self) -> Dict:
        h = {"Content-Type": "application/json", "User-Agent": "HermesV2/1.0"}
        if self.jwt_token:
            h["Authorization"] = f"Bearer {self.jwt_token}"
        return h

    async def _request(self, method: str, path: str, payload: Optional[Dict] = None) -> Dict:
        if not aiohttp:
            return {"error": "aiohttp missing"}
        url = f"{self.base_url.rstrip('/')}{path}"
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

    async def health(self) -> Dict:
        return await self._request("GET", "/health")

    async def qualify_lead(self, lead: Dict) -> Dict:
        return await self._request("POST", "/api/agents/sales/qualify-lead", lead)

    async def create_campaign(self, campaign: Dict) -> Dict:
        return await self._request("POST", "/api/agents/marketing/create-campaign", campaign)

    async def analyze_market(self, sector: str, query: str = "", include_competitors: bool = False) -> Dict:
        return await self._request("POST", "/api/ai/advanced/dubai-market-analysis", {
            "sector": sector,
            "query": query,
            "include_competitors": include_competitors,
        })

    async def list_campaigns(self) -> Dict:
        return await self._request("GET", "/api/agents/marketing/campaigns")

    async def lead_pipeline(self) -> Dict:
        return await self._request("GET", "/api/agents/sales/pipeline")

    def report(self) -> Dict:
        return {"base_url": self.base_url, "token_set": bool(self.jwt_token), "last_error": self._last_error}


class FixfizxMCPBridge:
    """MCP-style tool registry for Fixfizx, callable via Hermes internal channel."""

    TOOLS = ["fixfizx.qualify_lead", "fixfizx.create_campaign", "fixfizx.analyze_market", "fixfizx.list_campaigns", "fixfizx.lead_pipeline", "fixfizx.health"]

    def __init__(self, client: FixfizxClient):
        self.client = client
        self.handlers = {
            "fixfizx.qualify_lead": self._qualify_lead,
            "fixfizx.create_campaign": self._create_campaign,
            "fixfizx.analyze_market": self._analyze_market,
            "fixfizx.list_campaigns": self._list_campaigns,
            "fixfizx.lead_pipeline": self._lead_pipeline,
            "fixfizx.health": self._health,
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

    async def _qualify_lead(self, **kwargs) -> Dict:
        return await self.client.qualify_lead(kwargs)
    async def _create_campaign(self, **kwargs) -> Dict:
        return await self.client.create_campaign(kwargs)
    async def _analyze_market(self, sector: str = "", query: str = "", include_competitors: bool = False) -> Dict:
        return await self.client.analyze_market(sector, query, include_competitors)
    async def _list_campaigns(self) -> Dict:
        return await self.client.list_campaigns()
    async def _lead_pipeline(self) -> Dict:
        return await self.client.lead_pipeline()
    async def _health(self) -> Dict:
        return await self.client.health()
