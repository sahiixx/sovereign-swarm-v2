"""HermesWiring — connects all ecosystem components to HermesV2 channels.

Provides ready-made wiring for Swarm, Fixfizx, Moltworker, and Agency.
"""
from ..config import *
from .hermes_v2 import HermesV2


class HermesWiring:
    """Registers default handlers + wiring adapters for every channel."""

    def __init__(
        self,
        hermes: HermesV2,
        meta=None,
        safety=None,
        audit=None,
        bus=None,
        mcp=None,
        a2a=None,
        openclaw=None,
        llm=None,
        memory=None,
        bridge=None,
    ):
        self.hermes = hermes
        self.meta = meta
        self.safety = safety
        self.audit = audit
        self.bus = bus
        self.mcp = mcp
        self.a2a = a2a
        self.openclaw = openclaw
        self.llm = llm
        self.memory = memory
        self.bridge = bridge

        # In-memory clients for external systems (replace with real clients in production)
        self._fixfizx_client: Optional[Any] = None
        self._moltworker_client: Optional[Any] = None
        self._agency_client: Optional[Any] = None

    # ── Handlers ──────────────────────────────────────────

    async def _swarm_handler(self, payload: Dict) -> Dict:
        action = payload.get("action", "")
        if action == "safety.scan":
            if self.safety:
                text = payload.get("text", "")
                load = payload.get("load", 0.0)
                return self.safety.scan(text, load)
            return {"error": "no_safety"}
        if action == "meta.route":
            if self.meta:
                skill = payload.get("skill", "")
                strategy = payload.get("strategy", "balanced")
                agent_id = self.meta.route(skill, strategy)
                return {"agent_id": agent_id, "strategy": strategy}
            return {"error": "no_meta"}
        if action == "agent.spawn":
            return {"status": "spawned", "agent_id": payload.get("specialty", "unknown")}
        return {"channel": "swarm", "received": True}

    async def _agency_handler(self, payload: Dict) -> Dict:
        action = payload.get("action", "")
        if action == "orchestrate":
            mission = payload.get("mission", "")
            return {"status": "accepted", "mission": mission}
        if action == "llm.chat" and self.llm:
            prompt = payload.get("prompt", "")
            return {"response": f"(llm stub) {prompt[:50]}"}
        return {"channel": "agency", "received": True}

    async def _fixfizx_handler(self, payload: Dict) -> Dict:
        action = payload.get("action", "")
        if action == "health":
            return {"status": "ok", "platform": "fixfizx", "region": "dubai"}
        if action == "qualify_lead":
            lead = payload.get("lead", {})
            tier = "A" if lead.get("budget", 0) > 50000 else "B"
            return {"status": "qualified", "tier": tier, "lead_id": lead.get("id", "unknown")}
        if action == "list_campaigns":
            return {"campaigns": []}
        if self._fixfizx_client:
            return await self._fixfizx_client.request(action, payload)
        return {"channel": "fixfizx", "received": True}

    async def _moltworker_handler(self, payload: Dict) -> Dict:
        action = payload.get("action", "")
        if action == "status":
            return {"status": "ok", "platform": "moltworker", "channels": ["telegram", "discord", "slack"]}
        if action == "send":
            platform = payload.get("platform", "telegram")
            target = payload.get("target", "")
            message = payload.get("message", "")
            return {"status": "sent", "platform": platform, "target": target, "message_preview": message[:100]}
        if self._moltworker_client:
            return await self._moltworker_client.request(action, payload)
        return {"channel": "moltworker", "received": True}

    async def _mcp_handler(self, payload: Dict) -> Dict:
        if self.mcp:
            return await self.mcp.handle(payload)
        return {"channel": "mcp", "received": True}

    async def _a2a_handler(self, payload: Dict) -> Dict:
        if self.a2a:
            return await self.a2a._rpc_handler(AioWeb.Request(json=payload))
        return {"channel": "a2a", "received": True}

    async def _openclaw_handler(self, payload: Dict) -> Dict:
        if self.openclaw:
            return await self.openclaw.trigger_hook(payload.get("hook_id", 1), payload.get("context", {}))
        return {"channel": "openclaw", "received": True}

    async def _webhook_handler(self, payload: Dict) -> Dict:
        event_type = payload.get("event_type", "unknown")
        return {"channel": "webhook", "event_type": event_type, "received": True}

    async def _telegram_relay(self, payload: Dict) -> Dict:
        payload["action"] = payload.get("action", "send")
        payload["platform"] = "telegram"
        return await self._moltworker_handler(payload)

    async def _discord_relay(self, payload: Dict) -> Dict:
        payload["action"] = payload.get("action", "send")
        payload["platform"] = "discord"
        return await self._moltworker_handler(payload)

    async def _slack_relay(self, payload: Dict) -> Dict:
        payload["action"] = payload.get("action", "send")
        payload["platform"] = "slack"
        return await self._moltworker_handler(payload)

    async def _internal_handler(self, payload: Dict) -> Dict:
        action = payload.get("action", "")
        if action == "bus.publish" and self.bus:
            topic = payload.get("topic", "internal")
            await self.bus.publish(topic, payload.get("payload", {}))
            return {"published": True}
        if action == "memory.store" and self.memory:
            await self.memory.store(payload.get("key", ""), payload.get("value", {}), tags=payload.get("tags", ""))
            return {"stored": True}
        if action == "audit.query":
            if self.audit:
                return {"entries": self.audit.read_jsonl(limit=payload.get("limit", 20))}
            return {"entries": []}
        return {"channel": "internal", "received": True}

    # ── Wiring API ────────────────────────────────────────

    def wire_all(self):
        """Wire all 12 channels with default handlers."""
        self.hermes.register("swarm", self._swarm_handler)
        self.hermes.register("agency", self._agency_handler)
        self.hermes.register("fixfizx", self._fixfizx_handler)
        self.hermes.register("moltworker", self._moltworker_handler)
        self.hermes.register("mcp", self._mcp_handler)
        self.hermes.register("a2a", self._a2a_handler)
        self.hermes.register("openclaw", self._openclaw_handler)
        self.hermes.register("webhook", self._webhook_handler)
        self.hermes.register("telegram", self._telegram_relay)
        self.hermes.register("discord", self._discord_relay)
        self.hermes.register("slack", self._slack_relay)
        self.hermes.register("internal", self._internal_handler)

    def register_fixfizx_client(self, client):
        self._fixfizx_client = client

    def register_moltworker_client(self, client):
        self._moltworker_client = client

    def register_agency_client(self, client):
        self._agency_client = client

    def report(self) -> Dict:
        return {
            "wired_channels": self.hermes.status()["handlers_registered"],
            "fixfizx_client": self._fixfizx_client is not None,
            "moltworker_client": self._moltworker_client is not None,
            "agency_client": self._agency_client is not None,
            "hermes": self.hermes.status(),
        }
