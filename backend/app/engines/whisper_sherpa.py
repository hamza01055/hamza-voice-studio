"""OpenAI Whisper (tiny/base, int8 ONNX export) via sherpa-onnx.

STATUS: implemented but NOT verified with real weights in the development
environment (the download was not approved there). It is unit-tested with a mocked
recognizer only. See docs/IMPLEMENTATION_STATUS.md.

Whisper processes at most 30 s per pass, so audio is decoded in <=28 s chunks.
Timestamps are chunk-level boundaries (``timestamp_kind="chunk"``), not word-level.
No diarization: speakers are never labelled automatically.
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
    EngineUnavailable,
    GenerationCancelled,
    ProgressFn,
    TranscriptionResult,
)

CHUNK_SECONDS = 28.0
WHISPER_LANGS = ["en", "ur", "hi", "ar", "es", "fr", "de", "it", "pt", "zh", "ja"]


class WhisperSherpaAdapter(ASRAdapter):
    def __init__(self, model_id: str, revision: str, model_dir: Path, threads: int = 1) -> None:
        super().__init__(model_id, revision, model_dir, threads)
        self._recognizers: dict[str, Any] = {}

    def capabilities(self) -> Capabilities:
        return Capabilities(kind="asr", languages_tested=[], languages_experimental=WHISPER_LANGS,
                            devices=["cpu"], segment_timestamps=True, word_timestamps=False,
                            diarization=False, progress_reporting="numeric",
                            cancellation="between_sentences", output_sample_rate=16000,
                            notes=["Not verified with real weights in the development environment.",
                                   "Timestamps are ~28 s chunk boundaries.",
                                   "Transcripts can contain errors; review before use."])

    def _files(self) -> tuple[Path, Path, Path]:
        def pick(pattern: str) -> Path:
            found = sorted(self.model_dir.glob(pattern))
            if not found:
                raise EngineUnavailable("Whisper model files are missing. Reinstall the model.")
            return found[0]

        enc = pick("*encoder.int8.onnx")
        dec = pick("*decoder.int8.onnx")
        tok = pick("*tokens.txt")
        return enc, dec, tok

    def load(self, language: str = "") -> None:  # type: ignore[override]
        with self._lock:
            if language in self._recognizers:
                return
            import sherpa_onnx as so

            enc, dec, tok = self._files()
            self._recognizers = {language: so.OfflineRecognizer.from_whisper(
                encoder=str(enc), decoder=str(dec), tokens=str(tok), language=language,
                task="transcribe", num_threads=self.threads)}
            self._loaded = True

    def unload(self) -> None:
        with self._lock:
            self._recognizers = {}
            self._loaded = False

    def transcribe(self, samples: np.ndarray, sample_rate: int, language: str | None,
                   progress: ProgressFn, should_cancel: Callable[[], bool]) -> TranscriptionResult:
        lang = language or ""  # "" = let Whisper detect
        if lang not in self._recognizers:
            progress(None, "Loading model")
            self.load(lang)
        rec = self._recognizers[lang]
        step = int(CHUNK_SECONDS * sample_rate)
        total = max(1, int(np.ceil(len(samples) / step)))
        segments: list[dict[str, Any]] = []
        detected: str | None = None
        for i in range(total):
            if should_cancel():
                raise GenerationCancelled("Transcription was cancelled.")
            progress(i / total, f"Transcribing chunk {i + 1} of {total}")
            chunk = samples[i * step:(i + 1) * step]
            try:
                stream = rec.create_stream()
                stream.accept_waveform(sample_rate, chunk.astype(np.float32))
                rec.decode_stream(stream)
                res = stream.result
            except Exception as e:  # noqa: BLE001
                raise EngineError(f"Transcription failed: {type(e).__name__}", retryable=True) from e
            text = (res.text or "").strip()
            detected = detected or (getattr(res, "lang", "") or "").strip("<|>") or None
            if text:
                segments.append({"start": round(i * CHUNK_SECONDS, 2),
                                 "end": round(min(len(samples) / sample_rate, (i + 1) * CHUNK_SECONDS), 2),
                                 "text": text})
        progress(1.0, "Done")
        return TranscriptionResult(text="\n".join(s["text"] for s in segments),
                                   language=detected or language, segments=segments,
                                   timestamp_kind="chunk")
