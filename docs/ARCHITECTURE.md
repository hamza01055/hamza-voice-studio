# Architecture

```
┌──────────────────────────┐        ┌──────────────────────────────────────────────┐
│ UI (React + TypeScript)  │  HTTP  │ API process (FastAPI, uvicorn, 127.0.0.1)     │
│ browser tab or Electron  │ ─────▶ │  • routes → domain services → SQLite (WAL)    │
│ renderer (no Node)       │ ◀───── │  • SSE: job updates (/api/events)             │
└──────────────────────────┘  SSE   │  • never runs inference in a request         │
                                    │  • WorkerSupervisor: spawns/restarts worker   │
                                    └───────────────┬──────────────────────────────┘
                                                    │ subprocess (same venv)
                                    ┌───────────────▼──────────────────────────────┐
                                    │ Worker process (app.jobs.worker)              │
                                    │  • single scheduler lease (worker_leases row) │
                                    │  • lanes: inference (1 job), io (1 job)       │
                                    │  • atomic claim, heartbeats, leases           │
                                    │  • EngineManager: ≤1 model loaded             │
                                    │  • adapters: Kokoro (sherpa-onnx), Whisper    │
                                    └──────────────────────────────────────────────┘
```

## Code layout

| Path | Responsibility |
|---|---|
| `backend/app/api/` | HTTP routes only (validation, status codes). |
| `backend/app/core/` | Config (per-user data dir), structured errors, logging, local access middleware. |
| `backend/app/db/` | SQLAlchemy models, session (SQLite WAL, FK on), Alembic migrations. |
| `backend/app/schemas/` | Pydantic request/response models. |
| `backend/app/services/` | Domain logic: projects/segments, voices, models manager, normalisation, segmentation, Roman-Urdu helper, settings, hardware. |
| `backend/app/engines/` | Adapter interface (`base.py`), registry (`registry.json`), Kokoro and Whisper adapters. |
| `backend/app/jobs/` | Durable queue, worker, handlers, supervisor, engine manager. |
| `backend/app/audio/` | FFmpeg wrappers (argument arrays + timeouts), signal analysis, assembly. |
| `backend/app/storage/` | Managed asset storage (IDs → server-controlled paths, atomic finalise, reference-counted deletion). |
| `frontend/src/` | Studio UI. `lib/` API client, SSE, queries; `pages/` workspaces. |
| `desktop/` | Electron shell (backend lifecycle, secure preload). |
| `scripts/` | Setup/start scripts, benchmark and evaluation harnesses. |

## Key design decisions

- **Engine adapters** expose `capabilities()`, `validate_request()`, `load()`, `unload()`,
  `synthesize()` / `transcribe()`, `estimate_resources()`. Capabilities (languages, voices,
  speed range, cancellation granularity, progress type, take variation…) drive the UI; no
  control is shown that the engine does not implement.
- **One runtime for now.** Kokoro and Whisper both run through `sherpa-onnx` (ONNX Runtime),
  so there are no conflicting ML stacks. A PyTorch engine (e.g. Chatterbox) must run in a
  separate worker environment; the job system already isolates inference in a subprocess.
- **Durable jobs.** Every generation/export/transcription/install is a row with status,
  stage, progress, error code/message, retry count, worker id, lease and output reference.
  Claiming is one atomic `UPDATE … WHERE status='queued' … RETURNING`. Leases are renewed every
  5 s; expired leases are recovered (auto re-queue once, then `interrupted`). At API startup all
  running jobs are recovered because no worker can own them yet.
- **Cancellation is honest.** Queued jobs cancel immediately. Running jobs move to
  `cancelling`; the worker polls the flag every 0.5 s and the Kokoro callback stops after the
  current sentence. A take is never saved for a cancelled job.
- **Progress is real.** Kokoro reports per-sentence fractions; downloads report bytes;
  exports report assembled pieces. Model loading, verification and extraction are shown as
  indeterminate stages.
- **Outputs are atomic.** Audio is written to `tmp/`, validated (decode + signal checks),
  moved into `media/` with `os.replace`, and the take row is committed in the same
  transaction that completes the job. Files are deleted only after the DB commit.
- **Text versions.** `original_text` is never modified by the system; `normalized_text` is
  derived. `text_revision` increments whenever the spoken text changes; takes store the
  revision and exact input text, so stale takes are flagged and an old job can't overwrite
  newer text or auto-select an outdated take.
- **Long-form assembly** concatenates selected takes in chapter/segment order with explicit
  silence (per-segment pause, chapter gap). 5 ms edge fades prevent clicks; takes never
  overlap. Loudness normalisation (EBU R128) is an explicit export option.
- **Native sample rate** (24 kHz for Kokoro) is preserved; resampling only happens when takes
  from different engines are mixed or the user picks an export rate.

## Data locations

Default data dir: `%LOCALAPPDATA%\HamzaVoiceStudio` (Windows),
`~/.local/share/HamzaVoiceStudio` (Linux), `~/Library/Application Support/HamzaVoiceStudio`
(macOS). Override with `HVS_DATA_DIR`; models with `HVS_MODELS_DIR`.

```
studio.db (+ -wal/-shm)   SQLite database
media/take|reference|upload/…   managed audio (IDs only)
exports/                  finished exports (never overwritten)
models/<model-id>/        installed models + .hvs-install.json manifest
models/.partial/          resumable downloads
tmp/                      scratch (cleared at startup)
logs/api.log, worker.log  rotating logs (no script text)
```

## Hosted edition (future, not built)

The local edition deliberately avoids Redis/Postgres/Docker. A hosted edition would need:
authentication, tenant isolation and roles; PostgreSQL; object storage with signed URLs; a
distributed queue and GPU worker scheduling; metering, quotas and billing; rate limits;
consent verification and abuse handling; retention controls; backups; monitoring. The
service/adapter boundaries (services don't know about HTTP; workers talk to the DB and
storage through narrow modules) are where those replacements would plug in.
