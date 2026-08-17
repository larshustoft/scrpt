"""
The acceptance desk — no manuscript leaves the house unchecked.

Two gates every finished draft must pass, exactly like a publishing house:

1. LENGTH: the book must land in its commercial band (>= genre floor and
   within -10%/+15% of target). Short books are repaired by REDRAFTING the
   shortest chapters at full length from their outline — never by padding.

2. EDITORIAL: a managing-editor read of the whole manuscript — arc held?
   beats landed? pacing, continuity, voice? — returning ACCEPT or REVISE
   with concrete chapter orders. REVISE triggers one bounded repair round
   (targeted chapter revisions), then a re-read.

The verdict is stored as data["acceptance"] and gates the Production Queue's
quality flag. Both gates run on the configured writing model (settings key
writing_model), so upgrading the model upgrades the editor — and any book
can be re-checked later with POST /api/scrpt/acceptance/{catalog}.
"""

import json

from ..craft import craft
from ..database import get_book_by_catalog
from ..prose.models import GENRE_PRESETS, Manuscript
from .client import complete, extract_json

LENGTH_LOW = 0.90    # accept from target-10%
LENGTH_HIGH = 1.15   # to target+15%
MAX_LENGTH_REDRAFTS = 4   # shortest chapters redrafted per repair round
MAX_REVISE_ORDERS = 6     # chapters revised per editorial repair round
SAMPLE_WORDS = 3500       # full-text sample cap per keystone chapter


def _chapter_words(ch: dict) -> int:
    return sum(len((b.get("text") or "").split()) for b in (ch.get("blocks") or []))


def measure_length(ms_data: dict, preset: dict) -> dict:
    chapters = ms_data.get("chapters") or []
    per = [{"index": c.get("index"), "title": c.get("title"),
            "words": _chapter_words(c)} for c in chapters]
    total = sum(c["words"] for c in per)
    target = ms_data.get("target_words") or preset.get("target_words") or 0
    floor = max(preset.get("min_words") or 0, int(target * LENGTH_LOW))
    ceiling = int(target * LENGTH_HIGH)
    ok = floor <= total <= ceiling
    return {"total_words": total, "target_words": target, "floor": floor,
            "ceiling": ceiling, "ok": ok, "chapters": per}


def shortest_chapters(length: dict, chapter_words_target: int) -> list:
    """Indices of drafted chapters furthest below their per-chapter target."""
    short = [c for c in length["chapters"]
             if c["words"] and c["words"] < chapter_words_target * 0.85]
    short.sort(key=lambda c: c["words"])
    return [c["index"] for c in short[:MAX_LENGTH_REDRAFTS]]


def _chapter_text(ch: dict, cap: int = SAMPLE_WORDS) -> str:
    words: list = []
    for b in ch.get("blocks") or []:
        words.extend((b.get("text") or "").split())
        if len(words) >= cap:
            break
    return " ".join(words[:cap])


async def editorial_review(catalog: str) -> dict:
    """The managing-editor read: whole-book view + keystone chapters in full."""
    book = get_book_by_catalog(catalog)
    ms = book["data"].get("manuscript") or {}
    preset = GENRE_PRESETS.get(ms.get("genre_preset"), {})
    chapters = ms.get("chapters") or []
    am = ms.get("arc_map") or {}

    ledger = "\n".join(
        f"  ch{c.get('index')} \"{c.get('title')}\" — {_chapter_words(c)} words"
        f"{', gate score ' + str(c.get('quality_score')) if c.get('quality_score') else ''}"
        f" | {(c.get('rolling_summary') or c.get('outline_summary') or '')[:180]}"
        for c in chapters)

    # keystone chapters read in full: opening, pinned midpoint/all-is-lost/
    # climax, the ending, and the two weakest-scoring chapters
    keystones = {1, len(chapters)}
    for b in am.get("pinned_beats", []):
        beat = (b.get("beat") or "").lower()
        if any(k in beat for k in ("midpoint", "all-is-lost", "climax")):
            keystones.add(b.get("chapter"))
    scored = sorted((c for c in chapters if c.get("quality_score")),
                    key=lambda c: c["quality_score"])
    for c in scored[:2]:
        keystones.add(c.get("index"))
    samples = "\n\n".join(
        f"=== FULL TEXT, CHAPTER {c.get('index')}: {c.get('title')} ===\n"
        f"{_chapter_text(c)}"
        for c in chapters if c.get("index") in keystones and c.get("blocks"))

    prompt = (
        f"MANUSCRIPT LEDGER ({len(chapters)} chapters):\n{ledger}\n\n"
        f"STORY ARCHITECTURE:\n{json.dumps(am)[:2500]}\n\n"
        f"KEYSTONE CHAPTERS IN FULL:\n{samples}\n\n"
        "You are the managing editor deciding whether this manuscript leaves "
        "the house. Judge it as a PUBLISHED BOOK will be judged: does the arc "
        "hold across the whole length, do the pinned beats actually land, "
        "does the middle sag, are setups paid off, is the voice consistent, "
        "would the target reader finish it and buy the next one?\n"
        f"{craft(ms.get('genre_preset', ''), 'REVISION')}\n"
        "Return JSON only:\n"
        '{"verdict": "accept" | "revise", "score": 0-10 one decimal, '
        '"strengths": ["..."], '
        '"issues": [{"chapter": N, "order": "the concrete fix, phrased as an '
        'editor\'s instruction"}] (only chapters that truly need work), '
        '"editor_letter": "6-10 sentences to the publisher: the honest read"}'
    )
    raw = await complete(
        "You are a veteran managing editor at a commercial publishing house. "
        "You accept nothing that would embarrass the imprint, and your "
        "revision orders are concrete enough to execute.",
        prompt, max_tokens=6000)
    out = extract_json(raw)
    out["keystones_read"] = sorted(k for k in keystones if k)
    return out


async def acceptance_job(handle, catalog: str) -> dict:
    """Length gate (with redraft repair) -> editorial gate (with revision
    repair) -> stored verdict."""
    from . import pipeline as wp
    from .quality import gate_chapter, revise_chapter
    from ..database import update_book

    book = get_book_by_catalog(catalog)
    ms = book["data"].get("manuscript") or {}
    preset = GENRE_PRESETS.get(ms.get("genre_preset"), {})
    report: dict = {"length_repairs": [], "revision_orders": []}

    # ── gate 1: length ───────────────────────────────────────────
    handle.progress(0.05, "length", "Measuring the manuscript")
    length = measure_length(ms, preset)
    if not length["ok"] and length["total_words"] < length["floor"]:
        targets = shortest_chapters(length, preset.get("chapter_words", 3000))
        for i, idx in enumerate(targets):
            handle.progress(0.08 + 0.3 * i / max(1, len(targets)), "length",
                            f"Redrafting short chapter {idx} at full length")
            await wp.draft_chapter(catalog, idx)
            try:
                await gate_chapter(catalog, idx)
            except Exception:
                pass
            report["length_repairs"].append(idx)
        ms = get_book_by_catalog(catalog)["data"].get("manuscript") or {}
        length = measure_length(ms, preset)
    report["length"] = length

    # ── gate 2: the editor ───────────────────────────────────────
    handle.progress(0.45, "editorial", "The managing editor is reading")
    review = await editorial_review(catalog)

    if review.get("verdict") == "revise" and review.get("issues"):
        orders = review["issues"][:MAX_REVISE_ORDERS]
        for i, issue in enumerate(orders):
            idx = issue.get("chapter")
            if not idx:
                continue
            handle.progress(0.55 + 0.3 * i / max(1, len(orders)), "revision",
                            f"Executing the editor's order on chapter {idx}")
            try:
                await revise_chapter(catalog, idx, [issue.get("order", "")], [])
                await gate_chapter(catalog, idx)
            except Exception:
                continue
            report["revision_orders"].append(issue)
        handle.progress(0.9, "editorial", "The editor re-reads")
        review = await editorial_review(catalog)

    report["review"] = review
    report["verdict"] = review.get("verdict", "revise")
    report["score"] = review.get("score")

    data = dict(get_book_by_catalog(catalog)["data"])
    data["acceptance"] = report
    update_book(book["id"], data)
    return {"verdict": report["verdict"], "score": report.get("score"),
            "total_words": report["length"]["total_words"],
            "length_ok": report["length"]["ok"],
            "repairs": len(report["length_repairs"]),
            "revisions": len(report["revision_orders"])}
