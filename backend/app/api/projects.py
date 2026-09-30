from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.models import GenerationTake
from app.db.session import get_db
from app.schemas import api as S
from app.services import projects as P

router = APIRouter(tags=["projects"])


@router.get("/projects")
def list_projects(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                  q: str | None = Query(None, max_length=100), db: Session = Depends(get_db)) -> dict[str, Any]:
    items, total = P.list_projects(db, limit, offset, q)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/projects", status_code=201)
def create_project(body: S.ProjectCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = P.create_project(db, body)
    db.flush()
    return P.serialize_project(db, p)


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return P.serialize_project(db, P.get_project(db, project_id))


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: S.ProjectPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = P.patch_project(db, P.get_project(db, project_id), body)
    return P.serialize_project(db, p)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"deleted": project_id, **P.delete_project(db, P.get_project(db, project_id))}


# chapters
@router.post("/projects/{project_id}/chapters", status_code=201)
def add_chapter(project_id: str, body: S.ChapterCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = P.get_project(db, project_id)
    P.add_chapter(db, p, body)
    return P.serialize_project(db, p)


@router.patch("/chapters/{chapter_id}")
def patch_chapter(chapter_id: str, body: S.ChapterPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    ch = P.patch_chapter(db, P.get_chapter(db, chapter_id), body)
    return P.serialize_project(db, ch.project)


@router.delete("/chapters/{chapter_id}")
def delete_chapter(chapter_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    ch = P.get_chapter(db, chapter_id)
    p = ch.project
    P.delete_chapter(db, ch)
    return P.serialize_project(db, p)


# segments
@router.post("/projects/{project_id}/segments", status_code=201)
def add_segments(project_id: str, body: S.SegmentsCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = P.get_project(db, project_id)
    created = P.add_segments(db, p, body)
    return {"created": [s.id for s in created], "project": P.serialize_project(db, p)}


@router.patch("/segments/{segment_id}")
def patch_segment(segment_id: str, body: S.SegmentPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = P.patch_segment(db, P.get_segment(db, segment_id), body)
    return P.serialize_segment(db, s)


@router.delete("/segments/{segment_id}")
def delete_segment(segment_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    P.delete_segment(db, P.get_segment(db, segment_id))
    return {"deleted": segment_id}


@router.post("/segments/{segment_id}/split")
def split_segment(segment_id: str, body: S.SegmentSplit, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = P.get_segment(db, segment_id)
    new = P.split_segment(db, s, body.at)
    return {"segment": P.serialize_segment(db, s), "new_segment": P.serialize_segment(db, new)}


# takes
@router.get("/segments/{segment_id}/takes")
def list_takes(segment_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = P.get_segment(db, segment_id)
    return {"items": P.list_takes(db, s), "selected_take_id": s.selected_take_id,
            "text_revision": s.text_revision}


@router.post("/segments/{segment_id}/selected-take")
def select_take(segment_id: str, body: S.SelectTake, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = P.select_take(db, P.get_segment(db, segment_id), body.take_id)
    return P.serialize_segment(db, s)


@router.delete("/takes/{take_id}")
def delete_take(take_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = db.get(GenerationTake, take_id)
    if not t:
        raise NotFound("Take not found.")
    P.delete_take(db, t)
    return {"deleted": take_id}


# generation
@router.post("/generations", status_code=202)
def create_generation(body: S.GenerationRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    return P.request_generation(db, body)
