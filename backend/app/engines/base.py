"""Engine adapter interface.

Every inference backend implements :class:`TTSAdapter` or :class:`ASRAdapter`. The UI
is driven by :class:`Capabilities` so controls only appear when the engine really
implements them.
"""

from __future__ import annotations

import abc
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


class EngineError(Exception):
    """Base for engine failures. ``retryable`` marks transient problems."""

    code = "engine_error"
    retryable = False

    def __init__(self, message: str, *, code: str | None = None, retryable: bool | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if retryable is not None:
            self.retryable = retryable


class EngineUnavailable(EngineError):
    code = "model_not_installed"


class InvalidEngineRequest(EngineError):
    code = "invalid_engine_request"


class GenerationCancelled(EngineError):
    code = "cancelled"


class EngineOutOfMemory(EngineError):
    code = "out_of_memory"
    retryable = True


@dataclass
class VoiceOption:
    id: str
    label: str
    language: str
    gender: str | None = None


@dataclass
class Capabilities:
    kind: str  # "tts" | "asr"
    languages_tested: list[str] = field(default_factory=list)
    languages_experimental: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=lambda: ["cpu"])
    preset_voices: list[VoiceOption] = field(default_factory=list)
    voice_cloning: bool = False
    voice_design: bool = False
    reference_formats: list[str] = field(default_factory=list)
    reference_min_seconds: float | None = None
    reference_max_seconds: float | None = None
    needs_reference_transcript: bool = False
    streaming: bool = False
    speed_control: bool = False
    speed_range: tuple[float, float] | None = None
    style_controls: list[str] = field(default_factory=list)
    seed_support: bool = False
    deterministic: bool = False
    # How much repeated takes with identical settings differ: none | subtle | substantial | unknown
    take_variation: str = "unknown"
    max_input_chars: int = 1000
    output_sample_rate: int | None = None
    progress_reporting: str = "none"  # none | per_sentence | numeric
    cancellation: str = "none"  # none | between_sentences | immediate
    word_timestamps: bool = False
    segment_timestamps: bool = False
    diarization: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# (progress 0..1 or None, stage text) -> None
ProgressFn = Callable[[float | None, str], None]


@dataclass
class SynthesisRequest:
    text: str
    language: str
    voice: str | None = None  # preset voice id
    reference_audio: np.ndarray | None = None
    reference_sample_rate: int | None = None
    reference_transcript: str | None = None
    speed: float = 1.0
    seed: int | None = None


@dataclass
class SynthesisResult:
    samples: np.ndarray
    sample_rate: int
    parameters: dict[str, Any]


@dataclass
class TranscriptionResult:
    text: str
    language: str | None
    segments: list[dict[str, Any]]
    timestamp_kind: str  # none | chunk | segment


class BaseAdapter(abc.ABC):
    model_id: str
    revision: str

    def __init__(self, model_id: str, revision: str, model_dir: Path, threads: int = 1) -> None:
        self.model_id = model_id
        self.revision = revision
        self.model_dir = model_dir
        self.threads = threads
        self._loaded = False
        self._lock = threading.Lock()

    @abc.abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abc.abstractmethod
    def load(self) -> None: ...

    def unload(self) -> None:
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def estimate_resources(self) -> dict[str, Any]:
        return {}


class TTSAdapter(BaseAdapter):
    def validate_request(self, req: SynthesisRequest) -> None:
        caps = self.capabilities()
        if not req.text.strip():
            raise InvalidEngineRequest("The text is empty.")
        if len(req.text) > caps.max_input_chars:
            raise InvalidEngineRequest(
                f"The text has {len(req.text)} characters; this model accepts at most "
                f"{caps.max_input_chars} per segment. Split the segment.")
        langs = caps.languages_tested + caps.languages_experimental
        if req.language not in langs:
            raise InvalidEngineRequest(
                f"Language '{req.language}' is not supported by {self.model_id}.",
                code="unsupported_language")
        if req.reference_audio is not None and not caps.voice_cloning:
            raise InvalidEngineRequest(f"{self.model_id} cannot use reference audio (no voice cloning).")
        if caps.speed_range and not (caps.speed_range[0] <= req.speed <= caps.speed_range[1]):
            raise InvalidEngineRequest(
                f"Speed must be between {caps.speed_range[0]} and {caps.speed_range[1]}.")

    @abc.abstractmethod
    def synthesize(self, req: SynthesisRequest, progress: ProgressFn,
                   should_cancel: Callable[[], bool]) -> SynthesisResult: ...


class ASRAdapter(BaseAdapter):
    @abc.abstractmethod
    def transcribe(self, samples: np.ndarray, sample_rate: int, language: str | None,
                   progress: ProgressFn, should_cancel: Callable[[], bool]) -> TranscriptionResult: ...
