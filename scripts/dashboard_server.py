#!/usr/bin/env python3
"""Sovereign Swarm Live Dashboard — Real-Time Ops Command Center

Serves at http://localhost:18804/
Auto-refreshes every 10 seconds. Dark theme, glassmorphism.
"""
import os, json, time, socket
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "18804"))
CRM_DIR = Path("/tmp/dubai_re_crm")
STATUS_FILE = Path.home() / "sovereign-swarm-v2/data/system_status.json"

HTML = '''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="10">
<title>Sovereign Swarm — Ops Dashboard</title>
<style>
:root{--bg:#0a0a0f;--card:#111118;--accent:#00ff9d;--warn:#ffd700;--crit:#ff3366;--text:#e0e0e0;--muted:#888}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);margin:0;padding:2rem;min-height:100vh}
.header{text-align:center;margin-bottom:2rem}
.header h1{font-size:2.5rem;margin:0;background:linear-gradient(90deg,var(--accent),#00ccff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header .subtitle{color:var(--muted);margin-top:.5rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1.5rem;max-width:1400px;margin:0 auto}
.card{background:var(--card);border:1px solid #1a1a2e;border-radius:16px;padding:1.5rem;backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(0,0,0,.3)}
.card h2{margin:0 0 1rem;font-size:1.1rem;color:var(--accent);text-transform:uppercase;letter-spacing:1px}
.status-dot{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:8px}
.healthy{background:var(--accent);box-shadow:0 0 10px var(--accent)}
.degraded{background:var(--warn);box-shadow:0 0 10px var(--warn)}
.critical{background:var(--crit);box-shadow:0 0 10px var(--crit)}
.metric{font-size:2.5rem;font-weight:700;margin:.5rem 0}
.metric-label{color:var(--muted);font-size:.9rem}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;color:var(--accent);padding:.5rem;border-bottom:1px solid #1a1a2e}
td{padding:.5rem;border-bottom:1px solid #1a1a2e}
tr:hover{background:rgba(255,255,255,.02)}
.timestamp{color:var(--muted);font-size:.8rem;text-align:center;margin-top:2rem}
.lead-card{background:rgba(0,255,157,.05);border-left:3px solid var(--accent);padding:.75rem;margin:.5rem 0;border-radius:0 8px 8px 0;font-size:.85rem}
.lead-card .name{font-weight:600;color:var(--accent)}
</style>
</head>
<body>
<div class="header">
  <h1>🦅 SOVEREIGN SWARM</h1>
  <div class="subtitle">Dubai Real Estate — Live Operations Command Center</div>
</div>
<div class="grid">
  <div class="card">
    <h2>🟢 System Health</h2>
    <div><span class="status-dot {{status_class}}"></span><strong>{{overall_status}}</strong></div>
    <div class="metric">{{crm_count}}</div>
    <div class="metric-label">Leads in Pipeline</div>
  </div>
  <div class="card">
    <h2>📡 Intake Server</h2>
    <div><span class="status-dot {{intake_class}}"></span><strong>{{intake_status}}</strong></div>
    <div class="metric-label">Port 18803 — HTTP Lead Router</div>
    <div style="margin-top:1rem;font-size:.85rem">
      <div>POST /lead <span style="color:var(--accent)">→ Telegram + WhatsApp + CRM</span></div>
    </div>
  </div>
  <div class="card">
    <h2>💾 C: Drive</h2>
    <div class="metric" style="color:{{c_color}}">{{c_pct}}%</div>
    <div class="metric-label">{{c_used}}GB / {{c_total}}GB used</div>
    <div style="margin-top:.5rem;height:6px;background:#1a1a2e;border-radius:3px;overflow:hidden">
      <div style="width:{{c_pct}}%;height:100%;background:{{c_color}};transition:width .5s"></div>
    </div>
  </div>
  <div class="card">
    <h2>⚡ Agent Config</h2>
    <div style="font-size:.85rem;line-height:1.8">
      <div>🤖 Model: <strong>kimi-k2.6:cloud</strong></div>
      <div>🔥 Provider: Groq (fallback ready)</div>
      <div>📡 Telegram: @sahiix_bot</div>
      <div>📞 WhatsApp: +971585476077</div>
      <div>🏛️ RERA: 15970</div>
      <div>📂 Git: 3 new commits</div>
    </div>
  </div>
  <div class="card" style="grid-column:1/-1">
    <h2>📥 Recent Leads (CRM)</h2>
    {{lead_cards}}
  </div>
</div>
<div class="timestamp">Last updated: {{timestamp}} — Auto-refreshes every 10s</div>
</body>
</html>
'''

def load_status():
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text())
    return {"intake_alive": True, "c_drive_pct": 90, "c_drive_used_gb": 215, "c_drive_total_gb": 238, "crm_count": 7, "overall": "🟡 DEGRADED"}

def load_recent_leads(limit=5):
    files = sorted(CRM_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    leads = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            lead = data.get("lead", {})
            leads.append({
                "id": data.get("lead_id", f.stem),
                "name": lead.get("name", "Unknown"),
                "phone": lead.get("phone", "N/A"),
                "budget": lead.get("budget", 0),
                "location": lead.get("location", "Dubai"),
                "timestamp": lead.get("timestamp", "Unknown"),
            })
        except:
            pass
    return leads

class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        status = load_status()
        leads = load_recent_leads()
        
        # Determine colors
        c_pct = status.get("c_drive_pct", 90)
        c_color = "#00ff9d" if c_pct < 85 else "#ffd700" if c_pct < 90 else "#ff3366"
        
        status_text = status.get("overall", "🟡 DEGRADED")
        status_class = "healthy" if "HEALTHY" in status_text else "degraded" if "DEGRADED" in status_text else "critical"
        
        intake_alive = status.get("intake_alive", True)
        intake_class = "healthy" if intake_alive else "critical"
        intake_status = "ONLINE" if intake_alive else "OFFLINE"
        
        # Build lead cards
        lead_html = ""
        for lead in leads:
            budget = f"AED {lead['budget']:,}" if lead['budget'] else "Budget N/A"
            lead_html += f'''
            <div class="lead-card">
              <span class="name">{lead['name']}</span> — {lead['location']} | {budget} | 📞 {lead['phone']} | 🆔 {lead['id']}
              <div style="color:var(--muted);font-size:.75rem;margin-top:.25rem">{lead['timestamp']}</div>
            </div>
            '''
        
        body = HTML.replace("{{overall_status}}", status_text)\
            .replace("{{status_class}}", status_class)\
            .replace("{{crm_count}}", str(status.get("crm_count", 7)))\
            .replace("{{intake_class}}", intake_class)\
            .replace("{{intake_status}}", intake_status)\
            .replace("{{c_pct}}", str(c_pct))\
            .replace("{{c_used}}", str(status.get("c_drive_used_gb", 215)))\
            .replace("{{c_total}}", str(status.get("c_drive_total_gb", 238)))\
            .replace("{{c_color}}", c_color)\
            .replace("{{lead_cards}}", lead_html or "<div style='color:var(--muted)'>No leads yet.</div>")\
            .replace("{{timestamp}}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

if __name__ == "__main__":
    srv = HTTPServer(("0.0.0.0", DASHBOARD_PORT), DashboardHandler)
    print(f"[DASHBOARD] http://localhost:{DASHBOARD_PORT}/")
    print(f"[DASHBOARD] http://127.0.0.1:{DASHBOARD_PORT}/")
    srv.serve_forever()
