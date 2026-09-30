"""Audio evaluation harness.

Generates every item in scripts/eval_texts.json with a real installed engine, records
automated signal metrics, tests segment joins, and writes a human review sheet.

    python scripts/evaluate.py --out eval-output [--voice af_heart] [--models-dir DIR]

Automated metrics catch empty/clipped/silent/truncated output only. Pronunciation,
naturalness, intelligibility and voice consistency REQUIRE human listening: fill in
review.csv. ASR-based WER, if you add it, is supporting evidence only.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.audio.analysis import check_generated  # noqa: E402
from app.audio.assemble import Piece, assemble  # noqa: E402
from app.core.config import default_data_dir  # noqa: E402
from app.engines.base import EngineError, SynthesisRequest  # noqa: E402
from app.engines.kokoro_sherpa import LANGUAGES, KokoroSherpaAdapter  # noqa: E402
from app.services.normalize import normalize  # noqa: E402

DEFAULT_VOICES = {"en-us": "af_heart", "en-gb": "bf_emma", "hi": "hf_alpha", "es": "ef_dora", "ur": "hf_alpha",
                  "fr": "ff_siwis", "it": "if_sara", "pt-br": "pf_dora", "zh": "zf_xiaoxiao"}
REVIEW_COLUMNS = ["intelligibility_1to5", "pronunciation_1to5", "naturalness_1to5", "voice_consistency_1to5",
                  "repeated_or_omitted_words", "unwanted_continuation", "audible_clipping", "join_quality_1to5",
                  "reviewer", "notes"]


def join_discontinuity(a: np.ndarray, b: np.ndarray, sr: int) -> float:
    """Largest sample jump across a direct join after edge fades (0 = seamless)."""
    audio, spans = assemble([Piece(a, sr, 0), Piece(b, sr, 0)], sr)
    i = int(spans[1][0] * sr)
    return float(abs(audio[i] - audio[i - 1])) if 0 < i < len(audio) else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval-output")
    ap.add_argument("--models-dir", default=os.environ.get("HVS_MODELS_DIR") or str(default_data_dir() / "models"))
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    out = Path(args.out)
    (out / "audio").mkdir(parents=True, exist_ok=True)
    suite = json.loads((ROOT / "scripts" / "eval_texts.json").read_text(encoding="utf-8"))
    adapter = KokoroSherpaAdapter("kokoro-multi-lang-v1_0", "eval", Path(args.models_dir) / "kokoro-multi-lang-v1_0",
                                  threads=args.threads, include_unevaluated=True)
    rows = []
    prev: tuple[np.ndarray, int] | None = None
    for item in suite["items"]:
        lang = item["language"]
        if lang not in LANGUAGES:
            rows.append({**item, "status": "unsupported_language"})
            continue
        norm = normalize(item["text"], lang).text
        voice = DEFAULT_VOICES.get(lang, "af_heart")
        adapter.load(lang)  # keep (re)load time out of the RTF measurement
        t0 = time.perf_counter()
        try:
            res = adapter.synthesize(SynthesisRequest(text=norm, language=lang, voice=voice), lambda *_: None,
                                     lambda: False)
        except EngineError as e:
            rows.append({**item, "normalized": norm, "voice": voice, "status": f"error:{e.code}"})
            continue
        dt = time.perf_counter() - t0
        rep = check_generated(res.samples, res.sample_rate, norm)
        path = out / "audio" / f"{item['id']}.wav"
        sf.write(path, res.samples, res.sample_rate, subtype="PCM_16")
        dur = len(res.samples) / res.sample_rate
        same_rate = prev is not None and prev[1] == res.sample_rate
        join = join_discontinuity(prev[0], res.samples, res.sample_rate) if prev and same_rate else None
        prev = (res.samples, res.sample_rate)
        rows.append({**item, "normalized": norm, "voice": voice,
                     "status": "error:" + ";".join(rep.errors) if rep.errors else "ok",
                     "duration_s": round(dur, 2), "gen_s": round(dt, 2), "rtf": round(dt / dur, 3) if dur else None,
                     "chars_per_s": round(len(norm) / dur, 1) if dur else None,
                     "peak_dbfs": round(rep.peak_dbfs, 1), "clipped_fraction": rep.clipped_fraction,
                     "silence_fraction": round(rep.silence_fraction, 3), "longest_silence_s": rep.longest_silence,
                     "warnings": " | ".join(rep.warnings), "join_jump_from_previous": join,
                     "file": str(path.relative_to(out))})
        print(f"{item['id']:<22} {rows[-1]['status']:<8} {dur:5.2f}s rtf={rows[-1]['rtf']}")
    (out / "metrics.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    with (out / "review.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "category", "language", "unevaluated_language", "file", "text", "normalized",
                    "auto_status", "auto_warnings", *REVIEW_COLUMNS])
        for r in rows:
            w.writerow([r["id"], r["category"], r["language"], r.get("unevaluated", False), r.get("file", ""),
                        r["text"], r.get("normalized", ""), r["status"], r.get("warnings", ""),
                        *[""] * len(REVIEW_COLUMNS)])
    ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"\n{ok}/{len(rows)} items produced valid audio. Human review sheet: {out / 'review.csv'}")


if __name__ == "__main__":
    main()
