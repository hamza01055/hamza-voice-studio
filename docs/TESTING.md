# Testing

Three layers, kept separate so CI never downloads model weights.

## 1. Backend unit + integration (mock engine) — runs in CI

```bash
.venv/bin/python -m pytest backend/tests -m "not real"      # from repo root: cd backend first
```

`backend/tests/mock_engine.py` is a **test-only** adapter that produces a synthetic tone. It
exercises job/storage/export logic; it is never registered by production code.

Covered: text normalisation (numbers, dates, currency, abbreviations, URLs, overrides,
Urdu/Roman Urdu), Unicode/RTL/mixed scripts, segmentation and ordering, capability
validation (languages, voice/language mismatch, limits), reference-audio validation (decode,
silence, too short/long, clipping, channels, size limit), job state transitions, atomic
claiming under 6 concurrent claimers, idempotency keys and duplicate submissions, bounded
queue, cancellation (queued and mid-run), automatic and manual retry, invalid output
(empty/NaN), model exceptions, out-of-memory reporting, lease-expiry and restart recovery,
asset lifecycle and reference counting, exports (WAV/MP3, no overwrite, missing takes,
chapter export), path traversal, token/origin/host checks, security headers, project
persistence, stale takes after edits, re-segmentation keeping unchanged segments, model
download (checksum, resume, unsafe archive, failed download, insufficient disk,
detection of installed models from disk), transcription flow and subtitle rules, SSE.

## 2. Real inference (needs installed Kokoro weights) — local only

```bash
cd backend
HVS_REAL_MODELS_DIR=~/.local/share/HamzaVoiceStudio/models ../.venv/bin/python -m pytest -m real tests/real
```

- `test_kokoro_real.py`: en-US and en-GB synthesis, real progress, cancellation between
  sentences, voice/language mismatch, repeat-take behaviour.
- `test_crash_recovery.py`: starts the real app, **SIGKILLs the worker mid-generation**
  (supervisor restarts it; job is recovered and completes once), then **SIGKILLs the whole
  app mid-generation** (worker exits, no orphan; job completes after restart). POSIX only.

## 3. End-to-end browser workflow (Playwright) — local only

```bash
cd frontend && npm run build
HVS_E2E_MODELS_DIR=~/.local/share/HamzaVoiceStudio/models npx playwright test
# If Playwright's bundled browser is unavailable: PW_CHROMIUM_PATH=/path/to/chrome
```

Starts its own backend on port 18765 with a temporary data dir, then: create project →
spoken-text preview → **real generation** of all segments → play a take → regenerate one
segment → choose take 2 → export WAV and MP3 (validated with ffprobe) → edit text (stale
badge) → **restart the backend** → reopen → verify text, selected takes and exports →
delete project. A second test checks the UI refuses to load without the token.

## Static checks

```bash
cd backend && ../.venv/bin/ruff check app tests && ../.venv/bin/mypy app
cd frontend && npx tsc -b
```

## Benchmarks and audio evaluation

```bash
.venv/bin/python scripts/benchmark.py --jobs 100      # engine + 100-job reliability run
.venv/bin/python scripts/evaluate.py --out eval-output # generates audio + review.csv
```

`evaluate.py` produces automated metrics and a **human review sheet**; automated metrics do
not judge pronunciation or naturalness.
