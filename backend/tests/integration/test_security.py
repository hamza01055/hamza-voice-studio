import pytest
from fastapi.testclient import TestClient

from app.core.errors import Forbidden
from app.jobs.handlers import safe_file_name, unique_path
from app.storage.assets import resolve_key
from tests.conftest import TOKEN


def test_health_is_public_but_everything_else_needs_token(client: TestClient):
    anon = TestClient(client.app, base_url="http://127.0.0.1:8765")
    assert anon.get("/api/health").status_code == 200
    r = anon.get("/api/projects")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert anon.get("/api/projects", headers={"X-HVS-Token": "wrong"}).status_code == 401
    assert anon.get("/api/projects", headers={"X-HVS-Token": TOKEN}).status_code == 200


def test_query_token_only_for_media_get(client: TestClient):
    anon = TestClient(client.app, base_url="http://127.0.0.1:8765")
    assert anon.get(f"/api/projects?t={TOKEN}").status_code == 401
    # allowed path pattern; 404 proves auth passed
    assert anon.get(f"/api/assets/{'0' * 32}/audio?t={TOKEN}").status_code == 404
    assert anon.post(f"/api/generations?t={TOKEN}", json={}).status_code == 401


def test_foreign_origin_rejected(client: TestClient):
    r = client.post("/api/projects", json={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "origin_not_allowed"
    ok = client.post("/api/projects", json={"name": "x"}, headers={"Origin": "http://127.0.0.1:8765"})
    assert ok.status_code == 201
    dev = client.get("/api/projects", headers={"Origin": "http://localhost:5173"})
    assert dev.status_code == 200


def test_dns_rebinding_host_rejected(client: TestClient):
    r = client.get("/api/health", headers={"Host": "attacker.example:8765"})
    assert r.status_code == 400


def test_security_headers(client: TestClient):
    r = client.get("/api/health")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_path_traversal_blocked(settings):
    with pytest.raises(Forbidden):
        resolve_key("../../etc/passwd")
    with pytest.raises(Forbidden):
        resolve_key("/etc/passwd")
    assert safe_file_name("../../evil/..\\name", "mp3") == "evil_.._name.mp3" or "/" not in safe_file_name(
        "../../evil", "mp3")
    assert "/" not in safe_file_name("a/b/c", "wav") and "\\" not in safe_file_name("a\\b", "wav")
    assert safe_file_name("", "wav") == "export.wav"


def test_unique_path_never_overwrites(tmp_path):
    (tmp_path / "a.mp3").write_text("x")
    (tmp_path / "a (1).mp3").write_text("x")
    assert unique_path(tmp_path, "a.mp3").name == "a (2).mp3"


def test_validation_errors_do_not_echo_input(client: TestClient):
    r = client.post("/api/projects", json={"name": "", "script": "secret script text"})
    assert r.status_code == 422
    assert "secret script text" not in r.text


def test_model_id_traversal(client: TestClient):
    assert client.post("/api/models/..%2F..%2Fetc/download").status_code in (404, 422)
