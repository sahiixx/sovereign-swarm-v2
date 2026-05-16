# Sovereign Swarm v2 — Dubai RE Deployment Guide

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Telegram                             │
└──────────────────────┬────────────────────────────────────────┘
                       │ POST / (webhook)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Telegram Bot  (port 18802)                      │
│   /start, /find, /dsl, /status                                   │
│   routes /dsl → n8n-lite → DSL daemon                          │
└┬─────────────────────┬───────────────────────────────────────────┘
 │                     │
 │ /find or /dsl       │ health
 │                     ▼
 ▼           ┌─────────────────────┐
POST         │   n8n-lite          │  (port 5678)
/webhook/    │   webhook engine    │
dsl-mission  │   /webhook/dsl-mission
             │   /webhook/telegram │
             └────────┬────────────┘
                      │ POST
                      ▼
            ┌─────────────────────┐
            │   DSL Daemon          │  (port 18800)
            │   Deterministic       │
            │   Sovereign Loop      │
            │   /api/v1/mission     │
            │   /api/v1/status      │
            └─────────────────────┘
```

## Ports

| Service        | Port  | Endpoints                         |
|----------------|-------|-----------------------------------|
| DSL Daemon     | 18800 | /api/v1/mission, /api/v1/status |
| n8n-lite       | 5678  | /webhook/dsl-mission, /webhook/telegram, /health, /workflows |
| Telegram Bot   | 18802 | / (webhook), /health, /status     |

## Systemd Services

- `n8n-lite.service`        → runs `scripts/n8n-lite.py` on port 5678, auto-restart
- `telegram-bot.service`    → runs `scripts/telegram_bot.py` on port 18802, after n8n-lite
- DSL daemon is started by deploy script (`python -m sovereign_swarm.dsl.daemon`)

## Commands

```bash
# Start all services
sudo systemctl start n8n-lite telegram-bot

# Enable on boot
sudo systemctl enable n8n-lite telegram-bot

# Check logs
sudo journalctl -u n8n-lite -f
sudo journalctl -u telegram-bot -f

# Health check
python3 scripts/health-check.py

# Full deploy (git pull, pip install, restart, health check)
./scripts/deploy-all.sh
```

## Environment

All services read credentials from `/home/sahiix/.hermes/secrets.env`:

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here
```

## n8n Workflow Import

Lite workflow (webhook → intent parse → condition → DSL POST → format → Telegram send):
`/home/sahiix/n8n/lite-workflow.json`

Import via n8n web UI: Settings → Import from file.

## Files Created

- `/etc/systemd/system/n8n-lite.service`
- `/etc/systemd/system/telegram-bot.service`
- `/home/sahiix/n8n/lite-workflow.json`
- `/home/sahiix/sovereign-swarm-v2/scripts/health-check.py`
- `/home/sahiix/sovereign-swarm-v2/scripts/deploy-all.sh`
- `/home/sahiix/sovereign-swarm-v2/README.md`
- `/home/sahiix/.hermes/secrets.env` (template)
