#!/usr/bin/env python3
"""Sovereign Swarm Health Monitor — Autonomous Survival System

Checks every 5 minutes:
  - Intake server alive (port 18803)
  - C: drive space (<85% warning, <90% critical)
  - CRM pipeline health
  - Auto-restart intake if dead
  - Telegram alerts to agent
"""
import os, sys, json, time, socket, subprocess, urllib.request
from pathlib import Path
from datetime import datetime

# ─── Config ──────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = "8252725134"
INTAKE_PORT = 18803
CRM_DIR = Path("/tmp/dubai_re_crm")
C_DRIVE_THRESHOLD_WARN = 85
C_DRIVE_THRESHOLD_CRIT = 90
LOG_FILE = Path.home() / ".hermes/logs/health_mon.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# ─── Helpers ─────────────────────────────────────────────────────────
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def tg_alert(text: str):
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"TG alert failed: {e}")

def check_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", port)) == 0

def get_c_drive_usage():
    try:
        stat = os.statvfs("/mnt/c/")
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used_pct = int((total - free) / total * 100)
        return used_pct, int((total - free) / 1e9), int(total / 1e9)
    except:
        return 0, 0, 0

def restart_intake():
    try:
        subprocess.run(["pkill", "-f", "lead_intake.py"], timeout=5)
        time.sleep(2)
        subprocess.Popen(
            ["python3", "scripts/lead_intake.py"],
            cwd=str(Path.home() / "sovereign-swarm-v2"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        log("INTAKE SERVER RESTARTED")
        tg_alert(f"⚠️ *AUTO-RECOVERY*\nIntake server on port {INTAKE_PORT} was dead. Restarted.")
    except Exception as e:
        log(f"Restart failed: {e}")

# ─── Main Check ──────────────────────────────────────────────────────
def run_health_check():
    now = datetime.now().strftime("%H:%M:%S")
    log(f"--- HEALTH CHECK {now} ---")
    
    # 1. Intake server
    intake_alive = check_port(INTAKE_PORT)
    log(f"Intake server (:{INTAKE_PORT}): {'ALIVE' if intake_alive else 'DEAD'}")
    if not intake_alive:
        restart_intake()
    
    # 2. C: drive
    c_pct, c_used, c_total = get_c_drive_usage()
    log(f"C: drive: {c_used}GB / {c_total}GB ({c_pct}%)")
    if c_pct >= C_DRIVE_THRESHOLD_CRIT:
        tg_alert(f"🔴 *CRITICAL*\nC: drive at {c_pct}% ({c_used}GB / {c_total}GB)\nImmediate action needed!")
    elif c_pct >= C_DRIVE_THRESHOLD_WARN:
        tg_alert(f"🟡 *WARNING*\nC: drive at {c_pct}% ({c_used}GB / {c_total}GB)\nConsider cleanup.")
    
    # 3. CRM pipeline
    crm_count = len(list(CRM_DIR.glob("*.json")))
    log(f"CRM records: {crm_count}")
    
    # 4. Memory
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        mem_avail = [l for l in lines if "MemAvailable" in l][0]
        avail_kb = int(mem_avail.split()[1])
        log(f"Memory available: {avail_kb // 1024}MB")
    except:
        pass
    
    # Status summary
    status = "🟢 HEALTHY" if intake_alive and c_pct < C_DRIVE_THRESHOLD_WARN else "🟡 DEGRADED" if intake_alive else "🔴 CRITICAL"
    log(f"Overall: {status}")
    
    # Write status JSON for dashboard
    status_json = {
        "timestamp": datetime.now().isoformat(),
        "intake_alive": intake_alive,
        "c_drive_pct": c_pct,
        "c_drive_used_gb": c_used,
        "c_drive_total_gb": c_total,
        "crm_count": crm_count,
        "overall": status,
    }
    status_file = Path.home() / "sovereign-swarm-v2/data/system_status.json"
    status_file.parent.mkdir(parents=True, exist_ok=True)
    with open(status_file, "w") as f:
        json.dump(status_json, f, indent=2)
    
    log("--- END ---")

if __name__ == "__main__":
    run_health_check()
