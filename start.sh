#!/usr/bin/env bash
# start.sh — simple, reliable runner for the Discord Gemini bot with clean logs.
# Usage:
#   ./start.sh
#   ./start.sh --no-restart  (run once, no auto-restart)

set -euo pipefail
IFS=$'\n\t'

VENV_DIR="venv"
BOT_SCRIPT="discord_gemini_bot.py"
LOG_DIR="logs"
LOG_FILE="${LOG_DIR}/app.log"
NO_RESTART=false

for arg in "$@"; do
  if [[ "$arg" == "--no-restart" ]]; then
    NO_RESTART=true
  fi
done

mkdir -p "$LOG_DIR"

# activate venv if exists
if [[ -f "${VENV_DIR}/bin/activate" ]]; then
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] ✅ Activating venv: $VENV_DIR" | tee -a "$LOG_FILE"
  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
else
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] ❌ No virtualenv found — using system Python" | tee -a "$LOG_FILE"
fi

if [[ ! -f "$BOT_SCRIPT" ]]; then
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] ❌ ERROR: Bot script '$BOT_SCRIPT' not found." | tee -a "$LOG_FILE" >&2
  exit 2
fi

run_once() {
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] ✅ Starting bot: ${BOT_SCRIPT}" | tee -a "$LOG_FILE"
  # start bot
  python "$BOT_SCRIPT" >> "$LOG_FILE" 2>&1 &
  BOT_PID=$!

  # simple watcher that looks for readiness
  tail -n0 -f "$LOG_FILE" &
  TAIL_PID=$!

  while kill -0 "$BOT_PID" 2>/dev/null; do
    if grep -q "Model .*ready.*accept queries" "$LOG_FILE"; then
      echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] ✅ Model is ready to interact" | tee -a "$LOG_FILE"
      break
    fi
    sleep 2
  done

  wait "$BOT_PID" || true
  kill "$TAIL_PID" 2>/dev/null || true
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] Bot process ended." | tee -a "$LOG_FILE"
}

if [[ "$NO_RESTART" == true ]]; then
  run_once
  exit 0
fi

RETRY_WAIT=3
MAX_WAIT=60
while true; do
  run_once
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] Restarting in ${RETRY_WAIT}s..." | tee -a "$LOG_FILE"
  sleep "$RETRY_WAIT"
  RETRY_WAIT=$(( RETRY_WAIT * 2 ))
  if [[ $RETRY_WAIT -gt $MAX_WAIT ]]; then RETRY_WAIT=$MAX_WAIT; fi
done
