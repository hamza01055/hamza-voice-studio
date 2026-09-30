"""Explicit, previewable Roman Urdu -> Urdu script conversion.

Dictionary-based only: words found in the table are converted, everything else
(English words, names, numbers, unknown Roman Urdu) is left unchanged and reported.
This is NOT a reliable transliterator; the user must review the preview.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

WORDS: dict[str, str] = {
    "hai": "ہے", "hain": "ہیں", "tha": "تھا", "thi": "تھی", "thay": "تھے", "the": "تھے",
    "ki": "کی", "ka": "کا", "ke": "کے", "ko": "کو", "se": "سے", "mein": "میں", "main": "میں",
    "par": "پر", "aur": "اور", "ya": "یا", "bhi": "بھی", "nahi": "نہیں", "nahin": "نہیں",
    "kya": "کیا", "kyun": "کیوں", "kaise": "کیسے", "kab": "کب", "kahan": "کہاں", "kaun": "کون",
    "ap": "آپ", "aap": "آپ", "hum": "ہم", "tum": "تم", "wo": "وہ", "woh": "وہ", "yeh": "یہ",
    "ye": "یہ", "is": "اس", "us": "اس", "un": "ان", "in": "ان", "mera": "میرا", "meri": "میری",
    "mere": "میرے", "apna": "اپنا", "apni": "اپنی", "hamara": "ہمارا", "tumhara": "تمہارا",
    "acha": "اچھا", "achha": "اچھا", "bohat": "بہت", "bahut": "بہت", "shukriya": "شکریہ",
    "salam": "سلام", "assalam": "السلام", "alaikum": "علیکم", "ji": "جی", "haan": "ہاں",
    "kal": "کل", "aaj": "آج", "abhi": "ابھی", "phir": "پھر", "sab": "سب", "kuch": "کچھ",
    "din": "دن", "raat": "رات", "saal": "سال", "mahina": "مہینہ", "hafta": "ہفتہ", "waqt": "وقت",
    "log": "لوگ", "ghar": "گھر", "kaam": "کام", "baat": "بات", "pani": "پانی", "khana": "کھانا",
    "karna": "کرنا", "karo": "کرو", "karein": "کریں", "kar": "کر", "kiya": "کیا", "gaya": "گیا",
    "gayi": "گئی", "hoga": "ہوگا", "hogi": "ہوگی", "ho": "ہو", "hona": "ہونا", "raha": "رہا",
    "rahi": "رہی", "rahe": "رہے", "sakta": "سکتا", "sakti": "سکتی", "chahiye": "چاہیے",
    "lekin": "لیکن", "magar": "مگر", "agar": "اگر", "to": "تو", "tou": "تو", "jab": "جب",
    "tak": "تک", "liye": "لیے", "sath": "ساتھ", "saath": "ساتھ", "pehle": "پہلے", "baad": "بعد",
    "zaroor": "ضرور", "shayad": "شاید", "sirf": "صرف", "ek": "ایک", "do": "دو", "teen": "تین",
    "fee": "فیس", "fees": "فیس",
}

# Tokens that collide with common English words; converted only when explicitly enabled.
AMBIGUOUS = {"is", "us", "in", "to", "the", "do", "main", "par", "fee", "log", "kal", "ho"}


@dataclass
class TransliterationResult:
    text: str
    converted: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    ambiguous_skipped: list[str] = field(default_factory=list)
    notice: str = ("Dictionary-based conversion. Unknown words, English words and names were left "
                   "unchanged. Review the result before using it.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def transliterate(text: str, convert_ambiguous: bool = False) -> TransliterationResult:
    res = TransliterationResult(text="")

    def repl(m: re.Match[str]) -> str:
        w = m.group(0)
        key = w.lower()
        if key in WORDS and (convert_ambiguous or key not in AMBIGUOUS):
            res.converted.append(w)
            return WORDS[key]
        if key in AMBIGUOUS:
            res.ambiguous_skipped.append(w)
        elif not w.isdigit():
            res.unchanged.append(w)
        return w

    out = re.sub(r"[A-Za-z]+|\d+", repl, text)
    if res.converted:
        out = out.replace("?", "؟")
        out = re.sub(r"(?<!\d),|,(?!\d)", "،", out)  # keep thousands separators
        out = re.sub(r"(?<=[؀-ۿ])\.(?=\s|$)", "۔", out)
    res.text = out
    res.unchanged = sorted(set(res.unchanged))
    res.ambiguous_skipped = sorted(set(res.ambiguous_skipped))
    return res
