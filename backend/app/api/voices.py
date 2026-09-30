from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import VoiceProfile
from app.db.session import get_db
from app.schemas import api as S
from app.services import voices as V

router = APIRouter(tags=["voices"])


@router.get("/voices")
def list_voices(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db)) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(VoiceProfile)) or 0
    rows = db.scalars(select(VoiceProfile).order_by(VoiceProfile.created_at.desc())
                      .limit(limit).offset(offset)).all()
    return {"items": [V.serialize(db, v) for v in rows], "total": total, "limit": limit, "offset": offset,
            "cloning_engines_installed": [e["id"] for e in V.cloning_engines()
                                          if V.models_service.is_installed(db, e["id"])],
            "consent_options": V.CONSENT_STATEMENTS}


@router.post("/voices", status_code=201)
async def create_voice(file: UploadFile = File(...), name: str = Form(..., max_length=120),
                       language: str = Form("en-us", max_length=16),
                       transcript: str = Form("", max_length=5000), tags: str = Form("[]", max_length=2000),
                       permission_basis: str = Form(...), consent_confirmed: bool = Form(False),
                       document_reference: str | None = Form(None, max_length=500),
                       db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        tag_list = [str(t) for t in json.loads(tags)] if tags else []
    except (ValueError, TypeError):
        tag_list = [t.strip() for t in tags.split(",")]
    vp = await V.create_voice(db, file=file, name=name, language=language, transcript=transcript,
                              tags=tag_list, permission_basis=permission_basis,
                              consent_confirmed=consent_confirmed, document_reference=document_reference)
    return V.serialize(db, vp)


@router.get("/voices/{voice_id}")
def get_voice(voice_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    vp = V.get_voice(db, voice_id)
    return {**V.serialize(db, vp), "usage": V.usage(db, vp)}


@router.patch("/voices/{voice_id}")
def patch_voice(voice_id: str, body: S.VoicePatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    return V.serialize(db, V.patch_voice(db, V.get_voice(db, voice_id), body))


@router.delete("/voices/{voice_id}")
def delete_voice(voice_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"deleted": voice_id, **V.delete_voice(db, V.get_voice(db, voice_id))}
