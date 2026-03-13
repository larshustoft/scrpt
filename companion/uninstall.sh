#!/bin/bash
# SCRPT Companion — Uninstall LaunchAgent

set -e

PLIST_NAME="com.scrpt.companion.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "Uninstalling SCRPT companion..."

if [ -f "$PLIST_DST" ]; then
  launchctl unload "$PLIST_DST" 2>/dev/null || true
  rm "$PLIST_DST"
  echo "  Removed LaunchAgent"
else
  echo "  LaunchAgent not found (already removed?)"
fi

echo "Done."
