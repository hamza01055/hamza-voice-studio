from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import update

from app.db.models import GenerationJob, utcnow
from app.db.session import get_engine


@dataclass
class JobContext:
    job_id: str
    worker_id: str
    type: str
    params: dict[str, Any]
    retry_count: int
    project_id: str | None
    segment_id: str | None
    input_revision: int | None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    _last_write: float = 0.0
    _last_stage: str = ""

    def should_cancel(self) -> bool:
        return self.cancel_event.is_set()

    def progress(self, frac: float | None, stage: str, *, status: str | None = None,
                 force: bool = False) -> None:
        """Persist real progress. ``frac=None`` means indeterminate."""
        now = time.monotonic()
        if not force and stage == self._last_stage and now - self._last_write < 0.25 and status is None:
            return
        self._last_write = now
        self._last_stage = stage
        values: dict[str, Any] = {"progress": None if frac is None else max(0.0, min(1.0, frac)),
                                  "progress_stage": stage[:200], "updated_at": utcnow()}
        with get_engine().begin() as conn:
            q = update(GenerationJob).where(GenerationJob.id == self.job_id,
                                            GenerationJob.worker_id == self.worker_id)
            if status:
                # never overwrite a pending cancellation with a running status
                q = q.where(GenerationJob.status != "cancelling")
                values["status"] = status
            conn.execute(q.values(**values))
