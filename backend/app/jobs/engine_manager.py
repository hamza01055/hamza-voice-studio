"""Keeps at most one inference model loaded in the worker process (RAM-constrained
machines should never hold a TTS and an ASR model at the same time)."""

from __future__ import annotations

import time
from typing import Any

from app.engines import registry
from app.engines.base import BaseAdapter


class EngineManager:
    def __init__(self) -> None:
        self._adapter: BaseAdapter | None = None
        self._key: tuple[str, str] | None = None
        self.last_used = time.monotonic()

    def get(self, model_id: str, opts: dict[str, Any] | None = None) -> BaseAdapter:
        key = (model_id, repr(sorted((opts or {}).items())))
        if self._key != key:
            self.unload()
            self._adapter = registry.create_adapter(model_id, opts)
            self._key = key
        self.last_used = time.monotonic()
        assert self._adapter is not None
        return self._adapter

    def unload(self) -> None:
        if self._adapter is not None:
            self._adapter.unload()
        self._adapter = None
        self._key = None

    def unload_if_idle(self, idle_seconds: float) -> bool:
        if self._adapter is not None and idle_seconds > 0 and \
                time.monotonic() - self.last_used > idle_seconds:
            self.unload()
            return True
        return False
