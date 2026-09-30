# Implementation status

Last updated: 2026-10-01 · version 0.1.0 · milestone: **first working release candidate
(Phases A–E core), tested on Linux only**.

Legend: ✅ implemented and tested · 🟡 implemented, partially tested · ⛔ blocked ·
❌ not implemented.

## Tested environment

Linux x86-64 cloud VM (2 vCPU Xeon 2.8 GHz, 7.8 GB RAM, no GPU), Python 3.11.15,
Node 22.22, FFmpeg 6.1.1, Chromium (Playwright 1.56), Electron 44.5.1 under Xvfb.
**Windows 10/11 — the target platform — has not been tested.** macOS has not been tested.

## Phase status

| Phase | Status |
|---|---|
| A. Environment inspection & model feasibility | ✅ MODEL_LICENSES.md, registry.json |
| B. Real speech generation via Python service | ✅ Kokoro-82M (sherpa-onnx), verified |
| C. Studio UI with projects, voices, exports | ✅ |
| D. Durable jobs, cancellation, retries, recovery | ✅ incl. real process-kill tests |
| E. Transcription & long-form | 🟡 long-form ✅; transcription implemented, ⛔ not verified with real weights |
| F. Desktop packaging | 🟡 Electron shell works in dev mode (Linux smoke test); Windows installer ❌ not built/tested |
| G. Dubbing, voice design, dictation, integrations | ❌ not started (hidden from the UI) |

## First-release checklist (spec §3 / §30)

| Requirement | Status | Evidence |
|---|---|---|
| Hardware detection | ✅ | `/system/capabilities`, Models page |
| Model catalogue + install status | ✅ | Models page; `test_model_manager.py` |
| At least one real TTS adapter | ✅ | Kokoro; `tests/real/test_kokoro_real.py`, E2E |
| Script editor (Unicode, RTL, counts, limits, autosave, undo/redo, restore) | ✅ | E2E + manual screenshots |
| Voice selection | ✅ | per project + per segment override |
| Authorised reference-audio upload / recording | ✅ / 🟡 | upload tested (API + E2E); microphone recording implemented, not automatable in headless tests |
| Voice library (rename, tags, transcript, trim, delete, consent, revocation) | ✅ | `test_voices_transcription.py`, E2E |
| Voice cloning with a profile | ⛔ | no cloning engine integrated (see below) |
| Project create/persist/reopen/delete | ✅ | E2E (incl. restart) |
| Paragraph/sentence segmentation, chapters, reorder, split | ✅ | unit + integration |
| Generation queue, real progress, actionable errors | ✅ | |
| Cancellation (honest, between sentences) and retry | ✅ | integration + real |
| Multiple takes, take selection, per-segment regeneration | ✅ | E2E |
| Stale-take detection after edits | ✅ | integration + E2E |
| Audio playback (range requests, waveform) | ✅ | E2E |
| WAV and MP3 export (validated, no overwrite, loudness option) | ✅ | E2E + ffprobe |
| Settings | ✅ | |
| Offline after setup | ✅ | no network use except approved downloads; E2E ran with models from disk |
| Clean install/start instructions | 🟡 | Linux scripts used; Windows scripts written, not executed |
| Restart recovery / worker crash / app killed mid-job | ✅ | `tests/real/test_crash_recovery.py` |
| 95/100 reliability target | ✅ on test machine | 100/100 (docs/BENCHMARKS.md) |

## Languages

- en-US, en-GB: verified by automated checks + spectrogram inspection. **No native-listener review yet.**
- es, fr, hi, it, pt-BR, zh: experimental (produce audio; unevaluated).
- **Urdu: no suitable voice.** Hidden behind "Show unevaluated experimental languages";
  quality unknown. The editor fully supports Urdu script, RTL and mixed text regardless.
- Roman Urdu: text is kept as-is; English G2P reads it (not evaluated). The
  Roman→Urdu-script helper is dictionary-based and preview-only.

## Blocked / not verified — and why

| Item | Reason | To unblock |
|---|---|---|
| Whisper transcription (real) | Download not approved during development | Install Whisper tiny/base from the Models page, run a real transcription, pin the checksum in `registry.json`, add `tests/real/test_whisper_real.py`. |
| Voice cloning | Only clearly-licensed commercial candidate (Chatterbox, MIT) needs PyTorch + Hugging Face; both blocked in the sandbox. ZipVoice is research-only (Emilia CC BY-NC); OmniVoice weights are non-commercial. | Add a Chatterbox adapter in a separate worker venv on a machine with HF access (GPU recommended); verify; wire `voice_cloning` capability (the UI and voice profiles are ready). |
| Windows | No Windows machine in development | Run `scripts\setup.ps1`, `pytest`, the E2E suite and the desktop shell on Windows; fix issues; update this file. |
| Desktop installer | Needs a bundled Python runtime (`desktop/build/python`) + code signing | Script the embeddable-Python bundle, `npm run dist:win`, test install/upgrade/uninstall. |
| Human audio review | Needs listeners | Run `scripts/evaluate.py`, fill `review.csv`, record results in BENCHMARKS.md. |

## Later milestones (not started)

FLAC export, per-segment ZIP, chapter packages, transcript export from projects, dubbing
workspace, voice design, audiobook character→voice mapping, dictation, OpenAI-compatible
routes, MCP, hosted edition.

## How to resume development

1. `scripts/setup.sh` (or `setup.ps1`), then `cd backend && ../.venv/bin/python -m pytest` —
   everything should pass (real tests skip without weights).
2. Install Kokoro via the Models page (or set `HVS_REAL_MODELS_DIR`) and run
   `pytest -m real tests/real` and the Playwright suite (docs/TESTING.md).
3. Next steps, in order: (a) Windows verification; (b) Whisper real verification;
   (c) human evaluation of en-US/en-GB (+ decide on Urdu); (d) cloning engine in an isolated
   worker; (e) Windows installer with bundled Python; (f) FLAC/ZIP exports; (g) Phase G.
4. Schema changes: edit `backend/app/db/models.py`, then
   `cd backend && HVS_DATA_DIR=/tmp/x ../.venv/bin/alembic revision --autogenerate -m "…"`.
