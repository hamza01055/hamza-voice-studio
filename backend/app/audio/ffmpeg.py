"""Safe FFmpeg / ffprobe wrappers.

All invocations use argument arrays (never a shell), fixed codecs/filters chosen by
the application, and a timeout. Inputs are always managed files resolved by the
server; user-supplied paths are never passed here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.errors import AppError


class MediaError(AppError):
    code = "invalid_media"
    status_code = 422


def ffmpeg_bin() -> str | None:
    return shutil.which("ffmpeg")


def ffprobe_bin() -> str | None:
    return shutil.which("ffprobe")


def require_ffmpeg() -> tuple[str, str]:
    f, p = ffmpeg_bin(), ffprobe_bin()
    if not f or not p:
        raise AppError("FFmpeg and ffprobe are required but were not found on PATH. "
                       "Install FFmpeg (see docs/SETUP_WINDOWS.md) and restart the studio.",
                       code="ffmpeg_missing", status_code=503)
    return f, p


def _timeout() -> float:
    from app.core.config import get_settings

    return get_settings().ffmpeg_timeout_seconds


def _run(args: list[str], *, input_bytes: bytes | None = None, timeout: float | None = None) -> bytes:
    try:
        proc = subprocess.run(args, input=input_bytes, capture_output=True,
                              timeout=timeout or _timeout(), check=False)
    except subprocess.TimeoutExpired as e:
        raise MediaError("Audio processing took too long and was stopped.", code="media_timeout") from e
    if proc.returncode != 0:
        raise MediaError("The audio could not be decoded or processed. "
                         "It may be corrupt or in an unsupported format.",
                         details={"tool": Path(args[0]).name})
    return proc.stdout


@dataclass
class ProbeInfo:
    duration: float
    sample_rate: int
    channels: int
    codec: str
    format_name: str


def probe(path: Path) -> ProbeInfo:
    _, ffprobe = require_ffmpeg()
    out = _run([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                "stream=codec_name,sample_rate,channels:format=duration,format_name",
                "-of", "json", str(path)], timeout=60)
    try:
        data = json.loads(out)
        stream = data["streams"][0]
        fmt = data.get("format", {})
        dur = float(fmt.get("duration") or 0.0)
        return ProbeInfo(duration=dur, sample_rate=int(stream["sample_rate"]),
                         channels=int(stream["channels"]), codec=str(stream.get("codec_name", "")),
                         format_name=str(fmt.get("format_name", "")))
    except (KeyError, IndexError, ValueError, TypeError) as e:
        raise MediaError("No decodable audio stream was found in the file.") from e


def decode(path: Path, *, sample_rate: int | None = None, mono: bool = True,
           max_seconds: float | None = None) -> tuple[np.ndarray, int]:
    """Decode any supported input into float32 samples. Keeps the native sample
    rate unless ``sample_rate`` is given."""
    ffmpeg, _ = require_ffmpeg()
    info = probe(path)
    sr = sample_rate or info.sample_rate
    args = [ffmpeg, "-v", "error", "-nostdin", "-i", str(path)]
    if max_seconds:
        args += ["-t", f"{max_seconds:.3f}"]
    args += ["-vn", "-sn", "-dn", "-f", "f32le", "-acodec", "pcm_f32le", "-ar", str(sr)]
    if mono:
        args += ["-ac", "1"]
    args += ["pipe:1"]
    raw = _run(args)
    samples = np.frombuffer(raw, dtype="<f4").astype(np.float32)
    if not mono:
        samples = samples.reshape(-1, info.channels)
    return samples, sr


def encode(src_wav: Path, dst: Path, fmt: str, *, bitrate_kbps: int = 192,
           sample_rate: int | None = None, loudnorm: bool = False) -> None:
    ffmpeg, _ = require_ffmpeg()
    args = [ffmpeg, "-v", "error", "-nostdin", "-y", "-i", str(src_wav)]
    filters = []
    if loudnorm:
        # EBU R128 single-pass loudness normalisation (explicit export option only).
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    if filters:
        args += ["-af", ",".join(filters)]
    if sample_rate:
        args += ["-ar", str(sample_rate)]
    elif loudnorm:
        # loudnorm internally upsamples to 192 kHz; restore the source rate.
        args += ["-ar", str(probe(src_wav).sample_rate)]
    if fmt == "mp3":
        args += ["-codec:a", "libmp3lame", "-b:a", f"{int(bitrate_kbps)}k", "-f", "mp3"]
    elif fmt == "wav":
        args += ["-codec:a", "pcm_s16le", "-f", "wav"]
    elif fmt == "flac":
        args += ["-codec:a", "flac", "-f", "flac"]
    else:  # pragma: no cover - validated earlier
        raise MediaError(f"Unsupported export format: {fmt}")
    args += [str(dst)]
    _run(args)
