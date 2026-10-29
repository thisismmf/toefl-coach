#!/usr/bin/env bash
# TOEFL Coach — start / stop / inspect the local server.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

VENV="$DIR/.venv"
PY="$VENV/bin/python"
PIDFILE="$DIR/data/server.pid"
LOGFILE="$DIR/data/server.log"

HOST="${TOEFL_HOST:-127.0.0.1}"
PORT="${TOEFL_PORT:-8781}"
[ -f "$DIR/.env" ] && HOST="$(grep -E '^TOEFL_HOST=' "$DIR/.env" | cut -d= -f2 || echo "$HOST")"
[ -f "$DIR/.env" ] && PORT="$(grep -E '^TOEFL_PORT=' "$DIR/.env" | cut -d= -f2 || echo "$PORT")"
HOST="${HOST:-127.0.0.1}"; PORT="${PORT:-8781}"
URL="http://$HOST:$PORT"

c_g(){ printf '\033[32m%s\033[0m\n' "$*"; }
c_y(){ printf '\033[33m%s\033[0m\n' "$*"; }
c_r(){ printf '\033[31m%s\033[0m\n' "$*"; }
c_d(){ printf '\033[2m%s\033[0m\n' "$*"; }

mkdir -p "$DIR/data/charts"

ensure_venv() {
  if [ ! -x "$PY" ]; then
    c_y "Creating virtual environment…"
    if command -v uv >/dev/null 2>&1; then
      uv venv "$VENV" >/dev/null
      c_y "Installing dependencies…"
      VIRTUAL_ENV="$VENV" uv pip install -q -r requirements.txt
    else
      python3 -m venv "$VENV"
      c_y "Installing dependencies…"
      "$VENV/bin/pip" install -q --upgrade pip
      "$VENV/bin/pip" install -q -r requirements.txt
    fi
    c_g "Environment ready."
  fi
}

running() {
  [ -f "$PIDFILE" ] || return 1
  local pid; pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

cmd_up() {
  if running; then c_y "Already running at $URL (pid $(cat "$PIDFILE"))"; exit 0; fi
  ensure_venv
  [ -f "$DIR/.env" ] || { cp "$DIR/.env.example" "$DIR/.env"; c_d "Created .env from .env.example"; }

  c_y "Starting TOEFL Coach…"
  nohup "$PY" -m app.main >"$LOGFILE" 2>&1 &
  echo $! > "$PIDFILE"

  for _ in $(seq 1 40); do
    sleep 0.25
    if curl -fsS --max-time 2 "$URL/api/health" >/dev/null 2>&1; then
      c_g "TOEFL Coach is up  →  $URL"
      if curl -fsS --max-time 2 "http://localhost:11434/api/tags" >/dev/null 2>&1; then
        c_d "Ollama detected."
      else
        c_y "Ollama not reachable on :11434 — start it, or use an API provider in the UI."
      fi
      command -v open >/dev/null 2>&1 && open "$URL" || true
      exit 0
    fi
    running || break
  done
  c_r "Server failed to start. Last lines of the log:"
  tail -n 25 "$LOGFILE" || true
  rm -f "$PIDFILE"
  exit 1
}

cmd_down() {
  if ! running; then
    pkill -f "app.main" 2>/dev/null && c_g "Stopped stray process." || c_y "Not running."
    rm -f "$PIDFILE"; exit 0
  fi
  local pid; pid="$(cat "$PIDFILE")"
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
  kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  rm -f "$PIDFILE"
  c_g "Stopped."
}

cmd_status() {
  if running; then
    c_g "Running  (pid $(cat "$PIDFILE"))  →  $URL"
    curl -fsS --max-time 2 "$URL/api/health" 2>/dev/null | head -c 400; echo
  else
    c_y "Not running."
  fi
  if curl -fsS --max-time 2 "http://localhost:11434/api/tags" >/dev/null 2>&1; then
    c_d "Ollama models:"
    curl -fsS "http://localhost:11434/api/tags" \
      | "$PY" -c 'import json,sys;[print("  -",m["name"]) for m in json.load(sys.stdin)["models"]]' 2>/dev/null \
      || true
  fi
}

case "${1:-up}" in
  up|start)    cmd_up ;;
  down|stop)   cmd_down ;;
  restart)     cmd_down; sleep 0.6; cmd_up ;;
  status)      cmd_status ;;
  logs)        tail -f "$LOGFILE" ;;
  install)     ensure_venv ;;
  reset)       cmd_down; rm -f "$DIR/data/toefl.db"* "$DIR"/data/charts/*.png; c_g "Data cleared." ;;
  *) cat <<USAGE
TOEFL Coach

  ./run.sh up        start the server and open the browser
  ./run.sh down      stop the server
  ./run.sh restart   stop then start
  ./run.sh status    show status, health and available Ollama models
  ./run.sh logs      follow the server log
  ./run.sh install   create the venv and install dependencies only
  ./run.sh reset     stop and delete all saved runs and charts
USAGE
  ;;
esac
