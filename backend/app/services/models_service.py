"""Model installation management: status, download, verify, atomic install, removal."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import tarfile
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, Conflict
from app.db.models import GenerationJob, ModelInstallation, utcnow
from app.engines import registry
from app.engines.base import EngineError, GenerationCancelled
from app.jobs import queue

CHUNK = 1 << 20


def _installation(db: Session, model_id: str) -> ModelInstallation | None:
    return db.get(ModelInstallation, model_id)


def free_disk_bytes() -> int:
    d = get_settings().models_dir
    d.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(d).free


def is_installed(db: Session, model_id: str) -> bool:
    inst = _installation(db, model_id)
    if not inst or inst.download_status != "installed":
        return False
    return registry.files_present(registry.get_model(model_id), registry.model_dir(model_id))


def installed_models(db: Session, kind: str | None = None) -> list[str]:
    out = []
    for m in registry.all_models():
        if kind and m["kind"] != kind:
            continue
        if m.get("adapter") and is_installed(db, m["id"]):
            out.append(m["id"])
    return out


def model_status(db: Session, entry: dict[str, Any], include_unevaluated: bool = False) -> dict[str, Any]:
    inst = _installation(db, entry["id"])
    download_size = sum(a.get("size_bytes") or 0 for a in entry.get("artifacts", []))
    status = "not_installed"
    if inst:
        status = inst.download_status
        if status == "installed" and not registry.files_present(entry, registry.model_dir(entry["id"])):
            status = "damaged"
    if not entry.get("adapter"):
        status = "not_integrated"
    caps = None
    if entry.get("adapter"):
        try:
            caps = registry.create_adapter(entry["id"], {"include_unevaluated": include_unevaluated}) \
                .capabilities().to_dict()
        except Exception:  # noqa: BLE001
            caps = None
    active_job = None
    if inst and inst.job_id:
        j = db.get(GenerationJob, inst.job_id)
        if j and j.status in queue.ACTIVE:
            active_job = j.id
    return {
        "id": entry["id"], "name": entry["name"], "kind": entry["kind"],
        "integration": entry.get("integration"), "verification": entry.get("verification"),
        "runtime": entry.get("runtime"), "upstream": entry.get("upstream"),
        "revision": entry.get("revision"), "license": entry.get("license"),
        "languages": entry.get("languages"), "download_size_bytes": download_size or None,
        "installed_size_bytes": entry.get("installed_size_bytes"),
        "reference_audio": entry.get("reference_audio"),
        "status": status,
        "integrity_status": inst.integrity_status if inst else None,
        "bytes_downloaded": inst.bytes_downloaded if inst else 0,
        "bytes_total": inst.bytes_total if inst else None,
        "error_message": inst.error_message if inst else None,
        "installed_at": inst.installed_at.isoformat() + "Z" if inst and inst.installed_at else None,
        "active_job_id": active_job,
        "capabilities": caps,
        "artifact_urls": [a["url"] for a in entry.get("artifacts", [])],
    }


def start_download(db: Session, model_id: str) -> GenerationJob:
    entry = registry.get_model(model_id)
    if not entry.get("adapter") or not entry.get("artifacts"):
        raise Conflict("This model is not integrated and cannot be installed.", code="not_integrated")
    inst = _installation(db, model_id)
    if inst and inst.job_id:
        j = db.get(GenerationJob, inst.job_id)
        if j and j.status in queue.ACTIVE:
            return j  # duplicate-download protection
    if inst and inst.download_status == "installed" and is_installed(db, model_id):
        raise Conflict("The model is already installed.", code="already_installed")
    need = sum(a.get("size_bytes") or 0 for a in entry["artifacts"]) + (entry.get("installed_size_bytes") or 0)
    free = free_disk_bytes()
    if free < need * 1.1:
        raise AppError(f"Not enough free disk space: about {need / 1e6:.0f} MB is needed and "
                       f"{free / 1e6:.0f} MB is free.", code="insufficient_disk", status_code=507)
    job, _ = queue.enqueue(db, type="model_download", params={"model_id": model_id},
                           stage="Waiting to download")
    if not inst:
        inst = ModelInstallation(model_id=model_id, revision=entry["revision"],
                                 source=entry["artifacts"][0]["url"])
        db.add(inst)
    inst.revision = entry["revision"]
    inst.download_status = "pending"
    inst.error_message = None
    inst.job_id = job.id
    inst.license_record = entry.get("license", {})
    db.flush()
    return job


def remove_installation(db: Session, model_id: str) -> None:
    registry.get_model(model_id)
    active = db.scalar(select(GenerationJob.id).where(
        GenerationJob.status.in_(queue.ACTIVE),
        (GenerationJob.params["model_id"].as_string() == model_id)).limit(1))
    if active:
        raise Conflict("The model is in use by a queued or running job. Cancel it first.",
                       code="model_in_use")
    d = registry.model_dir(model_id)
    if d.exists():
        trash = d.with_name(f".trash-{model_id}-{uuid.uuid4().hex[:8]}")
        os.replace(d, trash)
        shutil.rmtree(trash, ignore_errors=True)
    inst = _installation(db, model_id)
    if inst:
        inst.download_status = "not_installed"
        inst.integrity_status = "unverified"
        inst.install_location = None
        inst.installed_at = None
        inst.bytes_downloaded = 0
    db.flush()


def cleanup_partials() -> None:
    """Remove staging/trash leftovers from interrupted installs (partial downloads are
    kept for resumption)."""
    base = get_settings().models_dir
    if not base.exists():
        return
    for p in base.iterdir():
        if p.name.startswith((".staging-", ".trash-")):
            shutil.rmtree(p, ignore_errors=True)


# ---------------------------------------------------------------------------
# Worker-side download (runs in the io lane)
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path, expected_size: int | None,
              progress: Callable[[int, int | None], None], should_cancel: Callable[[], bool]) -> None:
    existing = dest.stat().st_size if dest.exists() else 0
    if expected_size and existing > expected_size:
        dest.unlink()
        existing = 0
    if expected_size and existing == expected_size:
        progress(existing, expected_size)
        return
    parsed = urllib.parse.urlparse(url)
    if not (parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost"))):
        raise EngineError("Refusing to download from a non-HTTPS URL.", code="insecure_url")
    req = urllib.request.Request(url, headers={"User-Agent": "HamzaVoiceStudio-model-manager"})  # noqa: S310
    if existing:
        req.add_header("Range", f"bytes={existing}-")
    try:
        resp = urllib.request.urlopen(req, timeout=60)  # noqa: S310 - scheme checked above
    except (OSError, http.client.HTTPException) as e:
        raise EngineError("The download could not start. Check the internet connection and try again.",
                          code="download_failed", retryable=True) from e
    with resp:
        status = getattr(resp, "status", 200)
        mode = "ab" if (existing and status == 206) else "wb"
        done = existing if mode == "ab" else 0
        total = expected_size or (int(resp.headers.get("Content-Length", 0)) + done) or None
        with dest.open(mode) as f:
            while True:
                if should_cancel():
                    raise GenerationCancelled("Download cancelled.")
                try:
                    chunk = resp.read(CHUNK)
                except (OSError, http.client.HTTPException) as e:
                    raise EngineError("The download was interrupted. Retry to resume it.",
                                      code="download_failed", retryable=True) from e
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                progress(done, total)
    if expected_size and dest.stat().st_size != expected_size:
        raise EngineError("The download was incomplete. Retry to resume it.", code="download_incomplete",
                          retryable=True)


def _sha256(path: Path, should_cancel: Callable[[], bool]) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            if should_cancel():
                raise GenerationCancelled("Cancelled during verification.")
            h.update(chunk)
    return h.hexdigest()


def _extract(archive: Path, staging: Path, strip_prefix: str) -> None:
    with tarfile.open(archive, "r:*") as tf:
        members = []
        for m in tf.getmembers():
            if strip_prefix:
                if not m.name.startswith(strip_prefix):
                    continue
                m.name = m.name[len(strip_prefix):]
            if not m.name:
                continue
            members.append(m)
        # filter='data' rejects absolute paths, '..', device files and unsafe links.
        tf.extractall(staging, members=members, filter="data")


def run_download(db_factory: Callable[[], Session], model_id: str,
                 progress: Callable[[float | None, str], None], should_cancel: Callable[[], bool]) -> dict[str, Any]:
    entry = registry.get_model(model_id)
    settings = get_settings()
    base = settings.models_dir
    partial_dir = base / ".partial"
    partial_dir.mkdir(parents=True, exist_ok=True)
    final = registry.model_dir(model_id)
    staging = base / f".staging-{model_id}-{uuid.uuid4().hex[:8]}"

    def set_inst(**kw: Any) -> None:
        with db_factory() as db:
            inst = db.get(ModelInstallation, model_id)
            if inst:
                for k, v in kw.items():
                    setattr(inst, k, v)
                db.commit()

    set_inst(download_status="downloading", error_message=None)
    checksums: dict[str, str] = {}
    try:
        staging.mkdir(parents=True)
        for art in entry["artifacts"]:
            fname = art["url"].rsplit("/", 1)[-1]
            dest = partial_dir / fname
            last = [0.0]

            def on_bytes(done: int, total: int | None, fname: str = fname, last: list[float] = last) -> None:
                frac = (done / total) if total else None
                if frac is None or frac - last[0] >= 0.005 or frac >= 1:
                    last[0] = frac or 0
                    progress(frac, f"Downloading {fname} ({done / 1e6:.0f} MB"
                                   + (f" of {total / 1e6:.0f} MB)" if total else ")"))
                    set_inst(bytes_downloaded=done, bytes_total=total)

            _download(art["url"], dest, art.get("size_bytes"), on_bytes, should_cancel)
            set_inst(download_status="verifying")
            progress(None, "Verifying checksum")
            digest = _sha256(dest, should_cancel)
            checksums[fname] = digest
            if art.get("sha256") and digest != art["sha256"]:
                dest.unlink(missing_ok=True)
                raise EngineError("The downloaded file failed its integrity check and was deleted. "
                                  "Retry the download.", code="checksum_mismatch", retryable=True)
            progress(None, "Extracting")
            if art["type"] in ("tar.bz2", "tar.gz", "tar"):
                _extract(dest, staging, art.get("strip_prefix", ""))
            else:
                shutil.copy2(dest, staging / fname)
        if not registry.files_present(entry, staging):
            raise EngineError("The archive did not contain the expected model files.",
                              code="install_incomplete")
        if should_cancel():
            raise GenerationCancelled("Cancelled.")
        progress(None, "Installing")
        if final.exists():
            trash = base / f".trash-{model_id}-{uuid.uuid4().hex[:8]}"
            os.replace(final, trash)
            shutil.rmtree(trash, ignore_errors=True)
        os.replace(staging, final)  # atomic on the same filesystem
        pinned = all(a.get("sha256") for a in entry["artifacts"])
        (final / ".hvs-install.json").write_text(
            json.dumps({"model_id": model_id, "revision": entry["revision"],
                                      "sha256": checksums, "pinned": pinned,
                                      "installed_at": utcnow().isoformat() + "Z"}, indent=2))
        for art in entry["artifacts"]:
            (partial_dir / art["url"].rsplit("/", 1)[-1]).unlink(missing_ok=True)
        set_inst(download_status="installed", integrity_status="verified" if pinned else "recorded_unpinned",
                 install_location=model_id, installed_at=utcnow())
        return {"model_id": model_id, "sha256": checksums, "pinned": pinned}
    except GenerationCancelled:
        set_inst(download_status="not_installed", error_message="Download cancelled. "
                 "The partial file is kept so a new download can resume.")
        raise
    except Exception as e:
        msg = e.message if isinstance(e, EngineError) else f"Installation failed ({type(e).__name__})."
        set_inst(download_status="failed", error_message=msg)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
