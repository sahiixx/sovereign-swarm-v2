"""HITL — Human-in-the-loop checkpoints with asyncio.Event."""

from ..config import *


class HITLStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class HITLCheckpoint:
    MIN_TIMEOUT = 1.0

    def __init__(self, action_id: str, description: str, timeout_seconds: float = 300.0):
        self.action_id = action_id
        self.description = description
        self.timeout = max(timeout_seconds, self.MIN_TIMEOUT)
        self.status = HITLStatus.PENDING
        self.resolved_at: Optional[float] = None
        self._event = asyncio.Event()

    async def wait(self) -> HITLStatus:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=self.timeout)
        except asyncio.TimeoutError:
            if self.status == HITLStatus.PENDING:
                self.status = HITLStatus.TIMEOUT
                self._event.set()
        return self.status

    def approve(self):
        if self.status == HITLStatus.PENDING:
            self.status = HITLStatus.APPROVED
            self.resolved_at = time.time()
            self._event.set()

    def reject(self):
        if self.status == HITLStatus.PENDING:
            self.status = HITLStatus.REJECTED
            self.resolved_at = time.time()
            self._event.set()


class HITLCouncil:
    def __init__(self):
        self.checkpoints: Dict[str, HITLCheckpoint] = {}

    def create(self, action_id: str, description: str, timeout: float = 300.0) -> HITLCheckpoint:
        cp = HITLCheckpoint(action_id, description, timeout)
        self.checkpoints[action_id] = cp
        return cp

    def get(self, action_id: str) -> Optional[HITLCheckpoint]:
        return self.checkpoints.get(action_id)

    def report(self) -> Dict:
        return {
            aid: {
                "status": cp.status.value,
                "description": cp.description,
                "resolved_at": cp.resolved_at,
                "timeout": cp.timeout,
            }
            for aid, cp in self.checkpoints.items()
        }
