"""Managed audio storage.

Files are identified by server-generated storage keys (relative POSIX paths under the
media directory). API callers only ever see asset IDs. Writes go to a temporary file
first, are validated, then moved into place atomically.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session

from app.audio import ffmpeg
from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound
from app.db.models import (
    AudioAsset,
    GenerationJob,
    GenerationTake,
    Transcription,
    VoiceProfile,
)


def resolve_key(key: str, base: Path | None = None) -> Path:
    base = (base or get_settings().media_dir).resolve()
    p = (base / key).resolve()
    if not p.is_relative_to(base):
        raise Forbidden("Invalid storage key.")
    return p


def temp_path(suffix: str = ".wav") -> Path:
    tmp = get_settings().tmp_dir
    tmp.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=suffix, dir=tmp)
    os.close(fd)
    return Path(name)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_wav_temp(samples: np.ndarray, sr: int) -> Path:
    p = temp_path(".wav")
    data = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    sf.write(str(p), data, sr, subtype="PCM_16")
    return p


def finalize_asset(db: Session, tmp_file: Path, kind: str, media_type: str = "audio/wav") -> AudioAsset:
    """Validate a temporary audio file by decoding it, then move it into managed storage."""
    info = ffmpeg.probe(tmp_file)
    if info.duration <= 0:
        tmp_file.unlink(missing_ok=True)
        raise ffmpeg.MediaError("Produced audio file is empty.")
    asset_id = uuid.uuid4().hex
    ext = tmp_file.suffix or ".wav"
    key = f"{kind}/{asset_id[:2]}/{asset_id}{ext}"
    dest = resolve_key(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    checksum = sha256_file(tmp_file)
    size = tmp_file.stat().st_size
    os.replace(tmp_file, dest)
    asset = AudioAsset(id=asset_id, managed_storage_key=key, kind=kind, media_type=media_type,
                       sample_rate=info.sample_rate, channel_count=info.channels,
                       duration=round(info.duration, 4), byte_size=size, checksum=checksum)
    db.add(asset)
    db.flush()
    return asset


def asset_path(asset: AudioAsset) -> Path:
    return resolve_key(asset.managed_storage_key)


def get_asset(db: Session, asset_id: str) -> AudioAsset:
    a = db.get(AudioAsset, asset_id)
    if not a:
        raise NotFound("Audio not found.")
    return a


def asset_in_use(db: Session, asset_id: str) -> bool:
    checks = [
        select(GenerationTake.id).where(GenerationTake.output_asset_id == asset_id),
        select(VoiceProfile.id).where(VoiceProfile.reference_asset_id == asset_id),
        select(Transcription.id).where(Transcription.source_asset_id == asset_id),
        select(GenerationJob.id).where(
            GenerationJob.status.in_(["queued", "loading_model", "running", "cancelling"]),
            or_(GenerationJob.output_asset_id == asset_id,
                GenerationJob.params["asset_id"].as_string() == asset_id)),
    ]
    return any(db.execute(q.limit(1)).first() for q in checks)


def release_asset(db: Session, asset_id: str | None) -> bool:
    """Delete an asset's row and file if nothing references it any more."""
    if not asset_id:
        return False
    a = db.get(AudioAsset, asset_id)
    if not a:
        return False
    db.flush()
    if asset_in_use(db, asset_id):
        return False
    path = asset_path(a)
    db.delete(a)
    db.flush()
    schedule_unlink(db, path)
    return True


def schedule_unlink(db: Session, path: Path) -> None:
    """Delete a file only after the surrounding transaction commits."""
    db.info.setdefault("pending_unlinks", []).append(path)


@event.listens_for(Session, "after_commit")
def _unlink_after_commit(session: Session) -> None:
    for p in session.info.pop("pending_unlinks", []):
        try:
            Path(p).unlink(missing_ok=True)
        except OSError:
            pass


@event.listens_for(Session, "after_rollback")
def _forget_unlinks(session: Session) -> None:
    session.info.pop("pending_unlinks", None)
