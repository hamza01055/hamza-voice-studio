# Local API

Base URL: `http://127.0.0.1:<port>/api`. Interactive OpenAPI docs: `/api/docs` (needs the
token header — use a browser extension or `curl`), schema: `/api/openapi.json`.

All routes except `GET /health` require `X-HVS-Token: <token>`. Errors always look like:

```json
{"error": {"code": "model_not_installed", "message": "…user-facing text…", "details": {}}}
```

Collections are paginated with `limit`/`offset` and return `{items, total, limit, offset}`.

## Endpoints

| Method & path | Purpose |
|---|---|
| `GET /health` | Liveness + worker state (public). |
| `GET /system/capabilities` | CPU/RAM/GPU/disk, FFmpeg, runtime versions, installed models, data dir. |
| `GET /settings`, `PATCH /settings` | App settings. |
| `POST /text/normalize` | Preview spoken text + list of changes (`{text, language, project_id?}`). |
| `POST /text/transliterate` | Roman Urdu → Urdu script preview (dictionary-based). |
| `GET /models`, `GET /models/{id}` | Registry + install status, licences, capabilities. |
| `POST /models/{id}/download` | Start an install job (202). Idempotent while running. 507 if disk is insufficient. |
| `GET /model-downloads/{id}` | Install job + model status. |
| `POST /model-downloads/{id}/cancel` | Cancel install (partial file kept for resume). |
| `DELETE /models/{id}/installation` | Remove files (409 if a job uses the model). |
| `GET/POST /voices`, `GET/PATCH/DELETE /voices/{id}` | Voice library. `POST` is multipart: `file`, `name`, `language`, `transcript`, `tags` (JSON list), `permission_basis`, `consent_confirmed`, `document_reference?`. `PATCH` supports rename, transcript, tags, trim (`trim_start`, `trim_end`), `revoke_consent`. |
| `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}` | Projects (GET returns chapters → segments). `POST` accepts an optional `script`. |
| `POST /projects/{id}/chapters`, `PATCH/DELETE /chapters/{id}` | Chapters. |
| `POST /projects/{id}/segments` | Segment a script into a chapter (`mode`: paragraph/sentence; `replace` keeps unchanged segments and their takes). |
| `PATCH /segments/{id}`, `DELETE /segments/{id}`, `POST /segments/{id}/split` | Edit text/voice/speed/pause/language/position, delete, split at a character offset. |
| `GET /segments/{id}/takes` | Takes, each with input revision, input text, parameters, quality warnings, `stale`. |
| `POST /segments/{id}/selected-take` | `{take_id}` or `{take_id: null}`. |
| `DELETE /takes/{id}` | Delete a take and its audio. |
| `POST /generations` | `{segment_ids[], takes=1..5, only_missing?, idempotency_key?}` → jobs + skipped (with reasons). 409 if the model is not installed, 429 if the queue is full. |
| `GET /jobs`, `GET /jobs/{id}` | Jobs (filter `status=a,b`, `type`, `project_id`). |
| `GET /jobs/{id}/events`, `GET /events` | Server-sent events (`event: job`). |
| `POST /jobs/{id}/cancel`, `POST /jobs/{id}/retry`, `POST /jobs/cancel-all` | Cancellation / retry. |
| `POST /projects/{id}/exports` | `{format: wav|mp3, file_name, chapter_id?, segment_ids?, bitrate_kbps, sample_rate?, loudnorm, skip_missing, chapter_gap_ms}`. |
| `GET /projects/{id}/exports`, `GET /exports/{id}`, `GET /exports/{id}/file`, `DELETE /exports/{id}` | Export records and files. |
| `GET /assets/{id}/audio` | Stream managed audio; supports HTTP Range. |
| `POST /transcriptions` (multipart `file`, `model_id`, `language?`), `GET/PATCH/DELETE /transcriptions/{id}`, `GET /transcriptions/{id}/export?format=txt|srt|vtt` | Transcription. SRT/VTT only from real model timestamps and only for the unedited transcript. |

## Example

```bash
T=<token>; H="X-HVS-Token: $T"
curl -s -X POST -H "$H" -H 'Content-Type: application/json' localhost:8765/api/projects \
     -d '{"name":"Demo","script":"Hello world.\n\nSecond paragraph."}'
curl -s -X POST -H "$H" -H 'Content-Type: application/json' localhost:8765/api/generations \
     -d '{"segment_ids":["<segment-id>"]}'
```

OpenAI-compatible routes and MCP are **not** implemented.
