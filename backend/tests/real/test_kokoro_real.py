"""REAL inference smoke tests. Skipped unless Kokoro weights are installed.

Run with:  HVS_REAL_MODELS_DIR=<data dir>/models pytest -m real tests/real
(<data dir> defaults to the platform app-data folder, e.g. %LOCALAPPDATA%\\HamzaVoiceStudio)
"""

import os
import time
from pathlib import Path

import numpy as np
import pytest

from app.audio.analysis import check_generated
from app.core.config import default_data_dir
from app.engines.base import InvalidEngineRequest, SynthesisRequest
from app.engines.kokoro_sherpa import KokoroSherpaAdapter

MODELS = Path(os.environ.get("HVS_REAL_MODELS_DIR") or default_data_dir() / "models")
KOKORO = MODELS / "kokoro-multi-lang-v1_0"

pytestmark = [pytest.mark.real,
              pytest.mark.skipif(not (KOKORO / "model.onnx").exists(), reason="Kokoro weights not installed")]


@pytest.fixture(scope="module")
def kokoro():
    a = KokoroSherpaAdapter("kokoro-multi-lang-v1_0", "real", KOKORO, threads=max(1, (os.cpu_count() or 2)))
    t = time.perf_counter()
    a.load("en-us")
    a.load_seconds = time.perf_counter() - t  # type: ignore[attr-defined]
    return a


@pytest.mark.parametrize("lang,voice,text", [
    ("en-us", "af_heart", "Hello there. This is a real speech generation test."),
    ("en-gb", "bm_george", "Good afternoon, and welcome to the studio."),
])
def test_real_synthesis(kokoro, lang, voice, text):
    prog = []
    res = kokoro.synthesize(SynthesisRequest(text=text, language=lang, voice=voice),
                            lambda f, s: prog.append(f), lambda: False)
    assert res.sample_rate == 24000
    rep = check_generated(res.samples, res.sample_rate, text)
    assert not rep.errors, rep.errors
    assert 1.0 < rep.duration < 12
    assert any(p == 1.0 for p in prog if p is not None)  # real progress reached completion


def test_real_repeat_takes_differ_only_subtly(kokoro):
    """Documents measured behaviour: not bit-identical, but same length/timing."""
    req = SynthesisRequest(text="Same input twice.", language="en-us", voice="am_adam")
    a = kokoro.synthesize(req, lambda *_: None, lambda: False).samples
    b = kokoro.synthesize(req, lambda *_: None, lambda: False).samples
    assert abs(len(a) - len(b)) / len(a) < 0.02
    n = min(len(a), len(b))
    assert not np.array_equal(a[:n], b[:n])
    assert kokoro.capabilities().take_variation == "subtle"


def test_real_cancel_between_sentences(kokoro):
    from app.engines.base import GenerationCancelled

    with pytest.raises(GenerationCancelled):
        kokoro.synthesize(SynthesisRequest(text="One. Two. Three. Four.", language="en-us", voice="af_heart"),
                          lambda *_: None, lambda: True)


def test_real_voice_language_mismatch(kokoro):
    with pytest.raises(InvalidEngineRequest):
        kokoro.validate_request(SynthesisRequest(text="Hola", language="es", voice="af_heart"))
