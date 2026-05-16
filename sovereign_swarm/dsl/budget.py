"""BudgetEnforcer — hard circuit breakers on tokens, time, and cost.

Wraps the existing BudgetController with DSL-specific tracking
and integration into the Mission/Result lifecycle.
"""

import time
from typing import Dict, Optional
from dataclasses import dataclass, field


@dataclass
class BudgetSnap:
    tokens_used: int = 0
    cost_usd: float = 0.0
    elapsed_sec: float = 0.0
    charges: list[tuple[str, float, float]] = field(default_factory=list)
    kill_switch: bool = False


class BudgetEnforcer:
    def __init__(self, clock_fn=time.time):
        self._clock = clock_fn
        self._budgets: Dict[str, BudgetSnap] = {}

    def _snap(self, mission_id: str) -> BudgetSnap:
        if mission_id not in self._budgets:
            self._budgets[mission_id] = BudgetSnap()
        return self._budgets[mission_id]

    def affordable(self, mission) -> bool:
        """Pre-flight check: is this mission affordable at all?"""
        snap = self._snap(mission.requester_id)
        return (
            snap.tokens_used <= mission.max_tokens
            and snap.cost_usd <= mission.max_cost_usd
            and snap.elapsed_sec <= mission.max_time_sec
            and not snap.kill_switch
        )

    def charge_tokens(self, mission_id: str, n: int):
        snap = self._snap(mission_id)
        snap.tokens_used += n

    def charge_cost(self, mission_id: str, usd: float):
        snap = self._snap(mission_id)
        snap.cost_usd += usd
        snap.charges.append((mission_id, self._clock(), usd))

    def charge_time(self, mission_id: str, sec: float):
        snap = self._snap(mission_id)
        snap.elapsed_sec += sec

    def exhausted(self, mission) -> bool:
        snap = self._snap(mission.requester_id)
        return (
            snap.tokens_used >= mission.max_tokens
            or snap.cost_usd >= mission.max_cost_usd
            or snap.elapsed_sec >= mission.max_time_sec
            or snap.kill_switch
        )

    def remaining(self, mission) -> dict:
        snap = self._snap(mission.requester_id)
        return {
            "tokens_remaining": max(0, mission.max_tokens - snap.tokens_used),
            "cost_remaining": max(0.0, mission.max_cost_usd - snap.cost_usd),
            "time_remaining": max(0.0, mission.max_time_sec - snap.elapsed_sec),
            "tokens_pct": snap.tokens_used / max(mission.max_tokens, 1),
            "cost_pct": snap.cost_usd / max(mission.max_cost_usd, 0.01),
            "time_pct": snap.elapsed_sec / max(mission.max_time_sec, 1),
        }

    def arm_kill_switch(self, mission_id: str):
        self._snap(mission_id).kill_switch = True

    def disarm_kill_switch(self, mission_id: str):
        self._snap(mission_id).kill_switch = False

    def report(self, mission_id: str, verbose: bool = False) -> dict:
        snap = self._snap(mission_id)
        r = {
            "tokens_used": snap.tokens_used,
            "cost_usd": round(snap.cost_usd, 6),
            "elapsed_sec": round(snap.elapsed_sec, 3),
            "kill_switch": snap.kill_switch,
        }
        if verbose:
            r["charges"] = snap.charges[-20:]
        return r

    def reset(self, mission_id: str):
        if mission_id in self._budgets:
            del self._budgets[mission_id]
