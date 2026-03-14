#!/bin/bash
# SCRPT Engine Startup Script
# Used by launchd to start the backend server

cd "/Users/tiger/Desktop/CATALOG ENGINE/bookr"

export PYTHONPATH="/Users/tiger/Desktop/CATALOG ENGINE/bookr:/Users/tiger/Library/Python/3.9/lib/python/site-packages"
export PATH="/Library/Developer/CommandLineTools/usr/bin:/Users/tiger/Library/Python/3.9/bin:/usr/local/bin:/usr/bin:/bin"

# Disable user site-packages auto-discovery (we add it via PYTHONPATH instead)
# to avoid launchd sandbox PermissionError on site-packages scanning
export PYTHONNOUSERSITE=1

exec /Library/Developer/CommandLineTools/usr/bin/python3 -m uvicorn engine.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --loop asyncio \
    --http h11
