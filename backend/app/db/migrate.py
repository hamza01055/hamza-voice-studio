"""Programmatic migration entry point used at application startup."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def alembic_config(db_url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["db_url"] = db_url or get_settings().db_url
    return cfg


def upgrade_to_head(db_url: str | None = None) -> None:
    get_settings().ensure_dirs()
    command.upgrade(alembic_config(db_url), "head")
