"""Health monitoring and load-balancing feedback."""
from ..config import *

class HealthController:
    def __init__(self, max_agents: int = 64):
        self.agents: Dict[str, Dict] = {}
        self.max_agents = max_agents
        self.overload_threshold = 0.85

    def register(self, agent_id: str, capacity: float = 1.0):
        self.agents[agent_id] = {"load": 0.0, "healthy": True, "capacity": capacity, "tasks": 0}

    def update(self, agent_id: str, load_delta: float = 0.0):
        if agent_id not in self.agents:
            self.register(agent_id)
        self.agents[agent_id]["load"] = max(0.0, min(1.0, self.agents[agent_id]["load"] + load_delta))
        self.agents[agent_id]["tasks"] += 1 if load_delta > 0 else 0
        if self.agents[agent_id]["load"] >= self.overload_threshold:
            self.agents[agent_id]["healthy"] = False

    def health(self, agent_id: str) -> Dict:
        a = self.agents.get(agent_id, {})
        return {"agent_id": agent_id, "healthy": a.get("healthy", False), "load": round(a.get("load", 0), 3), "tasks": a.get("tasks", 0)}

    def all_healthy(self) -> bool:
        return all(a["healthy"] for a in self.agents.values()) if self.agents else True

    def report(self) -> Dict:
        loads = [a["load"] for a in self.agents.values()]
        return {
            "agents": len(self.agents),
            "healthy": sum(1 for a in self.agents.values() if a["healthy"]),
            "avg_load": round(sum(loads) / len(loads), 3) if loads else 0.0,
            "max_load": round(max(loads), 3) if loads else 0.0,
        }

    def rebalance_candidates(self) -> List[str]:
        return [aid for aid, a in self.agents.items() if not a["healthy"]]
