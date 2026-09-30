from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.session import get_db
from app.storage import assets

router = APIRouter(tags=["assets"])


@router.get("/assets/{asset_id}/audio")
def asset_audio(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """Streams a managed audio asset. Supports HTTP Range requests for seeking."""
    a = assets.get_asset(db, asset_id)
    path = assets.asset_path(a)
    if not path.exists():
        raise NotFound("The audio file is missing on disk.", code="file_missing")
    return FileResponse(path, media_type=a.media_type, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/assets/{asset_id}")
def asset_info(asset_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    a = assets.get_asset(db, asset_id)
    return {"id": a.id, "kind": a.kind, "media_type": a.media_type, "sample_rate": a.sample_rate,
            "channel_count": a.channel_count, "duration": a.duration, "byte_size": a.byte_size,
            "checksum": a.checksum, "created_at": a.created_at.isoformat() + "Z"}
