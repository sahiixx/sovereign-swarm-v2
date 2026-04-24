from ..config import *

class A2ACardServer:
    def __init__(self, port: int = 18797):
        self.port = port; self.agents: Dict[str, Dict] = {}; self.app = AioWeb.Application() if AioWeb else None
        if self.app:
            self.app.router.add_get("/agent.json", self._agent_card)
            self.app.router.add_post("/rpc", self._rpc_handler)

    def register_agent(self, agent_id: str, skills: List[str], endpoint: str):
        self.agents[agent_id] = {"agent_id": agent_id, "skills": skills, "endpoint": endpoint, "status": "active"}

    async def _agent_card(self, request):
        return AioWeb.json_response({"name": "Sovereign Swarm", "version": "1.4", "agents": list(self.agents.values())})

    async def _rpc_handler(self, request):
        try:
            body = await request.json(); method = body.get("method"); params = body.get("params", {})
            if method == "discover":
                skill = params.get("skill")
                return AioWeb.json_response({"result": [a for a in self.agents.values() if skill in a["skills"]]})
            elif method == "ping": return AioWeb.json_response({"result": "pong"})
            return AioWeb.json_response({"error": "unknown_method"}, status=400)
        except Exception as e: return AioWeb.json_response({"error": str(e)}, status=500)

    async def start(self):
        if self.app:
            runner = AioWeb.AppRunner(self.app); await runner.setup()
            site = AioWeb.TCPSite(runner, "0.0.0.0", self.port); await site.start()
            print(f"[a2a] Agent card server on :{self.port}"); return runner
        return None

    def report(self) -> Dict:
        return {"port": self.port, "agents_registered": len(self.agents)}


