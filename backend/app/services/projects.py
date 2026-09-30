"""Project, chapter and segment domain logic."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import Conflict, NotFound, Unprocessable
from app.db.models import (
    AudioAsset,
    Chapter,
    Export,
    GenerationJob,
    GenerationTake,
    Project,
    ScriptSegment,
    VoiceProfile,
)
from app.engines import registry
from app.engines.base import EngineError, SynthesisRequest, TTSAdapter
from app.jobs import queue
from app.schemas import api as S
from app.services import models_service, settings_service
from app.services.normalize import normalize
from app.services.segmentation import segment as split_script
from app.storage import assets


# ---------------------------------------------------------------- helpers
def get_project(db: Session, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise NotFound("Project not found.")
    return p


def get_segment(db: Session, segment_id: str) -> ScriptSegment:
    s = db.get(ScriptSegment, segment_id)
    if not s:
        raise NotFound("Segment not found.")
    return s


def get_chapter(db: Session, chapter_id: str) -> Chapter:
    c = db.get(Chapter, chapter_id)
    if not c:
        raise NotFound("Chapter not found.")
    return c


def project_settings(p: Project) -> S.ProjectSettings:
    try:
        return S.ProjectSettings(**(p.settings or {}))
    except Exception:  # noqa: BLE001
        return S.ProjectSettings()


def seg_language(p: Project, s: ScriptSegment) -> str:
    return s.language or p.default_language


def renormalize(p: Project, s: ScriptSegment) -> bool:
    """Recompute normalized text; bumps text_revision if it changed."""
    ps = project_settings(p)
    res = normalize(s.original_text, seg_language(p, s), [o.model_dump() for o in ps.pronunciations])
    if res.text != s.normalized_text:
        s.normalized_text = res.text
        s.text_revision += 1
        return True
    return False


def _reindex(items: list[Any]) -> None:
    for i, it in enumerate(items):
        it.position = i


# ---------------------------------------------------------------- projects
def create_project(db: Session, body: S.ProjectCreate) -> Project:
    app_s = settings_service.get_all(db)
    ps = body.settings or S.ProjectSettings(model_id=app_s.default_model_id, voice=app_s.default_voice,
                                            pause_ms=app_s.default_pause_ms,
                                            segmentation_mode=app_s.segmentation_mode)
    p = Project(name=body.name.strip(), default_language=body.default_language, settings=ps.model_dump())
    db.add(p)
    db.flush()
    ch = Chapter(project_id=p.id, position=0, title="Chapter 1", script_text=body.script or "")
    p.chapters.append(ch)
    db.flush()
    if body.script and body.script.strip():
        add_segments(db, p, S.SegmentsCreate(chapter_id=ch.id, script=body.script,
                                             mode=ps.segmentation_mode))
    return p


def list_projects(db: Session, limit: int, offset: int, q: str | None) -> tuple[list[dict[str, Any]], int]:
    base = select(Project)
    if q:
        base = base.where(Project.name.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(Project.updated_at.desc()).limit(limit).offset(offset)).all()
    out = []
    for p in rows:
        seg_count = db.scalar(select(func.count()).where(ScriptSegment.project_id == p.id)) or 0
        gen = db.scalar(select(func.count()).where(ScriptSegment.project_id == p.id,
                                                   ScriptSegment.selected_take_id.is_not(None))) or 0
        out.append(S.ProjectSummary.model_validate(p).model_copy(
            update={"segment_count": seg_count, "generated_count": gen}).model_dump(mode="json"))
    return out, total


def serialize_segment(db: Session, s: ScriptSegment, take_counts: dict[str, int] | None = None,
                      active: dict[str, GenerationJob] | None = None) -> dict[str, Any]:
    out = S.SegmentOut.model_validate(s)
    upd: dict[str, Any] = {}
    upd["take_count"] = take_counts.get(s.id, 0) if take_counts is not None else len(s.takes)
    if s.selected_take_id:
        t = db.get(GenerationTake, s.selected_take_id)
        if t:
            upd["selected_take_stale"] = t.input_revision != s.text_revision
            a = db.get(AudioAsset, t.output_asset_id)
            upd["selected_take_duration"] = a.duration if a else None
    if active is not None and s.id in active:
        upd["active_job_id"] = active[s.id].id
        upd["active_job_status"] = active[s.id].status
    return out.model_copy(update=upd).model_dump(mode="json")


def serialize_project(db: Session, p: Project) -> dict[str, Any]:
    p = db.scalars(select(Project).where(Project.id == p.id).options(
        selectinload(Project.chapters).selectinload(Chapter.segments))
        .execution_options(populate_existing=True)).one()
    counts = dict(db.execute(select(GenerationTake.segment_id, func.count())
                             .join(ScriptSegment, ScriptSegment.id == GenerationTake.segment_id)
                             .where(ScriptSegment.project_id == p.id)
                             .group_by(GenerationTake.segment_id)).all())
    active: dict[str, GenerationJob] = {}
    for j in db.scalars(select(GenerationJob).where(GenerationJob.project_id == p.id,
                                                    GenerationJob.status.in_(queue.ACTIVE),
                                                    GenerationJob.type == "tts")
                        .order_by(GenerationJob.created_at)):
        if j.segment_id and j.segment_id not in active:
            active[j.segment_id] = j
    data = S.ProjectOut.model_validate(p).model_dump(mode="json", exclude={"chapters"})
    data["settings"] = project_settings(p).model_dump()
    data["chapters"] = []
    for ch in p.chapters:
        c = S.ChapterOut.model_validate(ch).model_dump(mode="json", exclude={"segments"})
        c["segments"] = [serialize_segment(db, s, counts, active) for s in ch.segments]
        data["chapters"].append(c)
    return data


def patch_project(db: Session, p: Project, body: S.ProjectPatch) -> Project:
    lang_changed = False
    if body.name is not None:
        p.name = body.name.strip()
    if body.default_language is not None and body.default_language != p.default_language:
        p.default_language = body.default_language
        lang_changed = True
    prons_changed = False
    if body.settings is not None:
        old = project_settings(p)
        prons_changed = old.pronunciations != body.settings.pronunciations
        p.settings = body.settings.model_dump()
    if lang_changed or prons_changed:
        for ch in p.chapters:
            for s in ch.segments:
                renormalize(p, s)
    db.flush()
    return p


def delete_project(db: Session, p: Project) -> dict[str, int]:
    """Deletes the project, its segments, takes and take audio. Queued jobs are
    cancelled; running jobs are asked to cancel (their output is discarded)."""
    cancelled = 0
    for j in db.scalars(select(GenerationJob).where(GenerationJob.project_id == p.id,
                                                    GenerationJob.status.in_(queue.ACTIVE))):
        if j.status != "cancelling":
            queue.request_cancel(db, j)
        cancelled += 1
    asset_ids = [t.output_asset_id for ch in p.chapters for s in ch.segments for t in s.takes]
    for ch in p.chapters:
        for s in ch.segments:
            s.selected_take_id = None
    db.flush()
    exports = db.scalars(select(Export).where(Export.project_id == p.id)).all()
    from app.core.config import get_settings

    for e in exports:
        if e.storage_key:
            assets.schedule_unlink(db, assets.resolve_key(e.storage_key, get_settings().exports_dir))
        db.delete(e)
    db.delete(p)
    db.flush()
    removed = sum(1 for a in asset_ids if assets.release_asset(db, a))
    return {"cancelled_jobs": cancelled, "deleted_audio_files": removed, "deleted_exports": len(exports)}


# ---------------------------------------------------------------- chapters
def add_chapter(db: Session, p: Project, body: S.ChapterCreate) -> Chapter:
    ch = Chapter(project_id=p.id, position=len(p.chapters), title=body.title, script_text=body.script or "")
    p.chapters.append(ch)
    db.flush()
    if body.script and body.script.strip():
        add_segments(db, p, S.SegmentsCreate(chapter_id=ch.id, script=body.script,
                                             mode=project_settings(p).segmentation_mode))
    return ch


def patch_chapter(db: Session, ch: Chapter, body: S.ChapterPatch) -> Chapter:
    if body.title is not None:
        ch.title = body.title
    if body.position is not None:
        chapters = [c for c in ch.project.chapters if c.id != ch.id]
        chapters.insert(min(body.position, len(chapters)), ch)
        _reindex(chapters)
    db.flush()
    return ch


def delete_chapter(db: Session, ch: Chapter) -> None:
    p = ch.project
    if len(p.chapters) <= 1:
        raise Conflict("A project needs at least one chapter.", code="last_chapter")
    asset_ids = [t.output_asset_id for s in ch.segments for t in s.takes]
    for s in ch.segments:
        s.selected_take_id = None
    db.flush()
    db.delete(ch)
    db.flush()
    for a in asset_ids:
        assets.release_asset(db, a)
    _reindex([c for c in p.chapters if c.id != ch.id])


# ---------------------------------------------------------------- segments
def add_segments(db: Session, p: Project, body: S.SegmentsCreate) -> list[ScriptSegment]:
    ch = get_chapter(db, body.chapter_id) if body.chapter_id else p.chapters[0]
    if ch.project_id != p.id:
        raise NotFound("Chapter not found in this project.")
    ps = project_settings(p)
    from app.core.config import get_settings

    parts = split_script(body.script, body.mode, get_settings().max_segment_chars)
    existing = list(ch.segments)
    reused: list[ScriptSegment] = []
    if body.replace:
        # Keep segments (and their takes) whose text is unchanged, to avoid regenerating them.
        by_text: dict[str, list[ScriptSegment]] = {}
        for s in existing:
            by_text.setdefault(s.original_text, []).append(s)
        new_list: list[ScriptSegment] = []
        for text in parts:
            if by_text.get(text):
                s = by_text[text].pop(0)
                reused.append(s)
                new_list.append(s)
            else:
                new_list.append(_new_segment(p, ch, text, ps))
        for leftover in [s for v in by_text.values() for s in v]:
            delete_segment(db, leftover, reindex=False)
        ch.script_text = body.script
        for s in new_list:
            if s not in existing:
                db.add(s)
        db.flush()
        ch.segments[:] = new_list
        _reindex(new_list)
        db.flush()
        return new_list
    created = [_new_segment(p, ch, t, ps) for t in parts]
    for s in created:
        db.add(s)
    at = len(existing) if body.insert_at is None else min(body.insert_at, len(existing))
    ordered = existing[:at] + created + existing[at:]
    db.flush()
    ch.segments[:] = ordered
    _reindex(ordered)
    if not ch.script_text:
        ch.script_text = body.script
    db.flush()
    return created


def _new_segment(p: Project, ch: Chapter, text: str, ps: S.ProjectSettings) -> ScriptSegment:
    s = ScriptSegment(project_id=p.id, chapter_id=ch.id, original_text=text, normalized_text="",
                      text_revision=0, pause_after_ms=ps.pause_ms)
    renormalize(p, s)
    return s


def patch_segment(db: Session, s: ScriptSegment, body: S.SegmentPatch) -> ScriptSegment:
    p = get_project(db, s.project_id)
    fields = body.model_dump(exclude_unset=True)
    if "original_text" in fields and body.original_text is not None and body.original_text != s.original_text:
        s.original_text = body.original_text
        renormalize(p, s)
    if "language" in fields:
        s.language = body.language or None
        renormalize(p, s)
    if body.clear_voice:
        s.preset_voice = None
        s.voice_profile_id = None
    if "preset_voice" in fields:
        s.preset_voice = body.preset_voice or None
        if body.preset_voice:
            s.voice_profile_id = None
    if "voice_profile_id" in fields:
        if body.voice_profile_id and not db.get(VoiceProfile, body.voice_profile_id):
            raise NotFound("Voice profile not found.")
        s.voice_profile_id = body.voice_profile_id or None
        if body.voice_profile_id:
            s.preset_voice = None
    if "model_id" in fields:
        if body.model_id:
            registry.get_model(body.model_id)
        s.model_id = body.model_id or None
    if "speed" in fields:
        s.speed = body.speed
    if body.pause_after_ms is not None:
        s.pause_after_ms = body.pause_after_ms
    if body.chapter_id and body.chapter_id != s.chapter_id:
        target = get_chapter(db, body.chapter_id)
        if target.project_id != s.project_id:
            raise NotFound("Chapter not found in this project.")
        old = get_chapter(db, s.chapter_id)
        old.segments.remove(s)
        _reindex(old.segments)
        pos = body.position if body.position is not None else len(target.segments)
        target.segments.insert(min(pos, len(target.segments)), s)
        s.chapter_id = target.id
        _reindex(target.segments)
    elif body.position is not None:
        ch = get_chapter(db, s.chapter_id)
        segs = [x for x in ch.segments if x.id != s.id]
        segs.insert(min(body.position, len(segs)), s)
        ch.segments[:] = segs
        _reindex(segs)
    db.flush()
    return s


def delete_segment(db: Session, s: ScriptSegment, reindex: bool = True) -> None:
    for j in db.scalars(select(GenerationJob).where(GenerationJob.segment_id == s.id,
                                                    GenerationJob.status.in_(queue.ACTIVE))):
        if j.status != "cancelling":
            queue.request_cancel(db, j)
    asset_ids = [t.output_asset_id for t in s.takes]
    s.selected_take_id = None
    db.flush()
    ch = s.chapter
    db.delete(s)
    db.flush()
    for a in asset_ids:
        assets.release_asset(db, a)
    if reindex:
        _reindex([x for x in ch.segments if x.id != s.id])


def split_segment(db: Session, s: ScriptSegment, at: int) -> ScriptSegment:
    if at >= len(s.original_text):
        raise Unprocessable("Split position must be inside the text.")
    first, second = s.original_text[:at].rstrip(), s.original_text[at:].lstrip()
    if not first or not second:
        raise Unprocessable("Both parts must contain text.")
    p = get_project(db, s.project_id)
    s.original_text = first
    renormalize(p, s)
    ch = get_chapter(db, s.chapter_id)
    new = ScriptSegment(project_id=p.id, chapter_id=ch.id, original_text=second, normalized_text="",
                        text_revision=0, pause_after_ms=s.pause_after_ms, preset_voice=s.preset_voice,
                        voice_profile_id=s.voice_profile_id, model_id=s.model_id, speed=s.speed,
                        language=s.language)
    renormalize(p, new)
    db.add(new)
    db.flush()
    segs = list(ch.segments)
    if new in segs:
        segs.remove(new)
    segs.insert(segs.index(s) + 1, new)
    ch.segments[:] = segs
    _reindex(segs)
    db.flush()
    return new


def list_takes(db: Session, s: ScriptSegment) -> list[dict[str, Any]]:
    out = []
    for t in s.takes:
        d = S.TakeOut.model_validate(t).model_copy(update={
            "duration": t.output_asset.duration, "stale": t.input_revision != s.text_revision})
        out.append(d.model_dump(mode="json"))
    return out


def select_take(db: Session, s: ScriptSegment, take_id: str | None) -> ScriptSegment:
    if take_id is not None:
        t = db.get(GenerationTake, take_id)
        if not t or t.segment_id != s.id:
            raise NotFound("Take not found for this segment.")
    s.selected_take_id = take_id
    db.flush()
    return s


def delete_take(db: Session, t: GenerationTake) -> None:
    s = db.get(ScriptSegment, t.segment_id)
    if s and s.selected_take_id == t.id:
        s.selected_take_id = None
    asset_id = t.output_asset_id
    db.flush()
    db.delete(t)
    db.flush()
    assets.release_asset(db, asset_id)


# ---------------------------------------------------------------- generation
def resolve_generation(db: Session, p: Project, s: ScriptSegment) -> dict[str, Any]:
    ps = project_settings(p)
    app_s = settings_service.get_all(db)
    model_id = s.model_id or ps.model_id or app_s.default_model_id
    voice_profile_id = s.voice_profile_id or (None if s.preset_voice else ps.voice_profile_id)
    voice = None if voice_profile_id else (s.preset_voice or ps.voice or app_s.default_voice)
    speed = s.speed if s.speed is not None else ps.speed
    language = seg_language(p, s)
    label = voice or ""
    if voice_profile_id:
        vp = db.get(VoiceProfile, voice_profile_id)
        label = f"Profile: {vp.name}" if vp else "Deleted profile"
    return {"model_id": model_id, "voice": voice, "voice_profile_id": voice_profile_id, "speed": speed,
            "language": language, "text": s.normalized_text, "voice_label": label}


def request_generation(db: Session, body: S.GenerationRequest) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    app_s = settings_service.get_all(db)
    adapters: dict[str, TTSAdapter] = {}
    for idx, seg_id in enumerate(body.segment_ids):
        s = db.get(ScriptSegment, seg_id)
        if not s:
            skipped.append({"segment_id": seg_id, "reason": "Segment not found."})
            continue
        p = get_project(db, s.project_id)
        if body.only_missing and s.selected_take_id:
            t = db.get(GenerationTake, s.selected_take_id)
            if t and t.input_revision == s.text_revision:
                skipped.append({"segment_id": seg_id, "reason": "Already has a current take."})
                continue
        params = resolve_generation(db, p, s)
        entry = registry.get_model(params["model_id"])
        if entry["kind"] != "tts":
            raise Unprocessable("The selected model cannot generate speech.")
        if not models_service.is_installed(db, params["model_id"]):
            raise Conflict(f"The model '{entry['name']}' is not installed. Install it on the Models page.",
                           code="model_not_installed")
        if params["model_id"] not in adapters:
            ad = registry.create_adapter(params["model_id"],
                                         {"include_unevaluated": app_s.show_unevaluated_languages})
            assert isinstance(ad, TTSAdapter)
            adapters[params["model_id"]] = ad
        adapter = adapters[params["model_id"]]
        caps = adapter.capabilities()
        if body.takes > 1 and caps.deterministic:
            raise Unprocessable(f"{entry['name']} is deterministic: identical settings always produce "
                                "identical audio, so extra takes would be duplicates. Change the speed "
                                "or voice and generate again to get a different take.",
                                code="deterministic_engine")
        try:
            adapter.validate_request(SynthesisRequest(
                text=params["text"], language=params["language"], voice=params["voice"],
                reference_audio=None if not params["voice_profile_id"] else _placeholder(),
                speed=params["speed"]))
        except EngineError as e:
            skipped.append({"segment_id": seg_id, "reason": e.message, "code": e.code})
            continue
        dedupe = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
        existing = db.scalar(select(GenerationJob).where(
            GenerationJob.segment_id == s.id, GenerationJob.status.in_(queue.ACTIVE),
            GenerationJob.input_revision == s.text_revision,
            GenerationJob.params["dedupe"].as_string() == dedupe))
        if existing and body.takes == 1:
            jobs.append({"job_id": existing.id, "segment_id": s.id, "deduplicated": True})
            continue
        for i in range(body.takes):
            key = f"{body.idempotency_key}:{s.id}:{i}" if body.idempotency_key else None
            job, created = queue.enqueue(
                db, type="tts", params={**params, "take_index": i, "dedupe": dedupe}, project_id=p.id,
                segment_id=s.id, input_revision=s.text_revision, idempotency_key=key)
            jobs.append({"job_id": job.id, "segment_id": s.id, "deduplicated": not created})
        _ = idx
    return {"jobs": jobs, "skipped": skipped}


def _placeholder() -> Any:
    import numpy as np

    return np.zeros(1, dtype="float32")
