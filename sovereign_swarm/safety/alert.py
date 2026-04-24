from ..config import *

class AlertDispatcher:
    SEVERITIES = ["info", "warn", "error", "critical"]
    def __init__(self):
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", ""); self.discord_webhook = os.getenv("DISCORD_WEBHOOK_URL", ""); self.history: list = []

    async def _telegram(self, message: str, severity: str = "info") -> Dict:
        if not self.telegram_token or not aiohttp: return {"sent": False, "channel": "telegram"}
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {"chat_id": os.getenv("TELEGRAM_CHAT_ID", ""), "text": f"[{severity.upper()}] {message}", "parse_mode": "Markdown"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return {"sent": resp.status == 200, "channel": "telegram", "status": resp.status}
        except Exception as e: return {"sent": False, "channel": "telegram", "error": str(e)}

    async def _discord(self, message: str, severity: str = "info") -> Dict:
        if not self.discord_webhook or not aiohttp: return {"sent": False, "channel": "discord"}
        colors = {"info": 3447003, "warn": 16776960, "error": 15158332, "critical": 16711680}
        payload = {"embeds": [{"title": f"Swarm Alert — {severity.upper()}", "description": message, "color": colors.get(severity, 3447003)}]}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.discord_webhook, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return {"sent": resp.status in (200, 204), "channel": "discord", "status": resp.status}
        except Exception as e: return {"sent": False, "channel": "discord", "error": str(e)}

    async def send(self, message: str, severity: str = "info") -> Dict:
        if severity not in self.SEVERITIES: severity = "info"
        self.history.append({"message": message, "severity": severity, "timestamp": time.time()})
        return {"telegram": await self._telegram(message, severity), "discord": await self._discord(message, severity)}

    def report(self) -> Dict:
        return {"telegram_configured": bool(self.telegram_token), "discord_configured": bool(self.discord_webhook), "alerts_sent": len(self.history), "last_alert": self.history[-1] if self.history else None}


