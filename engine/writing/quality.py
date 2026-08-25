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
from . import storygrid as _sg
from .parsing import blocks_to_text, parse_chapter_text, count_words

PASS_SCORE = 7.0
OPENING_PASS_SCORE = 8.0      # chapter one is held higher: it sells the book

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


def _chapter_readability(text: str) -> dict:
    """Objective density stats for one chapter (see acceptance.readability)."""
    import re
    sentences = [x for x in re.split(r"[.!?]+[\s\"']", text) if x.strip()]
    lens = [len(x.split()) for x in sentences if x.split()]
    if not lens:
        return {"avg": 0, "long_share": 0}
    return {"avg": round(sum(lens) / len(lens), 1),
            "long_share": round(sum(1 for n in lens if n > 25) / len(lens), 3)}


async def audit_chapter(catalog: str, index: int) -> dict:
    """Score one chapter against the playbook. Returns the audit dict."""
    book = get_book_by_catalog(catalog)
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    ch = next(c for c in ms.chapters if c.index == index)
    text = blocks_to_text(ch.blocks)
    rd = _chapter_readability(text)
    from .acceptance import read_target
    tgt = read_target(ms.genre_preset)
    # a little slack per chapter; the book-level target is the real bar
    dense = rd["avg"] > tgt["avg"] + 1.5 or rd["long_share"] > tgt["long"] + 0.03
    playbook = ""

    prompt = (
        f"{playbook}\n"
        f"CHAPTER {index} of {len(ms.chapters)} — \"{ch.title}\".\n"
        f"{_position_context(index, len(ms.chapters))}\n"
        f"Chapter brief it must fulfill: {ch.outline_summary}\n\n"
        f"CHAPTER TEXT:\n{text[:14000]}\n\n"
        f"MEASURED DENSITY: average sentence {rd['avg']} words, "
        f"{round(rd['long_share']*100)}% of sentences over 25 words."
        + (" THIS IS TOO DENSE — the house writes effortless, fun page-turners. "
           "List 'simplify dense prose: break long sentences, plainer words, "
           "more white space' as a priority issue and cap the score at 6 until "
           "it reads easily." if dense else " (within the easy-read target)")
        + "\n\n"
        + ("THE OPENING CHAPTER — the house rule: a reader decides in the first page. "
           "Chapter one must open IN SCENE (no weather, no waking up, no backstory first), "
           "put the story's question or a live tension on the page within the first 300 "
           "words, make the protagonist want something immediately and concretely, set the "
           "book's tone in its first paragraph, and end on a pull that makes chapter two "
           "unavoidable. If any of these is missing, list it as the FIRST issue and cap the "
           "score at 6.\n\n" if index == 1 else "")
        + "Audit this chapter as a ruthless senior editor holding it to the "
        "house standard: it must be an EFFORTLESS, FUN, captivating read — "
        "exciting, hard to put down, easy on the eye. Be strict — a 7 means "
        "publishable commercial quality; most first drafts have real problems.\n\n"
        + _sg.STORY_EVENT_RULE + "\n\n"
        "FIRST, before scoring, answer the Story Grid test honestly. Name the "
        "VALUE that shifts in this chapter and the two poles it moves between, "
        "and name the CRISIS — the dilemma the character actually faced. If you "
        "cannot name a real value shift, or the chapter only moves information "
        "around, then `value_shift` is \"none\": say so plainly, list "
        "'no value shift — this is exposition, not a scene' as the FIRST issue, "
        "and cap the score at 5 however well written the prose is.\n"
        "Return JSON only:\n"
        "{\"value_shift\": \"e.g. safety -> danger, or 'none'\", "
        "\"crisis\": \"the dilemma faced, or 'none'\", "
        "\"score\": 1-10, "
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
                         strengths: list[str], target_words: int = 0) -> None:
    """One rewrite fixing the named issues, preserving continuity and length
    (or hitting `target_words` when an order changes the length on purpose)."""
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
        + "\n\nKeep the same events and continuity facts. "
        + (f"TARGET LENGTH: about {target_words} words — this is deliberate. "
           if target_words else f"Keep the approximate length ({ch.word_count} words). ")
        + "Same format dialect as the original.\n\n"
        f"ORIGINAL CHAPTER:\n{text[:14000]}\n\n"
        "Write the revised chapter text only — no commentary. Then one line "
        "'@@META@@ ' + JSON {\"rolling_summary\": \"150-250 words\"}."
    )
    original_words = len(text.split())
    new_text, meta = "", {}
    for attempt in range(2):
        raw = await complete(system, prompt, max_tokens=16000, mechanical=True)
        meta = {}
        new_text = raw
        if "@@META@@" in raw:
            new_text, _, meta_line = raw.rpartition("@@META@@")
            try:
                meta = extract_json(meta_line)
            except ValueError:
                pass
        new_text = new_text.strip()
        # a rewrite must come back whole: not cut short, ending on a sentence
        words = len(new_text.split())
        floor = (target_words * 0.7) if target_words else (original_words * 0.72)
        tail = new_text.rstrip().rstrip('*_"\'\u201d\u2019\u00bb)\u2014\u2013 \t\n')
        ends_clean = bool(tail) and tail[-1] in '.!?\u2026'
        if not ends_clean and new_text and new_text.rstrip()[-1:] in '"\u201d\u2019':
            ends_clean = True        # dialogue close
        if words >= floor and ends_clean:
            break
        if attempt == 1:
            raise RuntimeError(f"rewrite of chapter {index} came back incomplete ({words} words, ends clean={ends_clean}) — original kept")

    book, ms = _load(catalog)
    ch = next(c for c in ms.chapters if c.index == index)
    ch.blocks = parse_chapter_text(new_text)
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

    bar = OPENING_PASS_SCORE if index == 1 else PASS_SCORE
    if score < bar and audit.get("issues"):
        await revise_chapter(catalog, index,
                             [str(i) for i in audit.get("issues", [])],
                             [str(s) for s in audit.get("strengths", [])])
        audit = await audit_chapter(catalog, index)
        score = float(audit.get("score", 0))

    book, ms = _load(catalog)
    ch = next(c for c in ms.chapters if c.index == index)
    ch.quality_score = score
    ch.value_shift = str(audit.get("value_shift", ""))[:120]
    ch.audited_crisis = str(audit.get("crisis", ""))[:200]
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


async def continuity_audit(catalog: str) -> dict:
    """Cheap, reliable continuity check reading only the chapter summaries and
    canon facts (not full text). Catches the class of error that quietly ships:
    contradicting timelines, a name/title that drifts between chapters, a beat
    told twice. Runs on the mechanical model — pennies, every book."""
    book = get_book_by_catalog(catalog)
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    ledger = "\n".join(
        f"Ch{c.index} ({c.title}): {c.rolling_summary or c.outline_summary}"
        for c in ms.chapters if c.blocks)
    facts = ""
    if ms.story_bible and ms.story_bible.facts:
        facts = "CANON FACTS:\n" + "\n".join(f"- {f}" for f in ms.story_bible.facts)
    prompt = (
        f"{facts}\n\nCHAPTER-BY-CHAPTER SUMMARY:\n{ledger}\n\n"
        "You are a continuity editor. Find only CONCRETE contradictions a "
        "reader would catch: timelines that disagree (how long ago an event "
        "happened, ages, dates, seasons), a person/place/object named "
        "differently in different chapters, a scene or beat that happens "
        "twice, a fact stated then contradicted. Ignore style. For each, name "
        "the chapters and the fix.\n\n"
        "THE CHAPTERS ARE CANON. The CANON FACTS list is the author's notes and "
        "may be stale: where a note disagrees with what the chapters consistently "
        "say, that is NOT a contradiction in the book — report it separately as "
        "note_drift with the corrected note. Only disagreements BETWEEN CHAPTERS "
        "go in contradictions.\n"
        'Return JSON only: {"contradictions": [{"chapters": "1, 19", '
        '"problem": "...", "fix": "the single correct version to use"}], '
        '"note_drift": [{"note": "the stale note, quoted", "corrected": "the note rewritten to match the chapters"}]}'
    )
    raw = await complete(
        "You catch continuity errors in manuscripts. You are precise and never "
        "invent problems.", prompt, max_tokens=3000, mechanical=True)
    try:
        out = extract_json(raw)
    except ValueError:
        out = {"contradictions": []}
    if not isinstance(out, dict):
        out = {"contradictions": []}
    # stale notes: correct the bible so the next audit agrees with the book
    drift = [d_ for d_ in (out.get("note_drift") or []) if isinstance(d_, dict) and d_.get("corrected")]
    if drift and ms.story_bible and ms.story_bible.facts:
        facts = list(ms.story_bible.facts)
        for d_ in drift:
            stale = (d_.get("note") or "").strip().lower()[:60]
            facts = [f for f in facts if not (stale and stale[:40] in f.lower())]
            facts.append(d_["corrected"].strip())
        try:
            from .pipeline import _load, _save
            book2, ms2 = _load(catalog)
            ms2.story_bible.facts = facts[-80:]
            _save(book2, ms2)
        except Exception:
            pass
    return {"contradictions": out.get("contradictions", []), "note_drift": drift}


async def simplify_chapter(catalog: str, index: int) -> dict:
    """Rewrite ONE chapter for readability only — same story, easier prose.

    Works in SEGMENTS of a few paragraphs at a time. A model asked to simplify
    3,000 words compresses them; asked to re-cut 600 words it does exactly the
    sentence surgery wanted and keeps the content. Events, dialogue, names and
    the ending beat are preserved; only sentence architecture changes.
    """
    from .pipeline import _fiction_system, _nonfiction_system, _load, _save
    from ..prose.models import BookKind
    from .acceptance import read_target

    book, ms = _load(catalog)
    ch = next(c for c in ms.chapters if c.index == index)
    text = blocks_to_text(ch.blocks)
    before = _chapter_readability(text)
    tgt = read_target(ms.genre_preset)
    system = (_fiction_system(ms) if ms.kind == BookKind.FICTION
              else _nonfiction_system(ms))

    # group paragraphs into ~600-word segments, never splitting a paragraph
    paras = [p for p in text.split("\n\n")]
    segments, cur, n = [], [], 0
    for para in paras:
        cur.append(para)
        n += len(para.split())
        if n >= 600:
            segments.append("\n\n".join(cur))
            cur, n = [], 0
    if cur:
        segments.append("\n\n".join(cur))

    out_parts = []
    for seg in segments:
        seg_words = len(seg.split())
        prompt = (
            "Re-cut this passage so it reads effortlessly — a page-turner a "
            "tired reader never has to re-read.\n\n"
            "HOW:\n"
            "- Break long stacked sentences into two or three short ones.\n"
            "- Swap ornate or rare words for the plain word a reader knows.\n"
            "- Vary rhythm: a short punch line after a longer one.\n"
            f"- Aim for an average sentence near {tgt['avg'] - 2} words.\n\n"
            "ABSOLUTE RULES:\n"
            "- Return EVERY paragraph, in the same order, carrying the same "
            "content. Nothing may be summarised, merged or dropped.\n"
            "- Keep every event, name, date, and all dialogue meaning.\n"
            f"- The passage is {seg_words} words; your version must be "
            f"{int(seg_words * 0.95)}-{int(seg_words * 1.1)} words. Splitting "
            "sentences preserves words — you are re-cutting, not shortening.\n"
            "- No commentary, no headings. Prose only.\n\n"
            f"PASSAGE:\n{seg}"
        )
        try:
            got = (await complete(system, prompt, max_tokens=4000,
                                  mechanical=True)).strip()
        except Exception:
            got = seg
        # a segment that lost content is discarded in favour of the original
        if len(got.split()) < seg_words * 0.9:
            got = seg
        out_parts.append(got)

    new_text = "\n\n".join(out_parts)
    import re as _re
    new_text = _re.sub(r"^\s*(?:#+\s*)?CHAPTER\s+\d+\s*[—\-:]?[^\n]*\n+", "",
                       new_text, flags=_re.I)
    ratio = len(new_text.split()) / max(1, len(text.split()))
    if ratio < 0.93:
        return {"index": index, "skipped": f"lost {round((1-ratio)*100)}% of words",
                "before": before}

    book, ms = _load(catalog)
    ch = next(c for c in ms.chapters if c.index == index)
    ch.blocks = parse_chapter_text(new_text)
    ch.word_count = count_words(ch.blocks)
    ms.word_count = sum(c.word_count for c in ms.chapters)
    _save(book, ms)
    after = _chapter_readability(blocks_to_text(ch.blocks))
    return {"index": index, "before": before, "after": after,
            "words": ch.word_count, "segments": len(segments)}


async def simplify_book(catalog: str, handle=None) -> dict:
    """Book-wide readability pass: every chapter over its genre target gets a
    simplify edit. This is the tool for prose density — the acceptance desk's
    revision loop only touches a handful of flagged chapters."""
    from .pipeline import _load
    from .acceptance import read_target, readability

    book, ms = _load(catalog)
    tgt = read_target(ms.genre_preset)
    todo = []
    for c in ms.chapters:
        if not c.blocks:
            continue
        rd = _chapter_readability(blocks_to_text(c.blocks))
        if rd["avg"] > tgt["avg"] or rd["long_share"] > tgt["long"]:
            todo.append(c.index)

    before = readability(get_book_by_catalog(catalog)["data"].get("manuscript") or {})
    done = []
    for i, idx in enumerate(todo):
        if handle:
            handle.progress(0.05 + 0.9 * i / max(1, len(todo)), "simplify",
                            f"Simplifying chapter {idx} of {len(ms.chapters)}")
        try:
            done.append(await simplify_chapter(catalog, idx))
        except Exception as e:
            done.append({"index": idx, "error": str(e)[:160]})
    after = readability(get_book_by_catalog(catalog)["data"].get("manuscript") or {})
    return {"catalog": catalog, "chapters_over_target": len(todo),
            "chapters_simplified": sum(1 for d in done if d.get("after")),
            "before": before, "after": after, "detail": done}


async def merge_chapters(catalog: str, src_index: int, dst_index: int,
                         order: str = "") -> int:
    """Fold chapter `src` into chapter `dst` as ONE scene, remove the source
    chapter and renumber. The structural fix the desk could not make on its
    own: three thin interior chapters in a row become two. Returns the new
    index of the merged chapter."""
    from .pipeline import _bible_digest, _fiction_system, _nonfiction_system, _load, _save
    from ..prose.models import BookKind
    import uuid

    book, ms = _load(catalog)
    src = next(c for c in ms.chapters if c.index == src_index)
    dst = next(c for c in ms.chapters if c.index == dst_index)
    system = (_fiction_system(ms) if ms.kind == BookKind.FICTION else _nonfiction_system(ms))
    target = int((src.word_count + dst.word_count) * 0.8)
    prompt = (
        f"BIBLE:\n{_bible_digest(ms)}\n\n"
        f"MERGE two chapters into ONE chapter of about {target} words. "
        f"{order or 'Fuse them into a single continuous scene or a tightly linked pair of scenes; no recap of one inside the other.'} "
        "Keep every continuity fact and every plot event of both; cut only rumination, repetition and paraphrase. "
        "Plain words, short sentences, the house's easy-read register. Same format dialect as the originals.\n\n"
        f"CHAPTER A (\"{src.title}\"):\n{blocks_to_text(src.blocks)[:12000]}\n\n"
        f"CHAPTER B (\"{dst.title}\"):\n{blocks_to_text(dst.blocks)[:12000]}\n\n"
        "Write the merged chapter text only — no commentary. Then one line "
        "'@@META@@ ' + JSON {\"title\": \"chapter title\", \"rolling_summary\": \"150-250 words\"}."
    )
    raw = await complete(system, prompt, max_tokens=16000, mechanical=True)
    meta = {}
    new_text = raw
    if "@@META@@" in raw:
        new_text, _, meta_line = raw.rpartition("@@META@@")
        try:
            meta = extract_json(meta_line)
        except ValueError:
            pass

    book, ms = _load(catalog)
    src = next(c for c in ms.chapters if c.index == src_index)
    dst = next(c for c in ms.chapters if c.index == dst_index)
    dst.blocks = parse_chapter_text(new_text.strip())
    dst.word_count = count_words(dst.blocks)
    if meta.get("title"):
        dst.title = str(meta["title"])[:80]
    if meta.get("rolling_summary"):
        dst.rolling_summary = str(meta["rolling_summary"])[:2000]
    dst.outline_summary = (src.outline_summary + " " + dst.outline_summary).strip()
    dst.beats = list(src.beats) + list(dst.beats)
    dst.revised = True
    dst.status = ChapterStatus.REVISED
    ms.chapters = [c for c in ms.chapters if c.index != src_index]
    for i, c in enumerate(sorted(ms.chapters, key=lambda c: c.index), start=1):
        c.index = i
    ms.chapters.sort(key=lambda c: c.index)
    ms.word_count = sum(c.word_count for c in ms.chapters)
    _save(book, ms)
    return dst.index
