"""FastAPI application factory."""

from __future__ import annotations

import logging
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import assets, exports, jobs, models, projects, system, transcriptions, voices
from app.branding import APP_NAME, APP_VERSION
from app.core.config import get_settings
from app.core.errors import install_handlers
from app.core.logging import setup_logging
from app.core.security import LocalAccessMiddleware
from app.db.migrate import upgrade_to_head
from app.db.session import session_factory
from app.jobs import queue
from app.jobs.supervisor import WorkerSupervisor
from app.services import models_service

log = logging.getLogger("hvs.api")


def startup_tasks() -> None:
    s = get_settings()
    s.ensure_dirs()
    upgrade_to_head()
    # Temporary files belong to no finished record; clear them on startup.
    for p in s.tmp_dir.glob("*"):
        if p.is_file():
            p.unlink(missing_ok=True)
        else:
            shutil.rmtree(p, ignore_errors=True)
    models_service.cleanup_partials()
    with session_factory()() as db:
        recovered = queue.recover_stale(db, force_all_running=True)
        detected = models_service.sync_installations(db)
        if detected:
            log.info("Detected installed model(s) on disk: %s", ", ".join(detected))
        # Installation rows left mid-download by a crash
        from app.db.models import ModelInstallation

        for inst in db.query(ModelInstallation).filter(
                ModelInstallation.download_status.in_(["downloading", "verifying"])):
            inst.download_status = "pending"
        db.commit()
    if recovered:
        log.warning("Recovered %d job(s) interrupted by the previous shutdown", len(recovered))


def create_app(start_worker: bool | None = None) -> FastAPI:
    settings = get_settings()
    setup_logging("api")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        startup_tasks()
        sup = None
        if start_worker if start_worker is not None else settings.start_worker:
            sup = WorkerSupervisor()
            sup.start()
        app.state.supervisor = sup
        log.info("%s %s ready on http://%s:%d", APP_NAME, APP_VERSION, settings.host, settings.port)
        try:
            yield
        finally:
            if sup:
                sup.stop()

    app = FastAPI(title=f"{APP_NAME} local API", version=APP_VERSION, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None,
                  description="Local-only API. All routes except GET /api/health require the "
                              "X-HVS-Token header. See docs/API.md.")
    install_handlers(app)
    for r in (system.router, models.router, voices.router, projects.router, jobs.router, exports.router,
              assets.router, transcriptions.router):
        app.include_router(r, prefix="/api")

    dev = [o for o in settings.allowed_origins() if not o.endswith(f":{settings.port}")]
    if dev:
        app.add_middleware(CORSMiddleware, allow_origins=dev, allow_credentials=False,
                           allow_methods=["GET", "POST", "PATCH", "DELETE"],
                           allow_headers=["X-HVS-Token", "Content-Type"])
    app.add_middleware(LocalAccessMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts())

    dist = settings.frontend_dist or (Path(__file__).resolve().parents[2] / "frontend" / "dist")
    if (dist / "index.html").exists():
        index = dist / "index.html"
        dist_resolved = dist.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                from app.core.errors import NotFound

                raise NotFound("Unknown API route.")
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and candidate.is_relative_to(dist_resolved):
                return FileResponse(candidate)
            return FileResponse(index, headers={"Cache-Control": "no-store"})
    else:
        @app.get("/", include_in_schema=False)
        def no_frontend() -> HTMLResponse:
            return HTMLResponse(f"<h1>{APP_NAME}</h1><p>The frontend has not been built. Run "
                                "<code>npm run build</code> in <code>frontend/</code>, or use the Vite dev "
                                "server. API docs: <a href='/api/docs'>/api/docs</a> (token required).</p>")
    return app
