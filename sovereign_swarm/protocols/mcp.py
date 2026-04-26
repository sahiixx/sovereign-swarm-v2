from ..config import *

class MCPServer:
    TOOLS = ["memory.search", "memory.store", "agent.spawn", "agent.kill", "bus.publish", "bus.subscribe", "safety.scan", "llm.chat", "audit.log", "backup.create", "backup.restore", "alert.send"]
    def __init__(self):
        self.handlers: Dict[str, Callable] = {}; self.request_count = 0

    def register(self, tool: str, handler: Callable):
        if tool in self.TOOLS: self.handlers[tool] = handler

    async def handle(self, request: Dict) -> Dict:
        self.request_count += 1; tool = request.get("tool"); params = request.get("params", {})
        if tool not in self.TOOLS: return {"error": "unknown_tool", "tool": tool}
        handler = self.handlers.get(tool)
        if not handler: return {"error": "no_handler", "tool": tool}
        try:
            if asyncio.iscoroutinefunction(handler): result = await handler(**params)
            else: result = handler(**params)
            return {"tool": tool, "result": result, "status": "ok"}
        except Exception as e: return {"tool": tool, "error": str(e), "status": "error"}

    MAX_MESSAGE_SIZE = 1_048_576  # 1MB

    async def stdio_loop(self):
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                if len(line) > self.MAX_MESSAGE_SIZE:
                    sys.stdout.write(json.dumps({"error": "message_too_large"}) + "\n")
                    sys.stdout.flush()
                    continue
                req = json.loads(line)
                resp = await self.handle(req)
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
            except Exception as e:
                sys.stdout.write(json.dumps({"error": str(e)}) + "\n")
                sys.stdout.flush()

    def schema(self, tool: str) -> Dict:
        schemas = {
            "memory.search": {"query": "string", "limit": "integer"}, "memory.store": {"key": "string", "value": "any", "tags": "string"},
            "agent.spawn": {"specialty": "string"}, "agent.kill": {"agent_id": "string"},
            "bus.publish": {"topic": "string", "payload": "dict"}, "bus.subscribe": {"topic": "string"},
            "safety.scan": {"text": "string"}, "llm.chat": {"prompt": "string", "model": "string"},
            "audit.log": {"event": "string", "data": "dict"}, "backup.create": {"name": "string"},
            "backup.restore": {"name": "string"}, "alert.send": {"message": "string", "severity": "string"}
        }
        return schemas.get(tool, {})

    def report(self) -> Dict:
        return {"tools": self.TOOLS, "registered": list(self.handlers.keys()), "requests_handled": self.request_count}


