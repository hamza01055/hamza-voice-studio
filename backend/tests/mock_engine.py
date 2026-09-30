"""TEST-ONLY mock adapters. Never registered in production code paths.

The mock TTS produces a synthetic tone whose length depends on the text, so that job,
storage and export logic can be tested without model weights. It is not speech.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from app.engines.base import (
    ASRAdapter,
    Capabilities,
    EngineError,
    GenerationCancelled,
    ProgressFn,
    SynthesisRequest,
    SynthesisResult,
    TranscriptionResult,
    TTSAdapter,
    VoiceOption,
)

MOCK_TTS_ENTRY: dict[str, Any] = {
    "id": "mock-tts", "name": "Mock TTS (tests only)", "kind": "tts", "adapter": "mock_tts",
    "integration": "integrated", "verification": "test_only", "revision": "mock-rev-1",
    "artifacts": [{"url": "https://example.invalid/mock.tar.bz2", "type": "tar.bz2", "size_bytes": 10,
                   "sha256": None}],
    "required_files": ["mock.bin"], "license": {"weights": "n/a"}, "languages": {},
}
MOCK_ASR_ENTRY: dict[str, Any] = {
    "id": "mock-asr", "name": "Mock ASR (tests only)", "kind": "asr", "adapter": "mock_asr",
    "integration": "integrated", "verification": "test_only", "revision": "mock-asr-1",
    "artifacts": [{"url": "https://example.invalid/mock-asr.tar.bz2", "type": "tar.bz2", "size_bytes": 10,
                   "sha256": None}],
    "required_files": ["mock.bin"], "license": {"weights": "n/a"}, "languages": {},
}


class Behaviour:
    fail_times = 0
    fail_retryable = True
    raise_exc: BaseException | None = None
    empty_output = False
    nan_output = False
    sentences = 3
    on_sentence: Callable[[int], None] | None = None
    calls = 0


class MockTTS(TTSAdapter):
    behaviour = Behaviour

    def capabilities(self) -> Capabilities:
        return Capabilities(kind="tts", languages_tested=["en-us"], languages_experimental=["ur"],
                            preset_voices=[VoiceOption("mock_a", "Mock A", "en-us")], speed_control=True,
                            speed_range=(0.5, 2.0), deterministic=False, seed_support=True,
                            max_input_chars=500, output_sample_rate=16000,
                            progress_reporting="per_sentence", cancellation="between_sentences")

    def load(self, language: str = "en-us") -> None:  # type: ignore[override]
        self._loaded = True

    def synthesize(self, req: SynthesisRequest, progress: ProgressFn,
                   should_cancel: Callable[[], bool]) -> SynthesisResult:
        b = self.behaviour
        b.calls += 1
        if b.raise_exc is not None:
            raise b.raise_exc
        if b.fail_times > 0:
            b.fail_times -= 1
            raise EngineError("mock transient failure", retryable=b.fail_retryable)
        sr = 16000
        for i in range(b.sentences):
            if b.on_sentence:
                b.on_sentence(i)
            progress((i + 1) / b.sentences, "Generating speech")
            if should_cancel():
                raise GenerationCancelled("cancelled")
        if b.empty_output:
            return SynthesisResult(np.zeros(0, dtype=np.float32), sr, {})
        n = int(sr * max(0.5, len(req.text) / 15.0 / req.speed))
        t = np.arange(n) / sr
        x = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        if b.nan_output:
            x[10] = np.nan
        return SynthesisResult(x, sr, {"voice": req.voice, "speed": req.speed})


class MockASR(ASRAdapter):
    def capabilities(self) -> Capabilities:
        return Capabilities(kind="asr", segment_timestamps=True)

    def load(self, language: str = "") -> None:  # type: ignore[override]
        self._loaded = True

    def transcribe(self, samples: np.ndarray, sample_rate: int, language: str | None,
                   progress: ProgressFn, should_cancel: Callable[[], bool]) -> TranscriptionResult:
        dur = len(samples) / sample_rate
        return TranscriptionResult(text="hello world", language=language or "en",
                                   segments=[{"start": 0.0, "end": round(dur, 2), "text": "hello world"}],
                                   timestamp_kind="chunk")


def factory_tts(entry: dict[str, Any], d: Path, threads: int, opts: dict[str, Any]) -> MockTTS:
    return MockTTS(entry["id"], entry["revision"], d, threads)


def factory_asr(entry: dict[str, Any], d: Path, threads: int, opts: dict[str, Any]) -> MockASR:
    return MockASR(entry["id"], entry["revision"], d, threads)
