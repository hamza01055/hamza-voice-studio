#!/usr/bin/env bash
# One-time setup (Linux/macOS). Requires Python 3.11+, Node.js 20+, FFmpeg.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v ffmpeg >/dev/null || echo "WARNING: ffmpeg not found on PATH (needed for import/export)."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r backend/requirements-dev.txt
(cd frontend && npm ci && npm run build)
echo "Setup complete. Start with: scripts/start.sh"
