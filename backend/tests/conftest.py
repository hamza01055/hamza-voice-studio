from __future__ import annotations

import copy
import io
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.core.config import Settings, set_settings
from app.db.models import ModelInstallation, utcnow
from app.db.session import session_factory
from app.engines import registry
from tests import mock_engine

TOKEN = "test-token-123"


@pytest.fixture()
def settings(tmp_path: Path) -> Iterator[Settings]:
    s = Settings(data_dir=tmp_path / "data", token=TOKEN, port=8765, start_worker=False,
                 lease_seconds=5, max_queued_jobs=50, dev_origins="http://localhost:5173")
    set_settings(s)
    from app.db.migrate import upgrade_to_head

    upgrade_to_head()
    yield s


@pytest.fixture()
def mock_models(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    reg = copy.deepcopy(registry.load_registry())
    reg["models"] = reg["models"] + [mock_engine.MOCK_TTS_ENTRY, mock_engine.MOCK_ASR_ENTRY]
    monkeypatch.setattr(registry, "load_registry", lambda: reg)
    monkeypatch.setitem(registry.ADAPTER_FACTORIES, "mock_tts", mock_engine.factory_tts)
    monkeypatch.setitem(registry.ADAPTER_FACTORIES, "mock_asr", mock_engine.factory_asr)
    b = mock_engine.Behaviour
    for k in ("fail_times", "raise_exc", "empty_output", "nan_output", "on_sentence", "calls"):
        setattr(b, k, {"fail_times": 0, "raise_exc": None, "empty_output": False, "nan_output": False,
                       "on_sentence": None, "calls": 0}[k])
    b.sentences = 3
    b.fail_retryable = True
    yield


def install_mock(model_id: str = "mock-tts") -> None:
    d = registry.model_dir(model_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "mock.bin").write_bytes(b"x")
    with session_factory()() as db:
        db.merge(ModelInstallation(model_id=model_id, revision="mock", source="test",
                                   download_status="installed", integrity_status="verified",
                                   installed_at=utcnow(), install_location=model_id))
        db.commit()


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    from app.main import create_app

    app = create_app(start_worker=False)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        c.headers.update({"X-HVS-Token": TOKEN})
        yield c


@pytest.fixture()
def studio(client: TestClient, mock_models: None) -> TestClient:
    install_mock("mock-tts")
    install_mock("mock-asr")
    r = client.patch("/api/settings", json={"default_model_id": "mock-tts", "default_voice": "mock_a"})
    assert r.status_code == 200
    return client


def wav_bytes(seconds: float = 3.0, sr: int = 22050, freq: float = 180.0, amp: float = 0.3,
              channels: int = 1, fmt: str = "WAV") -> bytes:
    t = np.arange(int(seconds * sr)) / sr
    # amplitude-modulated tone: not silent, not clipped
    x = amp * np.sin(2 * np.pi * freq * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    if channels > 1:
        x = np.stack([x] * channels, axis=1)
    buf = io.BytesIO()
    sf.write(buf, x, sr, format=fmt, subtype="PCM_16" if fmt == "WAV" else None)
    return buf.getvalue()


def run_worker(lane: str = "inference", max_jobs: int = 50) -> int:
    from app.jobs.worker import Worker

    w = Worker(worker_id="test-worker")
    n = 0
    while n < max_jobs and w.process_next(lane):
        n += 1
    return n
