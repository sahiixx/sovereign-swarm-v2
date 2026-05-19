#!/usr/bin/env python3
"""Dubai RE Lead Capture Server — Real-time lead intake and instant routing.

Exposes API endpoints for any lead source (website forms, other bots, platforms)
to push leads directly into the pipeline with instant scoring + routing.

Endpoints:
  POST /api/v1/lead        — Submit a new lead
  GET  /api/v1/lead/:id    — Get lead status
  GET  /api/v1/leads       — List recent leads
  GET  /api/v1/health      — Server health

Usage:
    python3 scripts/lead_capture_server.py   # runs on port 18803
"""
import os, sys, json, time, asyncio, threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from sovereign_swarm.agents.dubai_re_agent import DubaiREAgent
from sovereign_swarm.campaigns.lead_router import LeadRouter

# ─── Config ──────────────────────────────────────────────────────────
PORT = int(os.getenv("LEAD_SERVER_PORT", "18803"))
CRM_DIR = Path(os.getenv("LEAD_CRM_DIR", "/tmp/dubai_re_crm"))
CRM_DIR.mkdir(parents=True, exist_ok=True)

# ─── In-Memory Lead Store ──────────────────────────────────────────
_leads: Dict[str, dict] = {}
_leads_lock = threading.Lock()

# ─── Agent + Router Singletons ─────────────────────────────────────
_agent: DubaiREAgent = None
_router: LeadRouter = None

def get_agent() -> DubaiREAgent:
    global _agent
    if _agent is None:
        _agent = DubaiREAgent()
    return _agent

def get_router() -> LeadRouter:
    global _router
    if _router is None:
        _router = LeadRouter()
    return _router

# ─── Lead Scoring ────────────────────────────────────────────────────

@dataclass
class RawLead:
    name: str = ""
    phone: str = ""
    email: str = ""
    source: str = ""        # website, bot, referral, etc.
    budget: int = 0         # AED
    location: str = ""
    bedrooms: int = 0
    property_type: str = ""
    urgency: str = ""       # immediate, soon, browsing
    notes: str = ""
    contact_pref: str = ""  # whatsapp, phone, email
    timestamp: str = ""
    lead_id: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.lead_id:
            self.lead_id = f"LD-{int(time.time()*1000)}"


def score_lead(raw: RawLead) -> dict:
    """Score a raw lead and return enriched result."""
    agent = get_agent()
    
    # Build query from raw data
    query_parts = []
    if raw.bedrooms:
        query_parts.append(f"{raw.bedrooms} bedroom")
    if raw.property_type:
        query_parts.append(raw.property_type)
    if raw.location:
        query_parts.append(f"in {raw.location}")
    if raw.budget:
        query_parts.append(f"budget {raw.budget}")
    if raw.urgency:
        query_parts.append(raw.urgency)
    
    query = " ".join(query_parts) or raw.notes or "property in Dubai"
    
    # Run through agent
    result = agent.handle_voice_query(query)
    
    # Merge raw lead data with scored result
    enriched = {
        "lead_id": raw.lead_id,
        "raw": asdict(raw),
        "scored": result,
        "agent_profile": agent.agent_profile,
        "routed": {
            "telegram": False,
            "whatsapp": "",
            "crm": "",
        },
        "status": "scored",
        "received_at": raw.timestamp,
        "routed_at": "",
    }
    
    return enriched


def route_enriched_lead(enriched: dict) -> dict:
    """Route scored lead to all channels immediately."""
    router = get_router()
    result = enriched["scored"]
    
    # Route to Telegram
    tg_ok = router.route_telegram(result)
    
    # Generate WhatsApp link
    wa_link = router.route_whatsapp(result)
    
    # Export to CRM
    crm_file = router.route_crm(result)
    
    enriched["routed"] = {
        "telegram": tg_ok,
        "whatsapp": wa_link,
        "crm": crm_file,
    }
    enriched["status"] = "routed"
    enriched["routed_at"] = datetime.now().isoformat()
    
    # Store in memory
    with _leads_lock:
        _leads[enriched["lead_id"]] = enriched
    
    return enriched


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class LeadHandler(BaseHTTPRequestHandler):
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
                "service": "dubai-re-lead-capture",
                "version": "1.0.0",
                "leads_in_memory": len(_leads),
                "listings_loaded": len(get_agent().listings_db),
                "timestamp": datetime.now().isoformat(),
            })
            return
        
        if self.path == "/api/v1/leads":
            with _leads_lock:
                leads = list(_leads.values())[-50:]  # last 50
            self._json({
                "ok": True,
                "count": len(leads),
                "leads": [{k: v for k, v in l.items() if k != "scored"} for l in leads],  # omit full scored data
            })
            return
        
        if self.path.startswith("/api/v1/lead/"):
            lead_id = self.path.split("/")[-1]
            with _leads_lock:
                lead = _leads.get(lead_id)
            if lead:
                self._json({"ok": True, "lead": lead})
            else:
                self._json({"ok": False, "error": "Lead not found"}, 404)
            return
        
        self._json({"ok": False, "error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/api/v1/lead":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode() if length else "{}"
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return self._json({"ok": False, "error": "Invalid JSON"}, 400)
            
            # Build RawLead from POST data
            raw = RawLead(
                name=data.get("name", ""),
                phone=data.get("phone", ""),
                email=data.get("email", ""),
                source=data.get("source", "api"),
                budget=data.get("budget", 0),
                location=data.get("location", ""),
                bedrooms=data.get("bedrooms", 0),
                property_type=data.get("property_type", ""),
                urgency=data.get("urgency", ""),
                notes=data.get("notes", ""),
                contact_pref=data.get("contact_pref", "whatsapp"),
            )
            
            # Score + Route in background thread
            def process():
                try:
                    enriched = score_lead(raw)
                    route_enriched_lead(enriched)
                    print(f"[LEAD] {raw.lead_id} scored={enriched['scored']['lead']['qualified']} routed=OK")
                except Exception as e:
                    print(f"[LEAD] {raw.lead_id} ERROR: {e}")
            
            threading.Thread(target=process, daemon=True).start()
            
            # Return immediately with lead ID (async processing)
            self._json({
                "ok": True,
                "lead_id": raw.lead_id,
                "status": "processing",
                "message": "Lead accepted. Scoring and routing in background.",
                "check_status": f"/api/v1/lead/{raw.lead_id}",
            })
            return
        
        self._json({"ok": False, "error": "Not found"}, 404)


def main():
    server = ThreadedHTTPServer(("0.0.0.0", PORT), LeadHandler)
    print(f"[LEAD SERVER] Dubai RE Lead Capture on port {PORT}")
    print(f"[LEAD SERVER] POST /api/v1/lead to submit leads")
    print(f"[LEAD SERVER] GET  /api/v1/leads to list recent")
    print(f"[LEAD SERVER] CRM dir: {CRM_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[LEAD SERVER] Stopped.")


if __name__ == "__main__":
    main()
