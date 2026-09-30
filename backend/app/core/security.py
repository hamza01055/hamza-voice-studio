"""Local access control.

* The server binds to 127.0.0.1 by default.
* Every /api request except GET /api/health must carry the per-session token in the
  ``X-HVS-Token`` header. Media/SSE GET endpoints (which browsers request via <audio>
  or EventSource and cannot add headers) may pass it as ``?t=`` instead.
* Requests carrying an ``Origin`` header must come from an allowed origin; this blocks
  other websites from driving the local API even if they guess the port.
* The Host header must be a loopback name (DNS-rebinding protection) - enforced by
  TrustedHostMiddleware in main.py.
"""

from __future__ import annotations

import re
import secrets

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.errors import error_body

QUERY_TOKEN_PATHS = [
    re.compile(r"^/api/assets/[0-9a-f]{32}/audio$"),
    re.compile(r"^/api/exports/[0-9a-f]{32}/file$"),
    re.compile(r"^/api/jobs/[0-9a-f]{32}/events$"),
    re.compile(r"^/api/events$"),
    re.compile(r"^/api/transcriptions/[0-9a-f]{32}/export$"),
]

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"content-security-policy",
     b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
     b"media-src 'self' blob:; connect-src 'self'; font-src 'self' data:; object-src 'none'; "
     b"base-uri 'none'; frame-ancestors 'none'; form-action 'none'"),
]


async def _deny(send: Send, status: int, code: str, message: str) -> None:
    import json

    body = json.dumps(error_body(code, message)).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class LocalAccessMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = get_settings()
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")
        origin = headers.get("origin")
        if origin and origin.rstrip("/") not in settings.allowed_origins():
            await _deny(send, 403, "origin_not_allowed", "Requests from this origin are not allowed.")
            return
        if path.startswith("/api") and not (path == "/api/health" and method == "GET"):
            if method != "OPTIONS":
                token = headers.get("x-hvs-token")
                if token is None and method == "GET" and any(p.match(path) for p in QUERY_TOKEN_PATHS):
                    from urllib.parse import parse_qs

                    qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
                    token = (qs.get("t") or [None])[0]
                if not token or not secrets.compare_digest(token, settings.token):
                    await _deny(send, 401, "unauthorized",
                                "Missing or invalid session token. Open the studio from its launcher.")
                    return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                hs = list(message.get("headers", []))
                existing = {k.lower() for k, _ in hs}
                for k, v in SECURITY_HEADERS:
                    if k not in existing:
                        hs.append((k, v))
                message["headers"] = hs
            await send(message)

        await self.app(scope, receive, send_with_headers)
