"""Inference worker process.

Started and supervised by the API process (``app.jobs.supervisor``) but runs as a
separate OS process so inference never blocks the API. Run manually with::

    python -m app.jobs.worker

Lanes:
* ``inference`` - one job at a time (TTS, transcription). Holds one loaded model.
* ``io`` - one job at a time (model downloads, exports).
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
import traceback
import uuid
from typing import Any

from sqlalchemy import update

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.models import GenerationJob, utcnow
from app.db.session import get_engine, session_factory
from app.engines.base import GenerationCancelled
from app.jobs import handlers, queue
from app.jobs.context import JobContext
from app.jobs.engine_manager import EngineManager
from app.services import settings_service

log = logging.getLogger("hvs.worker")


class Worker:
    def __init__(self, worker_id: str | None = None) -> None:
        self.settings = get_settings()
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.stop = threading.Event()
        self.engines = EngineManager()
        self.active: dict[str, JobContext] = {}
        self._active_lock = threading.Lock()

    # ------------------------------------------------------------------
    def process_next(self, lane: str) -> str | None:
        """Claim and run one job from ``lane``. Returns the job id or None."""
        job_id = queue.claim(get_engine(), lane, self.worker_id, self.settings.lease_seconds)
        if not job_id:
            return None
        with session_factory()() as db:
            job = db.get(GenerationJob, job_id)
            assert job is not None
            ctx = JobContext(job_id=job.id, worker_id=self.worker_id, type=job.type, params=dict(job.params),
                             retry_count=job.retry_count, project_id=job.project_id,
                             segment_id=job.segment_id, input_revision=job.input_revision)
            if job.cancel_requested:
                ctx.cancel_event.set()
        with self._active_lock:
            self.active[job_id] = ctx
        try:
            self._run(ctx)
        finally:
            with self._active_lock:
                self.active.pop(job_id, None)
        return job_id

    def _run(self, ctx: JobContext) -> None:
        handler = handlers.HANDLERS.get(ctx.type)
        try:
            if handler is None:
                raise handlers.JobFailed(f"Unknown job type {ctx.type}", code="unknown_job_type")
            engines = self.engines
            result = handler(ctx, engines)
            self._finish(ctx, "completed", result=result)
        except GenerationCancelled as e:
            self._finish(ctx, "cancelled", message=e.message)
        except BaseException as e:  # noqa: BLE001
            if isinstance(e, KeyboardInterrupt | SystemExit):
                raise
            code, msg, retryable = handlers.classify(e)
            if code == "internal_error":
                log.error("Job %s failed: %s", ctx.job_id, "".join(
                    traceback.format_exception_only(type(e), e)).strip())
                log.debug("%s", traceback.format_exc())
            else:
                log.info("Job %s failed: %s", ctx.job_id, code)
            if ctx.should_cancel():
                self._finish(ctx, "cancelled", message="Cancelled.")
            elif retryable and ctx.retry_count < self.settings.max_auto_retries:
                self._requeue(ctx, code, msg)
            else:
                self._finish(ctx, "failed", code=code, message=msg, retryable=retryable)

    def _finish(self, ctx: JobContext, status: str, *, result: dict[str, Any] | None = None,
                code: str | None = None, message: str | None = None, retryable: bool = False) -> None:
        stage = {"completed": "Completed", "cancelled": "Cancelled", "failed": "Failed"}[status]
        values: dict[str, Any] = {"status": status, "finished_at": utcnow(), "progress_stage": stage,
                                  "lease_expires_at": None, "updated_at": utcnow()}
        if status == "completed":
            values["progress"] = 1.0
            values["result"] = result or {}
        if code:
            values["error_code"] = code
        if message and status != "completed":
            values["error_message"] = message
        values["retryable"] = retryable
        with get_engine().begin() as conn:
            conn.execute(update(GenerationJob).where(GenerationJob.id == ctx.job_id,
                                                     GenerationJob.worker_id == self.worker_id).values(**values))
        if ctx.type == "export":
            handlers.mark_export_failed(ctx.params.get("export_id"), status, message) \
                if status != "completed" else None

    def _requeue(self, ctx: JobContext, code: str, msg: str) -> None:
        with get_engine().begin() as conn:
            conn.execute(update(GenerationJob).where(GenerationJob.id == ctx.job_id,
                                                     GenerationJob.worker_id == self.worker_id).values(
                status="queued", retry_count=GenerationJob.retry_count + 1, worker_id=None,
                lease_expires_at=None, progress=None, error_code=code, error_message=msg,
                progress_stage="Automatic retry after a transient error", updated_at=utcnow()))

    # ------------------------------------------------------------------
    def _lane_loop(self, lane: str) -> None:
        while not self.stop.is_set():
            try:
                if self.process_next(lane) is None:
                    if lane == "inference":
                        self._maybe_unload()
                    self.stop.wait(0.4)
            except Exception:  # noqa: BLE001
                log.exception("Lane %s loop error", lane)
                self.stop.wait(2)

    def _maybe_unload(self) -> None:
        try:
            with session_factory()() as db:
                minutes = settings_service.get_all(db).idle_unload_minutes
            if self.engines.unload_if_idle(minutes * 60):
                log.info("Unloaded idle model")
        except Exception:  # noqa: BLE001
            log.debug("idle-unload check failed", exc_info=True)

    def _heartbeat_loop(self) -> None:
        eng = get_engine()
        last_lease = 0.0
        last_recover = 0.0
        parent = int(os.environ.get("HVS_PARENT_PID", "0") or 0)
        while not self.stop.is_set():
            now = time.monotonic()
            with self._active_lock:
                ids = list(self.active)
            try:
                for jid, flag in queue.cancel_flags(eng, ids).items():
                    if flag:
                        with self._active_lock:
                            if jid in self.active:
                                self.active[jid].cancel_event.set()
                if now - last_lease >= self.settings.heartbeat_seconds:
                    last_lease = now
                    if not queue.acquire_scheduler(eng, self.worker_id, self.settings.lease_seconds):
                        log.error("Lost scheduler lease; stopping worker")
                        self.stop.set()
                        break
                    queue.renew_leases(eng, self.worker_id, ids, self.settings.lease_seconds)
                if now - last_recover >= 10:
                    last_recover = now
                    with session_factory()() as db:
                        rec = queue.recover_stale(db)
                        db.commit()
                    if rec:
                        log.warning("Recovered %d stale job(s)", len(rec))
            except Exception:  # noqa: BLE001
                log.exception("Heartbeat error")
            if parent and not _pid_alive(parent):
                log.warning("Parent process exited; stopping worker to avoid an orphan")
                self.stop.set()
                break
            self.stop.wait(0.5)

    def run(self) -> None:
        eng = get_engine()
        deadline = time.monotonic() + self.settings.lease_seconds + 5
        while not queue.acquire_scheduler(eng, self.worker_id, self.settings.lease_seconds):
            if time.monotonic() > deadline:
                log.error("Another worker owns the scheduler lease; exiting")
                return
            time.sleep(1)
        log.info("Worker %s started (threads=%d)", self.worker_id, self.settings.inference_threads)
        threads = [threading.Thread(target=self._heartbeat_loop, name="heartbeat", daemon=True),
                   threading.Thread(target=self._lane_loop, args=("inference",), name="inference",
                                    daemon=True),
                   threading.Thread(target=self._lane_loop, args=("io",), name="io", daemon=True)]
        for t in threads:
            t.start()
        try:
            while not self.stop.is_set():
                self.stop.wait(0.5)
        finally:
            self.stop.set()
            # Give running jobs a moment to observe the stop; leases will expire otherwise.
            for t in threads[1:]:
                t.join(timeout=5)
            queue.release_scheduler(eng, self.worker_id)
            log.info("Worker stopped")


def _pid_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:  # noqa: BLE001
        return True


def main() -> None:
    setup_logging("worker")
    w = Worker()

    def _sig(_s: int, _f: Any) -> None:
        w.stop.set()

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    w.run()


if __name__ == "__main__":
    main()
