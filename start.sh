#!/usr/bin/env bash
# start.sh — start the Discord Gemini bot with auto-restart, log streaming, and model-readiness watch
# Usage:
#   ./start.sh            -> run with auto-restart on crash
#   ./start.sh --no-restart -> run once (no restart)
# Exit codes: non-zero on fatal setup problems

set -euo pipefail
IFS=$'\n\t'

# ====== CONFIG ======
VENV_DIR="venv"
BOT_SCRIPT="discord_gemini_bot.py"
LOG_DIR="logs"
LOG_FILE="${LOG_DIR}/app.log"
NO_RESTART=false
# ====================

for arg in "$@"; do
  if [[ "$arg" == "--no-restart" ]]; then
    NO_RESTART=true
  fi
done

mkdir -p "$LOG_DIR"

# activate venv if exists
if [[ -d "$VENV_DIR" && -f "${VENV_DIR}/bin/activate" ]]; then
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] Activating venv: $VENV_DIR" | tee -a "$LOG_FILE"
  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
else
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] No virtualenv found at ${VENV_DIR} — running system Python" | tee -a "$LOG_FILE"
fi

# sanity checks
if [[ ! -f "$BOT_SCRIPT" ]]; then
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] ERROR: Bot script '$BOT_SCRIPT' not found." | tee -a "$LOG_FILE" >&2
  exit 2
fi

if [[ ! -f ".env" ]]; then
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] WARNING: .env file not found. Ensure DISCORD_TOKEN and GEMINI_API_KEY exist." | tee -a "$LOG_FILE"
fi

# helper to run one iteration
run_once() {
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] Starting bot: ${BOT_SCRIPT}" | tee -a "$LOG_FILE"

  # Start Python process
  python "$BOT_SCRIPT" >> "$LOG_FILE" 2>&1 &
  BOT_PID=$!

  # Watch logs for model readiness
  (
    gtail -n0 -f "$LOG_FILE" --pid=$BOT_PID | \
    while IFS= read -r line; do
      if [[ "$line" == *"Model"*ready*"accept queries"* ]]; then
        echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] ✅ Model is ready to interact (detected from bot logs)" | tee -a "$LOG_FILE"
      fi
    done
  ) &

  WATCH_PID=$!

  wait $BOT_PID
  RC=$?
  kill $WATCH_PID 2>/dev/null || true

  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] Bot exited with code ${RC}" | tee -a "$LOG_FILE"
  return $RC
}

# main loop: restart on crash unless no-restart
if [[ "$NO_RESTART" == true ]]; then
  run_once
  exit $?
fi

RETRY_WAIT=3
MAX_WAIT=60
while true; do
  run_once
  rc=$?
  if [[ $rc -eq 0 ]]; then
    echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] Exiting (normal termination)." | tee -a "$LOG_FILE"
    exit 0
  fi
  echo "[`date -u +'%Y-%m-%dT%H:%M:%SZ'`] Restarting in ${RETRY_WAIT}s (exit code ${rc})." | tee -a "$LOG_FILE"
  sleep "$RETRY_WAIT"
  RETRY_WAIT=$(( RETRY_WAIT * 2 ))
  if [[ $RETRY_WAIT -gt $MAX_WAIT ]]; then RETRY_WAIT=$MAX_WAIT; fi
done
