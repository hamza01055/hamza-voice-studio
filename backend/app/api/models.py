from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.models import GenerationJob
from app.db.session import get_db
from app.engines import registry
from app.jobs import queue
from app.schemas.api import JobOut
from app.services import models_service, settings_service

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models(db: Session = Depends(get_db)) -> dict[str, Any]:
    inc = settings_service.get_all(db).show_unevaluated_languages
    items = [models_service.model_status(db, m, inc) for m in registry.all_models()]
    return {"items": items, "free_disk_bytes": models_service.free_disk_bytes(),
            "registry_reviewed_at": registry.load_registry().get("reviewed_at")}


@router.get("/models/{model_id}")
def get_model(model_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    inc = settings_service.get_all(db).show_unevaluated_languages
    return models_service.model_status(db, registry.get_model(model_id), inc)


@router.post("/models/{model_id}/download", status_code=202)
def download_model(model_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = models_service.start_download(db, model_id)
    return {"download_id": job.id, "job": JobOut.model_validate(job).model_dump(mode="json")}


def _download_job(db: Session, download_id: str) -> GenerationJob:
    j = db.get(GenerationJob, download_id)
    if not j or j.type != "model_download":
        raise NotFound("Download not found.")
    return j


@router.get("/model-downloads/{download_id}")
def get_download(download_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    j = _download_job(db, download_id)
    return {"job": JobOut.model_validate(j).model_dump(mode="json"),
            "model": models_service.model_status(db, registry.get_model(j.params["model_id"]))}


@router.post("/model-downloads/{download_id}/cancel")
def cancel_download(download_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    j = queue.request_cancel(db, _download_job(db, download_id))
    if j.status == "cancelled":
        inst = db.get(models_service.ModelInstallation, j.params["model_id"])
        if inst and inst.download_status in ("pending", "downloading"):
            inst.download_status = "not_installed"
    return {"job": JobOut.model_validate(j).model_dump(mode="json")}


@router.delete("/models/{model_id}/installation")
def delete_installation(model_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    models_service.remove_installation(db, model_id)
    return {"model_id": model_id, "status": "not_installed"}
