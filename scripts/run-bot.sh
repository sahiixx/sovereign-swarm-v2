#!/bin/bash
# Dubai RE Bot — Production launcher with auto-restart
# Usage: bash scripts/run-bot.sh

LOG_DIR="/tmp/dubai-re-bot"
mkdir -p "$LOG_DIR"

PID_FILE="$LOG_DIR/bot.pid"
LOG_FILE="$LOG_DIR/bot.log"

cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd)"

# Check if already running
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Bot already running (PID: $(cat $PID_FILE))"
    echo "Logs: tail -f $LOG_FILE"
    exit 0
fi

# Start bot with nohup for persistence
echo "Starting Dubai RE Bot..."
nohup python3 scripts/telegram_bot_polling.py > "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"
echo "Bot started (PID: $PID)"
echo "Logs: tail -f $LOG_FILE"
echo "Stop: kill $(cat $PID_FILE)"
