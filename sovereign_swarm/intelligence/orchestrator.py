from ..config import *
from .agent_profile import AgentProfile

class MetaOrchestrator:
    def __init__(self):
        self.agents: Dict[str, AgentProfile] = {}

    def register(self, profile: AgentProfile):
        self.agents[profile.agent_id] = profile

    def route(self, task_skill: str, strategy: str = "balanced") -> Optional[str]:
        candidates = [a for a in self.agents.values() if task_skill in a.skills]
        if not candidates: return None
        if strategy == "trust":
            candidates.sort(key=lambda x: x.trust, reverse=True)
        elif strategy == "latency":
            candidates.sort(key=lambda x: x.latency_ms)
        elif strategy == "cost":
            candidates.sort(key=lambda x: x.cost_usd)
        else:
            candidates.sort(key=lambda x: (x.trust * 0.5) + (1 / (1 + x.latency_ms / 1000)) * 0.3 + (1 / (1 + x.cost_usd * 100)) * 0.2, reverse=True)
        return candidates[0].agent_id

    def fallback(self, agent_id: str, task_skill: str) -> Optional[str]:
        candidates = [a for a in self.agents.values() if task_skill in a.skills and a.agent_id != agent_id]
        if not candidates: return None
        candidates.sort(key=lambda x: x.trust, reverse=True)
        return candidates[0].agent_id


