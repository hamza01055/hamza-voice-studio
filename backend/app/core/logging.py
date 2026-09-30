"""Logging setup. Script text and recordings are never logged by application code;
logs contain IDs, error codes and timings only."""

from __future__ import annotations

import logging
import logging.handlers

from app.core.config import get_settings


def setup_logging(name: str) -> None:
    s = get_settings()
    s.ensure_dirs()
    root = logging.getLogger()
    if getattr(root, "_hvs_configured", False):
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    fh = logging.handlers.RotatingFileHandler(s.logs_dir / f"{name}.log", maxBytes=2_000_000,
                                              backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)
    # Access logs include only method/path (IDs), never bodies.
    root._hvs_configured = True  # type: ignore[attr-defined]
