"""SRT/VTT from real model timestamps only (never fabricated)."""

from __future__ import annotations

from typing import Any


def _ts(seconds: float, sep: str) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(segments: list[dict[str, Any]]) -> str:
    out = []
    for i, seg in enumerate(segments, 1):
        out.append(f"{i}\n{_ts(seg['start'], ',')} --> {_ts(seg['end'], ',')}\n{seg['text'].strip()}\n")
    return "\n".join(out)


def to_vtt(segments: list[dict[str, Any]]) -> str:
    out = ["WEBVTT\n"]
    for seg in segments:
        out.append(f"{_ts(seg['start'], '.')} --> {_ts(seg['end'], '.')}\n{seg['text'].strip()}\n")
    return "\n".join(out)
