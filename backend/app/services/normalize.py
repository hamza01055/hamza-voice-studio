"""Testable text normalisation.

The original script is never modified; normalisation produces a separate
``normalized_text`` used only for generation, plus a list of changes so the user can
preview exactly what will be spoken.

Only English verbalisation of numbers/currency/dates is implemented. For Urdu
(``ur``) and Roman Urdu (``ur-latn``) numbers are left untouched and a warning is
returned, because a wrong verbalisation would change meaning.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from app.services import numbers as num

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
MONTH_RE = "|".join(MONTHS + [m[:3] for m in MONTHS])
MONTH_LOOKUP = {m.lower(): m for m in MONTHS} | {m[:3].lower(): m for m in MONTHS}

ABBREVIATIONS = {
    "Dr.": "Doctor", "Mr.": "Mister", "Mrs.": "Missus", "Ms.": "Miz", "Prof.": "Professor",
    "e.g.": "for example", "i.e.": "that is", "etc.": "et cetera", "vs.": "versus",
    "approx.": "approximately", "No.": "number",
}

ARABIC_SCRIPT = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
LATIN = re.compile(r"[A-Za-z]")
# Zero-width characters except ZWNJ (U+200C), which Urdu/Persian text legitimately uses.
ZERO_WIDTH = re.compile(r"[​‍⁠﻿]")
URL_RE = re.compile(r"\bhttps?://[^\s]+|\bwww\.[^\s]+", re.I)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


@dataclass
class Change:
    rule: str
    original: str
    replacement: str


@dataclass
class NormalizationResult:
    text: str
    changes: list[Change] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_scripts(text: str) -> list[str]:
    out = []
    if ARABIC_SCRIPT.search(text):
        out.append("arabic")
    if LATIN.search(text):
        out.append("latin")
    return out


def is_english(language: str) -> bool:
    return language.lower().startswith("en")


def _sub(pattern: re.Pattern[str] | str, repl: Any, text: str, rule: str,
         changes: list[Change], flags: int = 0) -> str:
    rx = re.compile(pattern, flags) if isinstance(pattern, str) else pattern

    def _r(m: re.Match[str]) -> str:
        new = repl(m) if callable(repl) else m.expand(repl)
        if new != m.group(0):
            changes.append(Change(rule, m.group(0), new))
        return new

    return rx.sub(_r, text)


def _int(s: str) -> int:
    return int(s.replace(",", ""))


def _money(amount: str, unit_singular: str, unit_plural: str, sub_unit: tuple[str, str] | None) -> str:
    whole, _, frac = amount.replace(",", "").partition(".")
    w = int(whole or "0")
    out = f"{num.cardinal(w)} {unit_singular if w == 1 else unit_plural}"
    if frac and sub_unit and int(frac[:2].ljust(2, "0")):
        c = int(frac[:2].ljust(2, "0"))
        out += f" and {num.cardinal(c)} {sub_unit[0] if c == 1 else sub_unit[1]}"
    elif frac:
        out = f"{num.decimal(whole + '.' + frac)} {unit_plural}"
    return out


AMOUNT = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"


def apply_overrides(text: str, overrides: list[dict[str, Any]], language: str,
                    changes: list[Change]) -> str:
    for o in overrides:
        src = (o.get("pattern") or "").strip()
        dst = o.get("replacement") or ""
        lang = (o.get("language") or "").lower()
        if not src or (lang and not language.lower().startswith(lang)):
            continue
        flags = 0 if o.get("case_sensitive") else re.I
        pat = re.escape(src)
        if o.get("whole_word", True):
            pat = rf"(?<!\w){pat}(?!\w)"
        text = _sub(pat, lambda _m, d=dst: d, text, "pronunciation_override", changes, flags)
    return text


def normalize(text: str, language: str = "en-us",
              overrides: list[dict[str, Any]] | None = None) -> NormalizationResult:
    changes: list[Change] = []
    warnings: list[str] = []
    t = unicodedata.normalize("NFC", text)
    t = ZERO_WIDTH.sub("", t)
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r"\s*\n\s*", " ", t).strip()
    scripts = detect_scripts(t)

    t = apply_overrides(t, overrides or [], language, changes)

    if not is_english(language):
        if re.search(r"[0-9۰-۹٠-٩]", t):
            warnings.append("Numbers, dates and currency are not verbalised for this language; "
                            "write them out in words if the model misreads them.")
        return NormalizationResult(t, changes, warnings, scripts)

    # URLs and e-mail addresses
    def speak_url(m: re.Match[str]) -> str:
        u = re.sub(r"^https?://", "", m.group(0), flags=re.I).rstrip("/.,;")
        return u.replace(".", " dot ").replace("/", " slash ").replace("-", " dash ").strip()

    t = _sub(URL_RE, speak_url, t, "url", changes)
    t = _sub(EMAIL_RE, lambda m: m.group(0).replace("@", " at ").replace(".", " dot "), t, "email",
             changes)

    # Currency
    t = _sub(rf"(?:\bRs\.?|\bPKR|₨)\s?{AMOUNT}", lambda m: _money(m.group(1), "rupee", "rupees", None),
             t, "currency", changes)
    t = _sub(rf"\${AMOUNT}", lambda m: _money(m.group(1), "dollar", "dollars", ("cent", "cents")),
             t, "currency", changes)
    t = _sub(rf"£{AMOUNT}", lambda m: _money(m.group(1), "pound", "pounds", ("penny", "pence")),
             t, "currency", changes)
    t = _sub(rf"€{AMOUNT}", lambda m: _money(m.group(1), "euro", "euros", ("cent", "cents")),
             t, "currency", changes)

    # ISO dates 2026-10-15
    def iso(m: re.Match[str]) -> str:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            return m.group(0)
        return f"{MONTHS[mo - 1]} {num.ordinal(d)}, {num.year(y)}"

    t = _sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", iso, t, "date", changes)

    # "15 October [2026]" and "October 15[, 2026]"
    def dm(m: re.Match[str]) -> str:
        d = int(m.group(1))
        if not 1 <= d <= 31:
            return m.group(0)
        out = f"{num.ordinal(d)} {MONTH_LOOKUP[m.group(2).lower().rstrip('.')]}"
        if m.group(3):
            out += f" {num.year(int(m.group(3)))}"
        return out

    t = _sub(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_RE})\.?\b(?:,?\s+(\d{{4}})\b)?", dm, t, "date",
             changes, re.I)

    def md(m: re.Match[str]) -> str:
        d = int(m.group(2))
        if not 1 <= d <= 31:
            return m.group(0)
        out = f"{MONTH_LOOKUP[m.group(1).lower().rstrip('.')]} {num.ordinal(d)}"
        if m.group(3):
            out += f", {num.year(int(m.group(3)))}"
        return out

    t = _sub(rf"\b({MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}})\b)?", md, t, "date",
             changes, re.I)

    # Times 10:30
    def time_(m: re.Match[str]) -> str:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            return m.group(0)
        if mi == 0:
            return f"{num.cardinal(h)} o'clock"
        mins = num.cardinal(mi) if mi >= 10 else f"oh {num.cardinal(mi)}"
        return f"{num.cardinal(h)} {mins}"

    t = _sub(r"\b(\d{1,2}):(\d{2})\b", time_, t, "time", changes)

    # Abbreviations
    for abbr, full in ABBREVIATIONS.items():
        t = _sub(rf"(?<!\w){re.escape(abbr)}(?=\s|$)", lambda _m, f=full: f, t, "abbreviation", changes)

    # Percentages, ordinals, decimals, integers
    t = _sub(rf"{AMOUNT}\s?%", lambda m: f"{_num_words(m.group(1))} percent", t, "number", changes)
    t = _sub(r"\b(\d+)(st|nd|rd|th)\b", lambda m: num.ordinal(int(m.group(1))), t, "number", changes)
    t = _sub(rf"(?<![\w.]){AMOUNT}(?![\w])", lambda m: _num_words(m.group(1)), t, "number", changes)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return NormalizationResult(t, changes, warnings, scripts)


def _num_words(s: str) -> str:
    s = s.replace(",", "")
    if "." in s:
        return num.decimal(s)
    return num.cardinal(int(s))
