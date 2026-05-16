"""Result — structured outcome of any DSL operation.

Provides rich error context so that callers know exactly what failed
and what checkpoint to roll back to.
"""

from dataclasses import dataclass
from typing import Any, Optional
import json
import time as _time


@dataclass(frozen=True)
class Result:
    ok: bool
    state: str = "unknown"          # One of MissionState values
    data: Any = None
    checkpoint_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: str = ""
    rollback_target: Optional[str] = None
    cost_incurred: float = 0.0
    tokens_used: int = 0
    elapsed_sec: float = 0.0
    metadata: dict = None
    timestamp: Optional[float] = None

    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", _time.time())

    def succeeded(self) -> bool:
        return self.ok and not self.error_code

    def needs_rollback(self) -> bool:
        return not self.ok and self.rollback_target is not None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "state": self.state,
            "data": self.data,
            "checkpoint_id": self.checkpoint_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "rollback_target": self.rollback_target,
            "cost_incurred": self.cost_incurred,
            "tokens_used": self.tokens_used,
            "elapsed_sec": self.elapsed_sec,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @staticmethod
    def success(data=None, state="complete", checkpoint_id=None, cost=0.0, tokens=0, elapsed=0.0):
        return Result(
            ok=True,
            state=state,
            data=data,
            checkpoint_id=checkpoint_id,
            cost_incurred=cost,
            tokens_used=tokens,
            elapsed_sec=elapsed,
        )

    @staticmethod
    def error(code: str, message: str = "", rollback_target: Optional[str] = None, checkpoint_id: Optional[str] = None, state="error"):
        return Result(
            ok=False,
            state=state,
            error_code=code,
            error_message=message,
            rollback_target=rollback_target,
            checkpoint_id=checkpoint_id,
        )
