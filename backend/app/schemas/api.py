"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_serializer

T = TypeVar("T")


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def _dt(self, v: Any) -> Any:
        if isinstance(v, datetime):
            return v.isoformat() + "Z"
        return v


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorOut(BaseModel):
    error: dict[str, Any]


# ---------------- projects ----------------
class PronunciationOverride(BaseModel):
    pattern: str = Field(min_length=1, max_length=100)
    replacement: str = Field(max_length=200)
    language: str | None = Field(None, max_length=16)
    whole_word: bool = True
    case_sensitive: bool = False


class ProjectSettings(BaseModel):
    model_id: str | None = None
    voice: str | None = None
    voice_profile_id: str | None = None
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pause_ms: int = Field(400, ge=0, le=10000)
    segmentation_mode: Literal["paragraph", "sentence"] = "paragraph"
    pronunciations: list[PronunciationOverride] = Field(default_factory=list, max_length=500)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    default_language: str = Field("en-us", max_length=16)
    settings: ProjectSettings | None = None
    script: str | None = Field(None, max_length=2_000_000)


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    default_language: str | None = Field(None, max_length=16)
    settings: ProjectSettings | None = None


class TakeOut(Out):
    id: str
    segment_id: str
    job_id: str | None
    input_revision: int
    input_text: str
    model_id: str
    model_revision: str
    voice_label: str
    generation_parameters: dict[str, Any]
    quality: dict[str, Any]
    output_asset_id: str
    created_at: datetime
    duration: float | None = None
    stale: bool = False


class SegmentOut(Out):
    id: str
    project_id: str
    chapter_id: str
    position: int
    original_text: str
    normalized_text: str
    language: str | None
    text_revision: int
    voice_profile_id: str | None
    preset_voice: str | None
    model_id: str | None
    speed: float | None
    pause_after_ms: int
    selected_take_id: str | None
    updated_at: datetime
    take_count: int = 0
    selected_take_stale: bool = False
    selected_take_duration: float | None = None
    active_job_id: str | None = None
    active_job_status: str | None = None


class ChapterOut(Out):
    id: str
    position: int
    title: str
    script_text: str
    segments: list[SegmentOut] = []


class ProjectSummary(Out):
    id: str
    name: str
    default_language: str
    created_at: datetime
    updated_at: datetime
    segment_count: int = 0
    generated_count: int = 0


class ProjectOut(Out):
    id: str
    name: str
    default_language: str
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    chapters: list[ChapterOut] = []


class ChapterCreate(BaseModel):
    title: str = Field("New chapter", min_length=1, max_length=200)
    script: str | None = Field(None, max_length=2_000_000)


class ChapterPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    position: int | None = Field(None, ge=0)


class SegmentsCreate(BaseModel):
    """Create segments by segmenting a script (append or replace chapter contents)."""
    chapter_id: str | None = None
    script: str = Field(max_length=2_000_000)
    mode: Literal["paragraph", "sentence"] = "paragraph"
    replace: bool = False
    insert_at: int | None = Field(None, ge=0)


class SegmentPatch(BaseModel):
    original_text: str | None = Field(None, max_length=20000)
    language: str | None = Field(None, max_length=16)
    preset_voice: str | None = Field(None, max_length=64)
    voice_profile_id: str | None = None
    model_id: str | None = Field(None, max_length=100)
    speed: float | None = Field(None, ge=0.5, le=2.0)
    pause_after_ms: int | None = Field(None, ge=0, le=20000)
    position: int | None = Field(None, ge=0)
    chapter_id: str | None = None
    clear_voice: bool = False


class SegmentSplit(BaseModel):
    at: int = Field(ge=1)


class SelectTake(BaseModel):
    take_id: str | None


# ---------------- generation / jobs ----------------
class GenerationRequest(BaseModel):
    segment_ids: list[str] = Field(min_length=1, max_length=2000)
    takes: int = Field(1, ge=1, le=5)
    only_missing: bool = False
    idempotency_key: str | None = Field(None, max_length=120)


class GenerationResponse(BaseModel):
    jobs: list[dict[str, Any]]
    skipped: list[dict[str, Any]] = []


class JobOut(Out):
    id: str
    type: str
    lane: str
    status: str
    project_id: str | None
    segment_id: str | None
    params: dict[str, Any]
    input_revision: int | None
    progress: float | None
    progress_stage: str
    error_code: str | None
    error_message: str | None
    retryable: bool
    retry_count: int
    cancel_requested: bool
    worker_id: str | None
    output_asset_id: str | None
    result: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


# ---------------- exports ----------------
class ExportCreate(BaseModel):
    format: Literal["wav", "mp3"] = "mp3"
    file_name: str | None = Field(None, max_length=150)
    chapter_id: str | None = None
    segment_ids: list[str] | None = None
    bitrate_kbps: Literal[96, 128, 160, 192, 256, 320] = 192
    sample_rate: Literal[16000, 22050, 24000, 44100, 48000] | None = None
    loudnorm: bool = False
    skip_missing: bool = False
    chapter_gap_ms: int = Field(1500, ge=0, le=20000)


class ExportOut(Out):
    id: str
    project_id: str | None
    chapter_id: str | None
    job_id: str | None
    file_name: str
    format: str
    options: dict[str, Any]
    status: str
    byte_size: int | None
    duration: float | None
    sample_rate: int | None
    details: dict[str, Any]
    created_at: datetime


# ---------------- voices ----------------
PermissionBasis = Literal["my_own_voice", "written_permission", "licensed_voice", "public_domain"]


class VoiceOut(Out):
    id: str
    name: str
    compatible_engine: str | None
    compatible_engine_installed: bool = False
    reference_asset_id: str
    reference_transcript: str
    language: str
    tags: list[str]
    analysis: dict[str, Any]
    consent: dict[str, Any]
    duration: float | None = None
    created_at: datetime
    updated_at: datetime


class VoicePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    reference_transcript: str | None = Field(None, max_length=5000)
    language: str | None = Field(None, max_length=16)
    tags: list[str] | None = Field(None, max_length=20)
    trim_start: float | None = Field(None, ge=0)
    trim_end: float | None = Field(None, ge=0)
    revoke_consent: bool = False


# ---------------- misc ----------------
class NormalizePreview(BaseModel):
    text: str = Field(max_length=20000)
    language: str = "en-us"
    project_id: str | None = None


class TransliteratePreview(BaseModel):
    text: str = Field(max_length=20000)
    convert_ambiguous: bool = False


class TranscriptionOut(Out):
    id: str
    name: str
    source_asset_id: str
    model_id: str
    language_requested: str | None
    language_detected: str | None
    text: str
    edited_text: str | None
    segments: list[dict[str, Any]]
    timestamp_kind: str
    job_id: str | None
    created_at: datetime
    updated_at: datetime


class TranscriptionPatch(BaseModel):
    edited_text: str | None = Field(None, max_length=2_000_000)
    name: str | None = Field(None, min_length=1, max_length=200)
