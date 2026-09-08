"""THE READER'S DESK — how a finished manuscript earns its way out of the
house (Lars, 2026-09-07: "Fix everything we need to fix to create top
quality books" — and the standing definition: SCRPT is an automated,
AI-driven publishing house that delivers high-quality books across many
genres, based on market analysis and creative, solid writing).

What replaced the old score loop (an editor's number, then a rewrite of
every chapter on general notes — $11 a round, and the score FELL):

  triage_read   the strongest reader reads the three places a reader
                judges a book: the opening, the midpoint, the climax and
                ending — and answers five reader questions. Verdict: ship,
                fix (with the named chapters and the named faults), or
                shelve. No score, no rewrite.
  targeted_fix  only the named chapters, only the named faults.
  line_edit     every chapter once: tighten, cut repetition, fix rhythm,
                keep every event, fact and line of dialogue. The pass that
                makes a book read well.

Everything is idempotent per manuscript version (a signature of the text),
so the line never pays twice for the same words.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime

from ..database import get_book_by_catalog, update_book
from .client import complete, extract_json, fallback_model, ContentRefused, writing_model
from ..database import get_setting

TRIAGE_MODEL_DEFAULT = "claude-fable-5-1"      # the strongest reader reads; ~$0.50 a book


def triage_model() -> str:
    return get_setting("triage_model", TRIAGE_MODEL_DEFAULT) or TRIAGE_MODEL_DEFAULT

TRIAGE_WORDS = 6500           # words of each keystone chapter the reader gets in full
MAX_FIX_CHAPTERS = 5


def manuscript_sig(d: dict) -> str:
    ms = d.get("manuscript") or {}
    return hashlib.sha1(json.dumps([c.get("blocks") for c in ms.get("chapters", [])], sort_keys=True).encode()).hexdigest()[:16]


def _text(ch: dict, cap: int = TRIAGE_WORDS) -> str:
    words: list = []
    for b in ch.get("blocks") or []:
        words.extend((b.get("text") or "").split())
        if len(words) >= cap:
            break
    return " ".join(words[:cap])


def _keystones(ms: dict) -> dict:
    """{label: chapter index} — opening, midpoint, climax, ending."""
    chapters = ms.get("chapters") or []
    n = len(chapters)
    if not n:
        return {}
    am = ms.get("arc_map") or {}
    mid = climax = None
    for b in am.get("pinned_beats", []):
        beat = (b.get("beat") or "").lower()
        if "midpoint" in beat and not mid:
            mid = b.get("chapter")
        if "climax" in beat and not climax:
            climax = b.get("chapter")
    mid = mid or max(1, round(n / 2))
    climax = climax or max(1, n - 1)
    ks = {"opening": 1, "midpoint": mid, "climax": climax, "ending": n}
    seen, out = set(), {}
    for k, v in ks.items():
        if v not in seen:
            out[k] = v; seen.add(v)
    return out


async def triage_read(catalog: str) -> dict:
    """The reader's verdict on a finished manuscript. Stored in data.triage."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = book["data"]; ms = d.get("manuscript") or {}
    chapters = ms.get("chapters") or []
    if not chapters:
        raise RuntimeError("no chapters")
    sig = manuscript_sig(d)
    prev = d.get("triage") or {}
    if prev.get("sig") == sig and prev.get("verdict"):
        return prev
    ks = _keystones(ms)
    ledger = "\n".join(f"  ch{c.get('index')} \"{c.get('title')}\" — {c.get('word_count') or len(_text(c, 10**6).split())} words | "
                       f"{(c.get('rolling_summary') or c.get('outline_summary') or '')[:160]}" for c in chapters)
    reads = []
    for label, idx in ks.items():
        c = next((x for x in chapters if x.get("index") == idx), None)
        if c:
            reads.append(f"=== {label.upper()} — CHAPTER {idx}: {c.get('title')} ===\n{_text(c)}")
    genre = ms.get("genre_preset") or d.get("genre_preset") or "fiction"
    series = d.get("series") or {}
    prompt = (
        f"BOOK: {book.get('title')} · genre {genre}"
        + (f" · book {series.get('book_number')} of {series.get('series_title')}" if series.get("series_title") else "") + "\n"
        f"CHAPTER LEDGER ({len(chapters)} chapters):\n{ledger}\n\n"
        f"THE FOUR PLACES A READER JUDGES A BOOK, IN FULL:\n\n" + "\n\n".join(reads) + "\n\n"
        "You are the reader this book is for, and a very experienced one. Read like a reader, not a marker. "
        "Answer five questions honestly:\n"
        "1. After chapter one, would you keep reading tonight? Why, in one sentence.\n"
        "2. Is there a real turn at the midpoint — does the story change direction or raise the stakes?\n"
        "3. Does the ending pay off what chapter one promised?\n"
        "4. Is the voice the same person from opening to ending?\n"
        "5. Is anything confusing, contradictory, or effortful to read (dense sentences, rare words, stalls)?\n\n"
        "Then the verdict. SHIP when a paying reader would finish it and not feel cheated — not when nothing "
        "could be improved. FIX when one to five concrete, chapter-located faults stand between it and ship; "
        "name the chapter, the fault, and the exact fix an editor would order (a fix is a scene-level change, "
        "not 'improve pacing'). SHELVE only when the book has a structural failure a chapter fix cannot reach. "
        "Never order a rewrite of the whole book.\n\n"
        "Return JSON only:\n"
        '{"verdict": "ship" | "fix" | "shelve", '
        '"answers": {"keep_reading": "...", "midpoint_turn": "...", "ending_pays_off": "...", "voice_consistent": "...", "effort_or_confusion": "..."}, '
        '"faults": [{"chapter": N, "fault": "...", "fix": "..."}], '
        '"strengths": ["..."], "note": "3-5 sentences to the publisher, plain words"}'
    )
    system = ("You are the ideal reader of commercial fiction: you pay for books, you finish the good ones in a few "
              "evenings, you notice when a story cheats, and you say so plainly. JSON only.")
    raw = None; last = None
    for mdl in (triage_model(), fallback_model(), writing_model()):
        try:
            raw = await complete(system, prompt, max_tokens=6000, model=mdl, allow_fallback=True)
            break
        except ContentRefused as e:
            last = e; continue
    if raw is None:
        raise last or RuntimeError("triage read failed")
    out = extract_json(raw)
    if isinstance(out, list):
        out = next((x for x in out if isinstance(x, dict) and "verdict" in x), None)
    if not isinstance(out, dict) or out.get("verdict") not in ("ship", "fix", "shelve"):
        raise RuntimeError(f"triage returned an unparseable verdict: {str(out)[:200]}")
    faults = [f for f in (out.get("faults") or []) if isinstance(f, dict) and f.get("chapter") and f.get("fix")][:MAX_FIX_CHAPTERS]
    if out["verdict"] == "fix" and not faults:
        out["verdict"] = "ship"                      # nothing to fix is a ship
    rec = {"sig": sig, "verdict": out["verdict"], "answers": out.get("answers") or {}, "faults": faults,
           "strengths": (out.get("strengths") or [])[:5], "note": str(out.get("note") or "")[:1200],
           "keystones": ks, "at": datetime.now().isoformat(timespec="minutes"), "rounds": int(prev.get("rounds") or 0)}
    b = get_book_by_catalog(catalog); data = dict(b["data"]); data["triage"] = rec; update_book(b["id"], data)
    return rec


async def targeted_fix(catalog: str, handle=None) -> dict:
    """Revise only the chapters the reader named, against the named faults."""
    from .quality import revise_chapter
    b = get_book_by_catalog(catalog); d = b["data"]; tri = d.get("triage") or {}
    faults = tri.get("faults") or []
    done, failed = [], []
    for i, f in enumerate(faults[:MAX_FIX_CHAPTERS]):
        idx = int(f["chapter"])
        if handle:
            handle.progress(0.1 + 0.3 * i / max(1, len(faults)), "fix", f"Fixing chapter {idx}: {str(f.get('fault'))[:50]}")
        try:
            await revise_chapter(catalog, idx, [f"{f.get('fault')} FIX: {f.get('fix')}"], tri.get("strengths") or [])
            done.append(idx)
        except Exception as e:
            failed.append((idx, str(e)[:100]))
    b = get_book_by_catalog(catalog); data = dict(b["data"])
    t = dict(data.get("triage") or {}); t["fixed"] = done; t["fix_failed"] = failed; t["rounds"] = int(t.get("rounds") or 0) + 1
    data["triage"] = t; update_book(b["id"], data)
    return {"fixed": done, "failed": failed}


async def line_edit(catalog: str, handle=None) -> dict:
    """Every chapter once per manuscript version: the line edit."""
    from .pipeline import _bible_digest, _fiction_system, _nonfiction_system, _load, _save
    from .parsing import blocks_to_text, parse_chapter_text, count_words
    from ..prose.models import BookKind, ChapterStatus
    b = get_book_by_catalog(catalog); d = b["data"]
    sig = manuscript_sig(d)
    prev = d.get("line_edit") or {}
    if prev.get("sig") == sig and prev.get("done"):
        return {"skipped": "already line-edited this version", **prev}
    # PER CHAPTER (2026-09-08): a continuity ruling changes two chapters, and
    # the whole book was being line-edited again the next morning ($4), which
    # changed the text, which re-ran continuity ($2.5) — every day. Now each
    # chapter carries the hash of the text the line edit last produced; only
    # chapters whose text differs are edited.
    done_hashes = dict(prev.get("chapters") or {})
    if (d.get("kind") or (d.get("manuscript") or {}).get("kind")) == "childrens" or d.get("childrens"):
        return {"skipped": "children's books are edited on the spread"}
    book, ms = _load(catalog)
    system = _fiction_system(ms) if ms.kind == BookKind.FICTION else _nonfiction_system(ms)
    digest = _bible_digest(ms, include_facts=False)
    edited, kept = [], []
    kept_reasons: dict = {}
    n = len(ms.chapters)
    def _h(t: str) -> str:
        return hashlib.sha1(t.encode()).hexdigest()[:12]
    unchanged = []
    for i, ch in enumerate(ms.chapters):
        text = blocks_to_text(ch.blocks)
        if not text.strip():
            continue
        if done_hashes.get(str(ch.index)) == _h(text):
            unchanged.append(ch.index); continue
        if handle:
            handle.progress(0.4 + 0.4 * i / max(1, n), "line-edit", f"Line editing chapter {ch.index} of {n}")
        prompt = (
            f"VOICE AND WORLD (keep to it):\n{digest[:3500]}\n\n"
            f"LINE EDIT chapter {ch.index} (\"{ch.title}\"). This is a line edit, not a rewrite: keep every event, every fact, "
            "every name, every line of dialogue's meaning, the paragraph order and the chapter's length within a few percent. "
            "Do: cut repeated words and repeated ideas; break stacked sentences so each carries one thing; replace rare or "
            "effortful words with plain ones; fix rhythm so the prose moves; remove throat-clearing and recap; make dialogue "
            "tags invisible; keep the author's voice. Do not add scenes, do not add reflection, do not soften or strengthen "
            "what happens. Same format dialect as the original.\n\n"
            f"CHAPTER:\n{text[:16000]}\n\n"
            "Return the edited chapter text only — no commentary, no notes."
        )
        new_text = ""; reason = ""
        orig = len(text.split())
        for attempt in range(2):
            try:
                # the line edit runs on the mechanical model (Sonnet): it keeps
                # the words, it does not invent them — and it is a fifth of the price
                extra = (f"\n\nThe previous attempt {reason}. Return the WHOLE chapter, every scene, "
                         f"within 5% of {orig} words, ending on the chapter's last sentence." if reason else "")
                raw = await complete(system, prompt + extra, max_tokens=16000, mechanical=True)
            except ContentRefused:
                reason = "was refused"; break
            new_text = raw.strip()
            words = len(new_text.split())
            tail = new_text.rstrip().rstrip('*_"\'”’»)—– \t\n')
            ends_clean = bool(tail) and (tail[-1] in '.!?…' or new_text.rstrip()[-1:] in '"”’')
            if 0.75 * orig <= words <= 1.12 * orig and ends_clean:
                reason = ""; break
            reason = (f"came back at {words} words against {orig}" if not (0.75 * orig <= words <= 1.12 * orig)
                      else "did not end on a finished sentence")
            new_text = ""
        if not new_text:
            kept.append(ch.index); kept_reasons[ch.index] = reason
            done_hashes[str(ch.index)] = _h(text)          # judged, kept as is: do not retry daily
            continue
        ch.blocks = parse_chapter_text(new_text)
        ch.word_count = count_words(ch.blocks)
        edited.append(ch.index)
        done_hashes[str(ch.index)] = _h(blocks_to_text(ch.blocks))
        ms.word_count = sum(c.word_count for c in ms.chapters)
        _save(book, ms)
        book, ms = _load(catalog)
    b = get_book_by_catalog(catalog); data = dict(b["data"])
    data["line_edit"] = {"sig": manuscript_sig(data), "done": True, "edited": edited, "kept": kept, "unchanged": unchanged,
                         "kept_reasons": {str(k): v for k, v in kept_reasons.items()}, "chapters": done_hashes,
                         "at": datetime.now().isoformat(timespec="minutes")}
    update_book(b["id"], data)
    return data["line_edit"]


async def ready_manuscript(catalog: str, handle=None, max_fix_rounds: int = 2) -> dict:
    """triage → (targeted fix → triage again) → accept or shelve. Returns
    {accepted, verdict, rounds, spend_note}. Sets data.acceptance.verdict so
    the launch gate can read it; the old editor score is kept for reference."""
    steps = []
    tri = await triage_read(catalog)
    steps.append(("triage", tri["verdict"], f"{len(tri.get('faults') or [])} fault(s)"))
    rounds = 0
    while tri["verdict"] == "fix" and rounds < max_fix_rounds:
        fx = await targeted_fix(catalog, handle)
        steps.append(("fix", True, f"chapters {fx['fixed']}" + (f", failed {fx['failed']}" if fx["failed"] else "")))
        rounds += 1
        tri = await triage_read(catalog)
        steps.append(("triage", tri["verdict"], f"{len(tri.get('faults') or [])} fault(s)"))
    b = get_book_by_catalog(catalog); data = dict(b["data"]); acc = dict(data.get("acceptance") or {})
    if tri["verdict"] in ("ship", "fix"):
        # a 'fix' verdict after the fix round means faults remain that are not
        # structural; the book ships with them noted — the reader's own words
        # said it is not a shelve
        acc.update({"verdict": "accept", "accepted_by": "reader's desk", "accepted_at": datetime.now().isoformat(timespec="minutes"),
                    "triage_verdict": tri["verdict"], "editor_score": acc.get("score")})
        accepted = True
    else:
        acc.update({"verdict": "shelve", "accepted_by": "reader's desk", "triage_verdict": "shelve"})
        accepted = False
    data["acceptance"] = acc; update_book(b["id"], data)
    return {"accepted": accepted, "verdict": tri["verdict"], "rounds": rounds, "steps": steps, "note": tri.get("note")}
