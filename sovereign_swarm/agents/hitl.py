from ..config import *

class HITLStatus(Enum):
    PENDING = "pending"; APPROVED = "approved"; REJECTED = "rejected"; TIMEOUT = "timeout"



from ..config import *

class HITLCheckpoint:
    def __init__(self, action_id: str, description: str, timeout_seconds: float = 300.0):
        self.action_id = action_id; self.description = description; self.timeout = timeout_seconds
        self.status = HITLStatus.PENDING; self.resolved_at: Optional[float] = None

    async def wait(self) -> HITLStatus:
        deadline = time.time() + self.timeout
        while self.status == HITLStatus.PENDING and time.time() < deadline:
            await asyncio.sleep(1)
        if self.status == HITLStatus.PENDING: self.status = HITLStatus.TIMEOUT
        return self.status

    def approve(self):
        if self.status == HITLStatus.PENDING: self.status = HITLStatus.APPROVED; self.resolved_at = time.time()

    def reject(self):
        if self.status == HITLStatus.PENDING: self.status = HITLStatus.REJECTED; self.resolved_at = time.time()



from ..config import *

class HITLCouncil:
    def __init__(self):
        self.checkpoints: Dict[str, HITLCheckpoint] = {}

    def create(self, action_id: str, description: str, timeout: float = 300.0) -> HITLCheckpoint:
        cp = HITLCheckpoint(action_id, description, timeout); self.checkpoints[action_id] = cp; return cp

    def get(self, action_id: str) -> Optional[HITLCheckpoint]:
        return self.checkpoints.get(action_id)

    def report(self) -> Dict:
        return {aid: {"status": cp.status.value, "description": cp.description, "resolved_at": cp.resolved_at, "timeout": cp.timeout} for aid, cp in self.checkpoints.items()}


