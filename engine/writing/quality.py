"""
The Quality Gate — how SCRPT earns trust on full-length books.

Every drafted chapter is audited against the genre's craft playbook (score,
issues, hook classification). Chapters below the bar get ONE rewrite that
must fix the named issues while preserving continuity. After the book is
drafted, a whole-book audit checks the things no single chapter can see:
hook-type monotony and pacing flatness.

This is the mechanism behind "quality through the whole book": the sag that
kills long AI drafts (chapters 15-30 going flat) is caught chapter by
chapter, at the moment it happens.
"""

from ..database import get_book_by_catalog
from ..prose.models import ChapterStatus, Manuscript
from .client import complete, extract_json
from .parsing import blocks_to_text, parse_chapter_text, count_words

PASS_SCORE = 7.0

HOOK_TYPES = [
    "danger", "interruption", "revelation", "partial_reveal", "decision",
    "question", "foreshadow", "emotional", "reversal", "resolution",
]


def _position_context(index: int, total: int) -> str:
    frac = index / max(1, total)
    if index == 1:
        return "This is the OPENING chapter — the hook that decides everything."
    if frac >= 0.78:
        return ("This chapter is in the CLIMAX ZONE (final quarter) — maximum "
                "compression and momentum expected.")
    if 0.45 <= frac <= 0.55:
        return "This is the MIDPOINT ZONE — a reversal/flip is expected here."
    if 0.3 <= frac <= 0.7:
        return ("This is the MIDDLE of the book — the zone where long drafts "
                "sag. Judge harshly for flatness, repetition, and missing "
                "tension.")
    return ""


async def audit_chapter(catalog: str, index: int) -> dict:
    """Score one chapter against the playbook. Returns the audit dict."""
    book = get_book_by_catalog(catalog)
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    ch = next(c for c in ms.chapters if c.index == index)
    text = blocks_to_text(ch.blocks)
    playbook = ""

    prompt = (
        f"{playbook}\n"
        f"CHAPTER {index} of {len(ms.chapters)} — \"{ch.title}\".\n"
        f"{_position_context(index, len(ms.chapters))}\n"
        f"Chapter brief it must fulfill: {ch.outline_summary}\n\n"
        f"CHAPTER TEXT:\n{text[:14000]}\n\n"
        "Audit this chapter as a ruthless senior editor holding it to the "
        "playbook above. Be strict — a 7 means publishable commercial "
        "quality; most first drafts have real problems.\n"
        "Return JSON only:\n"
        "{\"score\": 1-10, "
        f"\"hook_type\": \"one of {HOOK_TYPES} for how the chapter ends\", "
        "\"issues\": [\"specific, fixable problems in priority order — empty if none\"], "
        "\"strengths\": [\"what must be preserved in any rewrite\"]}"
    )
    raw = await complete(
        "You are a ruthless senior fiction/non-fiction editor at a commercial "
        "publishing house. You audit manuscripts against the house craft "
        "standard and you do not flatter.",
        prompt, max_tokens=4000)
    return extract_json(raw)


async def revise_chapter(catalog: str, index: int, issues: list[str],
                         strengths: list[str]) -> None:
    """One rewrite fixing the named issues, preserving continuity and length."""
    from .pipeline import _bible_digest, _fiction_system, _nonfiction_system, _load, _save
    from ..prose.models import BookKind

    book, ms = _load(catalog)
    ch = next(c for c in ms.chapters if c.index == index)
    text = blocks_to_text(ch.blocks)
    system = (_fiction_system(ms) if ms.kind == BookKind.FICTION
              else _nonfiction_system(ms))
    prev = next((c for c in ms.chapters if c.index == index - 1), None)

    prompt = (
        f"BIBLE:\n{_bible_digest(ms)}\n\n"
        f"{'PREVIOUS CHAPTER SUMMARY: ' + prev.rolling_summary if prev else ''}\n"
        f"REWRITE chapter {index} (\"{ch.title}\") to fix these editorial "
        f"issues, in priority order:\n"
        + "\n".join(f"  {i+1}. {iss}" for i, iss in enumerate(issues[:6]))
        + "\nPRESERVE these strengths:\n"
        + "\n".join(f"  - {s}" for s in strengths[:5])
        + "\n\nKeep the same events, continuity facts, and approximate length "
        f"({ch.word_count} words). Same format dialect as the original.\n\n"
        f"ORIGINAL CHAPTER:\n{text[:14000]}\n\n"
        "Write the revised chapter text only — no commentary. Then one line "
        "'@@META@@ ' + JSON {\"rolling_summary\": \"150-250 words\"}."
    )
    raw = await complete(system, prompt, max_tokens=16000)

    meta = {}
    new_text = raw
    if "@@META@@" in raw:
        new_text, _, meta_line = raw.rpartition("@@META@@")
        try:
            meta = extract_json(meta_line)
        except ValueError:
            pass

    book, ms = _load(catalog)
    ch = next(c for c in ms.chapters if c.index == index)
    ch.blocks = parse_chapter_text(new_text.strip())
    ch.word_count = count_words(ch.blocks)
    if meta.get("rolling_summary"):
        ch.rolling_summary = str(meta["rolling_summary"])[:2000]
    ch.revised = True
    ch.status = ChapterStatus.REVISED
    ms.word_count = sum(c.word_count for c in ms.chapters)
    _save(book, ms)


async def gate_chapter(catalog: str, index: int) -> dict:
    """Audit; rewrite once if below the bar; re-audit. Persists scores."""
    from .pipeline import _load, _save

    audit = await audit_chapter(catalog, index)
    score = float(audit.get("score", 0))

    if score < PASS_SCORE and audit.get("issues"):
        await revise_chapter(catalog, index,
                             [str(i) for i in audit.get("issues", [])],
                             [str(s) for s in audit.get("strengths", [])])
        audit = await audit_chapter(catalog, index)
        score = float(audit.get("score", 0))

    book, ms = _load(catalog)
    ch = next(c for c in ms.chapters if c.index == index)
    ch.quality_score = score
    ch.quality_notes = "; ".join(str(i) for i in audit.get("issues", [])[:3])
    ch.hook_type = str(audit.get("hook_type", ""))
    _save(book, ms)
    return {"index": index, "score": score, "revised": ch.revised}


def book_audit(catalog: str) -> dict:
    """Whole-book checks no single chapter can see. Pure computation."""
    from .pipeline import _load, _save

    book, ms = _load(catalog)
    chapters = [c for c in ms.chapters if c.blocks]
    hooks = [c.hook_type for c in chapters]
    scores = [c.quality_score for c in chapters if c.quality_score]

    issues = []
    # hook monotony: 3+ consecutive identical hook types
    run_type, run_len = None, 0
    for i, h in enumerate(hooks):
        if h and h == run_type:
            run_len += 1
            if run_len >= 3:
                issues.append(f"Hook monotony: chapters {i - run_len + 2}-{i + 1} "
                              f"all end on '{h}'")
        else:
            run_type, run_len = h, 1
    # resolution hooks overused (>10% of chapters)
    if hooks and hooks.count("resolution") > max(1, len(hooks) // 10):
        issues.append(f"Too many quiet endings: {hooks.count('resolution')} "
                      f"of {len(hooks)} chapters end on 'resolution'")
    # weak stretch: 2+ consecutive sub-7 chapters
    weak = [c.index for c in chapters
            if c.quality_score is not None and c.quality_score < PASS_SCORE]
    if weak:
        issues.append(f"Chapters below the bar after revision: {weak}")

    report = {
        "chapters_audited": len(scores),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
        "min_score": min(scores) if scores else None,
        "revised_count": sum(1 for c in chapters if c.revised),
        "hook_distribution": {h: hooks.count(h) for h in set(hooks) if h},
        "issues": issues,
        "passed": not issues and bool(scores) and min(scores) >= PASS_SCORE,
    }
    ms.quality_report = report
    _save(book, ms)
    return report
