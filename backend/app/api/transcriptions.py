from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audio import ffmpeg
from app.core.config import get_settings
from app.core.errors import Conflict, NotFound, Unprocessable
from app.db.models import GenerationJob, Transcription
from app.db.session import get_db
from app.engines import registry
from app.jobs import queue
from app.schemas import api as S
from app.services import models_service
from app.services.subtitles import to_srt, to_vtt
from app.services.voices import save_upload
from app.storage import assets

router = APIRouter(tags=["transcription"])


def _out(t: Transcription, db: Session) -> dict[str, Any]:
    d = S.TranscriptionOut.model_validate(t).model_dump(mode="json")
    j = db.get(GenerationJob, t.job_id) if t.job_id else None
    d["job_status"] = j.status if j else None
    return d


@router.post("/transcriptions", status_code=202)
async def create_transcription(file: UploadFile = File(...), model_id: str = Form(...),
                               language: str | None = Form(None, max_length=16),
                               name: str | None = Form(None, max_length=200),
                               db: Session = Depends(get_db)) -> dict[str, Any]:
    entry = registry.get_model(model_id)
    if entry["kind"] != "asr":
        raise Unprocessable("Choose a transcription model.")
    if not models_service.is_installed(db, model_id):
        raise Conflict(f"'{entry['name']}' is not installed. Install it on the Models page.",
                       code="model_not_installed")
    s = get_settings()
    tmp = await save_upload(file, s.max_upload_bytes * 10)
    try:
        info = ffmpeg.probe(tmp)
        if info.duration > s.max_transcription_seconds:
            raise Unprocessable("The recording is too long for transcription.", code="too_long")
        # Store a validated 16 kHz mono copy (decoding proves the content is audio).
        samples, sr = ffmpeg.decode(tmp, sample_rate=16000)
    finally:
        tmp.unlink(missing_ok=True)
    wav = assets.write_wav_temp(samples, sr)
    asset = assets.finalize_asset(db, wav, "upload")
    t = Transcription(name=(name or file.filename or "Transcription")[:200], source_asset_id=asset.id,
                      model_id=model_id, language_requested=language or None)
    db.add(t)
    db.flush()
    job, _ = queue.enqueue(db, type="transcribe", params={"model_id": model_id, "asset_id": asset.id,
                                                         "language": language, "transcription_id": t.id})
    t.job_id = job.id
    db.flush()
    return _out(t, db)


@router.get("/transcriptions")
def list_transcriptions(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                        db: Session = Depends(get_db)) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(Transcription)) or 0
    rows = db.scalars(select(Transcription).order_by(Transcription.created_at.desc())
                      .limit(limit).offset(offset)).all()
    return {"items": [_out(t, db) for t in rows], "total": total, "limit": limit, "offset": offset}


def _get(db: Session, tid: str) -> Transcription:
    t = db.get(Transcription, tid)
    if not t:
        raise NotFound("Transcription not found.")
    return t


@router.get("/transcriptions/{tid}")
def get_transcription(tid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _out(_get(db, tid), db)


@router.patch("/transcriptions/{tid}")
def patch_transcription(tid: str, body: S.TranscriptionPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = _get(db, tid)
    if body.edited_text is not None:
        t.edited_text = body.edited_text
    if body.name is not None:
        t.name = body.name
    db.flush()
    return _out(t, db)


@router.delete("/transcriptions/{tid}")
def delete_transcription(tid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = _get(db, tid)
    j = db.get(GenerationJob, t.job_id) if t.job_id else None
    if j and j.status in queue.ACTIVE:
        if j.status in ("queued", "loading_model", "running"):
            queue.request_cancel(db, j)
    asset_id = t.source_asset_id
    db.delete(t)
    db.flush()
    assets.release_asset(db, asset_id)
    return {"deleted": tid}


@router.get("/transcriptions/{tid}/export")
def export_transcription(tid: str, format: Literal["txt", "srt", "vtt"] = "txt",
                         db: Session = Depends(get_db)) -> Response:
    t = _get(db, tid)
    if format == "txt":
        body = t.edited_text if t.edited_text is not None else t.text
        media = "text/plain; charset=utf-8"
    else:
        if t.timestamp_kind == "none" or not t.segments:
            raise Conflict("This transcript has no timestamps, so subtitles cannot be created.",
                           code="no_timestamps")
        if t.edited_text is not None and t.edited_text != t.text:
            raise Conflict("The transcript was edited; subtitle timing only matches the original "
                           "machine transcript. Export TXT, or clear your edits.", code="edited_transcript")
        body = to_srt(t.segments) if format == "srt" else to_vtt(t.segments)
        media = "application/x-subrip; charset=utf-8" if format == "srt" else "text/vtt; charset=utf-8"
    safe = "".join(c for c in t.name if c.isalnum() or c in " -_")[:80] or "transcript"
    return Response(body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{safe}.{format}"'})
