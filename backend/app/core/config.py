"""Application configuration.

Values come from environment variables prefixed with ``HVS_`` (see ``.env.example``).
Runtime data (database, audio, models) lives in a platform-appropriate per-user
data directory, never the installation directory.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.branding import APP_SLUG


def default_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / APP_SLUG
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_SLUG
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_SLUG


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HVS_", env_file=None, extra="ignore")

    data_dir: Path = Field(default_factory=default_data_dir)
    host: str = "127.0.0.1"
    port: int = 8765
    # Per-session access token. Generated at startup unless supplied by a launcher.
    token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    # Extra allowed browser origins (e.g. the Vite dev server). Comma separated.
    dev_origins: str = ""
    # Start the inference worker subprocess with the API (disable in some tests).
    start_worker: bool = True
    # Serve the built frontend from this directory if present.
    frontend_dist: Path | None = None

    # Limits
    max_upload_bytes: int = 50 * 1024 * 1024
    max_reference_seconds: float = 300.0
    max_transcription_seconds: float = 3 * 3600.0
    max_queued_jobs: int = 500
    max_segment_chars: int = 2000

    # Job system
    lease_seconds: float = 30.0
    heartbeat_seconds: float = 5.0
    max_auto_retries: int = 1
    ffmpeg_timeout_seconds: float = 600.0
    inference_threads: int = Field(default_factory=lambda: max(1, min(4, (os.cpu_count() or 2))))

    # Privacy
    log_content: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "studio.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.models_dir, self.media_dir, self.exports_dir,
                  self.tmp_dir, self.logs_dir):
            p.mkdir(parents=True, exist_ok=True)

    def allowed_origins(self) -> list[str]:
        origins = {f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"}
        for o in self.dev_origins.split(","):
            if o.strip():
                origins.add(o.strip().rstrip("/"))
        return sorted(origins)

    def allowed_hosts(self) -> list[str]:
        return ["127.0.0.1", "localhost", f"127.0.0.1:{self.port}", f"localhost:{self.port}",
                "testserver"]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(s: Settings) -> None:
    """Used by tests and the launcher to inject configuration."""
    global _settings
    _settings = s
    from app.db import session as db_session

    db_session.reset_engine()
