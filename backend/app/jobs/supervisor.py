"""Starts, restarts and stops the worker subprocess on behalf of the API process."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("hvs.supervisor")


class WorkerSupervisor:
    def __init__(self, max_restarts_per_minute: int = 5) -> None:
        self.proc: subprocess.Popen[bytes] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.max_restarts = max_restarts_per_minute
        self.restarts: list[float] = []
        self.state = "stopped"
        self.last_exit_code: int | None = None

    def _spawn(self) -> None:
        env = dict(os.environ)
        env["HVS_PARENT_PID"] = str(os.getpid())
        from app.core.config import get_settings

        s = get_settings()
        env["HVS_DATA_DIR"] = str(s.data_dir)
        backend_dir = Path(__file__).resolve().parents[2]
        env["PYTHONPATH"] = str(backend_dir) + os.pathsep + env.get("PYTHONPATH", "")
        kwargs: dict[str, object] = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        self.proc = subprocess.Popen([sys.executable, "-m", "app.jobs.worker"], env=env,
                                     cwd=str(backend_dir), **kwargs)  # type: ignore[call-overload]
        self.state = "running"
        log.info("Worker started (pid %s)", self.proc.pid)

    def start(self) -> None:
        self._spawn()
        self._thread = threading.Thread(target=self._monitor, name="worker-supervisor", daemon=True)
        self._thread.start()

    def _monitor(self) -> None:
        while not self._stop.is_set():
            p = self.proc
            if p is not None and p.poll() is not None and not self._stop.is_set():
                self.last_exit_code = p.returncode
                now = time.monotonic()
                self.restarts = [t for t in self.restarts if now - t < 60] + [now]
                if len(self.restarts) > self.max_restarts:
                    self.state = "crashed"
                    log.error("Worker keeps crashing (exit %s); not restarting", p.returncode)
                    return
                log.warning("Worker exited with %s; restarting", p.returncode)
                self.state = "restarting"
                time.sleep(min(10, 2 ** (len(self.restarts) - 1)))
                if not self._stop.is_set():
                    self._spawn()
            self._stop.wait(1)

    def stop(self, timeout: float = 10) -> None:
        self._stop.set()
        p = self.proc
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                log.warning("Worker did not stop in time; killing it")
                p.kill()
                p.wait(timeout=5)
        self.state = "stopped"

    def status(self) -> dict[str, object]:
        alive = self.proc is not None and self.proc.poll() is None
        return {"state": self.state if alive or self.state != "running" else "exited",
                "pid": self.proc.pid if alive and self.proc else None,
                "restarts_last_minute": len(self.restarts), "last_exit_code": self.last_exit_code}
