"""Voice library: authorised reference recordings with consent records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import soundfile as sf
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audio import ffmpeg
from app.audio.analysis import check_reference
from app.core.config import get_settings
from app.core.errors import AppError, NotFound, Unprocessable
from app.db.models import ConsentRecord, GenerationTake, ScriptSegment, VoiceProfile, utcnow
from app.engines import registry
from app.schemas import api as S
from app.services import models_service
from app.storage import assets

GENERIC_MIN_SECONDS = 2.0
CONSENT_STATEMENTS = {
    "my_own_voice": "I confirm this recording is of my own voice.",
    "written_permission": "I confirm I have the speaker's written permission to use their voice for "
                          "speech generation.",
    "licensed_voice": "I confirm this voice is licensed to me for speech generation.",
    "public_domain": "I confirm this recording is in the public domain or under a licence that permits "
                     "voice cloning.",
}


async def save_upload(file: UploadFile, max_bytes: int) -> Path:
    suffix = Path(file.filename or "upload").suffix.lower()[:8] or ".bin"
    if not suffix[1:].isalnum():
        suffix = ".bin"
    tmp = assets.temp_path(suffix)
    size = 0
    try:
        with tmp.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > max_bytes:
                    raise AppError(f"The file is larger than {max_bytes // 2**20} MB.",
                                   code="file_too_large", status_code=413)
                out.write(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if size == 0:
        tmp.unlink(missing_ok=True)
        raise Unprocessable("The uploaded file is empty.", code="empty_file")
    return tmp


def cloning_engines() -> list[dict[str, Any]]:
    out = []
    for m in registry.all_models():
        if m["kind"] != "tts" or not m.get("adapter"):
            continue
        caps = registry.create_adapter(m["id"]).capabilities()
        if caps.voice_cloning:
            out.append({"id": m["id"], "caps": caps})
    return out


def _ingest(db: Session, tmp_upload: Path, min_s: float, max_s: float) -> tuple[Any, dict[str, Any]]:
    """Decode (validates the real content, not the extension), analyse, and store as
    mono 16-bit WAV at the native sample rate."""
    try:
        info = ffmpeg.probe(tmp_upload)
        if info.duration and info.duration > max_s + 1:
            raise Unprocessable(f"The recording is {info.duration:.0f}s long; the maximum is {max_s:.0f}s.",
                                code="too_long")
        samples, sr = ffmpeg.decode(tmp_upload, mono=True, max_seconds=max_s + 1)
    finally:
        tmp_upload.unlink(missing_ok=True)
    report = check_reference(samples, sr, native_sr=info.sample_rate, channels=info.channels,
                             min_seconds=min_s, max_seconds=max_s)
    if report.errors:
        raise Unprocessable(" ".join(report.errors), code="unsuitable_reference",
                            details={"analysis": report.to_dict()})
    wav = assets.write_wav_temp(samples, sr)
    asset = assets.finalize_asset(db, wav, "reference")
    analysis = report.to_dict()
    analysis["source"] = {"codec": info.codec, "sample_rate": info.sample_rate, "channels": info.channels}
    return asset, analysis


async def create_voice(db: Session, *, file: UploadFile, name: str, language: str, transcript: str,
                       tags: list[str], permission_basis: str, consent_confirmed: bool,
                       document_reference: str | None) -> VoiceProfile:
    if permission_basis not in CONSENT_STATEMENTS:
        raise Unprocessable("Choose the basis on which you may use this voice.", code="consent_required")
    if not consent_confirmed:
        raise Unprocessable("You must confirm that you own this voice or have permission to use it.",
                            code="consent_required")
    settings = get_settings()
    tmp = await save_upload(file, settings.max_upload_bytes)
    asset, analysis = _ingest(db, tmp, GENERIC_MIN_SECONDS, settings.max_reference_seconds)
    consent = ConsentRecord(permission_basis=permission_basis, statement=CONSENT_STATEMENTS[permission_basis],
                            document_reference=(document_reference or None))
    db.add(consent)
    db.flush()
    engines = cloning_engines()
    vp = VoiceProfile(name=name.strip()[:120] or "Untitled voice", language=language,
                      reference_transcript=transcript.strip(), tags=[t.strip()[:40] for t in tags if t.strip()][:20],
                      reference_asset_id=asset.id, consent_record_id=consent.id,
                      compatible_engine=engines[0]["id"] if engines else None,
                      analysis={**analysis, "engine_compatibility": _compat(engines, asset.duration, transcript)})
    db.add(vp)
    db.flush()
    return vp


def _compat(engines: list[dict[str, Any]], duration: float, transcript: str) -> list[dict[str, Any]]:
    out = []
    for e in engines:
        c = e["caps"]
        problems = []
        if c.reference_min_seconds and duration < c.reference_min_seconds:
            problems.append(f"needs at least {c.reference_min_seconds:.0f}s")
        if c.reference_max_seconds and duration > c.reference_max_seconds:
            problems.append(f"accepts at most {c.reference_max_seconds:.0f}s; trim the recording")
        if c.needs_reference_transcript and not transcript.strip():
            problems.append("needs an exact transcript of the recording")
        out.append({"model_id": e["id"], "ok": not problems, "problems": problems})
    return out


def serialize(db: Session, vp: VoiceProfile) -> dict[str, Any]:
    installed = bool(vp.compatible_engine and models_service.is_installed(db, vp.compatible_engine))
    out = S.VoiceOut(
        id=vp.id, name=vp.name, compatible_engine=vp.compatible_engine, compatible_engine_installed=installed,
        reference_asset_id=vp.reference_asset_id, reference_transcript=vp.reference_transcript,
        language=vp.language, tags=vp.tags or [], analysis=vp.analysis or {},
        consent={"permission_basis": vp.consent.permission_basis, "statement": vp.consent.statement,
                 "recorded_at": vp.consent.recorded_at.isoformat() + "Z",
                 "revoked_at": vp.consent.revoked_at.isoformat() + "Z" if vp.consent.revoked_at else None,
                 "document_reference": vp.consent.document_reference},
        duration=vp.reference_asset.duration, created_at=vp.created_at, updated_at=vp.updated_at)
    return out.model_dump(mode="json")


def get_voice(db: Session, voice_id: str) -> VoiceProfile:
    vp = db.get(VoiceProfile, voice_id)
    if not vp:
        raise NotFound("Voice profile not found.")
    return vp


def patch_voice(db: Session, vp: VoiceProfile, body: S.VoicePatch) -> VoiceProfile:
    if body.name is not None:
        vp.name = body.name.strip()
    if body.reference_transcript is not None:
        vp.reference_transcript = body.reference_transcript.strip()
    if body.language is not None:
        vp.language = body.language
    if body.tags is not None:
        vp.tags = [t.strip()[:40] for t in body.tags if t.strip()]
    if body.revoke_consent and not vp.consent.revoked_at:
        vp.consent.revoked_at = utcnow()
    if body.trim_start is not None or body.trim_end is not None:
        old = vp.reference_asset
        src = assets.asset_path(old)
        data, sr = sf.read(str(src), dtype="float32")
        start = int((body.trim_start or 0) * sr)
        end = int((body.trim_end if body.trim_end is not None else len(data) / sr) * sr)
        if end - start <= 0:
            raise Unprocessable("Trim end must be after trim start.")
        tmp = assets.temp_path(".wav")  # re-ingested through the same validation path
        sf.write(str(tmp), data[start:end], sr, subtype="PCM_16")
        asset, analysis = _ingest(db, tmp, GENERIC_MIN_SECONDS, get_settings().max_reference_seconds)
        vp.reference_asset = asset
        engines = cloning_engines()
        vp.analysis = {**analysis, "engine_compatibility": _compat(engines, asset.duration,
                                                                   vp.reference_transcript),
                       "trimmed": {"start": body.trim_start, "end": body.trim_end}}
        db.flush()
        assets.release_asset(db, old.id)
    db.flush()
    return vp


def usage(db: Session, vp: VoiceProfile) -> dict[str, int]:
    segs = db.scalar(select(func.count()).where(ScriptSegment.voice_profile_id == vp.id)) or 0
    takes = db.scalar(select(func.count()).where(
        GenerationTake.generation_parameters["voice_profile_id"].as_string() == vp.id)) or 0
    return {"segments": segs, "takes": takes}


def delete_voice(db: Session, vp: VoiceProfile) -> dict[str, Any]:
    """Deletes the profile and its reference audio. The consent record is kept, marked
    revoked, as an audit trail (it contains no audio). Segments using the voice lose
    their assignment. Previously generated takes stay in their projects until deleted."""
    u = usage(db, vp)
    asset_id = vp.reference_asset_id
    consent = vp.consent
    if not consent.revoked_at:
        consent.revoked_at = utcnow()
    for s in db.scalars(select(ScriptSegment).where(ScriptSegment.voice_profile_id == vp.id)):
        s.voice_profile_id = None
    db.delete(vp)
    db.flush()
    removed = assets.release_asset(db, asset_id)
    return {"unassigned_segments": u["segments"], "reference_audio_deleted": removed,
            "note": "Takes already generated with this voice remain in their projects until you delete them."}
