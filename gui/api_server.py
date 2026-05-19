"""Sovereign Swarm Full-Stack GUI

FastAPI backend + Vanilla JS SPA. Single-file deployment.
Run: python3 gui/api_server.py

Endpoints:
  GET  /            → SPA dashboard
  GET  /api/health  → system status
  GET  /api/leads   → CRM leads (JSON)
  POST /api/leads   → add lead manually
  POST /api/search  → property search
  POST /api/notify  → send Telegram/WhatsApp
  WS   /ws          → real-time updates
"""
import os, sys, json, time, asyncio, socket, subprocess, urllib.parse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from sovereign_swarm.agents.dubai_re_agent import DubaiREAgent
from sovereign_swarm.campaigns.lead_router import LeadRouter
from sovereign_swarm.pipeline.worker import process_sync

# ─── Config ──────────────────────────────────────────────────────────
PORT = int(os.getenv("SWARM_GUI_PORT", "18805"))
CRM_DIR = Path("/tmp/dubai_re_crm")
STATUS_FILE = Path.home() / "sovereign-swarm-v2/data/system_status.json"
AGENT_NAME = "Sahil Khan"
AGENT_PHONE = "+971585476077"
AGENT_RERA = "15970"

# ─── State ───────────────────────────────────────────────────────────
_agent: Optional[DubaiREAgent] = None
_router: Optional[LeadRouter] = None
_clients: set = set()

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

# ─── Models ────────────────────────────────────────────────────────
@dataclass
class Lead:
    name: str
    phone: str = ""
    email: str = ""
    budget: int = 0
    location: str = ""
    bedrooms: int = 0
    property_type: str = ""
    urgency: str = ""
    notes: str = ""
    timestamp: str = ""
    lead_id: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.lead_id:
            self.lead_id = f"LD-{int(time.time()*1000)}"

# ─── SPA HTML ────────────────────────────────────────────────────────
SPA_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sovereign Swarm — Command Center</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#06060a;--surface:#0f0f1a;--surface2:#16162a;--border:#1e1e3a;--accent:#00ff9d;--accent2:#00ccff;--warn:#ffd700;--crit:#ff3366;--text:#e8e8f0;--muted:#6b6b8a;--font:'Inter',system-ui,sans-serif;--radius:12px;--shadow:0 8px 32px rgba(0,0,0,.4)}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font);background:var(--bg);color:var(--text);min-height:100vh;line-height:1.5}
.container{max-width:1440px;margin:0 auto;padding:2rem}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:2rem;padding-bottom:1.5rem;border-bottom:1px solid var(--border)}
.brand{display:flex;align-items:center;gap:1rem}
.brand-icon{width:48px;height:48px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:var(--radius);display:flex;align-items:center;justify-content:center;font-size:1.5rem;box-shadow:0 0 20px rgba(0,255,157,.3)}
.brand h1{font-size:1.5rem;font-weight:800;letter-spacing:-.5px;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.brand .subtitle{color:var(--muted);font-size:.85rem;font-weight:400}
.status-pill{background:var(--surface);border:1px solid var(--border);padding:.5rem 1rem;border-radius:100px;font-size:.85rem;display:flex;align-items:center;gap:.5rem}
.status-pill .dot{width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1.5rem;margin-bottom:2rem}
@media(max-width:1200px){.grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:768px){.grid{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.5rem;box-shadow:var(--shadow);transition:transform .2s,border-color .2s}
.card:hover{transform:translateY(-2px);border-color:var(--accent)}
.card-header{display:flex;align-items:center;gap:.75rem;margin-bottom:1rem}
.card-icon{width:36px;height:36px;background:var(--surface2);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:1.1rem;border:1px solid var(--border)}
.card h3{font-size:.85rem;text-transform:uppercase;letter-spacing:1px;color:var(--muted);font-weight:600}
.card .metric{font-size:2.5rem;font-weight:800;margin:.5rem 0;color:var(--text)}
.card .metric span{font-size:1rem;font-weight:400;color:var(--muted);margin-left:.25rem}
.card .change{font-size:.85rem;color:var(--accent);font-weight:500}
.card .change.negative{color:var(--crit)}
.progress{height:6px;background:var(--surface2);border-radius:3px;overflow:hidden;margin-top:.75rem}
.progress-bar{height:100%;border-radius:3px;transition:width .5s ease}
.two-col{grid-column:span 2}
@media(max-width:768px){.two-col{grid-column:span 1}}
.section-title{font-size:1.1rem;font-weight:700;margin-bottom:1rem;display:flex;align-items:center;gap:.5rem}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th{text-align:left;padding:.75rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.5px;font-size:.75rem;border-bottom:2px solid var(--border)}
td{padding:.75rem;border-bottom:1px solid var(--border);vertical-align:middle}
tr:hover td{background:rgba(0,255,157,.03)}
.btn{background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--bg);border:none;padding:.6rem 1.2rem;border-radius:8px;font-weight:600;cursor:pointer;transition:all .2s;font-family:inherit;font-size:.85rem}
.btn:hover{transform:translateY(-1px);box-shadow:0 4px 16px rgba(0,255,157,.3)}
.btn-secondary{background:var(--surface2);color:var(--text);border:1px solid var(--border)}
.btn-secondary:hover{border-color:var(--accent);box-shadow:none}
input,select,textarea{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:.6rem .75rem;border-radius:8px;font-family:inherit;font-size:.9rem;width:100%;outline:none;transition:border-color .2s}
input:focus,select:focus,textarea:focus{border-color:var(--accent)}
.form-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:1rem}
@media(max-width:768px){.form-grid{grid-template-columns:1fr}}
.lead-row{cursor:pointer;transition:background .2s}
.lead-row:hover{background:rgba(0,255,157,.05)}
.badge{display:inline-block;padding:.2rem .5rem;border-radius:6px;font-size:.75rem;font-weight:600}
.badge-hot{background:rgba(255,51,102,.15);color:var(--crit)}
.badge-warm{background:rgba(255,215,0,.15);color:var(--warn)}
.badge-cold{background:rgba(0,255,157,.15);color:var(--accent)}
.tag{display:inline-block;padding:.15rem .5rem;border-radius:4px;font-size:.75rem;background:var(--surface2);border:1px solid var(--border);margin-right:.3rem}
.property-card{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:1rem;margin-bottom:.75rem;transition:border-color .2s}
.property-card:hover{border-color:var(--accent)}
.property-card .price{font-size:1.25rem;font-weight:700;color:var(--accent)}
.property-card .meta{color:var(--muted);font-size:.85rem;margin-top:.25rem}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);backdrop-filter:blur(8px);z-index:1000;align-items:center;justify-content:center}
.modal.active{display:flex}
.modal-content{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:2rem;max-width:600px;width:90%;max-height:90vh;overflow-y:auto;box-shadow:var(--shadow)}
.modal-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem}
.modal-header h2{font-size:1.25rem}
.close-btn{background:none;border:none;color:var(--muted);font-size:1.5rem;cursor:pointer}
.close-btn:hover{color:var(--text)}
.ws-indicator{position:fixed;bottom:1rem;right:1rem;padding:.5rem 1rem;background:var(--surface);border:1px solid var(--border);border-radius:100px;font-size:.75rem;display:flex;align-items:center;gap:.5rem;z-index:100}
.ws-indicator .dot{width:8px;height:8px;border-radius:50%}
.ws-indicator.online .dot{background:var(--accent);box-shadow:0 0 8px var(--accent)}
.ws-indicator.offline .dot{background:var(--crit);box-shadow:0 0 8px var(--crit)}
.logs{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:1rem;font-family:'JetBrains Mono',monospace;font-size:.8rem;max-height:300px;overflow-y:auto;color:var(--muted);line-height:1.6}
.logs .log-time{color:var(--accent2);margin-right:.5rem}
.logs .log-info{color:var(--accent)}
.logs .log-warn{color:var(--warn)}
.logs .log-error{color:var(--crit)}
.tab-bar{display:flex;gap:.5rem;margin-bottom:1.5rem;border-bottom:1px solid var(--border);padding-bottom:.5rem}
.tab-btn{background:none;border:none;color:var(--muted);padding:.5rem 1rem;cursor:pointer;font-family:inherit;font-size:.9rem;border-radius:6px;transition:all .2s}
.tab-btn.active{background:var(--surface2);color:var(--accent);font-weight:600}
.tab-btn:hover{color:var(--text)}
.tab-panel{display:none}
.tab-panel.active{display:block}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <div class="brand-icon">🦅</div>
      <div>
        <h1>SOVEREIGN SWARM</h1>
        <div class="subtitle">Dubai Real Estate — AI Command Center | Agent: ''' + AGENT_NAME + ''' | RERA ''' + AGENT_RERA + '''</div>
      </div>
    </div>
    <div class="status-pill">
      <span class="dot"></span>
      <span id="conn-status">Live</span>
    </div>
  </header>

  <div class="grid">
    <div class="card">
      <div class="card-header">
        <div class="card-icon">📥</div>
        <h3>Total Leads</h3>
      </div>
      <div class="metric" id="total-leads">—</div>
      <div class="change" id="lead-change">Pipeline active</div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-icon">🎯</div>
        <h3>Qualified</h3>
      </div>
      <div class="metric" id="qualified-leads">—</div>
      <div class="change" id="qualified-rate">Conversion rate —</div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-icon">📡</div>
        <h3>Intake Server</h3>
      </div>
      <div class="metric" id="intake-status">—</div>
      <div class="change" id="intake-detail">Port 18803</div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-icon">💾</div>
        <h3>C: Drive</h3>
      </div>
      <div class="metric" id="c-drive">—</div>
      <div class="progress">
        <div class="progress-bar" id="c-bar" style="width:0%"></div>
      </div>
      <div class="change" id="c-detail">—</div>
    </div>
  </div>

  <div class="tab-bar">
    <button class="tab-btn active" onclick="showTab('leads')">📋 Lead Pipeline</button>
    <button class="tab-btn" onclick="showTab('search')">🔍 Property Search</button>
    <button class="tab-btn" onclick="showTab('notify')">📨 Send Message</button>
    <button class="tab-btn" onclick="showTab('system')">⚙️ System Logs</button>
  </div>

  <!-- LEADS TAB -->
  <div id="tab-leads" class="tab-panel active">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
      <div class="section-title">📋 Lead Pipeline</div>
      <button class="btn" onclick="openAddLead()">+ Add Lead</button>
    </div>
    <div id="leads-table-container">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>Phone</th>
            <th>Location</th>
            <th>Budget</th>
            <th>Urgency</th>
            <th>Status</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody id="leads-body">
          <tr><td colspan="8" style="text-align:center;color:var(--muted)">Loading...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- SEARCH TAB -->
  <div id="tab-search" class="tab-panel">
    <div class="section-title">🔍 Property Search</div>
    <div class="form-grid">
      <div>
        <label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Location</label>
        <input id="search-location" placeholder="e.g. Business Bay, Marina">
      </div>
      <div>
        <label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Bedrooms</label>
        <select id="search-bedrooms">
          <option value="">Any</option>
          <option value="1">1 BR</option>
          <option value="2">2 BR</option>
          <option value="3">3 BR</option>
          <option value="4">4+ BR</option>
        </select>
      </div>
      <div>
        <label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Budget Max (AED)</label>
        <input id="search-budget" type="number" placeholder="3000000">
      </div>
    </div>
    <div style="display:flex;gap:.5rem;margin-bottom:1rem">
      <button class="btn" onclick="doSearch()">🔍 Search</button>
      <button class="btn btn-secondary" onclick="clearSearch()">Clear</button>
    </div>
    <div id="search-results">
      <div style="color:var(--muted);text-align:center;padding:2rem">Enter search criteria above</div>
    </div>
  </div>

  <!-- NOTIFY TAB -->
  <div id="tab-notify" class="tab-panel">
    <div class="section-title">📨 Quick Message</div>
    <div class="form-grid">
      <div>
        <label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Channel</label>
        <select id="notify-channel">
          <option value="telegram">Telegram</option>
          <option value="whatsapp">WhatsApp Link</option>
        </select>
      </div>
      <div>
        <label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Target (phone/chat_id)</label>
        <input id="notify-target" value="8252725134" placeholder="8252725134">
      </div>
      <div>
        <label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Message</label>
        <input id="notify-text" value="New lead alert! Check dashboard." placeholder="Message...">
      </div>
    </div>
    <button class="btn" onclick="doNotify()">📨 Send</button>
    <div id="notify-result" style="margin-top:1rem"></div>
  </div>

  <!-- SYSTEM TAB -->
  <div id="tab-system" class="tab-panel">
    <div class="section-title">⚙️ System Logs</div>
    <div class="logs" id="system-logs">
      <div><span class="log-time">--:--:--</span>Connecting...</div>
    </div>
    <div style="margin-top:1.5rem">
      <div class="section-title">🔧 Actions</div>
      <div style="display:flex;gap:.5rem;flex-wrap:wrap">
        <button class="btn btn-secondary" onclick="apiCall('/api/restart-intake')">🔄 Restart Intake</button>
        <button class="btn btn-secondary" onclick="apiCall('/api/cleanup-crm')">🧹 Cleanup CRM</button>
        <button class="btn btn-secondary" onclick="window.open('http://localhost:18804/','_blank')">📊 Legacy Dashboard</button>
      </div>
      <div id="action-result" style="margin-top:1rem"></div>
    </div>
  </div>
</div>

<!-- Add Lead Modal -->
<div class="modal" id="add-lead-modal">
  <div class="modal-content">
    <div class="modal-header">
      <h2>➕ Add New Lead</h2>
      <button class="close-btn" onclick="closeAddLead()">&times;</button>
    </div>
    <div class="form-grid">
      <div><label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Name</label><input id="lead-name" placeholder="Full name"></div>
      <div><label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Phone</label><input id="lead-phone" placeholder="+971..."></div>
      <div><label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Email</label><input id="lead-email" placeholder="email@domain.com"></div>
      <div><label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Budget (AED)</label><input id="lead-budget" type="number" placeholder="3000000"></div>
      <div><label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Location</label><input id="lead-location" placeholder="Business Bay"></div>
      <div><label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Bedrooms</label><input id="lead-bedrooms" type="number" placeholder="2"></div>
      <div><label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Property Type</label><input id="lead-type" placeholder="Apartment / Villa"></div>
      <div><label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Urgency</label><input id="lead-urgency" placeholder="hot / warm / browsing"></div>
      <div><label style="display:block;color:var(--muted);font-size:.8rem;margin-bottom:.3rem">Notes</label><input id="lead-notes" placeholder="Any details..."></div>
    </div>
    <button class="btn" onclick="submitLead()" style="width:100%">✅ Create Lead & Route</button>
  </div>
</div>

<div class="ws-indicator offline" id="ws-indicator">
  <span class="dot"></span>
  <span id="ws-text">Connecting...</span>
</div>

<script>
let ws;
let reconnectTimer;
let logs = [];

function connectWS() {
  ws = new WebSocket('ws://' + window.location.host + '/ws');
  ws.onopen = () => {
    document.getElementById('ws-indicator').className = 'ws-indicator online';
    document.getElementById('ws-text').textContent = 'Live';
    addLog('WebSocket connected', 'info');
  };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'health') updateHealth(msg.data);
    if (msg.type === 'leads') renderLeads(msg.data);
    if (msg.type === 'log') addLog(msg.text, msg.level);
  };
  ws.onclose = () => {
    document.getElementById('ws-indicator').className = 'ws-indicator offline';
    document.getElementById('ws-text').textContent = 'Reconnecting...';
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connectWS, 3000);
  };
}

async function apiCall(path, method='GET', body=null) {
  const opts = {method, headers:{'Content-Type':'application/json'}};
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  return r.json();
}

function updateHealth(data) {
  document.getElementById('total-leads').textContent = data.total_leads || '0';
  document.getElementById('qualified-leads').textContent = data.qualified || '0';
  document.getElementById('qualified-rate').textContent = data.qualified_rate || '0% rate';
  
  const intake = data.intake_alive ? 'ONLINE' : 'OFFLINE';
  document.getElementById('intake-status').textContent = intake;
  document.getElementById('intake-status').style.color = data.intake_alive ? 'var(--accent)' : 'var(--crit)';
  
  const c = data.c_drive_pct || 0;
  document.getElementById('c-drive').textContent = c + '%';
  document.getElementById('c-bar').style.width = c + '%';
  document.getElementById('c-bar').style.background = c < 85 ? 'var(--accent)' : c < 90 ? 'var(--warn)' : 'var(--crit)';
  document.getElementById('c-detail').textContent = (data.c_used || 0) + 'GB / ' + (data.c_total || 0) + 'GB';
}

function renderLeads(leads) {
  const tbody = document.getElementById('leads-body');
  if (!leads.length) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted)">No leads yet. Add one above.</td></tr>';
    return;
  }
  tbody.innerHTML = leads.map(l => {
    const urgency = (l.urgency || '').toLowerCase();
    const badge = urgency.includes('hot') ? 'badge-hot' : urgency.includes('warm') ? 'badge-warm' : 'badge-cold';
    const badgeText = l.urgency || 'browsing';
    return `<tr class="lead-row">
      <td><span class="tag">${l.lead_id}</span></td>
      <td><strong>${l.name || 'Unknown'}</strong></td>
      <td>${l.phone || '-'}</td>
      <td>${l.location || '-'}</td>
      <td>${l.budget ? 'AED ' + l.budget.toLocaleString() : '-'}</td>
      <td><span class="badge ${badge}">${badgeText}</span></td>
      <td>🟢 New</td>
      <td><span style="color:var(--muted);font-size:.8rem">${l.timestamp?.slice(0,16) || '-'}</span></td>
    </tr>`;
  }).join('');
}

async function doSearch() {
  const container = document.getElementById('search-results');
  container.innerHTML = '<div style="color:var(--muted);text-align:center;padding:2rem">Searching...</div>';
  const result = await apiCall('/api/search', 'POST', {
    location: document.getElementById('search-location').value,
    bedrooms: document.getElementById('search-bedrooms').value,
    budget_max: parseInt(document.getElementById('search-budget').value) || 0
  });
  if (!result.results?.length) {
    container.innerHTML = '<div style="color:var(--muted);text-align:center;padding:2rem">No properties found.</div>';
    return;
  }
  container.innerHTML = `
    <div style="margin-bottom:.5rem;color:var(--muted)">Found ${result.results_count} properties <span style="color:var(--accent)">| Score: ${Math.round(result.lead?.confidence*100)}%</span></div>
    ${result.results.slice(0,5).map(r => `
      <div class="property-card">
        <div class="price">AED ${(r.price_aed/1000000).toFixed(2)}M</div>
        <div class="meta">${r.bedrooms}BR ${r.type} • ${r.area_sqft?.toLocaleString()} sq ft • ${r.location?.title()} ${r.project ? '• ' + r.project : ''}</div>
        <div class="meta" style="margin-top:.5rem">🏠 ${r.id} | Ready: ${r.ready ? 'Yes' : 'No'} | Amenities: ${r.amenities?.join(', ') || 'None'}</div>
      </div>
    `).join('')}
  `;
}

function clearSearch() {
  document.getElementById('search-location').value = '';
  document.getElementById('search-bedrooms').value = '';
  document.getElementById('search-budget').value = '';
  document.getElementById('search-results').innerHTML = '<div style="color:var(--muted);text-align:center;padding:2rem">Enter search criteria above</div>';
}

async function doNotify() {
  const result = await apiCall('/api/notify', 'POST', {
    channel: document.getElementById('notify-channel').value,
    target: document.getElementById('notify-target').value,
    text: document.getElementById('notify-text').value
  });
  document.getElementById('notify-result').innerHTML = `
    <div style="padding:1rem;background:var(--surface2);border-radius:8px;border-left:3px solid var(--accent)">
      <strong>${result.ok ? '✅ Sent' : '❌ Failed'}</strong>: ${result.message || result.error || ''}
    </div>
  `;
}

function openAddLead() { document.getElementById('add-lead-modal').classList.add('active'); }
function closeAddLead() { document.getElementById('add-lead-modal').classList.remove('active'); }

async function submitLead() {
  const lead = {
    name: document.getElementById('lead-name').value,
    phone: document.getElementById('lead-phone').value,
    email: document.getElementById('lead-email').value,
    budget: parseInt(document.getElementById('lead-budget').value) || 0,
    location: document.getElementById('lead-location').value,
    bedrooms: parseInt(document.getElementById('lead-bedrooms').value) || 0,
    property_type: document.getElementById('lead-type').value,
    urgency: document.getElementById('lead-urgency').value,
    notes: document.getElementById('lead-notes').value
  };
  const result = await apiCall('/api/leads', 'POST', lead);
  closeAddLead();
  addLog(`Lead created: ${result.lead_id}`, 'info');
  // Refresh
  const health = await apiCall('/api/health');
  updateHealth(health);
  const leads = await apiCall('/api/leads');
  renderLeads(leads);
}

function addLog(text, level='info') {
  const now = new Date().toLocaleTimeString();
  logs.unshift({time: now, text, level});
  if (logs.length > 100) logs.pop();
  const el = document.getElementById('system-logs');
  el.innerHTML = logs.map(l => `<div><span class="log-time">${l.time}</span><span class="log-${l.level}">${l.text}</span></div>`).join('');
}

function showTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
}

// Init
connectWS();
// Initial load
apiCall('/api/health').then(updateHealth);
apiCall('/api/leads').then(renderLeads);
addLog('Dashboard initialized', 'info');
</script>
</body>
</html>
'''

# ─── FastAPI App ───────────────────────────────────────────────────
app = FastAPI(title="Sovereign Swarm GUI", version="2.2.0")

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=SPA_HTML, status_code=200)

@app.get("/api/health")
async def health():
    # Check intake
    intake_alive = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            intake_alive = s.connect_ex(("127.0.0.1", 18803)) == 0
    except:
        pass
    
    # C: drive
    c_pct, c_used, c_total = 0, 0, 0
    try:
        stat = os.statvfs("/mnt/c/")
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        c_pct = int((total - free) / total * 100)
        c_used = int((total - free) / 1e9)
        c_total = int(total / 1e9)
    except:
        pass
    
    # CRM
    crm_files = list(CRM_DIR.glob("*.json"))
    total_leads = len(crm_files)
    qualified = 0
    for f in crm_files:
        try:
            data = json.loads(f.read_text())
            if data.get("lead", {}).get("qualified"):
                qualified += 1
        except:
            pass
    
    rate = f"{int(qualified/total_leads*100)}%" if total_leads else "N/A"
    
    return {
        "intake_alive": intake_alive,
        "c_drive_pct": c_pct,
        "c_used": c_used,
        "c_total": c_total,
        "total_leads": total_leads,
        "qualified": qualified,
        "qualified_rate": rate,
        "timestamp": datetime.now().isoformat(),
    }

@app.get("/api/leads")
async def get_leads():
    files = sorted(CRM_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    leads = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            lead = data.get("lead", {})
            leads.append({
                "lead_id": data.get("lead_id", f.stem),
                "name": lead.get("name", "Unknown"),
                "phone": lead.get("phone", ""),
                "email": lead.get("email", ""),
                "budget": lead.get("budget", 0),
                "location": lead.get("location", ""),
                "bedrooms": lead.get("bedrooms", 0),
                "property_type": lead.get("property_type", ""),
                "urgency": lead.get("urgency", ""),
                "notes": lead.get("notes", ""),
                "timestamp": lead.get("timestamp", ""),
                "qualified": lead.get("qualified", False),
            })
        except:
            pass
    return leads

@app.post("/api/leads")
async def add_lead(lead: dict):
    """Replace fragile inline code with 4-layer pipeline."""
    # Build raw_text from form fields (matches what SPA sends)
    parts = []
    name = lead.get("name", "")
    if name:
        parts.append(f"My name is {name}")
    if lead.get("bedrooms"):
        parts.append(f"looking for {lead.get('bedrooms')}BR")
    if lead.get("property_type"):
        parts.append(lead.get("property_type"))
    if lead.get("location"):
        parts.append(f"in {lead.get('location')}")
    if lead.get("budget"):
        parts.append(f"budget {lead.get('budget')}")
    if lead.get("urgency"):
        parts.append(f"urgency: {lead.get('urgency')}")
    if lead.get("notes"):
        parts.append(lead.get("notes"))
    if lead.get("phone"):
        parts.append(f"call me on {lead.get('phone')}")
    if lead.get("email"):
        parts.append(f"email: {lead.get('email')}")

    raw_text = " ".join(parts)
    if not raw_text.strip():
        return {"ok": False, "error": "Empty lead data"}

    result = process_sync(raw_text, source="web")
    await broadcast({"type": "log", "text": f"Lead {result['lead_id']}: {result['status']}", "level": "info"})
    return {"ok": result.get("valid", True), "lead_id": result["lead_id"], "status": result["status"], "valid": result.get("valid", True)}

@app.post("/api/ingest")
async def ingest_raw(payload: dict):
    """Direct pipeline ingest: raw_text → 4 layers → routed/invalid."""
    raw_text = payload.get("raw_text", "")
    source = payload.get("source", "web")
    source_id = payload.get("source_id", "")
    if not raw_text or not raw_text.strip():
        return JSONResponse({"ok": False, "error": "raw_text required"}, status_code=400)

    result = process_sync(raw_text, source=source, source_id=source_id)
    await broadcast({"type": "log", "text": f"Ingest {result['lead_id']}: {result['status']}", "level": "info"})
    return {"ok": result.get("valid", True), **result}

@app.get("/api/stats")
async def pipeline_stats():
    """Pipeline processing stats + system health."""
    stats = {"processed": 0, "valid": 0, "invalid": 0, "low_conf": 0, "errors": 0}
    dlq_count = 0
    try:
        from sovereign_swarm.pipeline.worker import _stats as pipeline_stats_module
        stats = dict(pipeline_stats_module)
    except:
        pass
    dlq_dir = Path("/tmp/dubai_re_dlq")
    if dlq_dir.exists():
        dlq_count = len(list(dlq_dir.glob("*.json")))
    return {
        "pipeline": {
            "processed": stats["processed"],
            "valid": stats["valid"],
            "invalid": stats["invalid"],
            "low_confidence": stats["low_conf"],
            "errors": stats["errors"],
            "dlq_files": dlq_count,
        },
        "crm_files": len(list(CRM_DIR.glob("*.json"))),
        "timestamp": datetime.now().isoformat(),
    }

@app.post("/api/search")
async def search_properties(params: dict):
    agent = get_agent()
    location = params.get("location", "")
    bedrooms = params.get("bedrooms", "")
    budget = params.get("budget_max", 0)
    
    query = f"{bedrooms} bedroom {location}".strip() if bedrooms else location
    if budget:
        query += f" budget {budget}"
    
    result = agent.handle_voice_query(query or "property in Dubai")
    return result

@app.post("/api/notify")
async def notify(params: dict):
    router = get_router()
    channel = params.get("channel", "telegram")
    target = params.get("target", "")
    text = params.get("text", "")
    
    if channel == "telegram":
        resp = router._tg_api("sendMessage", {
            "chat_id": target,
            "text": text,
            "parse_mode": "Markdown",
        })
        ok = resp.get("ok", False)
        return {"ok": ok, "message": "Telegram sent" if ok else resp.get("error", "Failed")}
    else:
        clean = target.replace("+", "").replace(" ", "")
        link = f"https://wa.me/{clean}?text={urllib.parse.quote(text[:300])}"
        return {"ok": True, "message": "WhatsApp link generated", "link": link}

@app.post("/api/restart-intake")
async def restart_intake():
    try:
        subprocess.run(["pkill", "-f", "lead_intake.py"], timeout=5)
        time.sleep(1)
        subprocess.Popen(
            ["python3", "scripts/lead_intake.py"],
            cwd=str(Path.home() / "sovereign-swarm-v2"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "message": "Intake server restarted"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/cleanup-crm")
async def cleanup_crm():
    count = 0
    for f in CRM_DIR.glob("*.json"):
        try:
            f.unlink()
            count += 1
        except:
            pass
    return {"ok": True, "deleted": count}

# ─── WebSocket ───────────────────────────────────────────────────────
async def broadcast(msg: dict):
    dead = set()
    for ws in _clients:
        try:
            await ws.send_text(json.dumps(msg))
        except:
            dead.add(ws)
    _clients.difference_update(dead)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    try:
        # Send initial data
        health = await health()
        await websocket.send_text(json.dumps({"type": "health", "data": health}))
        leads = await get_leads()
        await websocket.send_text(json.dumps({"type": "leads", "data": leads}))
        
        while True:
            await asyncio.sleep(5)
            health = await health()
            await websocket.send_text(json.dumps({"type": "health", "data": health}))
            leads = await get_leads()
            await websocket.send_text(json.dumps({"type": "leads", "data": leads}))
    except WebSocketDisconnect:
        _clients.discard(websocket)
    except Exception:
        _clients.discard(websocket)

# ─── Periodic Broadcast ──────────────────────────────────────────────
async def periodic_broadcast():
    while True:
        await asyncio.sleep(5)
        try:
            health = await health()
            await broadcast({"type": "health", "data": health})
            leads = await get_leads()
            await broadcast({"type": "leads", "data": leads})
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    print(f"[GUI] http://localhost:{PORT}/")
    print(f"[GUI] http://127.0.0.1:{PORT}/")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
