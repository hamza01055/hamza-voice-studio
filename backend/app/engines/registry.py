"""Machine-readable model registry (registry.json) and adapter factory."""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.errors import NotFound
from app.engines.base import BaseAdapter

REGISTRY_PATH = Path(__file__).with_name("registry.json")

AdapterFactory = Callable[[dict[str, Any], Path, int, dict[str, Any]], BaseAdapter]


def _kokoro(entry: dict[str, Any], d: Path, threads: int, opts: dict[str, Any]) -> BaseAdapter:
    from app.engines.kokoro_sherpa import KokoroSherpaAdapter

    return KokoroSherpaAdapter(entry["id"], entry["revision"], d, threads,
                               include_unevaluated=bool(opts.get("include_unevaluated")))


def _whisper(entry: dict[str, Any], d: Path, threads: int, opts: dict[str, Any]) -> BaseAdapter:
    from app.engines.whisper_sherpa import WhisperSherpaAdapter

    return WhisperSherpaAdapter(entry["id"], entry["revision"], d, threads)


# Tests may register mock factories here; production only uses real adapters.
ADAPTER_FACTORIES: dict[str, AdapterFactory] = {
    "kokoro_sherpa": _kokoro,
    "whisper_sherpa": _whisper,
}


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def all_models() -> list[dict[str, Any]]:
    return list(load_registry()["models"])


def get_model(model_id: str) -> dict[str, Any]:
    for m in all_models():
        if m["id"] == model_id:
            return m
    raise NotFound(f"Unknown model '{model_id}'.")


def model_dir(model_id: str) -> Path:
    base = get_settings().models_dir.resolve()
    p = (base / model_id).resolve()
    if not p.is_relative_to(base):
        raise NotFound("Invalid model id.")
    return p


def files_present(entry: dict[str, Any], d: Path) -> bool:
    if not d.is_dir():
        return False
    for f in entry.get("required_files", []):
        if not (d / f).exists():
            return False
    return all(any(d.glob(g)) for g in entry.get("required_globs", []))


def create_adapter(model_id: str, opts: dict[str, Any] | None = None) -> BaseAdapter:
    entry = get_model(model_id)
    adapter = entry.get("adapter")
    if not adapter or adapter not in ADAPTER_FACTORIES:
        raise NotFound(f"Model '{model_id}' is not integrated in this version.")
    return ADAPTER_FACTORIES[adapter](entry, model_dir(model_id), get_settings().inference_threads,
                                      opts or {})
