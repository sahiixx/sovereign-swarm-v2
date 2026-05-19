#!/usr/bin/env python3
"""Telegram Bot — Polling Mode (WSL-friendly, no webhook needed).

Continuously polls Telegram for messages and routes /find commands
directly to DubaiREAgent.

Usage:
    python3 telegram_bot_polling.py        # foreground
    nohup python3 telegram_bot_polling.py &   # background daemon
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import json
import logging
import urllib.request
from urllib.parse import urlencode

from sovereign_swarm.agents.dubai_re_agent import DubaiREAgent
from sovereign_swarm.campaigns.lead_router import LeadRouter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TOKEN:
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        import re
        with open(env_path) as f:
            for line in f:
                m = re.match(r'^TELEGRAM_BOT_TOKEN\s*=\s*(.*)$', line.strip())
                if m:
                    TOKEN = m.group(1).strip().strip('"').strip("'")
                    break

if not TOKEN:
    log.error("TELEGRAM_BOT_TOKEN not found. Set in env or ~/.hermes/.env")
    sys.exit(1)

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
POLL_INTERVAL = 2  # seconds between polls

# ─── Agent + Router Singletons ────────────────────────────────────────
_agent: DubaiREAgent = None
_router: LeadRouter = None

def get_agent() -> DubaiREAgent:
    global _agent
    if _agent is None:
        _agent = DubaiREAgent()
        log.info("DubaiREAgent loaded: %s listings", len(_agent.listings_db))
    return _agent

def get_router() -> LeadRouter:
    global _router
    if _router is None:
        _router = LeadRouter(telegram_token=TOKEN, telegram_chat_id="8252725134")
        log.info("LeadRouter initialized")
    return _router

# ─── Telegram API ─────────────────────────────────────────────────────

def tg_post(method: str, payload: dict = None) -> dict:
    url = f"{TELEGRAM_API}/{method}"
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log.warning("Telegram API %s failed: %s", method, e)
        return {"ok": False, "error": str(e)}

# ─── Message Handler ────────────────────────────────────────────────────

HELP_TEXT = (
    "🏠 *Dubai RE Voice Agent — Sahil Khan (RERA 15970)*\n"
    "Direct property search powered by AI. No middlemen.\n\n"
    "Commands:\n"
    "/find \u003cquery\u003e — search properties (e.g. `/find 2BR in Marina under 3M`)\n"
    "/start — show this help\n\n"
    "Examples:\n"
    "• `/find villa in Palm Jumeirah with pool budget 10M`\n"
    "• `/find off-plan studio in Dubai Land`\n"
    "• `/find 2 bedroom in Business Bay urgent`"
)

def handle_message(text: str, chat_id: int, message_id: int):
    text = text.strip()
    if not text.startswith("/"):
        return  # Ignore non-commands

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/start":
        tg_post("sendMessage", {"chat_id": chat_id, "text": HELP_TEXT, "parse_mode": "Markdown"})
        return
    if cmd == "/find":
        if not arg:
            tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": "Usage: `/find 2 bedroom apartment in Dubai Marina under 3M`",
                "parse_mode": "Markdown"
            })
            return

        tg_post("sendChatAction", {"chat_id": chat_id, "action": "typing"})

        try:
            agent = get_agent()
            result = agent.handle_voice_query(arg)
            lead = result.get("lead", {})

            # Format user-facing response
            lines = [
                f"🔍 *{arg[:60]}*",
                f"📊 *Results:* {result['results_count']} properties",
                "",
            ]

            if lead.get("qualified"):
                lines.append(f"🎯 *Qualified Lead* — Score: {int(lead.get('confidence', 0) * 100)}%")
                lines.append(f"Intent: _{lead.get('intent', '?')}_ | Urgency: _{lead.get('urgency', '?')}_")
                lines.append("")

            for r in result.get("results", [])[:5]:
                price_m = r["price_aed"] / 1000000
                lines.append(f"🏠 *{r['id']}* — {r['bedrooms']}BR {r['type']} in {r['location'].title()}")
                lines.append(f"   {r['area_sqft']:,} sq ft | AED {price_m:.2f}M")
                if r.get("project"):
                    lines.append(f"   📍 {r['project']}")
                lines.append(f"   ✅ Ready: {'Yes' if r.get('ready') else 'No'} | {', '.join(r.get('amenities', [])[:3])}")
                lines.append("")

            profile = agent.agent_profile
            lines.append(f"👤 {profile['name']} ({profile['rera']})")
            lines.append(f"💬 WhatsApp: `{profile['contact']['whatsapp']}`")

            msg = "\n".join(lines)
            tg_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

            # DUAL-CHANNEL: Route qualified leads to Telegram + WhatsApp
            if lead.get("qualified"):
                router = get_router()
                router.route_telegram(result)
                router.route_whatsapp(result)
                router.route_crm(result)
                tg_post("sendMessage", {
                    "chat_id": chat_id,
                    "text": "✅ Your lead has been forwarded to our agent. Expect contact within 24 hours!",
                    "parse_mode": "Markdown"
                })

        except Exception as e:
            log.exception("Find failed for chat %s", chat_id)
            tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": f"❌ Search failed. Try again or contact support.\n`{str(e)[:200]}`",
                "parse_mode": "Markdown"
            })
        return

    # Unknown command
    tg_post("sendMessage", {
        "chat_id": chat_id,
        "text": f"Unknown command: `{cmd}`\nTry `/find` or `/start`",
        "parse_mode": "Markdown"
    })

# ─── Main Poll Loop ───────────────────────────────────────────────────

def poll_loop():
    offset = 0
    log.info("🤖 Dubai RE Bot polling started. Press Ctrl+C to stop.")

    while True:
        try:
            resp = tg_post("getUpdates", {"offset": offset, "limit": 10, "timeout": 30})
            if not resp.get("ok"):
                log.warning("getUpdates error: %s", resp)
                time.sleep(POLL_INTERVAL)
                continue

            updates = resp.get("result", [])
            for update in updates:
                offset = max(offset, update["update_id"] + 1)
                msg = update.get("message", {})
                text = msg.get("text", "")
                chat = msg.get("chat", {})
                chat_id = chat.get("id")
                msg_id = msg.get("message_id", 0)
                username = msg.get("from", {}).get("username", "unknown")

                if text and chat_id:
                    log.info("Message from @%s in chat %s: %s", username, chat_id, text[:60])
                    handle_message(text, chat_id, msg_id)

            if not updates:
                time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log.info("Bot stopped by user.")
            break
        except Exception as e:
            log.exception("Poll error: %s", e)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    import time  # lazy import for sleep in loop
    poll_loop()
