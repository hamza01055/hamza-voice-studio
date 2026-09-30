"""Job handlers executed by the worker process."""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from sqlalchemy import select

from app.audio import ffmpeg
from app.audio.analysis import check_generated
from app.audio.assemble import Piece, assemble
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import (
    AudioAsset,
    Chapter,
    Export,
    GenerationJob,
    GenerationTake,
    ScriptSegment,
    Transcription,
    VoiceProfile,
)
from app.db.session import session_factory
from app.engines import registry
from app.engines.base import (
    ASRAdapter,
    EngineError,
    EngineUnavailable,
    GenerationCancelled,
    SynthesisRequest,
    TTSAdapter,
)
from app.jobs.context import JobContext
from app.jobs.engine_manager import EngineManager
from app.services import models_service, settings_service
from app.storage import assets


class JobFailed(EngineError):
    pass


def _include_unevaluated() -> bool:
    with session_factory()() as db:
        return settings_service.get_all(db).show_unevaluated_languages


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

def handle_tts(ctx: JobContext, engines: EngineManager) -> dict[str, Any]:
    p = ctx.params
    model_id = p["model_id"]
    with session_factory()() as db:
        if not models_service.is_installed(db, model_id):
            raise EngineUnavailable(f"The model '{model_id}' is not installed. Install it on the Models page.")
        ref_audio = ref_sr = None
        ref_text = None
        if p.get("voice_profile_id"):
            vp = db.get(VoiceProfile, p["voice_profile_id"])
            if not vp:
                raise JobFailed("The voice profile was deleted.", code="voice_deleted")
            if vp.consent.revoked_at:
                raise JobFailed("Permission for this voice was revoked.", code="consent_revoked")
            ref_audio, ref_sr = sf.read(str(assets.asset_path(vp.reference_asset)), dtype="float32")
            ref_text = vp.reference_transcript
    adapter = engines.get(model_id, {"include_unevaluated": _include_unevaluated()})
    if not isinstance(adapter, TTSAdapter):
        raise JobFailed("The selected model is not a speech generation model.", code="wrong_model_kind")
    req = SynthesisRequest(text=p["text"], language=p["language"], voice=p.get("voice"),
                           reference_audio=ref_audio, reference_sample_rate=ref_sr,
                           reference_transcript=ref_text, speed=float(p.get("speed") or 1.0),
                           seed=p.get("seed"))
    adapter.validate_request(req)
    t_load = 0.0
    needs_load = getattr(adapter, "needs_load", lambda _l: not adapter.loaded)(req.language)
    if needs_load:
        ctx.progress(None, "Loading model", status="loading_model", force=True)
        t0 = time.perf_counter()
        adapter.load(req.language)  # type: ignore[call-arg]
        t_load = time.perf_counter() - t0
    ctx.progress(0.0, "Generating speech", status="running", force=True)
    t0 = time.perf_counter()
    result = adapter.synthesize(req, lambda f, s: ctx.progress(f, s), ctx.should_cancel)
    t_gen = time.perf_counter() - t0
    if ctx.should_cancel():
        raise GenerationCancelled("Generation was cancelled.")

    ctx.progress(None, "Validating audio", force=True)
    report = check_generated(result.samples, result.sample_rate, req.text, req.speed)
    if report.errors:
        raise JobFailed(" ".join(report.errors), code="invalid_output", retryable=False)
    tmp = assets.write_wav_temp(result.samples, result.sample_rate)
    audio_s = len(result.samples) / result.sample_rate
    timings = {"load_seconds": round(t_load, 3), "generation_seconds": round(t_gen, 3),
               "audio_seconds": round(audio_s, 3), "rtf": round(t_gen / audio_s, 4) if audio_s else None}
    try:
        with session_factory()() as db:
            job = db.get(GenerationJob, ctx.job_id)
            if job is None or job.cancel_requested:
                raise GenerationCancelled("Generation was cancelled.")
            seg = db.get(ScriptSegment, ctx.segment_id) if ctx.segment_id else None
            if seg is None:
                raise JobFailed("The segment was deleted before generation finished; the audio was discarded.",
                                code="segment_deleted")
            asset = assets.finalize_asset(db, tmp, "take")
            entry = registry.get_model(model_id)
            take = GenerationTake(
                segment_id=seg.id, job_id=ctx.job_id, input_revision=ctx.input_revision or 0,
                input_text=req.text, model_id=model_id, model_revision=entry["revision"],
                voice_label=p.get("voice_label") or p.get("voice") or "",
                generation_parameters={**result.parameters, "seed": None,
                                       "voice_profile_id": p.get("voice_profile_id"),
                                       "original_text_revision": ctx.input_revision,
                                       "take_index": p.get("take_index", 0)},
                quality={"warnings": report.warnings, "signal": report.to_dict(), "timings": timings},
                output_asset_id=asset.id)
            db.add(take)
            db.flush()
            # Auto-select only if nothing is selected and the take matches the current text.
            if seg.selected_take_id is None and ctx.input_revision == seg.text_revision:
                seg.selected_take_id = take.id
            job.output_asset_id = asset.id
            db.commit()
            return {"take_id": take.id, "asset_id": asset.id, "warnings": report.warnings, **timings}
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def handle_transcribe(ctx: JobContext, engines: EngineManager) -> dict[str, Any]:
    p = ctx.params
    model_id = p["model_id"]
    with session_factory()() as db:
        if not models_service.is_installed(db, model_id):
            raise EngineUnavailable(f"The model '{model_id}' is not installed. Install it on the Models page.")
        asset = db.get(AudioAsset, p["asset_id"])
        if asset is None:
            raise JobFailed("The uploaded audio was deleted.", code="asset_deleted")
        path = assets.asset_path(asset)
    ctx.progress(None, "Decoding audio", status="running", force=True)
    samples, sr = ffmpeg.decode(path, sample_rate=16000, mono=True)
    adapter = engines.get(model_id)
    if not isinstance(adapter, ASRAdapter):
        raise JobFailed("The selected model is not a transcription model.", code="wrong_model_kind")
    t0 = time.perf_counter()
    res = adapter.transcribe(samples, sr, p.get("language") or None,
                             lambda f, s: ctx.progress(f, s), ctx.should_cancel)
    elapsed = time.perf_counter() - t0
    with session_factory()() as db:
        tr = db.get(Transcription, p["transcription_id"])
        if tr is None:
            raise JobFailed("The transcription was deleted.", code="deleted")
        tr.text = res.text
        tr.segments = res.segments
        tr.language_detected = res.language
        tr.timestamp_kind = res.timestamp_kind
        db.commit()
    return {"transcription_id": p["transcription_id"], "seconds": round(elapsed, 2),
            "audio_seconds": round(len(samples) / sr, 2)}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

SAFE_NAME = re.compile(r"[^\w\-. ()؀-ۿ]+")


def safe_file_name(name: str, ext: str) -> str:
    base = SAFE_NAME.sub("_", name).strip(" ._") or "export"
    base = base[:120]
    if base.lower().endswith(f".{ext}"):
        base = base[: -(len(ext) + 1)]
    return f"{base}.{ext}"


def unique_path(directory: Path, file_name: str) -> Path:
    p = directory / file_name
    stem, suffix = p.stem, p.suffix
    i = 1
    while p.exists():
        p = directory / f"{stem} ({i}){suffix}"
        i += 1
    return p


def place_without_overwrite(src: Path, directory: Path, file_name: str) -> Path:
    """Move ``src`` into ``directory`` under a name that does not exist yet. Uses
    exclusive creation so a file that appears concurrently is never overwritten."""
    for _ in range(50):
        final = unique_path(directory, file_name)
        try:
            os.link(src, final)  # atomic, fails if the name exists
        except FileExistsError:
            continue
        except OSError:
            try:
                with final.open("xb") as out, src.open("rb") as inp:
                    shutil.copyfileobj(inp, out)
            except FileExistsError:
                continue
        src.unlink(missing_ok=True)
        return final
    raise JobFailed("Could not find a free file name for the export.", code="export_name_conflict")


def handle_export(ctx: JobContext, _engines: EngineManager) -> dict[str, Any]:
    p = ctx.params
    settings = get_settings()
    warnings: list[str] = []
    with session_factory()() as db:
        export = db.get(Export, p["export_id"])
        if export is None:
            raise JobFailed("The export record was deleted.", code="deleted")
        export.status = "running"
        chapters = list(db.scalars(select(Chapter).where(Chapter.project_id == p["project_id"])
                                   .order_by(Chapter.position)))
        if p.get("chapter_id"):
            chapters = [c for c in chapters if c.id == p["chapter_id"]]
        only = set(p.get("segment_ids") or [])
        items: list[tuple[str, int, bool]] = []  # (storage_key, pause_ms, stale)
        missing = 0
        for ci, ch in enumerate(chapters):
            segs = [s for s in ch.segments if not only or s.id in only]
            for si, seg in enumerate(segs):
                if not seg.selected_take_id:
                    missing += 1
                    continue
                take = db.get(GenerationTake, seg.selected_take_id)
                if take is None:
                    missing += 1
                    continue
                last_in_chapter = si == len(segs) - 1
                pause = seg.pause_after_ms
                if last_in_chapter and ci < len(chapters) - 1:
                    pause = int(p.get("chapter_gap_ms", 1500))
                stale = take.input_revision != seg.text_revision
                items.append((take.output_asset.managed_storage_key, pause, stale))
        db.commit()
    if missing and not p.get("skip_missing"):
        raise JobFailed(f"{missing} segment(s) have no selected take. Generate or select takes first, "
                        "or enable 'skip segments without a take'.", code="missing_takes")
    if missing:
        warnings.append(f"{missing} segment(s) without a selected take were skipped.")
    if not items:
        raise JobFailed("There is nothing to export.", code="nothing_to_export")
    stale_n = sum(1 for i in items if i[2])
    if stale_n:
        warnings.append(f"{stale_n} selected take(s) were generated from an older version of the text.")

    pieces: list[Piece] = []
    rates: list[int] = []
    for n, (key, pause, _stale) in enumerate(items):
        if ctx.should_cancel():
            raise GenerationCancelled("Export cancelled.")
        ctx.progress(n / (len(items) + 2), f"Reading take {n + 1} of {len(items)}", status="running")
        data, sr = sf.read(str(assets.resolve_key(key)), dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        pieces.append(Piece(np.asarray(data, dtype=np.float32), sr, pause))
        rates.append(sr)
    target_sr = max(set(rates), key=rates.count)
    for pc in pieces:
        if pc.sample_rate != target_sr:
            # Mixed engines: resample the minority to the dominant native rate.
            tmp_in = assets.write_wav_temp(pc.samples, pc.sample_rate)
            try:
                pc.samples, pc.sample_rate = ffmpeg.decode(tmp_in, sample_rate=target_sr)
            finally:
                tmp_in.unlink(missing_ok=True)
            warnings.append("Takes had different sample rates and were resampled for assembly.")
    audio, _spans = assemble(pieces, target_sr)
    expected = len(audio) / target_sr
    ctx.progress(len(items) / (len(items) + 2), "Encoding", status="running", force=True)
    fmt = p["format"]
    wav_tmp = assets.write_wav_temp(audio, target_sr)
    out_tmp = assets.temp_path(f".{fmt}")
    try:
        out_sr = p.get("sample_rate") or None
        ffmpeg.encode(wav_tmp, out_tmp, fmt, bitrate_kbps=int(p.get("bitrate_kbps") or 192),
                      sample_rate=out_sr, loudnorm=bool(p.get("loudnorm")))
        if ctx.should_cancel():
            raise GenerationCancelled("Export cancelled.")
        ctx.progress((len(items) + 1) / (len(items) + 2), "Validating export", force=True)
        info = ffmpeg.probe(out_tmp)
        tolerance = 0.25 + expected * 0.01
        if abs(info.duration - expected) > tolerance:
            raise JobFailed("The exported file's duration did not match the assembled audio; "
                            "the export was discarded.", code="invalid_export")
        settings.exports_dir.mkdir(parents=True, exist_ok=True)
        final = place_without_overwrite(out_tmp, settings.exports_dir, safe_file_name(p["file_name"], fmt))
        with session_factory()() as db:
            export = db.get(Export, p["export_id"])
            if export is None:
                final.unlink(missing_ok=True)
                raise JobFailed("The export record was deleted.", code="deleted")
            export.status = "completed"
            export.storage_key = final.name
            export.file_name = final.name
            export.byte_size = final.stat().st_size
            export.duration = round(info.duration, 3)
            export.sample_rate = info.sample_rate
            export.details = {"warnings": warnings, "segments": len(items),
                              "native_sample_rate": target_sr}
            db.commit()
        return {"export_id": p["export_id"], "duration": round(info.duration, 3), "warnings": warnings}
    finally:
        wav_tmp.unlink(missing_ok=True)
        out_tmp.unlink(missing_ok=True)


def mark_export_failed(export_id: str | None, status: str, message: str | None) -> None:
    if not export_id:
        return
    with session_factory()() as db:
        e = db.get(Export, export_id)
        if e and e.status != "completed":
            e.status = status
            e.details = {**(e.details or {}), "error": message}
            db.commit()


# ---------------------------------------------------------------------------
# Model download
# ---------------------------------------------------------------------------

def handle_model_download(ctx: JobContext, _engines: EngineManager) -> dict[str, Any]:
    ctx.progress(None, "Starting download", status="running", force=True)
    return models_service.run_download(lambda: session_factory()(), ctx.params["model_id"],
                                       lambda f, s: ctx.progress(f, s), ctx.should_cancel)


HANDLERS = {
    "tts": handle_tts,
    "transcribe": handle_transcribe,
    "export": handle_export,
    "model_download": handle_model_download,
}


def classify(exc: BaseException) -> tuple[str, str, bool]:
    """(error_code, user_message, retryable)"""
    if isinstance(exc, EngineError):
        return exc.code, exc.message, exc.retryable
    if isinstance(exc, AppError):
        return exc.code, exc.message, False
    if isinstance(exc, MemoryError):
        return "out_of_memory", "Ran out of memory. Close other applications or use shorter segments.", True
    return "internal_error", f"Unexpected error ({type(exc).__name__}). See the application log.", True
