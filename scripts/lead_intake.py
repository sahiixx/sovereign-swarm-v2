#!/usr/bin/env python3
"""Dubai RE Lead Intake — Instant Dual-Channel Router

POST /lead → scores + routes immediately to:
  1. Telegram → your personal chat with full lead card
  2. WhatsApp → wa.me pre-filled link for instant outreach
  3. CRM → JSON export

No bot interaction required. Direct push from any source.
"""
import os, sys, json, time, threading
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from sovereign_swarm.agents.dubai_re_agent import DubaiREAgent
from sovereign_swarm.campaigns.lead_router import LeadRouter

# ─── Config ─────────────────────────────────────────────────────────
PORT = int(os.getenv("LEAD_INTAKE_PORT", "18803"))
CRM_DIR = Path(os.getenv("LEAD_CRM_DIR", "/tmp/dubai_re_crm"))
CRM_DIR.mkdir(parents=True, exist_ok=True)

AGENT_NAME = "Sahil Khan"
AGENT_PHONE = "+971585476077"
AGENT_RERA = "15970"

# ─── Singletons ───────────────────────────────────────────────────────
_agent: DubaiREAgent = None
_router: LeadRouter = None

def get_agent():
    global _agent
    if _agent is None:
        _agent = DubaiREAgent()
    return _agent

def get_router():
    global _router
    if _router is None:
        _router = LeadRouter()
    return _router

# ─── Lead Model ───────────────────────────────────────────────────────

@dataclass
class Lead:
    name: str = ""
    phone: str = ""           # Lead's phone (not agent's)
    email: str = ""
    source: str = "api"
    budget: int = 0
    location: str = ""
    bedrooms: int = 0
    property_type: str = ""
    urgency: str = ""
    notes: str = ""
    contact_pref: str = "whatsapp"
    timestamp: str = ""
    lead_id: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.lead_id:
            self.lead_id = f"LD-{int(time.time()*1000)}"

# ─── Scoring ──────────────────────────────────────────────────────────

def score_and_route(lead: Lead) -> dict:
    """Full pipeline: score → search → route → store."""
    agent = get_agent()
    router = get_router()
    
    # Build search query from lead data
    parts = []
    if lead.bedrooms:
        parts.append(f"{lead.bedrooms} bedroom")
    if lead.property_type:
        parts.append(lead.property_type)
    if lead.location:
        parts.append(f"in {lead.location}")
    if lead.budget:
        parts.append(f"budget {lead.budget}")
    if lead.urgency:
        parts.append(lead.urgency)
    
    query = " ".join(parts) or lead.notes or "property in Dubai"
    
    # Score via agent
    result = agent.handle_voice_query(query)
    
    # Build lead card for agent (you)
    card = build_agent_card(lead, result)
    
    # Route to Telegram (you get notified)
    tg_ok = router.route_telegram(result)  # Uses the search result
    
    # Also send the lead card directly to you
    tg_card = router._tg_api("sendMessage", {
        "chat_id": "8252725134",
        "text": card,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    })
    
    # Generate WhatsApp outreach link (to contact the LEAD)
    wa_text = f"Hi {lead.name}, this is {AGENT_NAME} from FAM Real Estate. I saw your interest in {lead.location or 'Dubai properties'}. I'd love to help you find the perfect match. Are you free for a quick call?"
    wa_link = router._generate_wa_link(lead.phone or AGENT_PHONE, wa_text) if lead.phone else f"https://wa.me/{AGENT_PHONE.replace('+', '')}"
    
    # CRM export
    crm_data = {
        "lead_id": lead.lead_id,
        "lead": asdict(lead),
        "search_result": result,
        "agent_card": card,
        "wa_outreach_link": wa_link,
        "telegram_sent": tg_ok and tg_card.get("ok", False),
        "routed_at": datetime.now().isoformat(),
    }
    crm_file = CRM_DIR / f"{lead.lead_id}.json"
    with open(crm_file, "w") as f:
        json.dump(crm_data, f, indent=2, default=str)
    
    print(f"[LEAD] {lead.lead_id} | {lead.name} | {lead.phone} | routed={tg_ok}")
    
    return {
        "lead_id": lead.lead_id,
        "qualified": result["lead"]["qualified"],
        "confidence": result["lead"]["confidence"],
        "results_count": result["results_count"],
        "telegram": tg_ok,
        "whatsapp_outreach": wa_link,
        "crm": str(crm_file),
    }


def build_agent_card(lead: Lead, result: dict) -> str:
    """Build the notification card YOU receive."""
    lines = [
        f"🔥 *NEW LEAD — {lead.urgency.upper()}*",
        f"",
        f"👤 *{lead.name}*",
        f"📞 `{lead.phone}`" if lead.phone else "📞 *No phone provided*",
        f"📧 {lead.email}" if lead.email else "",
        f"💰 Budget: AED {lead.budget:,}" if lead.budget else "💰 Budget: Not specified",
        f"🏠 Looking: {lead.bedrooms}BR {lead.property_type} in {lead.location}" if any([lead.bedrooms, lead.property_type, lead.location]) else "🏠 Looking: Dubai properties",
        f"📝 {lead.notes}" if lead.notes else "",
        f"",
        f"📊 *Agent Search Results:*",
        f"Properties found: {result['results_count']}",
        f"Lead score: {int(result['lead']['confidence'] * 100)}%",
        f"Qualified: {'✅ YES' if result['lead']['qualified'] else '❌ No'}",
    ]
    
    # Add matching properties
    for r in result.get("results", [])[:3]:
        price_m = (r["price_aed"] or 0) / 1000000
        sqft = r.get("area_sqft") or 0
        lines.append(f"")
        lines.append(f"🏠 {r.get('id', '')} | {r.get('bedrooms', 0)}BR {r.get('type', '')}")
        lines.append(f"   {sqft:,} sq ft | AED {price_m:.2f}M")
        loc = (r.get("location") or "").title()
        lines.append(f"   {loc}")
        if r.get("project"):
            lines.append(f"   📍 {r['project']}")
    
    # Actions
    lines.append(f"")
    lines.append(f"🚀 *ACTIONS:*")
    if lead.phone:
        wa_msg = f"Hi {lead.name}, this is {AGENT_NAME} from FAM Real Estate. I saw your interest in {lead.location or 'Dubai properties'}. I'd love to help!"
        from urllib.parse import quote
        clean_phone = lead.phone.replace("+", "").replace(" ", "")
        wa_link = f"https://wa.me/{clean_phone}?text={quote(wa_msg[:300])}"
        lines.append(f"💬 [WhatsApp Lead]({wa_link})")
    lines.append(f"📞 [Call Lead](tel:{lead.phone.replace(' ', '')})" if lead.phone else "")
    lines.append(f"💬 [Your WhatsApp](https://wa.me/971585476077)")
    lines.append(f"")
    lines.append(f"ID: `{lead.lead_id}`")
    lines.append(f"Source: {lead.source}")
    lines.append(f"Time: {lead.timestamp}")
    
    return "\n".join(lines)

# ─── HTTP Server ─────────────────────────────────────────────────────

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class IntakeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {fmt % args}")

    def _json(self, data: dict, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def do_GET(self):
        if self.path in ("/", "/health"):
            self._json({
                "ok": True,
                "service": "dubai-re-lead-intake",
                "agent": AGENT_NAME,
                "rera": AGENT_RERA,
                "phone": AGENT_PHONE,
                "listings": len(get_agent().listings_db),
            })
            return
        self._json({"ok": False, "error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/lead":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode() if length else "{}"
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return self._json({"ok": False, "error": "Invalid JSON"}, 400)
            
            lead = Lead(
                name=data.get("name", "Anonymous"),
                phone=data.get("phone", ""),
                email=data.get("email", ""),
                source=data.get("source", "api"),
                budget=data.get("budget", 0),
                location=data.get("location", ""),
                bedrooms=data.get("bedrooms", 0),
                property_type=data.get("property_type", ""),
                urgency=data.get("urgency", "soon"),
                notes=data.get("notes", ""),
                contact_pref=data.get("contact_pref", "whatsapp"),
            )
            
            # Route in background
            def bg():
                try:
                    score_and_route(lead)
                except Exception as e:
                    print(f"[LEAD ERROR] {lead.lead_id}: {e}")
            
            threading.Thread(target=bg, daemon=True).start()
            
            self._json({
                "ok": True,
                "lead_id": lead.lead_id,
                "status": "routing",
                "check": f"/lead/{lead.lead_id}",
            })
            return
        
        self._json({"ok": False, "error": "Not found"}, 404)


def main():
    server = ThreadedHTTPServer(("0.0.0.0", PORT), IntakeHandler)
    print(f"[INTAKE] Dubai RE Lead Intake on port {PORT}")
    print(f"[INTAKE] POST /lead to submit leads")
    print(f"[INTAKE] Agent: {AGENT_NAME} | {AGENT_PHONE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
