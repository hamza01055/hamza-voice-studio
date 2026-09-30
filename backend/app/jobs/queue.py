"""Durable job queue on SQLite.

* Jobs are rows in ``generation_jobs``; every state transition is persisted.
* Claiming is a single ``UPDATE ... WHERE status='queued' ... RETURNING`` statement,
  which SQLite executes atomically, so two workers can never claim the same job.
* A running job holds a lease that the worker renews; a job whose lease expires
  (worker crash, power loss) is detected and recovered.
* Only one process may act as scheduler at a time (``worker_leases`` row).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, TooManyRequests
from app.db.models import GenerationJob, utcnow

ACTIVE = ("queued", "loading_model", "running", "cancelling")
RUNNING = ("loading_model", "running", "cancelling")
TERMINAL = ("completed", "failed", "cancelled", "interrupted")

TRANSITIONS: dict[str, set[str]] = {
    "queued": {"loading_model", "running", "cancelled", "failed"},
    "loading_model": {"running", "cancelling", "failed", "cancelled", "interrupted", "queued",
                      "completed"},
    "running": {"completed", "failed", "cancelling", "cancelled", "interrupted", "queued"},
    "cancelling": {"cancelled", "completed", "failed", "interrupted"},
    "failed": {"queued"},
    "cancelled": {"queued"},
    "interrupted": {"queued"},
    "completed": set(),
}

LANE_FOR_TYPE = {"tts": "inference", "transcribe": "inference", "export": "io", "model_download": "io"}


def can_transition(src: str, dst: str) -> bool:
    return dst in TRANSITIONS.get(src, set())


def enqueue(db: Session, *, type: str, params: dict[str, Any], project_id: str | None = None,
            segment_id: str | None = None, input_revision: int | None = None,
            idempotency_key: str | None = None, stage: str = "Waiting in queue") -> tuple[GenerationJob, bool]:
    """Create a job. Returns (job, created). Re-submitting the same idempotency key
    returns the existing job instead of creating a duplicate."""
    if idempotency_key:
        existing = db.scalar(select(GenerationJob).where(GenerationJob.idempotency_key == idempotency_key))
        if existing:
            return existing, False
    queued = db.scalar(select(func.count()).select_from(GenerationJob)
                       .where(GenerationJob.status == "queued")) or 0
    if queued >= get_settings().max_queued_jobs:
        raise TooManyRequests(f"The queue already holds {queued} jobs. Wait for some to finish "
                              "or cancel them before adding more.")
    job = GenerationJob(type=type, lane=LANE_FOR_TYPE[type], params=params, project_id=project_id,
                        segment_id=segment_id, input_revision=input_revision,
                        idempotency_key=idempotency_key, progress_stage=stage)
    db.add(job)
    db.flush()
    return job, True


def claim(engine: Engine, lane: str, worker_id: str, lease_seconds: float) -> str | None:
    now = utcnow()
    lease = now + timedelta(seconds=lease_seconds)
    with engine.begin() as conn:
        row = conn.execute(text(
            """
            UPDATE generation_jobs
               SET status='loading_model', worker_id=:w, lease_expires_at=:lease,
                   started_at=:now, updated_at=:now, progress=NULL,
                   progress_stage='Starting', error_code=NULL, error_message=NULL
             WHERE id = (SELECT id FROM generation_jobs
                          WHERE status='queued' AND lane=:lane
                          ORDER BY created_at, id LIMIT 1)
               AND status='queued'
            RETURNING id
            """), {"w": worker_id, "lease": lease, "now": now, "lane": lane}).first()
    return row[0] if row else None


def renew_leases(engine: Engine, worker_id: str, job_ids: list[str], lease_seconds: float) -> None:
    if not job_ids:
        return
    lease = utcnow() + timedelta(seconds=lease_seconds)
    with engine.begin() as conn:
        for jid in job_ids:
            conn.execute(text("UPDATE generation_jobs SET lease_expires_at=:l WHERE id=:id AND worker_id=:w "
                              "AND status IN ('loading_model','running','cancelling')"),
                         {"l": lease, "id": jid, "w": worker_id})


def cancel_flags(engine: Engine, job_ids: list[str]) -> dict[str, bool]:
    if not job_ids:
        return {}
    with engine.connect() as conn:
        rows = conn.execute(select(GenerationJob.id, GenerationJob.cancel_requested, GenerationJob.status)
                            .where(GenerationJob.id.in_(job_ids))).all()
    found = {r[0]: bool(r[1]) for r in rows}
    # A job whose row disappeared counts as cancelled.
    return {jid: found.get(jid, True) for jid in job_ids}


def request_cancel(db: Session, job: GenerationJob) -> GenerationJob:
    if job.status == "queued":
        job.status = "cancelled"
        job.cancel_requested = True
        job.finished_at = utcnow()
        job.progress_stage = "Cancelled before it started"
    elif job.status in RUNNING:
        job.cancel_requested = True
        if job.status != "cancelling":
            job.status = "cancelling"
        job.progress_stage = "Cancellation requested; waiting for the engine to stop"
    else:
        raise Conflict(f"The job is already {job.status}.", code="job_not_cancellable")
    db.flush()
    return job


def retry(db: Session, job: GenerationJob) -> GenerationJob:
    if job.status not in ("failed", "cancelled", "interrupted"):
        raise Conflict(f"Only failed, cancelled or interrupted jobs can be retried (job is {job.status}).",
                       code="job_not_retryable")
    job.status = "queued"
    job.retry_count += 1
    job.cancel_requested = False
    job.error_code = None
    job.error_message = None
    job.progress = None
    job.progress_stage = "Waiting in queue (manual retry)"
    job.worker_id = None
    job.lease_expires_at = None
    job.finished_at = None
    job.started_at = None
    job.created_at = utcnow()  # move to the back of the queue
    db.flush()
    return job


def recover_stale(db: Session, *, force_all_running: bool = False) -> list[str]:
    """Detect jobs whose worker vanished. ``force_all_running`` is used at API startup
    before any worker exists."""
    now = utcnow()
    q = select(GenerationJob).where(GenerationJob.status.in_(RUNNING))
    if not force_all_running:
        q = q.where((GenerationJob.lease_expires_at.is_(None)) | (GenerationJob.lease_expires_at < now))
    recovered = []
    max_auto = get_settings().max_auto_retries
    for job in db.scalars(q).all():
        recovered.append(job.id)
        job.worker_id = None
        job.lease_expires_at = None
        if job.cancel_requested:
            job.status = "cancelled"
            job.finished_at = now
            job.progress_stage = "Cancelled (worker stopped)"
        elif job.retry_count < max_auto and job.type in ("tts", "transcribe", "export", "model_download"):
            job.status = "queued"
            job.retry_count += 1
            job.progress = None
            job.progress_stage = "Re-queued after the worker stopped unexpectedly"
        else:
            job.status = "interrupted"
            job.finished_at = now
            job.error_code = "interrupted"
            job.error_message = ("The worker stopped while this job was running. "
                                 "Press Retry to run it again.")
            job.retryable = True
    db.flush()
    return recovered


def acquire_scheduler(engine: Engine, owner: str, lease_seconds: float, name: str = "scheduler") -> bool:
    now = utcnow()
    exp = now + timedelta(seconds=lease_seconds)
    with engine.begin() as conn:
        conn.execute(text("INSERT OR IGNORE INTO worker_leases(name, owner, expires_at) "
                          "VALUES (:n, '', :past)"), {"n": name, "past": now - timedelta(seconds=1)})
        res = conn.execute(text("UPDATE worker_leases SET owner=:o, expires_at=:e WHERE name=:n "
                                "AND (owner=:o OR expires_at < :now)"),
                           {"o": owner, "e": exp, "n": name, "now": now})
        return res.rowcount == 1


def release_scheduler(engine: Engine, owner: str, name: str = "scheduler") -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE worker_leases SET expires_at=:past WHERE name=:n AND owner=:o"),
                     {"past": utcnow() - timedelta(seconds=1), "n": name, "o": owner})
