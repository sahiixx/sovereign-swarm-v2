from ..config import *

class AgentProfile:
    def __init__(self, agent_id: str, skills: List[str], trust: float = 0.5, latency_ms: float = 100, cost_usd: float = 0.001):
        self.agent_id = agent_id; self.skills = skills; self.trust = trust; self.latency_ms = latency_ms; self.cost_usd = cost_usd

