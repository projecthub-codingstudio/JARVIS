#!/bin/bash
# ProjectHub Web Interface — Start Script
# Starts both JARVIS backend (port 8000) and frontend dev server (port 3000)

set -e

JARVIS_ROOT="/Users/codingstudio/__PROJECTHUB__/JARVIS"
BACKEND_DIR="$JARVIS_ROOT/alliance_20260317_130542"
FRONTEND_DIR="$JARVIS_ROOT/ProjectHub-terminal-architect"
BACKEND_VENV="$BACKEND_DIR/.venv/bin/python"
PID_DIR="$FRONTEND_DIR/.pids"

mkdir -p "$PID_DIR"

# ── Check if already running ─────────────────────
if [ -f "$PID_DIR/backend.pid" ] && kill -0 "$(cat "$PID_DIR/backend.pid")" 2>/dev/null; then
  echo "⚠ Backend already running (PID $(cat "$PID_DIR/backend.pid"))"
else
  # ── Start Backend ────────────────────────────────
  echo "▶ Starting JARVIS backend (port 8000)..."
  cd "$JARVIS_ROOT"

  # LLM model chain: use EXAONE-3.5-7.8B for actual responses (not stub)
  # MLX alias: exaone3.5:7.8b → mlx-community/EXAONE-3.5-7.8B-Instruct-4bit
  export JARVIS_MENU_BAR_MODEL_CHAIN="${JARVIS_MENU_BAR_MODEL_CHAIN:-exaone3.5:7.8b,stub}"

  "$BACKEND_VENV" -m jarvis.web_api --port 8000 > "$PID_DIR/backend.log" 2>&1 &
  echo $! > "$PID_DIR/backend.pid"
  echo "  PID: $(cat "$PID_DIR/backend.pid")"
fi

if [ -f "$PID_DIR/frontend.pid" ] && kill -0 "$(cat "$PID_DIR/frontend.pid")" 2>/dev/null; then
  echo "⚠ Frontend already running (PID $(cat "$PID_DIR/frontend.pid"))"
else
  # ── Start Frontend ───────────────────────────────
  echo "▶ Starting frontend dev server (port 3000)..."
  cd "$FRONTEND_DIR"
  npm run dev > "$PID_DIR/frontend.log" 2>&1 &
  echo $! > "$PID_DIR/frontend.pid"
  echo "  PID: $(cat "$PID_DIR/frontend.pid")"
fi

# ── Wait for backend health ────────────────────────
echo ""
echo "⏳ Waiting for backend..."
for i in $(seq 1 30); do
  if curl -s "http://localhost:8000/api/health" > /dev/null 2>&1; then
    echo "✓ Backend ready"
    break
  fi
  sleep 1
done

echo ""
echo "═══════════════════════════════════════════"
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000"
echo "  Logs:      $PID_DIR/*.log"
echo "  Stop:      scripts/stop.sh"
echo "═══════════════════════════════════════════"
