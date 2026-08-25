"""
Live market check — a standing stage of the factory line.

Before any book drafts, the current writing model verifies the commercial
parameters against the live market (web search): what length, word count and
trim size the genre's Amazon top sellers actually run right now. The house
presets are researched templates; this stage keeps them honest per book.

User-set values are respected: a parameter is only adjusted when it still
equals the house default (i.e. the publisher didn't choose it deliberately),
and only within sane bounds. The full check is stored on the book as
data["market_check"] so the publisher can always see what the market said.
"""

import re

from ..prose.models import GENRE_PRESETS
from .client import complete, extract_json

_TRIM_RE = re.compile(r"^\d+(\.\d+)?x\d+(\.\d+)?$")


def _valid_trim(t: str) -> str:
    t = (t or "").replace("″", "").replace('"', "").replace(" ", "").strip()
    if not _TRIM_RE.match(t):
        return ""
    w, h = (float(x) for x in t.split("x"))
    return t if 4.5 <= w <= 8.5 and 6.5 <= h <= 11.5 else ""


async def market_check(book: dict, ms) -> dict:
    """Live-verify length + trim for this genre/concept. Never raises."""
    p = GENRE_PRESETS.get(ms.genre_preset, {})
    prompt = (
        f"A publisher is about to produce a {p.get('label', 'book')} "
        f"(paperback + ebook, Amazon KDP).\nConcept: {ms.idea[:400]}\n"
        f"House template: {p.get('target_words', 0):,} words, trim "
        f"{p.get('trim', '')}″.\n\n"
        "Web-search the CURRENT market for this genre on Amazon — what the "
        "top sellers actually run right now: typical word counts / page "
        "counts, the dominant paperback trim size, and whether this concept "
        "suggests deviating from the norm. Be specific and numeric.\n"
        'Return JSON only: {"target_words": the market-right word count for '
        'this book, "trim_size": "WxH" like "5.25x8", '
        '"summary": "2-3 sentences: what the live market showed and why '
        'these numbers"}'
    )
    raw = await complete(
        "You verify publishing decisions against the live market before "
        "committing production resources. Numbers over adjectives.",
        prompt, max_tokens=2500, web_search=4, mechanical=True)
    out = extract_json(raw)
    return {
        "target_words": int(out.get("target_words") or 0),
        "trim_size": _valid_trim(str(out.get("trim_size") or "")),
        "summary": str(out.get("summary") or "").strip(),
    }


def apply_market_check(book_data: dict, ms, check: dict) -> list:
    """Adopt checked values where the publisher left house defaults.

    Returns a list of human-readable adjustments (empty = template confirmed).
    Mutates ms.target_words and book_data format/trim fields in place.
    """
    p = GENRE_PRESETS.get(ms.genre_preset, {})
    applied = []

    mw = check.get("target_words") or 0
    floor = p.get("min_words", 0) or 0
    ceiling = int((p.get("target_words") or mw or 1) * 1.3)
    if (mw and ms.target_words == p.get("target_words")
            and floor <= mw <= ceiling and mw != ms.target_words):
        applied.append(f"target length {ms.target_words:,} → {mw:,} words")
        ms.target_words = mw

    mt = check.get("trim_size") or ""
    current = ((book_data.get("format") or {}).get("trim_size")
               or book_data.get("trim_size") or "")
    if mt and current == p.get("trim") and mt != current:
        applied.append(f"trim {current}″ → {mt}″")
        book_data["trim_size"] = mt
        if isinstance(book_data.get("format"), dict):
            book_data["format"]["trim_size"] = mt

    return applied
