# Hamza Voice Studio

A local-first AI voice-production studio: write and organise scripts, generate speech with
a locally installed model, compare takes per segment, regenerate individual segments,
assemble long-form narration and export WAV/MP3 — all on your own computer.


"Hamza Voice Studio" is a working name; branding lives in `backend/app/branding.py`,
`frontend/src/branding.ts` and `desktop/package.json`.

> **Honest status (v0.1.0, 2026-10-01).** The core studio works end-to-end with **real
> speech generation** (Kokoro-82M, CPU) and is tested on **Linux x86-64 only**. Windows is
> the target platform but has **not been tested yet**. Voice cloning, verified
> transcription, dubbing and dictation are not available yet. Details:
> [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md).




## What works today

- Projects with chapters and segments (paragraph or sentence segmentation), autosave,
  undo/redo, crash-safe drafts, reordering, splitting, per-segment voice/speed/language/pause.
- Unicode and right-to-left editing (Urdu, mixed Urdu/English), text normalisation with a
  preview of exactly what will be spoken (numbers, dates, currency, abbreviations, URLs),
  project pronunciation dictionary, explicit Roman-Urdu→Urdu preview helper.
- Real speech generation with **Kokoro-82M v1.0** (Apache-2.0 weights) via sherpa-onnx on CPU:
  53 built-in voices; English (US/UK) verified, 6 more languages experimental.
- Durable job queue in a separate worker process: real per-sentence progress, cancellation,
  retries, crash/restart recovery, idempotent submissions, live updates (SSE).
- Multiple takes per segment, take selection, stale-take detection after edits.
- WAV and MP3 export with ordered assembly, pauses, chapter gaps, optional loudness
  normalisation, validation, no overwrites.
- Voice library: upload or record reference audio, validation by decoding, consent records,
  trim/rename/transcript/delete. (No installed engine can clone voices yet.)
- Model manager: licences (code vs weights), checksum-pinned downloads with approval,
  resume, atomic install, removal. Offline after setup.
- Transcription UI and Whisper adapter (implemented; **not yet verified** with real weights).
- Electron desktop shell (dev mode; packaging not yet tested).

## Quick start

Requirements: Python 3.11, Node.js 20+, FFmpeg on PATH.

```bash
# Linux/macOS
scripts/setup.sh
scripts/start.sh            # prints and opens http://127.0.0.1:8765/#token=…
```

```powershell
# Windows (untested so far — see docs/SETUP_WINDOWS.md)
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
scripts\start.cmd
```

Then: **Models → Kokoro → Install** (334 MB, one time) → **Projects → New project** → paste
a script → **Generate missing** → review takes → **Export**.

Development with hot reload: `scripts/dev.sh` (backend :8765 + Vite :5173).
Desktop shell: `cd desktop && npm install && npm start`.

## Documentation

| Doc | Contents |
|---|---|
| [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) | What is implemented/tested/blocked, and how to resume development |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, job system, data layout, hosted-edition notes |
| [docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md) | Windows installation, data location, backup/restore, uninstall |
| [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md) | Installing models, offline use, air-gapped install |
| [MODEL_LICENSES.md](MODEL_LICENSES.md) | Model feasibility and licence review |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Third-party licences (incl. the eSpeak-NG GPL note) |
| [docs/API.md](docs/API.md) | Local API |
| [docs/SECURITY.md](docs/SECURITY.md) | Local access control, privacy, consent |
| [docs/TESTING.md](docs/TESTING.md) | Test layers and commands |
| [docs/BENCHMARKS.md](docs/BENCHMARKS.md) | Measured performance and reliability |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common problems |

## Privacy

Everything runs on `127.0.0.1`. There is no telemetry. The network is used only for model
downloads you approve. Only use voices you own or have permission to use.
