# Model licences and feasibility review

Reviewed: 2026-10-01. Machine-readable version: `backend/app/engines/registry.json`.

**Code licences and weight licences are listed separately. A permissive code licence does
not imply the weights are permissive.** This is a technical summary, not legal advice;
get a lawyer's review before commercial distribution.

## Summary

| Model | Integrated | Verified with real weights | Code licence | Weight licence | Commercial use |
|---|---|---|---|---|---|
| Kokoro-82M v1.0 (via sherpa-onnx) | Yes (default TTS) | **Yes** (Linux x86-64, CPU) | Apache-2.0 (sherpa-onnx) | Apache-2.0 | Permitted — see eSpeak-NG notice |
| Whisper tiny / base (via sherpa-onnx) | Yes (transcription) | **No** — download not approved in development | Apache-2.0 (sherpa-onnx), MIT (whisper) | MIT | Permitted |
| ZipVoice-Distill zh/en | No | No | Apache-2.0 | Unclear — trained on Emilia (CC BY-NC 4.0) | Treat as research-only |
| Chatterbox (Resemble AI) | No | No | MIT | MIT (per model card) | Permitted; outputs carry a Perth watermark |
| OmniVoice (k2-fsa) | No (rejected) | No | Apache-2.0 | CC-BY-NC (per model card) | **Not permitted** |

## Kokoro-82M v1.0 — default speech model

- Upstream: <https://huggingface.co/hexgrad/Kokoro-82M> (`hexgrad/Kokoro-82M`, v1.0 released 2025-01-27).
- Artifact actually used: sherpa-onnx ONNX export
  `https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_0.tar.bz2`
- Exact revision pinned by checksum: **sha256 `c5f7e2d2caf082bc1d20fb70334a61d99d20b484500aad32e7cf84c128ea3298`**
  (349,906,910 bytes; ~384 MB extracted). The installer rejects any other file.
- Weights licence: Apache-2.0 (the `LICENSE` file ships inside the archive). The model card
  states it was trained on permissive/non-copyrighted audio and allows commercial use.
- Gated terms: none.
- **Third-party notice:** grapheme-to-phoneme uses eSpeak-NG (GPL-3.0-or-later) inside the
  sherpa-onnx runtime, and the archive ships `espeak-ng-data`. Closed-source commercial
  redistribution of a bundle containing eSpeak-NG needs legal review. See THIRD_PARTY_NOTICES.md.
- Runtime: `sherpa-onnx==1.13.8` (bundles ONNX Runtime, MIT), CPU only, fp32. No PyTorch.
- Reference audio / transcript: not applicable — **no voice cloning**. 53 usable built-in
  voices (Japanese voices hidden: no Japanese text front-end in this runtime).
- Controls implemented by the model: voice (speaker id), speed (0.5–2.0). No seed, no
  emotion/pitch/stability controls — the UI does not show any.
- Measured behaviour (see docs/BENCHMARKS.md): per-sentence progress callback; cancellation
  takes effect between sentences; repeated runs are **not bit-identical** (random vocoder
  excitation) but timing is the same.
- Languages:
  - Verified by automated checks + spectrogram inspection: **en-US, en-GB**. No native
    listener review has been done yet.
  - Experimental (produce speech-like audio, unevaluated): es, fr, hi, it, pt-BR, zh.
  - **Urdu: no Kokoro voice exists.** eSpeak-NG Urdu phonemes with a Hindi voice produce
    audio, but it is unevaluated and hidden unless the user enables "unevaluated
    experimental languages". Hindi support is not treated as Urdu support.
- Observed resources: ~0.9 GB peak process RAM, 0 VRAM; RTF ~0.6–0.8 on a 2-vCPU Xeon.

## Whisper tiny / base — transcription (integrated, unverified)

- Upstream: <https://github.com/openai/whisper>; artifacts are k2-fsa int8 ONNX exports:
  `asr-models/sherpa-onnx-whisper-tiny.tar.bz2` (116,204,861 bytes) and
  `asr-models/sherpa-onnx-whisper-base.tar.bz2` (207,557,382 bytes).
- Licence: MIT (code and weights).
- Revision pinning: upstream publishes no checksum; the installer records the sha256 on first
  install (`integrity_status = recorded_unpinned`). Pin it in the registry after verifying.
- Status: the adapter is implemented and unit-tested with a mock recogniser only. The user
  declined these downloads during development, so **real transcription has not been run**.
- Timestamps: chunk-level (~28 s), no word timestamps, no diarization (speakers are never
  labelled). Accuracy is unmeasured; tiny is expected to be weak for Urdu.

## ZipVoice-Distill (evaluated, not integrated)

- Repository <https://github.com/k2-fsa/ZipVoice> is Apache-2.0. Zero-shot cloning; needs a
  reference recording **and its exact transcript**; separate vocoder file.
- The checkpoint is trained on Emilia, whose licence is CC BY-NC 4.0. The weight licence
  is therefore unclear → **research only** until clarified. Download (634,815,977 bytes) was
  offered and declined; no adapter ships in this version.

## Chatterbox (evaluated, not integrated)

- <https://github.com/resemble-ai/chatterbox>, `ResembleAI/chatterbox`. MIT code and weights
  (per model card), ~0.5 B parameters, zero-shot cloning from ~10 s reference, 23+ languages
  in the multilingual variant (Urdu not listed), Perth neural watermark on every output.
- Best candidate for a **commercial** cloning engine. Not integrated because it needs PyTorch
  and Hugging Face downloads (both blocked in the development sandbox) and a GPU for
  reasonable speed. It should run in its own worker environment (dependency isolation).

## OmniVoice (rejected for commercial use)

- <https://huggingface.co/k2-fsa/OmniVoice>: code Apache-2.0, **pretrained weights CC-BY-NC**
  ("due to constraints from its training data (e.g., Emilia)"). Re-checked 2026-10-01: the
  non-commercial restriction still applies. Its "600+ languages" claim is catalogue-level and
  was not tested. Not integrated.

## Policy

- No model code is executed from the network: models are ONNX files run by the pinned
  sherpa-onnx runtime. `trust_remote_code` is never used.
- Downloads only happen after explicit approval in the Models page, which shows the exact
  artifact URL, size, weight licence and destination.
- Registry entries are pinned to an exact artifact + checksum; "latest" is never fetched.
