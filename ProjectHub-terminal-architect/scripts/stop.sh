#!/bin/bash
# ProjectHub Web Interface — Stop Script
# Stops both JARVIS backend and frontend dev server

FRONTEND_DIR="/Users/codingstudio/__PROJECTHUB__/JARVIS/ProjectHub-terminal-architect"
PID_DIR="$FRONTEND_DIR/.pids"

stop_process() {
  local name="$1"
  local pid_file="$PID_DIR/$name.pid"

  if [ -f "$pid_file" ]; then
    local pid
    pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null
      echo "■ Stopped $name (PID $pid)"
    else
      echo "  $name was not running"
    fi
    rm -f "$pid_file"
  else
    echo "  No PID file for $name"
  fi
}

echo "Stopping ProjectHub..."
stop_process "frontend"
stop_process "backend"

# Fallback: kill by port if PID files were stale
for port in 3000 8000; do
  pid=$(lsof -ti ":$port" 2>/dev/null)
  if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null
    echo "■ Killed process on port $port (PID $pid)"
  fi
done

echo "✓ All stopped"
