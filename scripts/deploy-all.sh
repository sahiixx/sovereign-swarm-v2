#!/bin/bash
set -euo pipefail
REPO=/home/sahiix/sovereign-swarm-v2
ENVFILE=/home/sahiix/.hermes/secrets.env

cd "$REPO"

echo "[deploy] pulling latest..."
git pull origin main 2>/dev/null || git pull

echo "[deploy] installing deps..."
"$REPO/venv/bin/pip" install -q -e "$REPO" || pip install -q -e "$REPO"

echo "[deploy] reloading systemd..."
sudo systemctl daemon-reload

echo "[deploy] restarting n8n-lite..."
sudo systemctl restart n8n-lite.service

echo "[deploy] restarting telegram-bot..."
sudo systemctl restart telegram-bot.service

echo "[deploy] waiting for services..."
sleep 2

echo "[deploy] running health check..."
python3 "$REPO/scripts/health-check.py"

echo "[deploy] done."
