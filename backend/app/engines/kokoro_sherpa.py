"""Kokoro-82M v1.0 via the sherpa-onnx runtime (CPU, ONNX).

Facts verified in development (see docs/BENCHMARKS.md):
* Output is 24 kHz mono float32.
* The sherpa-onnx generation callback fires once per sentence with a real progress
  fraction; returning 0 from it stops generation after the current sentence. So
  cancellation takes effect *between sentences*, not instantly.
* Kokoro has no user-controllable seed. The vocoder's noise excitation is random, so
  repeated runs with identical settings are NOT bit-identical: timing and prosody are
  (near) identical, waveform detail differs (measured ~15-17 dB SNR between runs).
* The G2P language is fixed when the runtime is constructed, so switching language
  reloads the runtime (a few seconds on CPU).
"""

from __future__ import annotations

import gc
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from app.engines.base import (
    Capabilities,
    EngineError,
    EngineOutOfMemory,
    EngineUnavailable,
    GenerationCancelled,
    InvalidEngineRequest,
    ProgressFn,
    SynthesisRequest,
    SynthesisResult,
    TTSAdapter,
    VoiceOption,
)

SPEAKERS = (
    "af_alloy,af_aoede,af_bella,af_heart,af_jessica,af_kore,af_nicole,af_nova,af_river,af_sarah,"
    "af_sky,am_adam,am_echo,am_eric,am_fenrir,am_liam,am_michael,am_onyx,am_puck,am_santa,"
    "bf_alice,bf_emma,bf_isabella,bf_lily,bm_daniel,bm_fable,bm_george,bm_lewis,ef_dora,em_alex,"
    "ff_siwis,hf_alpha,hf_beta,hm_omega,hm_psi,if_sara,im_nicola,jf_alpha,jf_gongitsune,jf_nezumi,"
    "jf_tebukuro,jm_kumo,pf_dora,pm_alex,pm_santa,zf_xiaobei,zf_xiaoni,zf_xiaoxiao,zf_xiaoyi,"
    "zm_yunjian,zm_yunxi,zm_yunxia,zm_yunyang,em_santa"
).split(",")
SPEAKER_IDS = {name: i for i, name in enumerate(SPEAKERS)}

# language -> (espeak voice, lexicon files, rule fsts, voice prefix)
LANGUAGES: dict[str, dict[str, Any]] = {
    "en-us": {"espeak": "en-us", "lexicon": ["lexicon-us-en.txt"], "prefix": "a"},
    "en-gb": {"espeak": "en-gb-x-rp", "lexicon": ["lexicon-gb-en.txt"], "prefix": "b"},
    "es": {"espeak": "es", "lexicon": [], "prefix": "e"},
    "fr": {"espeak": "fr-fr", "lexicon": [], "prefix": "f"},
    "hi": {"espeak": "hi", "lexicon": [], "prefix": "h"},
    "it": {"espeak": "it", "lexicon": [], "prefix": "i"},
    "pt-br": {"espeak": "pt-br", "lexicon": [], "prefix": "p"},
    "zh": {"espeak": "", "lexicon": ["lexicon-us-en.txt", "lexicon-zh.txt"], "prefix": "z",
           "fsts": ["phone-zh.fst", "date-zh.fst", "number-zh.fst"]},
    # Urdu has no Kokoro voice. eSpeak-NG Urdu phonemes + a Hindi voice produce audio,
    # but quality has NOT been evaluated. Only exposed when the user enables
    # unevaluated experimental languages in Settings.
    "ur": {"espeak": "ur", "lexicon": [], "prefix": "h"},
}
TESTED = ["en-us", "en-gb"]
EXPERIMENTAL = ["es", "fr", "hi", "it", "pt-br", "zh"]
UNEVALUATED = ["ur"]

REQUIRED_FILES = ["model.onnx", "voices.bin", "tokens.txt", "espeak-ng-data"]


def _gender(name: str) -> str:
    return "female" if name[1] == "f" else "male"


class KokoroSherpaAdapter(TTSAdapter):
    def __init__(self, model_id: str, revision: str, model_dir: Path, threads: int = 1,
                 include_unevaluated: bool = False) -> None:
        super().__init__(model_id, revision, model_dir, threads)
        self._tts: Any = None
        self._lang: str | None = None
        self.include_unevaluated = include_unevaluated

    # ---- capabilities -------------------------------------------------
    def capabilities(self) -> Capabilities:
        voices = []
        for name in SPEAKERS:
            langs = [lang for lang, cfg in LANGUAGES.items()
                     if cfg["prefix"] == name[0] and lang != "ur"]
            if not langs:
                continue  # e.g. Japanese voices: no working G2P in this runtime
            voices.append(VoiceOption(id=name, label=name.split("_", 1)[1].title(),
                                      language=langs[0], gender=_gender(name)))
        return Capabilities(
            kind="tts",
            languages_tested=list(TESTED),
            languages_experimental=list(EXPERIMENTAL) + (list(UNEVALUATED) if self.include_unevaluated else []),
            devices=["cpu"],
            preset_voices=voices,
            voice_cloning=False,
            speed_control=True,
            speed_range=(0.5, 2.0),
            seed_support=False,
            deterministic=False,
            take_variation="subtle",
            max_input_chars=1500,
            output_sample_rate=24000,
            progress_reporting="per_sentence",
            cancellation="between_sentences",
            notes=[
                "No voice cloning: choose one of the built-in voices.",
                "Repeated takes with identical settings differ only subtly (same timing and "
                "intonation). Change speed or voice for a clearly different take.",
                "Cancellation takes effect after the sentence currently being generated.",
                "Japanese voices are hidden: this runtime has no Japanese text front-end.",
            ],
        )

    def voice_language(self, voice: str) -> str | None:
        for lang, cfg in LANGUAGES.items():
            if cfg["prefix"] == voice[:1] and lang != "ur":
                return lang
        return None

    # ---- lifecycle ------------------------------------------------------
    def check_files(self) -> None:
        missing = [f for f in REQUIRED_FILES if not (self.model_dir / f).exists()]
        if missing:
            raise EngineUnavailable(f"Model files are missing ({', '.join(missing)}). "
                                    "Reinstall the model from the Models page.")

    def load(self, language: str = "en-us") -> None:  # type: ignore[override]
        with self._lock:
            if self._tts is not None and self._lang == language:
                return
            self.check_files()
            import sherpa_onnx as so

            cfg = LANGUAGES[language]
            d = self.model_dir
            lex = ",".join(str(d / x) for x in cfg["lexicon"])
            fsts = ",".join(str(d / x) for x in cfg.get("fsts", []))
            self._tts = None
            gc.collect()
            try:
                kcfg = so.OfflineTtsKokoroModelConfig(
                    model=str(d / "model.onnx"), voices=str(d / "voices.bin"),
                    tokens=str(d / "tokens.txt"), data_dir=str(d / "espeak-ng-data"),
                    lexicon=lex, lang=cfg["espeak"])
                tcfg = so.OfflineTtsConfig(
                    model=so.OfflineTtsModelConfig(kokoro=kcfg, num_threads=self.threads,
                                                   provider="cpu"),
                    rule_fsts=fsts, max_num_sentences=1)
                if not tcfg.validate():
                    raise EngineUnavailable("Model configuration is invalid; files may be corrupt. "
                                            "Reinstall the model.")
                self._tts = so.OfflineTts(tcfg)
            except MemoryError as e:
                raise EngineOutOfMemory("Not enough memory to load the model.") from e
            self._lang = language
            self._loaded = True

    def needs_load(self, language: str) -> bool:
        return self._tts is None or self._lang != language

    def unload(self) -> None:
        with self._lock:
            self._tts = None
            self._lang = None
            self._loaded = False
            gc.collect()

    def estimate_resources(self) -> dict[str, Any]:
        return {"ram_mb_approx": 900, "vram_mb": 0, "disk_mb": 384}

    # ---- inference -------------------------------------------------------
    def validate_request(self, req: SynthesisRequest) -> None:
        super().validate_request(req)
        if not req.voice or req.voice not in SPEAKER_IDS:
            raise InvalidEngineRequest("Choose one of the built-in Kokoro voices.", code="invalid_voice")
        if req.language not in LANGUAGES:
            raise InvalidEngineRequest(f"Language '{req.language}' is not supported.",
                                       code="unsupported_language")
        if LANGUAGES[req.language]["prefix"] != req.voice[0]:
            raise InvalidEngineRequest(
                f"Voice '{req.voice}' is a {self.voice_language(req.voice) or 'different'} voice and "
                f"cannot be used for '{req.language}'. Choose a voice for that language.",
                code="voice_language_mismatch")

    def synthesize(self, req: SynthesisRequest, progress: ProgressFn,
                   should_cancel: Callable[[], bool]) -> SynthesisResult:
        self.validate_request(req)
        if self.needs_load(req.language):
            progress(None, "Loading model")
            self.load(req.language)
        progress(0.0, "Generating speech")
        assert req.voice is not None  # checked by validate_request
        voice: str = req.voice
        cancelled = threading.Event()

        def cb(_samples: Any, frac: float) -> int:
            progress(float(frac), "Generating speech")
            if should_cancel():
                cancelled.set()
                return 0  # sherpa-onnx: 0 stops generation, 1 continues
            return 1

        try:
            with self._lock:
                audio = self._tts.generate(req.text, sid=SPEAKER_IDS[voice], speed=float(req.speed),
                                           callback=cb)
        except MemoryError as e:
            raise EngineOutOfMemory("Ran out of memory while generating.") from e
        except Exception as e:  # noqa: BLE001 - runtime raises generic errors
            raise EngineError(f"The model failed while generating: {type(e).__name__}",
                              retryable=True) from e
        if cancelled.is_set():
            raise GenerationCancelled("Generation was cancelled.")
        samples = np.asarray(audio.samples, dtype=np.float32)
        return SynthesisResult(samples=samples, sample_rate=int(audio.sample_rate),
                               parameters={"voice": req.voice, "speaker_id": SPEAKER_IDS[voice],
                                           "speed": req.speed, "language": req.language,
                                           "espeak_voice": LANGUAGES[req.language]["espeak"]})
