from ..config import *
import asyncio

class A2ACardServer:
    def __init__(self, port: int = 18797, host: str = "127.0.0.1"):
        self.port = port; self.agents: Dict[str, Dict] = {}; self.app = AioWeb.Application() if AioWeb else None
        self._sse_queues: List[asyncio.Queue] = []
        if self.app:
            self.app.router.add_get("/agent.json", self._agent_card)
            self.app.router.add_post("/rpc", self._rpc_handler)
            self.app.router.add_get("/sse", self._sse_handler)
            self.app.router.add_post("/sse/send", self._sse_send)

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

    async def _sse_handler(self, request):
        if not AioWeb:
            return AioWeb.json_response({"error": "aiohttp missing"}, status=500)
        queue = asyncio.Queue()
        self._sse_queues.append(queue)
        resp = AioWeb.StreamResponse()
        resp.headers["Content-Type"] = "text/event-stream"
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["Connection"] = "keep-alive"
        await resp.prepare(request)
        try:
            while True:
                msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                data = json.dumps(msg)
                await resp.write(f"data: {data}\n\n".encode())
                await resp.drain()
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
        finally:
            if queue in self._sse_queues:
                self._sse_queues.remove(queue)
        return resp

    async def _sse_send(self, request):
        try:
            body = await request.json()
            msg = {"type": body.get("type", "message"), **body}
            await self.broadcast_sse(msg)
            return AioWeb.json_response({"broadcasted": True, "listeners": len(self._sse_queues)})
        except Exception as e:
            return AioWeb.json_response({"error": str(e)}, status=500)

    async def broadcast_sse(self, message: Dict):
        for q in list(self._sse_queues):
            try:
                await q.put(message)
            except Exception:
                pass

    async def start(self):
        if self.app:
            runner = AioWeb.AppRunner(self.app); await runner.setup()
            site = AioWeb.TCPSite(runner, self.host, self.port); await site.start()
            print(f"[a2a] Agent card + SSE server on :{self.port}"); return runner
        return None

    def report(self) -> Dict:
        return {"port": self.port, "agents_registered": len(self.agents), "sse_listeners": len(self._sse_queues)}


