"""Hermes v2 — Universal Async Message Bus for the SAHIIXX ecosystem.

12 channels. Safety-gated. Audit-trailed. Backpressure-aware.
"""
import collections
import itertools

from ..config import *


class HermesMessage:
    def __init__(self, channel: str, payload: Dict[str, Any], sender: str = "system", msg_id: str = None):
        self.channel = channel
        self.payload = payload
        self.sender = sender
        self.msg_id = msg_id or f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
        self.timestamp = time.time()
        self.result: Any = None
        self.error: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "msg_id": self.msg_id,
            "channel": self.channel,
            "sender": self.sender,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "result": self.result,
            "error": self.error,
        }


class HermesV2:
    """Central async message bus connecting 12 channels with safety + audit."""

    CHANNELS = [
        "agency", "swarm", "fixfizx", "moltworker",
        "mcp", "a2a", "openclaw", "webhook",
        "telegram", "discord", "slack", "internal",
    ]

    def __init__(
        self,
        safety: Optional[Any] = None,
        audit: Optional[Any] = None,
        bus: Optional[Any] = None,
    ):
        self._handlers: Dict[str, Callable] = {ch: None for ch in self.CHANNELS}
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._processor_task: Optional[asyncio.Task] = None
        self._running = False
        self._stats: Dict[str, Dict[str, int]] = {
            ch: {"sent": 0, "received": 0, "errors": 0, "blocked": 0} for ch in self.CHANNELS
        }
        self._history: collections.deque = collections.deque(maxlen=10000)
        self._backpressure = 0
        self.safety = safety
        self.audit = audit
        self.bus = bus
        self._relay_map: Dict[str, str] = {
            "telegram": "moltworker",
            "discord": "moltworker",
            "slack": "moltworker",
        }

    def register(self, channel: str, handler: Callable):
        if channel not in self.CHANNELS:
            raise ValueError(f"Unknown channel '{channel}'. Use: {self.CHANNELS}")
        self._handlers[channel] = handler

    def relay(self, from_channel: str, to_channel: str):
        self._relay_map[from_channel] = to_channel

    async def _safety_scan(self, msg: HermesMessage) -> bool:
        if not self.safety:
            return True
        text = json.dumps(msg.payload)
        load = self._backpressure / 500.0
        result = self.safety.scan(text, system_load=load)
        if result.get("blocked"):
            self._stats[msg.channel]["blocked"] += 1
            msg.error = f"SAFETY_BLOCKED:{result.get('rule','unknown')}"
            self._log_audit(msg, blocked=True)
            return False
        return True

    def _log_audit(self, msg: HermesMessage, blocked: bool = False):
        if not self.audit:
            return
        self.audit.log(
            event="hermes.message",
            data={
                "msg_id": msg.msg_id,
                "channel": msg.channel,
                "sender": msg.sender,
                "blocked": blocked,
                "error": msg.error,
                "payload_preview": json.dumps(msg.payload)[:200],
            },
            agent_id=msg.sender,
        )

    async def _dispatch(self, msg: HermesMessage) -> Any:
        handler = self._handlers.get(msg.channel)
        if not handler:
            # Try relay for bot channels
            relay_target = self._relay_map.get(msg.channel)
            if relay_target:
                handler = self._handlers.get(relay_target)
                if handler:
                    msg.channel = relay_target
        if not handler:
            msg.error = f"NO_HANDLER for channel {msg.channel}"
            self._stats[msg.channel]["errors"] += 1
            return None
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(msg.payload)
            else:
                result = handler(msg.payload)
            msg.result = result
            self._stats[msg.channel]["received"] += 1
            return result
        except Exception as e:
            msg.error = str(e)
            self._stats[msg.channel]["errors"] += 1
            return {"error": str(e), "channel": msg.channel}

    async def _processor(self):
        while self._running:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            safe = await self._safety_scan(msg)
            if not safe:
                self._history.append(msg.to_dict())
                self._queue.task_done()
                continue
            await self._dispatch(msg)
            self._history.append(msg.to_dict())
            self._queue.task_done()

    async def start(self):
        if self._running:
            return
        self._running = True
        self._processor_task = asyncio.create_task(self._processor())

    async def stop(self):
        self._running = False
        if self._processor_task:
            await self._processor_task
            self._processor_task = None
        await self._queue.join()

    async def send(self, channel: str, payload: Dict[str, Any], sender: str = "system") -> Dict[str, Any]:
        if channel not in self.CHANNELS:
            return {"error": f"Unknown channel '{channel}'"}
        msg = HermesMessage(channel=channel, payload=payload, sender=sender)
        self._stats[channel]["sent"] += 1
        if self._queue.qsize() >= 480:
            self._backpressure = self._queue.qsize()
        try:
            self._queue.put_nowait(msg)
        except asyncio.QueueFull:
            msg.error = "QUEUE_FULL"
            self._stats[channel]["errors"] += 1
            return {"error": "QUEUE_FULL", "channel": channel}
        # If queue is running async, return immediately with msg_id
        # Wait briefly for processed result (best-effort sync)
        for _ in range(20):
            await asyncio.sleep(0.01)
            if msg.result is not None or msg.error:
                break
        self._log_audit(msg)
        return {
            "msg_id": msg.msg_id,
            "channel": msg.channel,
            "result": msg.result,
            "error": msg.error,
        }

    async def broadcast(self, payload: Dict[str, Any], channels: Optional[List[str]] = None, exclude: Optional[List[str]] = None, sender: str = "system") -> Dict[str, Any]:
        targets = channels or self.CHANNELS
        if exclude:
            targets = [ch for ch in targets if ch not in exclude]
        results = {}
        for ch in targets:
            results[ch] = await self.send(ch, payload, sender=sender)
        return {"broadcast": True, "channels": targets, "results": results}

    async def auto_route(self, event_type: str, payload: Dict[str, Any], sender: str = "system") -> Dict[str, Any]:
        """Auto-route webhook-style events based on event_type string."""
        routes = {
            "lead.qualified": ["fixfizx", "moltworker", "agency"],
            "lead.new": ["agency", "fixfizx"],
            "message.received": ["moltworker", "agency"],
            "agent.spawned": ["swarm", "internal"],
            "agent.killed": ["swarm", "internal"],
            "safety.violation": ["swarm", "internal", "moltworker"],
            "backup.complete": ["internal"],
        }
        channels = routes.get(event_type, ["internal"])
        return await self.broadcast(payload, channels=channels, sender=sender)

    def audit_trail(self, limit: int = 20) -> List[Dict]:
        return list(itertools.islice(self._history, max(0, len(self._history) - limit), len(self._history)))

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "channels": self.CHANNELS,
            "handlers_registered": [ch for ch, h in self._handlers.items() if h is not None],
            "stats": self._stats,
            "queue_size": self._queue.qsize() if hasattr(self._queue, "qsize") else -1,
            "history_entries": len(self._history),
            "backpressure": self._backpressure,
        }

    def report(self) -> Dict[str, Any]:
        return {
            "version": "2.0",
            "channels": self.CHANNELS,
            "handlers": {ch: (h.__name__ if h else None) for ch, h in self._handlers.items()},
            "relay_map": self._relay_map,
            "stats": self._stats,
            "queue_size": self._queue.qsize() if hasattr(self._queue, "qsize") else -1,
            "history_entries": len(self._history),
        }
