#!/usr/bin/env python3
"""Health monitor + auto-restart for Dubai RE Bot.
Install as cron: */5 * * * * /home/sahiix/sovereign-swarm-v2/scripts/health-check.py
"""
import os, subprocess, sys, time

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PID_FILE = "/tmp/dubai-re-bot/bot.pid"
LOG_FILE = "/tmp/dubai-re-bot/bot.log"
RESTART_THRESHOLD = 300  # seconds since last log line before restart

def is_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False

def restart_bot():
    print(f"[{time.strftime('%H:%M:%S')}] Bot dead/unhealthy. Restarting...")
    os.makedirs("/tmp/dubai-re-bot", exist_ok=True)
    os.chdir(BOT_DIR)
    env = os.environ.copy()
    env["PYTHONPATH"] = BOT_DIR
    
    # Kill old if exists
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                old_pid = int(f.read().strip())
            if is_running(old_pid):
                os.kill(old_pid, 9)
                print(f"  Killed old PID {old_pid}")
        except Exception:
            pass
    
    # Start new
    log = open(LOG_FILE, "a")
    proc = subprocess.Popen(
        [sys.executable, "scripts/telegram_bot_polling.py"],
        stdout=log, stderr=subprocess.STDOUT,
        env=env, cwd=BOT_DIR
    )
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    print(f"  Started new PID {proc.pid}")
    
    # Also send Telegram status
    try:
        import urllib.request, json, socket
        socket.setdefaulttimeout(10)
        token = "8687957975:AAG111FdOEVZBgxRixaqzSsq2tysnGKOzoY"
        msg = f"🔄 *Bot Restarted*\nTime: {time.strftime('%Y-%m-%d %H:%M:%S')}\nPID: {proc.pid}"
        payload = json.dumps({"chat_id": "8252725134", "text": msg, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req)
    except Exception:
        pass

def main():
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        if is_running(pid):
            # Check log freshness
            if os.path.exists(LOG_FILE):
                mtime = os.path.getmtime(LOG_FILE)
                if time.time() - mtime > RESTART_THRESHOLD:
                    restart_bot()
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] Bot healthy (PID: {pid})")
            else:
                restart_bot()
        else:
            restart_bot()
    else:
        restart_bot()

if __name__ == "__main__":
    main()
