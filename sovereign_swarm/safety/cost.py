from ..config import *

class CostController:
    def __init__(self, session_budget_usd: float = 10.0, daily_budget_usd: float = 50.0):
        self.session_budget = session_budget_usd; self.daily_budget = daily_budget_usd; self.spent_session = 0.0; self.spent_daily = 0.0
        self.agent_spent: Dict[str, float] = {}; self.session_start = time.time(); self.day_start = time.time()

    def charge(self, agent_id: str, cost_usd: float) -> bool:
        if self.spent_session + cost_usd > self.session_budget: return False
        if self.spent_daily + cost_usd > self.daily_budget: return False
        self.spent_session += cost_usd; self.spent_daily += cost_usd; self.agent_spent[agent_id] = self.agent_spent.get(agent_id, 0.0) + cost_usd
        return True

    def kill_switch_armed(self) -> bool:
        return self.spent_session >= self.session_budget or self.spent_daily >= self.daily_budget

    def report(self) -> Dict:
        return {"session_spent": round(self.spent_session, 4), "session_budget": self.session_budget, "daily_spent": round(self.spent_daily, 4), "daily_budget": self.daily_budget, "kill_switch": self.kill_switch_armed(), "per_agent": {k: round(v, 4) for k, v in self.agent_spent.items()}}


