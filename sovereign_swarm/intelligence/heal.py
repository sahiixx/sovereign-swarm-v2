from ..config import *
from .heal_strategy import HealStrategy
class HealEngine:
    STRATEGIES = list(HealStrategy)
    def __init__(self):
        self.failure_log: List[Dict] = []; self.circuit_state: Dict[str, str] = {}; self.quarantine: set = set()

    def classify(self, error: Exception) -> str:
        msg = str(error).lower()
        if any(x in msg for x in ["timeout", "connection", "unreachable", "refused"]): return "network"
        if any(x in msg for x in ["rate limit", "too many requests", "quota"]): return "rate_limit"
        if any(x in msg for x in ["validation", "schema", "invalid"]): return "validation"
        if any(x in msg for x in ["permission", "unauthorized", "forbidden"]): return "auth"
        return "unknown"

    async def heal(self, agent_id: str, error: Exception, context: Dict, tools: Dict[str, Callable]) -> Dict:
        cause = self.classify(error)
        self.failure_log.append({"agent_id": agent_id, "cause": cause, "error": str(error)[:200], "timestamp": time.time()})
        strategy = {"network": HealStrategy.RETRY, "rate_limit": HealStrategy.DEGRADE_MODEL, "validation": HealStrategy.ROLLBACK, "auth": HealStrategy.ESCALATE}.get(cause, HealStrategy.FALLBACK_AGENT)
        result = {"strategy": strategy.value, "agent_id": agent_id, "cause": cause, "success": False}
        if strategy == HealStrategy.RETRY:
            for attempt in range(1, 4):
                await asyncio.sleep(1.5 ** attempt)
                try:
                    if "task" in context and "executor" in tools: await tools["executor"](context["task"])
                    result["success"] = True; break
                except Exception: continue
        elif strategy == HealStrategy.FALLBACK_AGENT:
            if "fallback" in tools:
                try: await tools["fallback"](context); result["success"] = True
                except Exception: pass
        elif strategy == HealStrategy.DEGRADE_MODEL:
            if "degrade" in tools:
                try: await tools["degrade"](context); result["success"] = True
                except Exception: pass
        elif strategy == HealStrategy.CIRCUIT_BREAK:
            self.circuit_state[agent_id] = "open"; result["circuit_opened"] = True
        elif strategy == HealStrategy.QUARANTINE:
            self.quarantine.add(agent_id); result["quarantined"] = True
        elif strategy == HealStrategy.ROLLBACK:
            if "rollback" in tools:
                try: await tools["rollback"](context); result["success"] = True
                except Exception: pass
        elif strategy == HealStrategy.ESCALATE:
            result["escalated"] = True
            if "escalate" in tools:
                try: await tools["escalate"](context)
                except Exception: pass
        return result

    def root_cause_summary(self, agent_id: str, window: int = 10) -> Dict:
        recent = [f for f in self.failure_log if f["agent_id"] == agent_id][-window:]
        causes = {}
        for r in recent: causes[r["cause"]] = causes.get(r["cause"], 0) + 1
        top = max(causes, key=causes.get) if causes else "none"
        return {"agent_id": agent_id, "top_cause": top, "failure_count": len(recent), "circuit_state": self.circuit_state.get(agent_id, "closed"), "quarantined": agent_id in self.quarantine}


