"""English number verbalisation (cardinals, ordinals, years, decimals)."""

from __future__ import annotations

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
        "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
SCALES = [(10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (1000, "thousand")]


def _under_1000(n: int) -> str:
    parts = []
    h, r = divmod(n, 100)
    if h:
        parts.append(f"{ONES[h]} hundred")
    if r:
        if r < 20:
            parts.append(ONES[r])
        else:
            t, o = divmod(r, 10)
            parts.append(TENS[t] + (f"-{ONES[o]}" if o else ""))
    return " ".join(parts)


def cardinal(n: int) -> str:
    if n < 0:
        return "minus " + cardinal(-n)
    if n < 20:
        return ONES[n]
    if n >= 10**15:
        return " ".join(ONES[int(d)] for d in str(n))
    parts = []
    for value, name in SCALES:
        q, n = divmod(n, value)
        if q:
            parts.append(f"{_under_1000(q)} {name}")
    if n:
        parts.append(_under_1000(n))
    return " ".join(parts)


_ORD_IRREGULAR = {"one": "first", "two": "second", "three": "third", "five": "fifth",
                  "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}


def ordinal(n: int) -> str:
    words = cardinal(n)
    head, sep, last = words.rpartition(" ")
    pre, dash, lastw = last.rpartition("-")
    if lastw in _ORD_IRREGULAR:
        lastw = _ORD_IRREGULAR[lastw]
    elif lastw.endswith("y"):
        lastw = lastw[:-1] + "ieth"
    else:
        lastw = lastw + "th"
    last = f"{pre}{dash}{lastw}"
    return f"{head}{sep}{last}"


def year(n: int) -> str:
    if 2000 <= n <= 2009:
        return cardinal(n)
    if 1100 <= n <= 2099:
        hi, lo = divmod(n, 100)
        if lo == 0:
            return f"{cardinal(hi)} hundred"
        if lo < 10:
            return f"{cardinal(hi)} oh {cardinal(lo)}"
        return f"{cardinal(hi)} {cardinal(lo)}"
    return cardinal(n)


def decimal(s: str) -> str:
    """'3.14' -> 'three point one four'."""
    whole, _, frac = s.partition(".")
    out = cardinal(int(whole or "0"))
    if frac:
        out += " point " + " ".join(ONES[int(d)] for d in frac)
    return out
