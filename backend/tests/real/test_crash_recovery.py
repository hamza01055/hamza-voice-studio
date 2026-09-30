"""REAL process-level crash tests: kills the worker and the whole app mid-generation.

Requires installed Kokoro weights (HVS_REAL_MODELS_DIR or the default app-data models
folder). Slow (~1-2 minutes). Run with:  pytest -m real tests/real/test_crash_recovery.py
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil
import pytest

from app.core.config import default_data_dir

MODELS = Path(os.environ.get("HVS_REAL_MODELS_DIR") or default_data_dir() / "models")
BACKEND = Path(__file__).resolve().parents[2]
TOKEN = "crash-test-token"
PORT = 18790

pytestmark = [pytest.mark.real,
              pytest.mark.skipif(not (MODELS / "kokoro-multi-lang-v1_0" / "model.onnx").exists(),
                                 reason="Kokoro weights not installed")]

LONG_TEXT = " ".join(f"This is sentence number {i} of a longer paragraph used to test recovery." for i in range(1, 9))


def api(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-HVS-Token": TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return json.loads(r.read())


def start(data_dir: Path) -> subprocess.Popen:
    env = {**os.environ, "HVS_TOKEN": TOKEN, "HVS_DATA_DIR": str(data_dir), "HVS_MODELS_DIR": str(MODELS),
           "HVS_LEASE_SECONDS": "5", "HVS_HEARTBEAT_SECONDS": "1"}
    p = subprocess.Popen([sys.executable, "-m", "app.run", "--no-browser", "--strict-port", "--port", str(PORT)],
                         cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            h = api("GET", "/health")
            if h["worker"].get("state") == "running" and h["worker"].get("pid"):
                return p
        except OSError:
            pass
        time.sleep(0.5)
    p.kill()
    raise RuntimeError("server did not start")


def wait_status(job_id: str, statuses: set[str], timeout: float) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        j = api("GET", f"/jobs/{job_id}")
        if j["status"] in statuses:
            return j
        time.sleep(0.3)
    raise AssertionError(f"job {job_id} did not reach {statuses}: {j['status']}")


@pytest.mark.skipif(sys.platform.startswith("win"), reason="uses POSIX signals")
def test_worker_crash_and_app_restart_recover(tmp_path):
    proc = start(tmp_path)
    try:
        p = api("POST", "/projects", {"name": "Crash", "script": f"{LONG_TEXT}\n\n{LONG_TEXT} Again."})
        s1, s2 = [s["id"] for s in p["chapters"][0]["segments"]]

        # 1) worker process killed mid-inference -> supervisor restarts it -> job re-queued
        job = api("POST", "/generations", {"segment_ids": [s1]})["jobs"][0]["job_id"]
        wait_status(job, {"running"}, 60)
        time.sleep(1.0)
        wpid = api("GET", "/health")["worker"]["pid"]
        os.kill(wpid, signal.SIGKILL)
        done = wait_status(job, {"completed", "failed", "interrupted"}, 120)
        assert done["status"] == "completed", done
        assert done["retry_count"] == 1
        assert api("GET", "/health")["worker"]["pid"] != wpid
        assert len(api("GET", f"/segments/{s1}/takes")["items"]) == 1  # no partial/duplicate takes

        # 2) whole application killed mid-inference -> worker exits (no orphan) -> recovered on restart
        job2 = api("POST", "/generations", {"segment_ids": [s2]})["jobs"][0]["job_id"]
        wait_status(job2, {"running"}, 60)
        wpid = api("GET", "/health")["worker"]["pid"]
        proc.send_signal(signal.SIGKILL)
        proc.wait(10)
        for _ in range(40):
            if not psutil.pid_exists(wpid) or psutil.Process(wpid).status() == psutil.STATUS_ZOMBIE:
                break
            time.sleep(0.25)
        else:
            raise AssertionError("worker was orphaned after the app was killed")
        proc = start(tmp_path)
        done = wait_status(job2, {"completed", "failed", "interrupted"}, 120)
        assert done["status"] == "completed", done
        assert len(api("GET", f"/segments/{s2}/takes")["items"]) == 1
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
