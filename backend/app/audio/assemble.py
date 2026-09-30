"""Long-form assembly: concatenates selected takes in order with explicit pauses.

Joins use a short (5 ms) fade-out/fade-in on each take's own edges to prevent clicks.
Takes never overlap: pauses are inserted *between* takes, and no crossfade that would
overlap speech is applied.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Piece:
    samples: np.ndarray
    sample_rate: int
    pause_after_ms: int


def edge_fade(x: np.ndarray, sr: int, ms: float = 5.0) -> np.ndarray:
    n = min(len(x) // 2, int(sr * ms / 1000))
    if n <= 0:
        return x
    y = x.astype(np.float32, copy=True)
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    y[:n] *= ramp
    y[-n:] *= ramp[::-1]
    return y


def assemble(pieces: list[Piece], sample_rate: int) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Returns (audio, [(start_s, end_s) per piece])."""
    out: list[np.ndarray] = []
    spans: list[tuple[float, float]] = []
    pos = 0
    for i, p in enumerate(pieces):
        if p.sample_rate != sample_rate:
            raise ValueError("All pieces must share the assembly sample rate.")
        seg = edge_fade(p.samples, sample_rate)
        spans.append((pos / sample_rate, (pos + len(seg)) / sample_rate))
        out.append(seg)
        pos += len(seg)
        if i < len(pieces) - 1 and p.pause_after_ms > 0:
            gap = np.zeros(int(sample_rate * p.pause_after_ms / 1000), dtype=np.float32)
            out.append(gap)
            pos += len(gap)
    audio = np.concatenate(out) if out else np.zeros(0, dtype=np.float32)
    return audio, spans
