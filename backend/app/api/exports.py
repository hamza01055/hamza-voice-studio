from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, NotFound
from app.db.models import Export
from app.db.session import get_db
from app.jobs import queue
from app.jobs.handlers import safe_file_name
from app.schemas import api as S
from app.services import projects as P
from app.storage import assets

router = APIRouter(tags=["exports"])

MEDIA = {"wav": "audio/wav", "mp3": "audio/mpeg", "flac": "audio/flac"}


def _out(e: Export) -> dict[str, Any]:
    return S.ExportOut.model_validate(e).model_dump(mode="json")


@router.post("/projects/{project_id}/exports", status_code=202)
def create_export(project_id: str, body: S.ExportCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = P.get_project(db, project_id)
    if body.chapter_id and body.chapter_id not in {c.id for c in p.chapters}:
        raise NotFound("Chapter not found in this project.")
    name = safe_file_name(body.file_name or p.name, body.format)
    e = Export(project_id=p.id, chapter_id=body.chapter_id, file_name=name, format=body.format,
               options=body.model_dump(), status="queued")
    db.add(e)
    db.flush()
    job, _ = queue.enqueue(db, type="export", project_id=p.id,
                           params={**body.model_dump(), "file_name": name, "project_id": p.id,
                                   "export_id": e.id})
    e.job_id = job.id
    db.flush()
    return {"export": _out(e), "job_id": job.id}


@router.get("/projects/{project_id}/exports")
def list_exports(project_id: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db)) -> dict[str, Any]:
    q = select(Export).where(Export.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Export.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [_out(e) for e in rows], "total": total, "limit": limit, "offset": offset}


def _export(db: Session, export_id: str) -> Export:
    e = db.get(Export, export_id)
    if not e:
        raise NotFound("Export not found.")
    return e


@router.get("/exports/{export_id}")
def get_export(export_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _out(_export(db, export_id))


@router.get("/exports/{export_id}/file")
def export_file(export_id: str, download: bool = True, db: Session = Depends(get_db)) -> FileResponse:
    e = _export(db, export_id)
    if e.status != "completed" or not e.storage_key:
        raise Conflict("The export is not complete.", code="export_not_ready")
    path = assets.resolve_key(e.storage_key, get_settings().exports_dir)
    if not path.exists():
        raise NotFound("The export file is missing on disk.", code="file_missing")
    return FileResponse(path, media_type=MEDIA.get(e.format, "application/octet-stream"),
                        filename=e.file_name if download else None,
                        content_disposition_type="attachment" if download else "inline")


@router.delete("/exports/{export_id}")
def delete_export(export_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    e = _export(db, export_id)
    if e.status in ("queued", "running"):
        raise Conflict("Cancel the export job before deleting it.", code="export_running")
    if e.storage_key:
        assets.schedule_unlink(db, assets.resolve_key(e.storage_key, get_settings().exports_dir))
    db.delete(e)
    return {"deleted": export_id}
