from ..config import *

try:
    from pydantic import Field
except Exception:
    Field = None

class ToolSchema:
    def __init__(self):
        self.schemas = self._build_schemas(); self.validation_failures: Dict[str, int] = {}; self.circuit_threshold = 5; self.circuit_open: set = set()

    def _build_schemas(self) -> Dict:
        if not BaseModel: return {}
        class MemorySearch(BaseModel):
            query: str = Field(..., min_length=1); limit: int = Field(10, ge=1, le=100)
        class MemoryStore(BaseModel):
            key: str = Field(..., min_length=1); value: Any; tags: str = ""
        class AgentSpawn(BaseModel):
            specialty: str = Field(..., min_length=1)
        class AgentKill(BaseModel):
            agent_id: str = Field(..., min_length=1)
        class BusPublish(BaseModel):
            topic: str = Field(..., min_length=1); payload: Dict
        class BusSubscribe(BaseModel):
            topic: str = Field(..., min_length=1)
        class SafetyScan(BaseModel):
            text: str = Field(..., min_length=1)
        class LLMChat(BaseModel):
            prompt: str = Field(..., min_length=1); model: Optional[str] = None
        class AuditLog(BaseModel):
            event: str = Field(..., min_length=1); data: Dict
        class BackupCreate(BaseModel):
            name: str = Field(..., min_length=1)
        class BackupRestore(BaseModel):
            name: str = Field(..., min_length=1)
        class AlertSend(BaseModel):
            message: str = Field(..., min_length=1); severity: str = Field("info", pattern="^(info|warn|error|critical)$")
        return {
            "memory.search": MemorySearch, "memory.store": MemoryStore, "agent.spawn": AgentSpawn, "agent.kill": AgentKill,
            "bus.publish": BusPublish, "bus.subscribe": BusSubscribe, "safety.scan": SafetyScan, "llm.chat": LLMChat,
            "audit.log": AuditLog, "backup.create": BackupCreate, "backup.restore": BackupRestore, "alert.send": AlertSend,
        }

    def validate(self, tool: str, params: Dict) -> Dict:
        if tool in self.circuit_open: return {"valid": False, "error": "circuit_open", "tool": tool}
        schema = self.schemas.get(tool)
        if not schema:
            required = {"memory.search": ["query"], "memory.store": ["key", "value"], "agent.spawn": ["specialty"],
                        "agent.kill": ["agent_id"], "bus.publish": ["topic", "payload"], "bus.subscribe": ["topic"],
                        "safety.scan": ["text"], "llm.chat": ["prompt"], "audit.log": ["event"],
                        "backup.create": ["name"], "backup.restore": ["name"], "alert.send": ["message"]}
            fields = required.get(tool)
            if fields:
                for f in fields:
                    v = params.get(f)
                    if v is None or (isinstance(v, str) and not v.strip()):
                        return {"valid": False, "error": f"empty_or_missing:{f}", "tool": tool}
            return {"valid": True, "tool": tool}
        try:
            schema(**params); return {"valid": True, "tool": tool}
        except ValidationError as e:
            self.validation_failures[tool] = self.validation_failures.get(tool, 0) + 1
            if self.validation_failures[tool] >= self.circuit_threshold: self.circuit_open.add(tool)
            return {"valid": False, "error": str(e), "tool": tool}

    def reset_circuit(self, tool: str):
        self.circuit_open.discard(tool); self.validation_failures[tool] = 0

    def report(self) -> Dict:
        return {"tools": list(self.schemas.keys()), "circuits_open": list(self.circuit_open), "failure_counts": self.validation_failures}


