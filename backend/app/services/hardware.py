"""Hardware and runtime detection. Detects capabilities; never assumes a GPU."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from typing import Any

import psutil

from app.audio import ffmpeg
from app.core.config import get_settings


def _gpus() -> list[dict[str, Any]]:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return []
    try:
        out = subprocess.run([smi, "--query-gpu=name,memory.total,memory.free,driver_version",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10,
                             check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            gpus.append({"vendor": "NVIDIA", "name": parts[0], "vram_total_mb": int(float(parts[1])),
                         "vram_free_mb": int(float(parts[2])), "driver": parts[3]})
    return gpus


def _cpu_name() -> str:
    name = platform.processor()
    if sys.platform.startswith("linux"):
        try:
            for line in open("/proc/cpuinfo", encoding="utf-8"):
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return name or platform.machine()


def capabilities() -> dict[str, Any]:
    s = get_settings()
    s.ensure_dirs()
    vm = psutil.virtual_memory()
    du = shutil.disk_usage(s.data_dir)
    try:
        import sherpa_onnx

        sherpa_version = getattr(sherpa_onnx, "__version__", "unknown")
    except Exception:  # noqa: BLE001
        sherpa_version = None
    gpus = _gpus()
    return {
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "cpu": {"name": _cpu_name(), "logical_cores": psutil.cpu_count(logical=True),
                "physical_cores": psutil.cpu_count(logical=False)},
        "ram": {"total_mb": vm.total // 2**20, "available_mb": vm.available // 2**20},
        "gpus": gpus,
        "cuda_available": False,
        "cuda_note": ("The bundled sherpa-onnx runtime is CPU-only; a GPU is not used even if present."
                      if gpus else "No NVIDIA GPU detected."),
        "selected_device": "cpu",
        "inference_threads": s.inference_threads,
        "disk": {"free_mb": du.free // 2**20, "total_mb": du.total // 2**20},
        "ffmpeg": {"ffmpeg": bool(ffmpeg.ffmpeg_bin()), "ffprobe": bool(ffmpeg.ffprobe_bin())},
        "runtimes": {"sherpa_onnx": sherpa_version},
    }
