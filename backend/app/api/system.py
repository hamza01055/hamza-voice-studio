from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.branding import APP_NAME, APP_VERSION
from app.db.session import get_db
from app.schemas import api as S
from app.services import hardware, models_service, settings_service
from app.services.normalize import normalize
from app.services.projects import get_project, project_settings
from app.services.roman_urdu import transliterate

router = APIRouter(tags=["system"])


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    sup = getattr(request.app.state, "supervisor", None)
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION,
            "worker": sup.status() if sup else {"state": "external_or_disabled"}}


@router.get("/system/capabilities")
def system_capabilities(db: Session = Depends(get_db)) -> dict[str, Any]:
    caps = hardware.capabilities()
    caps["installed_models"] = models_service.installed_models(db)
    caps["network_use"] = ("Network is used only when you start a model download from the Models page. "
                           "Generation, transcription and export run locally.")
    return caps


@router.get("/settings", response_model=settings_service.AppSettings)
def get_settings_route(db: Session = Depends(get_db)) -> settings_service.AppSettings:
    return settings_service.get_all(db)


@router.patch("/settings", response_model=settings_service.AppSettings)
def patch_settings(body: settings_service.AppSettingsPatch,
                   db: Session = Depends(get_db)) -> settings_service.AppSettings:
    return settings_service.update(db, body)


@router.post("/text/normalize")
def normalize_preview(body: S.NormalizePreview, db: Session = Depends(get_db)) -> dict[str, Any]:
    overrides: list[dict[str, Any]] = []
    if body.project_id:
        overrides = [o.model_dump() for o in project_settings(get_project(db, body.project_id)).pronunciations]
    return normalize(body.text, body.language, overrides).to_dict()


@router.post("/text/transliterate")
def transliterate_preview(body: S.TransliteratePreview) -> dict[str, Any]:
    return transliterate(body.text, body.convert_ambiguous).to_dict()
