#!/bin/bash
# SCRPT Companion — Install LaunchAgent
# Starts the Python companion server on login (port 8000)

set -e

PLIST_NAME="com.scrpt.companion.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"
LOG_DIR="$HOME/.scrpt"

echo "Installing SCRPT companion..."

# Create log directory
mkdir -p "$LOG_DIR"

# Copy plist
cp "$PLIST_SRC" "$PLIST_DST"
echo "  Installed plist → $PLIST_DST"

# Unload first if already loaded (ignore errors)
launchctl unload "$PLIST_DST" 2>/dev/null || true

# Load the agent
launchctl load "$PLIST_DST"
echo "  Loaded LaunchAgent"

# Verify
sleep 1
if curl -s http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
  echo "  ✓ Companion is running on http://127.0.0.1:8000"
else
  echo "  ⏳ Companion starting up... check logs at $LOG_DIR/"
fi

echo "Done."
