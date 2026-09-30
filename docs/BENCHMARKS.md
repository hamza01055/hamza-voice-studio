# Benchmarks

Measured on the development machine only. **Your numbers will differ**; run
`scripts/benchmark.py` on your own hardware. Raw data: `docs/benchmarks/*.json`.

## Test machine (2026-10-01)

Linux x86-64 cloud VM · Intel Xeon @ 2.80 GHz, **2 vCPUs** · 7.8 GB RAM · **no GPU** ·
Python 3.11.15 · sherpa-onnx 1.13.8 (CPU, fp32) · 2 inference threads.
This is a modest machine; a typical 6–8-core desktop CPU should be faster.

RTF = generation time ÷ generated audio duration (below 1.0 = faster than real time).
Model-load time is reported separately from warm inference.

## Kokoro-82M v1.0 — engine (in-process, warm, `af_heart`, en-US, 3 repeats each)

| Text length | Median generation | Audio | Median RTF |
|---|---|---|---|
| 33 chars | 1.43 s | 1.95 s | 0.74 |
| 85 chars | 3.09 s | 4.49 s | 0.69 |
| 94 chars | 3.48 s | 5.15 s | 0.67 |
| 206 chars | 7.26 s | 10.46 s | 0.69 |

- Cold model load (en-US): **2.75 s**. Switching language reloads the runtime (~1.5–3 s).
- Peak process RAM: **716 MB** (54 MB before loading). VRAM: 0.
- Overall warm RTF: median **0.69**, max 0.75.

## System reliability run (real app, API → queue → worker, 100 jobs)

`scripts/benchmark.py --jobs 100`: one project with 100 segments (4 texts of 33–206 chars
cycled), all queued at once.

| Metric | Result |
|---|---|
| Jobs completed | **100 / 100** (target was ≥ 95/100) |
| Failures / retries | 0 / 0 |
| Wall clock | 528 s for 670 s of audio |
| Per-job RTF | median 0.75, p95 1.03 |
| Max queue wait | 523 s (last job; one inference job runs at a time by design) |
| Worker peak RAM | 750 MB |

Caveat: during part of this run other test suites were running on the same 2 vCPUs, which
inflates p95 RTF. The 100/100 result is for this one machine and text mix only.

## Evaluation suite (`scripts/evaluate.py`, 20 items)

All 20 items produced valid audio under the automated checks (non-empty, finite, not
silent, no clipping, no long silences; joins between consecutive items had no sample
discontinuity after edge fades). Warm RTF 0.56–0.99 per item.

Speaking rate (characters/second) was 15–20 for English items and 9.6–12 for Urdu-script and
Hindi items. **Automated checks do not show whether words were pronounced correctly.**
The human listening review (`review.csv` columns: intelligibility, pronunciation,
naturalness, voice consistency, repeated/omitted words, unwanted continuation, clipping,
join quality) has **not been done yet** — that is why only en-US/en-GB are marked verified
and Urdu remains hidden/unevaluated.

## Other measured behaviour

- Progress: the Kokoro runtime reports per-sentence fractions (e.g. 0.33 → 0.67 → 1.0).
- Cancellation: stops after the current sentence (measured ~0.9 s for a short sentence).
- Repeat takes with identical settings are not bit-identical (≈15–17 dB SNR between runs,
  identical length ±0.1 %); timing and prosody are effectively the same.
- Model download (334 MB) took ~3 s on the datacentre link; bz2 extraction ~90 s on 2 vCPUs.
- Process shutdown: API + worker stop within ~3.5 s of SIGTERM (graceful timeout capped).
