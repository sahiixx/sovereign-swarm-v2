from ..config import *

class BudgetController:
    def __init__(self, session_limit: float = 10.0, daily_limit: float = 50.0):
        self.session_limit = session_limit
        self.daily_limit = daily_limit
        self.session_spent = 0.0
        self.daily_spent = 0.0
        self.day_start = time.time()
        self.agent_spent: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    def _rollover_day(self):
        if time.time() - self.day_start >= 86400:
            self.daily_spent = 0.0
            self.day_start = time.time()

    async def charge(self, agent_id: str, cost: float) -> bool:
        async with self._lock:
            self._rollover_day()
            if self.session_spent + cost > self.session_limit:
                return False
            if self.daily_spent + cost > self.daily_limit:
                return False
            self.session_spent += cost
            self.daily_spent += cost
            self.agent_spent[agent_id] = self.agent_spent.get(agent_id, 0.0) + cost
            return True

    async def remaining(self) -> Dict:
        async with self._lock:
            self._rollover_day()
            return {
                "session_remaining": round(self.session_limit - self.session_spent, 4),
                "daily_remaining": round(self.daily_limit - self.daily_spent, 4),
                "session_limit": self.session_limit,
                "daily_limit": self.daily_limit,
            }

    async def kill_switch_armed(self) -> bool:
        async with self._lock:
            return self.session_spent >= self.session_limit or self.daily_spent >= self.daily_limit

    async def report(self) -> Dict:
        async with self._lock:
            r = await self.remaining()
            r["per_agent"] = {k: round(v, 4) for k, v in self.agent_spent.items()}
            r["kill_switch"] = await self.kill_switch_armed()
            return r


