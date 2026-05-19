"""Dual-Channel Lead Router — WhatsApp + Telegram + CRM

Routes qualified Dubai RE leads to multiple channels simultaneously.

Usage:
    from sovereign_swarm.campaigns.lead_router import LeadRouter
    router = LeadRouter()
    await router.route_lead(lead_result)
"""
import json, os, re, time
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import quote

TELEGRAM_API = "https://api.telegram.org/bot{token}"


class LeadRouter:
    """Routes leads to WhatsApp, Telegram, and CRM."""

    def __init__(self, telegram_token: str = None, telegram_chat_id: str = None,
                 crm_dir: str = "/tmp/dubai_re_crm", whatsapp_number: str = None):
        self.token = telegram_token or self._load_env("TELEGRAM_BOT_TOKEN")
        self.chat_id = telegram_chat_id or "8252725134"  # Default: Sahil's Telegram
        self.whatsapp = whatsapp_number or "+971585476077"
        self.crm_dir = Path(crm_dir)
        self.crm_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_env(key: str) -> str:
        env_path = Path.home() / ".hermes/.env"
        if not env_path.exists():
            return ""
        with open(env_path) as f:
            for line in f:
                m = re.match(rf'^{re.escape(key)}\s*=\s*(.*)$', line.strip())
                if m:
                    return m.group(1).strip().strip('"').strip("'")
        return ""

    def _tg_api(self, method: str, payload: dict) -> dict:
        """Fire Telegram API call."""
        if not self.token:
            return {"ok": False, "error": "no_token"}
        import urllib.request, socket
        socket.setdefaulttimeout(15)
        url = f"{TELEGRAM_API.format(token=self.token)}/{method}"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _generate_wa_link(self, text: str) -> str:
        """Generate WhatsApp click-to-chat link."""
        clean = self.whatsapp.replace("+", "").replace(" ", "")
        msg = quote(text[:300])
        return f"https://wa.me/{clean}?text={msg}"

    def _format_lead_message(self, result: dict) -> str:
        """Format lead result for Telegram/WhatsApp."""
        lead = result.get("lead", {})
        lines = [
            f"🎯 *NEW QUALIFIED LEAD*",
            f"Score: {int(lead.get('confidence', 0) * 100)}% | Intent: {lead.get('intent', '?')} | Urgency: {lead.get('urgency', '?')}",
            "",
            f"Query: `{result.get('search_params', {}).get('location', 'N/A')}`",
            f"Budget: AED {result.get('search_params', {}).get('budget_max', 0):,}",
            f"Properties found: {result.get('results_count', 0)}",
            "",
        ]

        for r in result.get("results", [])[:3]:
            price_m = r["price_aed"] / 1000000
            lines.append(f"🏠 {r['id']} | {r['bedrooms']}BR {r['type']} | AED {price_m:.2f}M | {r['location'].title()}")
            if r.get("project"):
                lines.append(f"   📍 {r['project']}")

        lines.append("")
        lines.append(f"👤 Agent: Sahil Khan (RERA 15970)")
        lines.append(f"💬 [Open WhatsApp]({self._generate_wa_link('Hi Sahil, interested in properties')})")
        lines.append(f"📞 Direct: `{self.whatsapp}`")

        return "\n".join(lines)

    def route_telegram(self, result: dict) -> bool:
        """Push lead to Telegram."""
        msg = self._format_lead_message(result)
        resp = self._tg_api("sendMessage", {
            "chat_id": self.chat_id,
            "text": msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        })
        ok = resp.get("ok", False)
        print(f"[LeadRouter] Telegram: {'SENT' if ok else 'FAILED'} ({resp.get('error', 'OK')})")
        return ok

    def route_whatsapp(self, result: dict) -> str:
        """Generate WhatsApp action link for the lead."""
        text = f"Hi, I'm interested in {result.get('results_count', 0)} properties you listed. Can we discuss?"
        link = self._generate_wa_link(text)
        print(f"[LeadRouter] WhatsApp link: {link[:80]}...")
        return link

    def route_crm(self, result: dict) -> str:
        """Export lead to CRM JSONL file."""
        timestamp = int(time.time())
        filename = self.crm_dir / f"lead_{timestamp}_{result.get('results_count', 0)}.json"
        with open(filename, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"[LeadRouter] CRM export: {filename}")
        return str(filename)

    def route_all(self, result: dict) -> dict:
        """Route lead to ALL channels simultaneously."""
        return {
            "telegram": self.route_telegram(result),
            "whatsapp_link": self.route_whatsapp(result),
            "crm_file": self.route_crm(result),
            "timestamp": int(time.time()),
        }


# ─── CLI Test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from sovereign_swarm.agents.dubai_re_agent import DubaiREAgent

    agent = DubaiREAgent()
    result = agent.handle_voice_query("2 bedroom apartment in Business Bay budget 3 million")

    router = LeadRouter()
    print("="*60)
    print("DUAL-CHANNEL LEAD ROUTER TEST")
    print("="*60)
    print(f"Query: 2BR in Business Bay budget 3M")
    print(f"Qualified: {result['lead']['qualified']}, Score: {result['lead']['confidence']}")
    print()

    routes = router.route_all(result)
    print()
    print("ROUTES:")
    for k, v in routes.items():
        print(f"  {k}: {v}")
