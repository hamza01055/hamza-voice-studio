#!/usr/bin/env bash
# Start the studio (API + worker + built UI) and open it in the browser.
set -euo pipefail
cd "$(dirname "$0")/../backend"
exec ../.venv/bin/python -m app.run "$@"
