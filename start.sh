#!/bin/bash
# SCRPT dev launcher — engine (:8000) + frontend (:3000).
#
# The repo lives on iCloud Desktop, which stalls Next.js file watching, so the
# frontend is mirrored to local disk (~/.scrpt/dev/frontend) and served from
# there. Re-run this script after editing frontend source to re-sync (fast,
# incremental), or edit directly in the mirror during long UI sessions and
# rsync back.

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
MIRROR="$HOME/.scrpt/dev/frontend"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SCRPT — Write. Publish. Sell."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── engine ──
cd "$ROOT"
PYTHONPATH=. python3 -m uvicorn engine.main:app --reload --port 8000 &
ENGINE_PID=$!

# ── frontend (local-disk mirror) ──
mkdir -p "$MIRROR"
rsync -a --delete --exclude ".git" --exclude ".next" --exclude "node_modules" \
  "$ROOT/frontend/" "$MIRROR/"
if [ ! -d "$MIRROR/node_modules" ]; then
  echo "Installing frontend dependencies (first run)…"
  (cd "$MIRROR" && npm install)
fi
(cd "$MIRROR" && npm run dev) &
FRONTEND_PID=$!

cleanup() {
  echo "Shutting down…"
  kill "$ENGINE_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "  Engine:   http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo ""
wait
