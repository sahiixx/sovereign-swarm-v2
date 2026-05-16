"""LazyConsensusGate — governance layer with auto-approve thresholds and HITL deferral.

Auto-approves when confidence > 0.9 AND risk < 0.1.
Otherwise, emits a governance request on the bus / to HITL channel.
"""

import asyncio, time, json
from dataclasses import dataclass
from typing import Optional, Dict, Callable, Awaitable
from enum import Enum


class Approval(Enum):
    GRANTED = "granted"
    DENIED = "denied"
    PENDING = "pending"


@dataclass(frozen=True)
class GovernanceRequest:
    proposal_id: str
    proposal: str
    confidence: float
    risk_score: float
    mission_id: str
    created_at: float
    voter_count: int = 1  # For multi-agent quorum
    quorum: int = 1

    def auto_approvable(self, min_confidence: float = 0.9, max_risk: float = 0.1) -> bool:
        return self.confidence >= min_confidence and self.risk_score <= max_risk


class LazyConsensusGate:
    def __init__(
        self,
        auto_confidence: float = 0.9,
        auto_risk: float = 0.1,
        poll_interval: int = 5,
        max_wait_sec: int = 300,
        hitl_callback: Optional[Callable[[GovernanceRequest], Awaitable[Approval]]] = None,
        bus=None,  # Optional SwarmBus for cross-agent voting
    ):
        self.auto_confidence = auto_confidence
        self.auto_risk = auto_risk
        self.poll_interval = poll_interval
        self.max_wait_sec = max_wait_sec
        self.hitl_callback = hitl_callback
        self._bus = bus
        self._cache: Dict[str, Approval] = {}

    async def request(self, proposal: str, confidence: float, risk_score: float, mission_id: str = "") -> GovernanceRequest:
        gid = f"gov:{mission_id}:{time.time():.6f}"
        req = GovernanceRequest(
            proposal_id=gid,
            proposal=proposal[:4096],  # Bounded
            confidence=confidence,
            risk_score=risk_score,
            mission_id=mission_id,
            created_at=time.time(),
        )

        if req.auto_approvable(self.auto_confidence, self.auto_risk):
            self._cache[gid] = Approval.GRANTED
            return req

        if self._bus:
            await self._bus.publish("governance.requests", req.__dict__)

        if self.hitl_callback:
            decision = await self.hitl_callback(req)
            self._cache[gid] = decision
            return req

        # No HITL configured and no auto-approve — deny safely
        self._cache[gid] = Approval.DENIED
        return req

    async def poll(self, proposal_id: str, timeout: int = None) -> Approval:
        timeout = timeout or self.max_wait_sec
        deadline = time.time() + timeout
        while time.time() < deadline:
            if proposal_id in self._cache:
                return self._cache[proposal_id]
            await asyncio.sleep(self.poll_interval)
        return Approval.DENIED

    def set(self, proposal_id: str, state: Approval):
        self._cache[proposal_id] = state

    def report(self) -> dict:
        return {
            "pending": sum(1 for v in self._cache.values() if v == Approval.PENDING),
            "granted": sum(1 for v in self._cache.values() if v == Approval.GRANTED),
            "denied": sum(1 for v in self._cache.values() if v == Approval.DENIED),
            "total": len(self._cache),
        }
