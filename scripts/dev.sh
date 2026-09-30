#!/usr/bin/env bash
# Development: backend on :8765 plus Vite dev server with hot reload on :5173.
set -euo pipefail
cd "$(dirname "$0")/.."
export HVS_TOKEN="${HVS_TOKEN:-dev-$(date +%s)}"
export HVS_DEV_ORIGINS="http://127.0.0.1:5173,http://localhost:5173"
(cd backend && ../.venv/bin/python -m app.run --no-browser --strict-port --port 8765) &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
echo "Open: http://127.0.0.1:5173/#token=$HVS_TOKEN"
cd frontend && npm run dev
