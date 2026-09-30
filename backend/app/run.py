"""Launcher: ``python -m app.run [--port N] [--no-browser]``.

Selects a free loopback port, creates the per-session token, starts the API (which
supervises the worker), and opens the studio in the default browser with the token in
the URL fragment (fragments are never sent to servers or written to access logs).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from app.core.config import Settings, set_settings


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def pick_port(host: str, preferred: int) -> int:
    if preferred and port_free(host, preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def main() -> None:
    ap = argparse.ArgumentParser(description="Hamza Voice Studio local server")
    ap.add_argument("--port", type=int, default=int(os.environ.get("HVS_PORT", "8765")))
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--print-json", action="store_true",
                    help="Print {port, token} as JSON on stdout (used by the desktop shell)")
    args = ap.parse_args()

    base = Settings()
    if base.host not in ("127.0.0.1", "localhost", "::1"):
        print("Refusing to bind to a non-loopback address; the local edition is single-user only.",
              file=sys.stderr)
        sys.exit(2)
    port = pick_port(base.host, args.port)
    settings = base.model_copy(update={"port": port})
    set_settings(settings)
    os.environ["HVS_PORT"] = str(port)
    url = f"http://127.0.0.1:{port}/#token={settings.token}"

    if args.print_json:
        print(json.dumps({"port": port, "token": settings.token}), flush=True)
    else:
        print(f"\n  Hamza Voice Studio is starting on http://127.0.0.1:{port}\n"
              f"  Open this link (contains your session token):\n  {url}\n", flush=True)

    if not args.no_browser and not args.print_json:
        def _open() -> None:
            for _ in range(120):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)  # noqa: S310
                    webbrowser.open(url)
                    return
                except OSError:
                    time.sleep(0.5)

        threading.Thread(target=_open, daemon=True).start()

    from app.main import create_app

    uvicorn.run(create_app(), host=settings.host, port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
