from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.models import GenerationJob, utcnow
from app.db.session import get_db, session_factory
from app.jobs import queue
from app.schemas.api import JobOut

router = APIRouter(tags=["jobs"])


def _job(db: Session, job_id: str) -> GenerationJob:
    j = db.get(GenerationJob, job_id)
    if not j:
        raise NotFound("Job not found.")
    return j


def _out(j: GenerationJob) -> dict[str, Any]:
    return JobOut.model_validate(j).model_dump(mode="json")


@router.get("/jobs")
def list_jobs(status: str | None = Query(None, max_length=100), type: str | None = Query(None, max_length=30),
              project_id: str | None = None, limit: int = Query(50, ge=1, le=500),
              offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> dict[str, Any]:
    q = select(GenerationJob)
    if status:
        q = q.where(GenerationJob.status.in_(status.split(",")))
    if type:
        q = q.where(GenerationJob.type == type)
    if project_id:
        q = q.where(GenerationJob.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(GenerationJob.created_at.desc()).limit(limit).offset(offset)).all()
    counts = dict(db.execute(select(GenerationJob.status, func.count()).group_by(GenerationJob.status)).all())
    return {"items": [_out(j) for j in rows], "total": total, "limit": limit, "offset": offset,
            "counts": counts}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _out(_job(db, job_id))


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _out(queue.request_cancel(db, _job(db, job_id)))


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _out(queue.retry(db, _job(db, job_id)))


@router.post("/jobs/cancel-all")
def cancel_all(project_id: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    q = select(GenerationJob).where(GenerationJob.status.in_(("queued", "loading_model", "running")))
    if project_id:
        q = q.where(GenerationJob.project_id == project_id)
    n = 0
    for j in db.scalars(q):
        queue.request_cancel(db, j)
        n += 1
    return {"cancelled_or_requested": n}


def _fetch_since(since: datetime, job_id: str | None) -> list[dict[str, Any]]:
    with session_factory()() as db:
        q = select(GenerationJob).where(GenerationJob.updated_at > since)
        if job_id:
            q = q.where(GenerationJob.id == job_id)
        return [_out(j) for j in db.scalars(q.order_by(GenerationJob.updated_at).limit(200))]


async def _stream(request: Request, job_id: str | None) -> AsyncIterator[str]:
    since = utcnow()
    if job_id:
        with session_factory()() as db:
            j = db.get(GenerationJob, job_id)
            if not j:
                yield "event: error\ndata: {\"code\": \"not_found\"}\n\n"
                return
            yield f"event: job\ndata: {json.dumps(_out(j))}\n\n"
            if j.status in queue.TERMINAL:
                return
    else:
        yield "event: ready\ndata: {}\n\n"
    idle = 0.0
    while not await request.is_disconnected():
        rows = await asyncio.to_thread(_fetch_since, since, job_id)
        for r in rows:
            since = max(since, datetime.fromisoformat(r["updated_at"].rstrip("Z")))
            yield f"event: job\ndata: {json.dumps(r)}\n\n"
            if job_id and r["status"] in queue.TERMINAL:
                return
        if rows:
            idle = 0.0
        else:
            idle += 0.5
            if idle >= 15:
                idle = 0.0
                yield ": keep-alive\n\n"
        await asyncio.sleep(0.5)


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    return StreamingResponse(_stream(request, job_id), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/events")
async def all_events(request: Request) -> StreamingResponse:
    """Server-sent events for every job update (one connection per UI)."""
    return StreamingResponse(_stream(request, None), media_type="text/event-stream", headers=SSE_HEADERS)
