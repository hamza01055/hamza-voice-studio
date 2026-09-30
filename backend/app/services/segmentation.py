"""Split a script into paragraphs or sentences, preserving the original text."""

from __future__ import annotations

import re

ABBREV = {"dr", "mr", "mrs", "ms", "prof", "st", "vs", "etc", "e.g", "i.e", "no", "rs", "approx",
          "jr", "sr", "inc", "ltd", "co", "mt", "fig", "u.s", "u.k"}
# Sentence terminators: Latin . ! ?, Urdu full stop ۔ (U+06D4), Arabic question mark ؟,
# CJK 。！？, and the ellipsis character.
TERMINATORS = ".!?۔؟。！？…"


def split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
    return [p.strip() for p in parts if p.strip()]


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    out: list[str] = []
    start = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in TERMINATORS:
            j = i
            while j + 1 < n and (text[j + 1] in TERMINATORS or text[j + 1] in "\"'”’)»"):
                j += 1
            at_end = j + 1 >= n
            followed_by_space = not at_end and text[j + 1] == " "
            if at_end or followed_by_space:
                if ch == "." and not _is_boundary(text, start, i):
                    i = j + 1
                    continue
                out.append(text[start:j + 1].strip())
                start = j + 1
            i = j + 1
            continue
        i += 1
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def _is_boundary(text: str, start: int, dot: int) -> bool:
    word = re.findall(r"[\w.]+$", text[start:dot])
    w = word[0].lower() if word else ""
    if w in ABBREV:
        return False
    if len(w) == 1 and w.isalpha():  # initials: "J. Smith"
        return False
    return True


def split_long(sentence: str, max_chars: int) -> list[str]:
    """Break an over-long sentence at commas/semicolons, then at spaces."""
    if len(sentence) <= max_chars:
        return [sentence]
    parts: list[str] = []
    cur = ""
    for piece in re.split(r"(?<=[,;:،])\s+", sentence):
        if len(cur) + len(piece) + 1 <= max_chars:
            cur = f"{cur} {piece}".strip()
            continue
        if cur:
            parts.append(cur)
        while len(piece) > max_chars:
            cut = piece.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            parts.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        cur = piece
    if cur:
        parts.append(cur)
    return parts


def segment(text: str, mode: str = "paragraph", max_chars: int = 1000) -> list[str]:
    paragraphs = split_paragraphs(text)
    out: list[str] = []
    if mode == "sentence":
        for p in paragraphs:
            for s in split_sentences(p):
                out.extend(split_long(s, max_chars))
    else:
        for p in paragraphs:
            if len(p) <= max_chars:
                out.append(p)
            else:
                cur = ""
                for s in split_sentences(p):
                    for piece in split_long(s, max_chars):
                        if cur and len(cur) + len(piece) + 1 > max_chars:
                            out.append(cur)
                            cur = piece
                        else:
                            cur = f"{cur} {piece}".strip()
                if cur:
                    out.append(cur)
    return out
