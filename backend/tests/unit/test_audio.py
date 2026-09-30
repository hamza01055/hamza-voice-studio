import numpy as np

from app.audio.analysis import analyse, check_generated, check_reference
from app.audio.assemble import Piece, assemble, edge_fade

SR = 16000


def tone(sec: float, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(sec * SR)) / SR
    return (amp * np.sin(2 * np.pi * 200 * t)).astype(np.float32)


def test_generated_empty_nan_silent_rejected():
    assert check_generated(np.zeros(0, np.float32), SR, "hello").errors
    x = tone(1.0)
    x[5] = np.nan
    assert any("invalid" in e for e in check_generated(x, SR, "hello").errors)
    assert any("silent" in e for e in check_generated(np.zeros(SR, np.float32), SR, "hello").errors)


def test_generated_warnings_truncation_and_clipping():
    text = "word " * 60  # 300 chars -> expected >= ~12 s
    r = check_generated(tone(1.0), SR, text)
    assert not r.errors and any("shorter" in w for w in r.warnings)
    clipped = np.clip(tone(3.0, amp=2.0), -1, 1)
    assert any("clipped" in w for w in check_generated(clipped, SR, "short text here").warnings)


def test_generated_excessive_silence_warning():
    x = np.concatenate([tone(1.0), np.zeros(SR * 3, np.float32), tone(1.0)])
    r = check_generated(x, SR, "a short sentence with some words in it")
    assert any("silence" in w for w in r.warnings)


def test_reference_checks():
    assert check_reference(tone(1.0), SR, native_sr=SR, channels=1, min_seconds=2, max_seconds=30).errors
    assert check_reference(tone(40), SR, native_sr=SR, channels=1, min_seconds=2, max_seconds=30).errors
    quiet = tone(5, amp=0.0001)
    assert any("silent" in e for e in check_reference(quiet, SR, native_sr=SR, channels=1,
                                                      min_seconds=2, max_seconds=30).errors)
    ok = check_reference(tone(5), 8000, native_sr=8000, channels=2, min_seconds=2, max_seconds=30)
    assert not ok.errors
    assert any("8000" in w for w in ok.warnings) and any("channels" in w for w in ok.warnings)
    assert any("Multiple-speaker" in w for w in ok.warnings)


def test_analyse_leading_trailing_silence():
    x = np.concatenate([np.zeros(SR // 2, np.float32), tone(1), np.zeros(SR, np.float32)])
    r = analyse(x, SR)
    assert 0.4 <= r.leading_silence <= 0.6 and 0.9 <= r.trailing_silence <= 1.1


def test_assemble_order_pauses_no_overlap():
    a, b, c = tone(1.0), tone(0.5), tone(0.25)
    audio, spans = assemble([Piece(a, SR, 500), Piece(b, SR, 250), Piece(c, SR, 9999)], SR)
    # last pause is not appended
    assert len(audio) == len(a) + SR // 2 + len(b) + SR // 4 + len(c)
    assert spans[0] == (0.0, 1.0)
    assert spans[1][0] == 1.5 and spans[2][0] == 1.5 + 0.5 + 0.25
    for (s0, e0), (s1, _e1) in zip(spans, spans[1:], strict=False):
        assert s1 >= e0  # never overlapping


def test_edge_fade_removes_clicks():
    x = np.ones(SR, np.float32)
    y = edge_fade(x, SR)
    assert y[0] == 0.0 and y[-1] == 0.0 and y[SR // 2] == 1.0
