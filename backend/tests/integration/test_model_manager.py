"""Model download/installation using a local HTTP server (no internet, no real weights)."""

import copy
import hashlib
import http.server
import io
import os
import tarfile
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engines import registry
from tests.conftest import run_worker


def make_archive(files: dict[str, bytes], prefix: str = "pkg/", evil: bool = False) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tf:
        for name, data in files.items():
            ti = tarfile.TarInfo(prefix + name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
        if evil:
            ti = tarfile.TarInfo(prefix + "../../escape.txt")
            ti.size = 4
            tf.addfile(ti, io.BytesIO(b"evil"))
    return buf.getvalue()


class Handler(http.server.BaseHTTPRequestHandler):
    payloads: dict[str, bytes] = {}
    fail_after: int | None = None

    def do_GET(self):  # noqa: N802
        data = self.payloads.get(self.path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        start = 0
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
        else:
            self.send_response(200)
        body = data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if Handler.fail_after is not None and not rng:
            self.wfile.write(body[:Handler.fail_after])
            self.wfile.flush()
            self.connection.close()
            return
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    Handler.payloads = {}
    Handler.fail_after = None


@pytest.fixture()
def fake_registry(monkeypatch, mock_models, server):
    archive = make_archive({"mock.bin": os.urandom(20000), "LICENSE": b"Apache"})
    Handler.payloads["/m.tar.bz2"] = archive
    reg = copy.deepcopy(registry.load_registry())
    for m in reg["models"]:
        if m["id"] == "mock-tts":
            m["artifacts"] = [{"url": server + "/m.tar.bz2", "type": "tar.bz2", "size_bytes": len(archive),
                               "sha256": hashlib.sha256(archive).hexdigest(), "strip_prefix": "pkg/"}]
    monkeypatch.setattr(registry, "load_registry", lambda: reg)
    return reg, archive


def test_download_verify_install_remove(client: TestClient, fake_registry, settings):
    r = client.post("/api/models/mock-tts/download")
    assert r.status_code == 202
    dl = r.json()["download_id"]
    # duplicate download request returns the same job
    assert client.post("/api/models/mock-tts/download").json()["download_id"] == dl
    assert run_worker("io") == 1
    st = client.get(f"/api/model-downloads/{dl}").json()
    assert st["job"]["status"] == "completed", st
    m = client.get("/api/models/mock-tts").json()
    assert m["status"] == "installed" and m["integrity_status"] == "verified"
    d = registry.model_dir("mock-tts")
    assert (d / "mock.bin").exists() and (d / ".hvs-install.json").exists()
    assert not list(settings.models_dir.glob(".staging-*"))
    assert client.post("/api/models/mock-tts/download").status_code == 409  # already installed
    assert client.delete("/api/models/mock-tts/installation").status_code == 200
    assert not d.exists()
    assert client.get("/api/models/mock-tts").json()["status"] == "not_installed"


def test_checksum_mismatch_rejected(client: TestClient, fake_registry, settings):
    reg, archive = fake_registry
    for m in reg["models"]:
        if m["id"] == "mock-tts":
            m["artifacts"][0]["sha256"] = "0" * 64
    dl = client.post("/api/models/mock-tts/download").json()["download_id"]
    run_worker("io")
    job = client.get(f"/api/model-downloads/{dl}").json()["job"]
    assert job["status"] == "failed" and job["error_code"] == "checksum_mismatch"
    assert client.get("/api/models/mock-tts").json()["status"] == "failed"
    assert not registry.model_dir("mock-tts").exists()
    assert not list((settings.models_dir / ".partial").glob("*"))  # corrupt file removed


def test_interrupted_download_resumes(client: TestClient, fake_registry, settings):
    Handler.fail_after = 500
    dl = client.post("/api/models/mock-tts/download").json()["download_id"]
    run_worker("io")  # first attempt fails, auto-retry resumes with Range
    job = client.get(f"/api/model-downloads/{dl}").json()["job"]
    assert job["status"] == "completed", job
    assert job["retry_count"] == 1
    assert client.get("/api/models/mock-tts").json()["status"] == "installed"


def test_unsafe_archive_rejected(client: TestClient, fake_registry, settings):
    reg, _ = fake_registry
    evil = make_archive({"mock.bin": b"x"}, evil=True)
    Handler.payloads["/m.tar.bz2"] = evil
    for m in reg["models"]:
        if m["id"] == "mock-tts":
            m["artifacts"][0].update(size_bytes=len(evil), sha256=hashlib.sha256(evil).hexdigest())
    dl = client.post("/api/models/mock-tts/download").json()["download_id"]
    run_worker("io")
    assert client.get(f"/api/model-downloads/{dl}").json()["job"]["status"] == "failed"
    assert not (Path(settings.data_dir) / "escape.txt").exists()
    assert not (settings.models_dir / "escape.txt").exists()


def test_insufficient_disk(client: TestClient, fake_registry, monkeypatch):
    from app.services import models_service

    monkeypatch.setattr(models_service, "free_disk_bytes", lambda: 10)
    r = client.post("/api/models/mock-tts/download")
    assert r.status_code == 507 and r.json()["error"]["code"] == "insufficient_disk"


def test_failed_download_reports_error(client: TestClient, fake_registry):
    Handler.payloads.clear()  # 404
    dl = client.post("/api/models/mock-tts/download").json()["download_id"]
    run_worker("io")
    job = client.get(f"/api/model-downloads/{dl}").json()["job"]
    assert job["status"] == "failed" and job["error_code"] == "download_failed"


def test_not_integrated_model_cannot_install(client: TestClient):
    r = client.post("/api/models/omnivoice/download")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_integrated"
    models = client.get("/api/models").json()["items"]
    omni = [m for m in models if m["id"] == "omnivoice"][0]
    assert omni["status"] == "not_integrated" and omni["license"]["commercial_use"] == "prohibited"
    kok = [m for m in models if m["id"] == "kokoro-multi-lang-v1_0"][0]
    assert kok["capabilities"]["voice_cloning"] is False
    assert kok["capabilities"]["cancellation"] == "between_sentences"
    assert "ur" not in kok["capabilities"]["languages_experimental"]  # hidden unless enabled
    client.patch("/api/settings", json={"show_unevaluated_languages": True})
    kok = client.get("/api/models/kokoro-multi-lang-v1_0").json()
    assert "ur" in kok["capabilities"]["languages_experimental"]


def test_detect_installed_model_from_disk_manifest(client: TestClient, fake_registry, settings):
    """A model folder restored from backup is detected at startup."""
    dl = client.post("/api/models/mock-tts/download").json()["download_id"]
    run_worker("io")
    assert client.get(f"/api/model-downloads/{dl}").json()["job"]["status"] == "completed"
    from app.db.models import ModelInstallation
    from app.db.session import session_factory
    from app.main import startup_tasks

    with session_factory()() as db:
        db.delete(db.get(ModelInstallation, "mock-tts"))
        db.commit()
    assert client.get("/api/models/mock-tts").json()["status"] == "not_installed"
    startup_tasks()
    m = client.get("/api/models/mock-tts").json()
    assert m["status"] == "installed" and m["integrity_status"] == "verified"
    # tampered manifest (wrong checksum) is not trusted
    with session_factory()() as db:
        db.delete(db.get(ModelInstallation, "mock-tts"))
        db.commit()
    import json as _json

    mf = registry.model_dir("mock-tts") / ".hvs-install.json"
    data = _json.loads(mf.read_text())
    data["sha256"] = {k: "0" * 64 for k in data["sha256"]}
    mf.write_text(_json.dumps(data))
    startup_tasks()
    assert client.get("/api/models/mock-tts").json()["status"] == "not_installed"
