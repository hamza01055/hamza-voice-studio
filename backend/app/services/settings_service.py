from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import AppSetting


class AppSettings(BaseModel):
    theme: Literal["system", "light", "dark"] = "system"
    default_model_id: str = "kokoro-multi-lang-v1_0"
    default_voice: str = "af_heart"
    default_language: str = "en-us"
    default_pause_ms: int = Field(400, ge=0, le=10000)
    segmentation_mode: Literal["paragraph", "sentence"] = "paragraph"
    chapter_gap_ms: int = Field(1500, ge=0, le=20000)
    show_unevaluated_languages: bool = False
    export_format: Literal["wav", "mp3"] = "mp3"
    mp3_bitrate_kbps: Literal[96, 128, 160, 192, 256, 320] = 192
    export_loudnorm: bool = False
    idle_unload_minutes: int = Field(10, ge=0, le=1440)
    # There is no analytics or telemetry code in this application. The flag exists so
    # the UI can state that explicitly; it cannot be enabled.
    analytics_enabled: Literal[False] = False
    log_content: bool = False


class AppSettingsPatch(BaseModel):
    theme: Literal["system", "light", "dark"] | None = None
    default_model_id: str | None = None
    default_voice: str | None = None
    default_language: str | None = None
    default_pause_ms: int | None = Field(None, ge=0, le=10000)
    segmentation_mode: Literal["paragraph", "sentence"] | None = None
    chapter_gap_ms: int | None = Field(None, ge=0, le=20000)
    show_unevaluated_languages: bool | None = None
    export_format: Literal["wav", "mp3"] | None = None
    mp3_bitrate_kbps: Literal[96, 128, 160, 192, 256, 320] | None = None
    export_loudnorm: bool | None = None
    idle_unload_minutes: int | None = Field(None, ge=0, le=1440)
    log_content: bool | None = None


def get_all(db: Session) -> AppSettings:
    stored = {r.key: r.value for r in db.query(AppSetting).all()}
    data: dict[str, Any] = AppSettings().model_dump()
    for k, v in stored.items():
        if k in data:
            data[k] = v
    try:
        return AppSettings(**data)
    except Exception:  # noqa: BLE001 - corrupt value: fall back to defaults for safety
        return AppSettings()


def update(db: Session, patch: AppSettingsPatch) -> AppSettings:
    for k, v in patch.model_dump(exclude_unset=True).items():
        if v is None:
            continue
        row = db.get(AppSetting, k)
        if row:
            row.value = v
        else:
            db.add(AppSetting(key=k, value=v))
    db.flush()
    return get_all(db)
