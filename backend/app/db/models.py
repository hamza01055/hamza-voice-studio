"""SQLAlchemy ORM models. Schema changes must go through Alembic migrations
(app/db/migrations/versions)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    default_language: Mapped[str] = mapped_column(String(16), default="en-us")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Chapter.position")


class Chapter(Base):
    __tablename__ = "chapters"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(200), default="Chapter 1")
    # The user's original script for this chapter, preserved verbatim.
    script_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="chapters")
    segments: Mapped[list[ScriptSegment]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan", order_by="ScriptSegment.position",
        foreign_keys="ScriptSegment.chapter_id")


class ScriptSegment(Base):
    __tablename__ = "script_segments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    original_text: Mapped[str] = mapped_column(Text, default="")
    normalized_text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text_revision: Mapped[int] = mapped_column(Integer, default=1)
    voice_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("voice_profiles.id", ondelete="SET NULL"), nullable=True)
    # Engine-provided preset voice, e.g. "af_heart" for Kokoro.
    preset_voice: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    pause_after_ms: Mapped[int] = mapped_column(Integer, default=400)
    selected_take_id: Mapped[str | None] = mapped_column(
        ForeignKey("generation_takes.id", ondelete="SET NULL", use_alter=True,
                   name="fk_segment_selected_take"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    chapter: Mapped[Chapter] = relationship(back_populates="segments", foreign_keys=[chapter_id])
    takes: Mapped[list[GenerationTake]] = relationship(
        back_populates="segment", cascade="all, delete-orphan",
        foreign_keys="GenerationTake.segment_id", order_by="GenerationTake.created_at")


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    permission_basis: Mapped[str] = mapped_column(String(40))
    statement: Mapped[str] = mapped_column(Text)
    document_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AudioAsset(Base):
    __tablename__ = "audio_assets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    managed_storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    kind: Mapped[str] = mapped_column(String(20))  # reference | take | upload | export
    media_type: Mapped[str] = mapped_column(String(50))
    sample_rate: Mapped[int] = mapped_column(Integer)
    channel_count: Mapped[int] = mapped_column(Integer)
    duration: Mapped[float] = mapped_column(Float)
    byte_size: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    compatible_engine: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_asset_id: Mapped[str] = mapped_column(ForeignKey("audio_assets.id", ondelete="RESTRICT"))
    reference_transcript: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(16), default="en-us")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    analysis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    consent_record_id: Mapped[str] = mapped_column(ForeignKey("consent_records.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    consent: Mapped[ConsentRecord] = relationship()
    reference_asset: Mapped[AudioAsset] = relationship()


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String(30))  # tts | transcribe | export | model_download
    lane: Mapped[str] = mapped_column(String(20), default="inference")  # inference | io
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    segment_id: Mapped[str | None] = mapped_column(
        ForeignKey("script_segments.id", ondelete="SET NULL"), nullable=True, index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    progress_stage: Mapped[str] = mapped_column(String(200), default="Waiting in queue")
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    output_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="SET NULL"), nullable=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, index=True)

    __table_args__ = (Index("ix_jobs_claim", "lane", "status", "created_at"),)


class GenerationTake(Base):
    __tablename__ = "generation_takes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    segment_id: Mapped[str] = mapped_column(
        ForeignKey("script_segments.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True)
    input_revision: Mapped[int] = mapped_column(Integer)
    input_text: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(String(100))
    model_revision: Mapped[str] = mapped_column(String(200))
    voice_label: Mapped[str] = mapped_column(String(200))
    generation_parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    quality: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_asset_id: Mapped[str] = mapped_column(ForeignKey("audio_assets.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    segment: Mapped[ScriptSegment] = relationship(back_populates="takes", foreign_keys=[segment_id])
    output_asset: Mapped[AudioAsset] = relationship()


class ModelInstallation(Base):
    __tablename__ = "model_installations"
    model_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    revision: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(500))
    install_location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    download_status: Mapped[str] = mapped_column(String(20), default="not_installed")
    integrity_status: Mapped[str] = mapped_column(String(20), default="unverified")
    license_record: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    bytes_downloaded: Mapped[int] = mapped_column(Integer, default=0)
    bytes_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Export(Base):
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    chapter_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(10))
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Transcription(Base):
    __tablename__ = "transcriptions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    source_asset_id: Mapped[str] = mapped_column(ForeignKey("audio_assets.id", ondelete="RESTRICT"))
    model_id: Mapped[str] = mapped_column(String(100))
    language_requested: Mapped[str | None] = mapped_column(String(16), nullable=True)
    language_detected: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    timestamp_kind: Mapped[str] = mapped_column(String(20), default="none")
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class WorkerLease(Base):
    """Single-owner lock so only one scheduler/worker claims jobs at a time."""

    __tablename__ = "worker_leases"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner: Mapped[str] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
