#!/bin/bash
# ProjectHub Web Interface — Restart Script

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Restarting ProjectHub..."
"$SCRIPT_DIR/stop.sh"
sleep 2
"$SCRIPT_DIR/start.sh"
