import pytest

from app.services import numbers as num
from app.services.normalize import detect_scripts, normalize
from app.services.roman_urdu import transliterate
from app.services.segmentation import segment, split_long, split_sentences
from app.services.subtitles import to_srt, to_vtt


@pytest.mark.parametrize("n,words", [
    (0, "zero"), (13, "thirteen"), (21, "twenty-one"), (100, "one hundred"),
    (2500, "two thousand five hundred"), (1_000_001, "one million one"), (-5, "minus five")])
def test_cardinal(n, words):
    assert num.cardinal(n) == words


@pytest.mark.parametrize("n,words", [(1, "first"), (2, "second"), (15, "fifteenth"), (21, "twenty-first"),
                                     (30, "thirtieth"), (112, "one hundred twelfth")])
def test_ordinal(n, words):
    assert num.ordinal(n) == words


@pytest.mark.parametrize("y,words", [(1999, "nineteen ninety-nine"), (2005, "two thousand five"),
                                     (2026, "twenty twenty-six"), (1900, "nineteen hundred"),
                                     (1905, "nineteen oh five")])
def test_year(y, words):
    assert num.year(y) == words


def test_evaluation_example_meaning_preserved():
    src = "AI ki training 15 October ko hai, fee Rs. 2,500 hai."
    r = normalize(src, "en-us")
    assert r.text == "AI ki training fifteenth October ko hai, fee two thousand five hundred rupees hai."
    # Roman Urdu tokens and the English token "AI" are preserved verbatim
    for tok in ("AI", "ki", "ko", "hai", "fee", "training"):
        assert tok in r.text.split() or tok + "," in r.text
    rules = {c.rule for c in r.changes}
    assert {"date", "currency"} <= rules


def test_currency_and_decimals():
    assert normalize("It costs $3.50.").text == "It costs three dollars and fifty cents."
    assert normalize("£1").text == "one pound"
    assert normalize("Pi is 3.14").text == "Pi is three point one four"


def test_dates_times_percent_abbrev():
    r = normalize("Dr. Ali met Mr. Khan on 2026-10-15 at 10:05, i.e. 15% late.")
    assert r.text == ("Doctor Ali met Mister Khan on October fifteenth, twenty twenty-six at ten oh five, "
                      "that is fifteen percent late.")
    assert normalize("October 3, 1999").text == "October third, nineteen ninety-nine"
    assert normalize("Meet at 9:00").text == "Meet at nine o'clock"


def test_urls_and_emails():
    r = normalize("Visit https://example.com/docs or mail me@site.org")
    assert "example dot com slash docs" in r.text
    assert "me at site dot org" in r.text


def test_invalid_dates_untouched():
    assert "32" in normalize("32 October").text or "thirty-two" in normalize("32 October").text
    assert normalize("2026-13-45").text != "" and "October" not in normalize("2026-13-45").text


def test_urdu_numbers_not_verbalised_with_warning():
    src = "آپ کی فیس 2500 روپے ہے۔"
    r = normalize(src, "ur")
    assert r.text == src
    assert r.warnings and "not verbalised" in r.warnings[0]
    assert r.scripts == ["arabic"]


def test_mixed_script_detection_and_unicode():
    assert detect_scripts("Hello دنیا") == ["arabic", "latin"]
    # NFC normalisation + zero-width space removed, ZWNJ preserved
    r = normalize("Café x​y ‌", "ur")
    assert "Café" in r.text and "​" not in r.text and "‌" in r.text


def test_pronunciation_overrides_language_scoped():
    ov = [{"pattern": "Hamza", "replacement": "Hum-zah", "language": "en"},
          {"pattern": "AI", "replacement": "A.I.", "language": "ur", "case_sensitive": True}]
    assert normalize("Hamza uses AI", "en-us", ov).text == "Hum-zah uses AI"
    assert normalize("Hamza uses AI", "ur", ov).text == "Hamza uses A.I."
    # whole-word only
    assert normalize("Hamzas", "en-us", ov).text == "Hamzas"


def test_sentence_split_abbrev_decimals_urdu():
    s = split_sentences('Dr. Smith paid 3.5 kg. He said: "Hi!" Then left. یہ جملہ ہے۔ کیا یہ ہے؟ OK')
    assert s == ['Dr. Smith paid 3.5 kg.', 'He said: "Hi!"', 'Then left.', 'یہ جملہ ہے۔', 'کیا یہ ہے؟', 'OK']


def test_segment_modes_preserve_order_and_text():
    text = "Para one. Still one.\n\nPara two!\n\n\n  Para three?  "
    assert segment(text, "paragraph") == ["Para one. Still one.", "Para two!", "Para three?"]
    assert segment(text, "sentence") == ["Para one.", "Still one.", "Para two!", "Para three?"]


def test_long_paragraph_is_split_under_limit():
    long = " ".join(["This is a fairly long sentence, with a comma, and more words."] * 30)
    parts = segment(long, "paragraph", max_chars=300)
    assert all(len(p) <= 300 for p in parts)
    assert " ".join(parts).split() == long.split()
    assert split_long("a " * 10, 5)


def test_transliteration_is_explicit_and_conservative():
    r = transliterate("AI ki training 15 October ko hai, fee Rs. 2,500 hai.")
    assert "کی" in r.text and "کو" in r.text and "ہے" in r.text
    assert "AI" in r.text and "training" in r.text and "2,500" in r.text  # thousands separator kept
    assert "fee" in r.ambiguous_skipped
    assert "training" in r.unchanged
    assert "Review" in r.notice


def test_subtitles_use_given_timestamps():
    segs = [{"start": 0.0, "end": 1.5, "text": "Hello"}, {"start": 61.25, "end": 3725.0, "text": "World"}]
    srt = to_srt(segs)
    assert "00:00:00,000 --> 00:00:01,500" in srt and "00:01:01,250 --> 01:02:05,000" in srt
    assert to_vtt(segs).startswith("WEBVTT")
