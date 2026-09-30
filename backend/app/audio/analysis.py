"""Signal checks for generated takes and reference recordings.

These are heuristics. They catch empty, invalid, clipped, silent or badly truncated
audio; they do not judge naturalness or speaker identity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


def dbfs(x: float) -> float:
    return float(20.0 * np.log10(max(x, 1e-10)))


@dataclass
class SignalReport:
    duration: float
    sample_rate: int
    peak_dbfs: float
    rms_dbfs: float
    clipped_fraction: float
    silence_fraction: float
    leading_silence: float
    trailing_silence: float
    longest_silence: float
    has_invalid_samples: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _frame_rms(x: np.ndarray, sr: int, frame_ms: float = 20.0) -> np.ndarray:
    n = max(1, int(sr * frame_ms / 1000))
    usable = (len(x) // n) * n
    if usable == 0:
        return np.array([float(np.sqrt(np.mean(x**2))) if len(x) else 0.0])
    frames = x[:usable].reshape(-1, n)
    return np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))


def analyse(samples: np.ndarray, sr: int, silence_threshold_dbfs: float = -45.0) -> SignalReport:
    x = np.asarray(samples, dtype=np.float32).reshape(-1)
    invalid = bool(len(x) and not np.all(np.isfinite(x)))
    clean = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    duration = len(clean) / sr if sr else 0.0
    peak = float(np.max(np.abs(clean))) if len(clean) else 0.0
    rms = float(np.sqrt(np.mean(clean.astype(np.float64) ** 2))) if len(clean) else 0.0
    clipped = float(np.mean(np.abs(clean) >= 0.999)) if len(clean) else 0.0
    frame_ms = 20.0
    fr = _frame_rms(clean, sr, frame_ms)
    silent = fr < 10 ** (silence_threshold_dbfs / 20)
    silence_fraction = float(np.mean(silent)) if len(fr) else 1.0
    fsec = frame_ms / 1000

    def run_len(arr: np.ndarray) -> int:
        c = 0
        for v in arr:
            if v:
                c += 1
            else:
                break
        return c

    leading = run_len(silent) * fsec
    trailing = run_len(silent[::-1]) * fsec
    longest = 0
    cur = 0
    for v in silent:
        cur = cur + 1 if v else 0
        longest = max(longest, cur)
    return SignalReport(duration=duration, sample_rate=sr, peak_dbfs=dbfs(peak), rms_dbfs=dbfs(rms),
                        clipped_fraction=clipped, silence_fraction=silence_fraction,
                        leading_silence=leading, trailing_silence=trailing,
                        longest_silence=longest * fsec, has_invalid_samples=invalid)


def check_generated(samples: np.ndarray, sr: int, text: str, speed: float = 1.0) -> SignalReport:
    """Validate TTS output. ``errors`` mean the take must not be saved."""
    r = analyse(samples, sr)
    if len(samples) == 0 or r.duration < 0.05:
        r.errors.append("The model returned no audio.")
    if r.has_invalid_samples:
        r.errors.append("The model returned invalid (NaN or infinite) samples.")
    if r.silence_fraction > 0.98:
        r.errors.append("The generated audio is silent.")
    if r.errors:
        return r
    chars = len(text.strip())
    # Very rough speaking-rate envelope (~5-25 characters/second at speed 1.0).
    expected_min = chars / 25.0 / max(speed, 0.1)
    expected_max = chars / 5.0 / max(speed, 0.1) + 2.0
    if chars > 20 and r.duration < expected_min * 0.6:
        r.warnings.append("Audio is much shorter than expected for this text; words may be missing.")
    if r.duration > expected_max * 1.5:
        r.warnings.append("Audio is much longer than expected; check for repetition or unwanted continuation.")
    if r.clipped_fraction > 0.001:
        r.warnings.append("Some samples are clipped.")
    if r.longest_silence > 2.5:
        r.warnings.append(f"Contains a silence of {r.longest_silence:.1f}s.")
    return r


def check_reference(samples: np.ndarray, sr: int, *, native_sr: int, channels: int,
                    min_seconds: float, max_seconds: float) -> SignalReport:
    """Validate a voice reference recording."""
    r = analyse(samples, sr)
    if r.has_invalid_samples:
        r.errors.append("The recording contains invalid samples.")
    if r.duration < min_seconds:
        r.errors.append(f"The recording is {r.duration:.1f}s long; at least {min_seconds:.0f}s is required.")
    if r.duration > max_seconds:
        r.errors.append(f"The recording is {r.duration:.1f}s long; the maximum is {max_seconds:.0f}s.")
    if r.rms_dbfs < -55 or r.silence_fraction > 0.9:
        r.errors.append("The recording is silent or nearly silent.")
    if r.errors:
        return r
    if native_sr < 16000:
        r.warnings.append(f"Sample rate is {native_sr} Hz; 16 kHz or higher is recommended.")
    if channels > 1:
        r.warnings.append("Recording has multiple channels; it is mixed to mono for voice use.")
    if r.clipped_fraction > 0.001:
        r.warnings.append("The recording is clipped (distorted peaks). Re-record at a lower level if possible.")
    if r.rms_dbfs < -35:
        r.warnings.append("The recording is quiet; a louder, cleaner recording usually works better.")
    if r.silence_fraction > 0.5:
        r.warnings.append("More than half of the recording is silence; consider trimming it.")
    if r.longest_silence > 3.0:
        r.warnings.append(f"Contains a pause of {r.longest_silence:.1f}s; consider trimming it.")
    r.warnings.append("Multiple-speaker detection is not performed; make sure only one person speaks.")
    return r
