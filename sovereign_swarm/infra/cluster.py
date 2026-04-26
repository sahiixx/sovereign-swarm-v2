"""Cluster management — cluster node discovery and health tracking."""

from ..config import *


class ClusterNode:
    """Represents a single node in the swarm cluster."""

    def __init__(self, node_id: str, host: str, port: int, capabilities: list[str] = None):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.capabilities = capabilities or []
        self.last_seen = time.time()
        self.status: str = "unknown"
        self.latency_ms: float = 0.0

    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "capabilities": self.capabilities,
            "last_seen": self.last_seen,
            "status": self.status,
            "latency_ms": self.latency_ms,
        }


class ClusterManager:
    """Manages cluster nodes, heartbeats, and leader election."""

    def __init__(self, node_id: str, heartbeat_interval: float = 30.0):
        self.node_id = node_id
        self.heartbeat_interval = heartbeat_interval
        self.nodes: Dict[str, ClusterNode] = {}
        self.leader_id: Optional[str] = None
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    def register(self, node: ClusterNode):
        self.nodes[node.node_id] = node

    def unregister(self, node_id: str):
        self.nodes.pop(node_id, None)

    def get(self, node_id: str) -> Optional[ClusterNode]:
        return self.nodes.get(node_id)

    def get_leader(self) -> Optional[ClusterNode]:
        if self.leader_id:
            return self.nodes.get(self.leader_id)
        return None

    def elect_leader(self, strategy: str = "oldest") -> Optional[str]:
        if not self.nodes:
            self.leader_id = None
            return None
        if strategy == "oldest":
            self.leader_id = min(self.nodes.keys(), key=lambda n: self.nodes[n].last_seen)
        elif strategy == "newest":
            self.leader_id = max(self.nodes.keys(), key=lambda n: self.nodes[n].last_seen)
        elif strategy == "first":
            self.leader_id = list(self.nodes.keys())[0]
        return self.leader_id

    def healthy_nodes(self) -> list[ClusterNode]:
        now = time.time()
        return [n for n in self.nodes.values() if now - n.last_seen < self.heartbeat_interval * 3]

    async def start_heartbeat(self):
        self._task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self):
        if self._task:
            self._task.cancel()
            self._task = None

    async def _heartbeat_loop(self):
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            stale = [nid for nid, n in self.nodes.items() if time.time() - n.last_seen > self.heartbeat_interval * 3]
            for nid in stale:
                self.nodes[nid].status = "offline"
