"""Mission — immutable, budgeted, and auditable goal definition.

The Mission is the atomic contract of intent. Every field is frozen
upfront so that downstream layers cannot silently relax constraints.
"""

from dataclasses import dataclass, field
from typing import Optional
import json
from enum import Enum


class MissionState(Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    EXECUTING = "executing"
    VALIDATING = "validating"
    GOVERNING = "governing"
    COMPLETE = "complete"
    ROLLBACK = "rollback"
    ERROR = "error"


@dataclass(frozen=True)
class Mission:
    goal: str
    domain: str = "general"
    max_tokens: int = 4096
    max_time_sec: int = 60
    max_cost_usd: float = 5.0
    allow_self_modify: bool = False
    priority: int = 5  # 1 = highest, 10 = lowest
    tags: tuple[str, ...] = ()
    parent_mission_id: Optional[str] = None
    requester_id: str = "unknown"
    created_at: Optional[float] = None

    def __post_init__(self):
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be > 0")
        if self.max_time_sec <= 0:
            raise ValueError("max_time_sec must be > 0")
        if self.max_cost_usd < 0:
            raise ValueError("max_cost_usd must be >= 0")

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "domain": self.domain,
            "max_tokens": self.max_tokens,
            "max_time_sec": self.max_time_sec,
            "max_cost_usd": self.max_cost_usd,
            "allow_self_modify": self.allow_self_modify,
            "priority": self.priority,
            "tags": list(self.tags),
            "parent_mission_id": self.parent_mission_id,
            "requester_id": self.requester_id,
            "created_at": self.created_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @property
    def budget_key(self) -> str:
        """Stable identifier for budget tracking."""
        return f"{self.requester_id}:{self.domain}:{self.priority}"


def mission_from_json(raw: str) -> Mission:
    d = json.loads(raw)
    d["tags"] = tuple(d.get("tags", []))
    return Mission(**d)
