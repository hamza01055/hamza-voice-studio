"""Benchmark and reliability run on the current machine.

Part 1 (engine): cold model load, warm generation time, real-time factor, peak RAM.
Part 2 (system): starts the real app, queues N generation jobs through the API, and
records completions, failures, queue wait, per-job RTF and the worker's peak RAM.

    python scripts/benchmark.py --jobs 100 --out docs/benchmarks

RTF = generation time / generated audio duration (lower is faster; <1 is faster
than real time). Model load time is reported separately from warm inference.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import default_data_dir  # noqa: E402
from app.engines.base import SynthesisRequest  # noqa: E402
from app.engines.kokoro_sherpa import KokoroSherpaAdapter  # noqa: E402

TEXTS = [
    "Hello, and welcome to the studio.",
    "The quick brown fox jumps over the lazy dog, and then it takes a well deserved nap in the sun.",
    "Every great story begins with a single decision. For Maya, it was the choice to leave the city before "
    "dawn, carrying nothing but a notebook and a borrowed camera. She did not know where the road would lead.",
    "The fee is two thousand five hundred rupees, payable before the fifteenth of October.",
]


def engine_bench(models: Path, threads: int, repeats: int) -> dict:
    proc = psutil.Process()
    rss0 = proc.memory_info().rss
    a = KokoroSherpaAdapter("kokoro-multi-lang-v1_0", "bench", models / "kokoro-multi-lang-v1_0", threads)
    t = time.perf_counter()
    a.load("en-us")
    load_s = time.perf_counter() - t
    peak = [proc.memory_info().rss]
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            peak.append(proc.memory_info().rss)
            time.sleep(0.05)

    th = threading.Thread(target=sample, daemon=True)
    th.start()
    runs = []
    for text in TEXTS:
        for _ in range(repeats):
            t = time.perf_counter()
            r = a.synthesize(SynthesisRequest(text=text, language="en-us", voice="af_heart"), lambda *_: None,
                             lambda: False)
            g = time.perf_counter() - t
            dur = len(r.samples) / r.sample_rate
            runs.append({"chars": len(text), "gen_s": round(g, 3), "audio_s": round(dur, 3), "rtf": round(g / dur, 3)})
    stop.set()
    th.join()
    return {"cold_load_s": round(load_s, 2), "runs": runs,
            "rtf_median": round(statistics.median(r["rtf"] for r in runs), 3),
            "rtf_max": round(max(r["rtf"] for r in runs), 3),
            "rss_before_load_mb": rss0 // 2**20, "peak_rss_mb": max(peak) // 2**20}


def api(port: int, token: str, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-HVS-Token": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
        return json.loads(r.read())


def system_bench(models: Path, n_jobs: int, port: int) -> dict:
    token = "bench-token"  # noqa: S105 - local throwaway session token
    data = Path(tempfile.mkdtemp(prefix="hvs-bench-"))
    env = {**os.environ, "HVS_TOKEN": token, "HVS_DATA_DIR": str(data), "HVS_MODELS_DIR": str(models)}
    proc = subprocess.Popen([sys.executable, "-m", "app.run", "--no-browser", "--strict-port", "--port", str(port)],
                            cwd=ROOT / "backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                h = api(port, token, "GET", "/health")
                if h["worker"].get("pid"):
                    break
            except OSError:
                pass
            time.sleep(0.5)
        worker = psutil.Process(api(port, token, "GET", "/health")["worker"]["pid"])
        script = "\n\n".join(TEXTS[i % len(TEXTS)] + f" Item {i + 1}." for i in range(n_jobs))
        p = api(port, token, "POST", "/projects", {"name": "Benchmark", "script": script})
        ids = [s["id"] for s in p["chapters"][0]["segments"]]
        t0 = time.time()
        api(port, token, "POST", "/generations", {"segment_ids": ids})
        peak = 0
        while True:
            try:
                peak = max(peak, worker.memory_info().rss)
            except psutil.NoSuchProcess:
                pass
            jobs = api(port, token, "GET", "/jobs?type=tts&limit=500")["items"]
            active = [j for j in jobs if j["status"] in ("queued", "loading_model", "running", "cancelling")]
            if not active:
                break
            time.sleep(1)
        wall = time.time() - t0
        done = [j for j in jobs if j["status"] == "completed"]
        failed = [j for j in jobs if j["status"] != "completed"]

        def ts(s: str) -> float:
            return datetime.fromisoformat(s.rstrip("Z")).timestamp()

        waits = [ts(j["started_at"]) - ts(j["created_at"]) for j in done if j["started_at"]]
        rtfs = [j["result"]["rtf"] for j in done if j["result"].get("rtf")]
        return {"jobs": len(jobs), "completed": len(done), "failed_or_other": len(failed),
                "failures": [{"status": j["status"], "code": j["error_code"]} for j in failed],
                "wall_clock_s": round(wall, 1),
                "audio_generated_s": round(sum(j["result"].get("audio_seconds", 0) for j in done), 1),
                "rtf_median": round(statistics.median(rtfs), 3) if rtfs else None,
                "rtf_p95": round(sorted(rtfs)[int(len(rtfs) * 0.95) - 1], 3) if rtfs else None,
                "queue_wait_max_s": round(max(waits), 1) if waits else None,
                "retries": sum(j["retry_count"] for j in jobs),
                "worker_peak_rss_mb": peak // 2**20}
    finally:
        proc.terminate()
        proc.wait(30)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=100)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--port", type=int, default=18799)
    ap.add_argument("--out", default=str(ROOT / "docs" / "benchmarks"))
    ap.add_argument("--models-dir", default=os.environ.get("HVS_MODELS_DIR") or str(default_data_dir() / "models"))
    args = ap.parse_args()
    models = Path(args.models_dir)
    threads = max(1, min(4, os.cpu_count() or 2))
    vm = psutil.virtual_memory()
    result = {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "machine": {"os": f"{platform.system()} {platform.release()}", "python": platform.python_version(),
                    "cpu": platform.processor() or platform.machine(), "logical_cpus": os.cpu_count(),
                    "ram_gb": round(vm.total / 2**30, 1), "gpu": "none used (CPU runtime)", "threads": threads},
        "model": "kokoro-multi-lang-v1_0 via sherpa-onnx (fp32, CPU)",
    }
    print("Engine benchmark…", flush=True)
    result["engine"] = engine_bench(models, threads, args.repeats)
    print(json.dumps(result["engine"], indent=1)[:600], flush=True)
    if args.jobs:
        print(f"System reliability run with {args.jobs} jobs…", flush=True)
        result["system"] = system_bench(models, args.jobs, args.port)
        print(json.dumps(result["system"], indent=1), flush=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"benchmark-{datetime.now(UTC).strftime('%Y%m%d-%H%M')}.json"
    f.write_text(json.dumps(result, indent=2))
    print(f"Saved {f}")


if __name__ == "__main__":
    main()
