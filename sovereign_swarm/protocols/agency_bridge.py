"""AgencyBridge — bridge for routing cross-system calls from agency-agents via Hermes.

This provides a callable interface that agency-agents can import and use to send
messages through Hermes instead of direct HTTP. Stub for future integration.
"""
from ..config import *


class AgencyBridge:
    """Callable bridge that agency-agents (sahiixx/agency-agents) can use to route
    Fixfizx, Moltworker, Swarm, and n8n calls through Hermes instead of direct HTTP.
    """

    def __init__(self, hermes=None):
        self._hermes = hermes

    def bind(self, hermes):
        self._hermes = hermes

    async def qualify_lead(self, lead: Dict) -> Dict:
        if not self._hermes:
            return {"error": "no_hermes"}
        return await self._hermes.send("fixfizx", {"action": "qualify_lead", "lead": lead})

    async def send_message(self, platform: str, target: str, message: str) -> Dict:
        if not self._hermes:
            return {"error": "no_hermes"}
        return await self._hermes.send("moltworker", {"action": "send", "platform": platform, "target": target, "message": message})

    async def n8n_trigger(self, workflow_tag: str, payload: Dict) -> Dict:
        if not self._hermes:
            return {"error": "no_hermes"}
        return await self._hermes.send("webhook", {"action": "n8n", "workflow_tag": workflow_tag, "payload": payload})

    async def swarm_orchestrate(self, mission: str, params: Dict) -> Dict:
        if not self._hermes:
            return {"error": "no_hermes"}
        return await self._hermes.send("agency", {"action": "orchestrate", "mission": mission, "params": params})

    def report(self) -> Dict:
        return {"connected": self._hermes is not None}
