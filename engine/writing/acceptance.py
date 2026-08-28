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

from ..database import get_book_by_catalog
from ..prose.models import GENRE_PRESETS, Manuscript
from .client import ContentRefused, complete, extract_json, fallback_model

LENGTH_LOW = 0.90    # accept from target-10%
LENGTH_HIGH = 1.15   # to target+15%
MAX_LENGTH_REDRAFTS = 4   # shortest chapters redrafted per repair round
MAX_REVISE_ORDERS = 10    # chapters revised per editorial repair round
MAX_CANON_REWRITES = 14   # chapter rewrites spent enforcing one ruling per contradiction
SAMPLE_WORDS = 3500       # full-text sample cap per keystone chapter


def _chapter_words(ch: dict) -> int:
    return sum(len((b.get("text") or "").split()) for b in (ch.get("blocks") or []))


# Genre-aware ease-of-reading targets. Thrillers live on propulsion, so their
# prose must be even punchier than romance, which carries more banter.
READ_TARGETS = {
    # hard = share of words with 3+ syllables (proper nouns excluded): the
    # "complicated words" number. Commercial bestsellers run ~6-9%.
    "action_thriller":      {"avg": 15, "long": 0.10, "dialogue": 0.20, "hard": 0.08},
    "conspiracy_thriller":  {"avg": 15, "long": 0.10, "dialogue": 0.20, "hard": 0.08},
    "superhero":            {"avg": 15, "long": 0.10, "dialogue": 0.22, "hard": 0.08},
    "legal_thriller":       {"avg": 16, "long": 0.12, "dialogue": 0.25, "hard": 0.09},
    "romance":              {"avg": 16, "long": 0.12, "dialogue": 0.25, "hard": 0.09},
    "historical_romance":   {"avg": 16, "long": 0.12, "dialogue": 0.25, "hard": 0.10},
}
DEFAULT_READ_TARGET = {"avg": 16, "long": 0.12, "dialogue": 0.22, "hard": 0.09}


def read_target(genre_preset: str) -> dict:
    return READ_TARGETS.get(genre_preset or "", DEFAULT_READ_TARGET)


def readability(ms: dict) -> dict:
    """Objective ease-of-reading stats, computed not guessed: average sentence
    length, share of marathon sentences, share of dialogue. The house target
    is an effortless page-turner, and these numbers say whether prose drifts
    literary-dense. Targets vary by genre (thrillers punchier than romance)."""
    import re
    text = " ".join(
        b.get("text", "")
        for c in (ms.get("chapters") or []) for b in (c.get("blocks") or []))
    if not text:
        return {}
    sentences = [x.strip() for x in re.split(r"[.!?]+[\s\"']", text) if x.strip()]
    lens = [len(x.split()) for x in sentences if x.split()]
    if not lens:
        return {}
    long_share = sum(1 for n in lens if n > 25) / len(lens)
    para = [b.get("text", "") for c in (ms.get("chapters") or [])
            for b in (c.get("blocks") or [])]
    dialogue = sum(1 for t in para if t.lstrip().startswith(("\u201c", '"')))
    t = read_target(ms.get("genre_preset", ""))
    avg = round(sum(lens) / len(lens), 1)
    dlg = round(dialogue / max(1, len(para)), 3)
    hard, hard_words = hard_word_share(text)
    hard_cap = t.get("hard", 0.09)
    return {
        "avg_sentence_words": avg,
        "long_sentence_share": round(long_share, 3),
        "dialogue_paragraph_share": dlg,
        "hard_word_share": round(hard, 3),
        "hard_words_sample": hard_words[:25],
        "target": t,
        "meets_target": bool(avg <= t["avg"] and long_share <= t["long"]
                             and dlg >= t["dialogue"] and hard <= hard_cap),
        "house_target": (f"avg <= {t['avg']} words, long-sentence share <= "
                         f"{int(t['long']*100)}%, dialogue >= {int(t['dialogue']*100)}%, "
                         f"hard words <= {int(hard_cap*100)}%"),
    }


def _syllables(word: str) -> int:
    w = word.lower()
    if len(w) <= 3:
        return 1
    w = w.rstrip("e") if not w.endswith(("le", "ee", "ye")) else w
    import re
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("ed") and not w.endswith(("ted", "ded")):
        n -= 1
    return max(1, n)


def hard_word_share(text: str) -> tuple:
    """Share of running words with 3+ syllables, ignoring proper nouns and a
    short list of everyday long words. Returns (share, most frequent hard words)."""
    import re
    from collections import Counter
    EASY = {"everything", "anything", "something", "nothing", "beautiful", "remember",
            "tomorrow", "yesterday", "family", "another", "already", "afternoon",
            "evening", "together", "probably", "suddenly", "whatever", "understand",
            "important", "different", "interested", "interesting", "carefully", "quietly",
            "finally", "actually", "usually", "really", "seriously", "obviously",
            "company", "somebody", "anybody", "everybody", "however", "several",
            "himself", "herself", "wonderful", "terrible", "impossible", "immediately"}
    tokens = re.findall(r"[A-Za-z][A-Za-z'\-]+", text)
    if not tokens:
        return 0.0, []
    counts = Counter()
    hard = 0
    total = 0
    for i, tok in enumerate(tokens):
        total += 1
        if tok[0].isupper() and i > 0 and not tokens[i - 1].endswith((".", "!", "?")):
            continue  # proper noun mid-sentence
        w = tok.lower().strip("'-")
        if w in EASY or len(w) < 7:
            continue
        if _syllables(w) >= 3:
            hard += 1
            counts[w] += 1
    return hard / max(1, total), [w for w, _ in counts.most_common(25)]


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
    def _samples(limit_chars: int = 0) -> str:
        """Keystone chapters for the editor to read. limit_chars > 0 trims each
        to an opening extract — a large all-chapters payload can trip the
        model's safeguards, and an extract still shows the prose."""
        out = []
        for c in chapters:
            if c.get("index") not in keystones or not c.get("blocks"):
                continue
            text = _chapter_text(c)
            if limit_chars and len(text) > limit_chars:
                text = text[:limit_chars] + "\n[extract ends]"
            label = "EXTRACT" if limit_chars else "FULL TEXT"
            out.append(f"=== {label}, CHAPTER {c.get('index')}: {c.get('title')} ===\n{text}")
        return "\n\n".join(out)

    samples = _samples()

    def _build(samples_text: str) -> str:
        return (
        f"MANUSCRIPT LEDGER ({len(chapters)} chapters):\n{ledger}\n\n"
        f"STORY ARCHITECTURE:\n{json.dumps(am)[:2500]}\n\n"
        f"KEYSTONE CHAPTERS:\n{samples_text}\n\n"
        "You are the managing editor deciding whether this manuscript leaves "
        "the house. Judge it as a PUBLISHED BOOK will be judged: does the arc "
        "hold across the whole length, do the pinned beats actually land, "
        "does the middle sag, are setups paid off, is the voice consistent — "
        "and above all, is it an EFFORTLESS, FUN read the target reader "
        "finishes in a few evenings and recommends? Judge the EMOTIONAL CURVE "
        "explicitly: does chapter one excite, does the story escalate with real "
        "highs and lows, does the middle lift and drop rather than plateau, does "
        "the climax pay off what was promised — the way the best fiction does? "
        "Name the flat stretches. Flag any stretch where "
        "prose turns dense or effortful: long stacked sentences, rare words, "
        "rumination that stalls the story. The reader must never work.\n\n"
        "THE BAR: accept means the book would sell and not embarrass the "
        "imprint — not that nothing could be improved. Separate BLOCKING "
        "problems (a fact stated two ways, a beat the plot depends on that is "
        "missing, a truncated or broken chapter, a sagging stretch, prose the "
        "reader must work at) from polish. If there are no blocking problems "
        "and the score is 8.3 or above, the verdict is ACCEPT, and the "
        "remaining notes go under \"polish\" rather than \"issues\". Never "
        "order the opposite of a previous round (do not ask to lengthen what "
        "you asked to cut). Return JSON only:\n"
        '{"verdict": "accept" | "revise", "score": 0-10 one decimal, '
        '"strengths": ["..."], '
        '"issues": [{"chapter": N, "order": "the concrete fix, phrased as an '
        'editor\'s instruction"}] (only chapters that truly need work), '
        '"polish": ["optional non-blocking notes"], '
        '"editor_letter": "6-10 sentences to the publisher: the honest read"}'
        )

    prompt = _build(samples)
    editor_system = (
        "You are a veteran managing editor at a commercial publishing house. "
        "You accept nothing that would embarrass the imprint, and your "
        "revision orders are concrete enough to execute.")
    # Reading ladder: the full payload on the writing model; if it declines,
    # a lighter read (extracts); if it still declines, other readers in turn.
    # A finished book must never end up with no verdict.
    from .client import mechanical_model
    attempts = [
        (None, prompt),
        (None, _build(_samples(6000))),
        (fallback_model(), _build(_samples(6000))),
        (mechanical_model(), _build(_samples(6000))),
    ]
    raw, last_refusal = None, None
    for mdl, body in attempts:
        try:
            raw = await complete(editor_system, body, max_tokens=16000,
                                 model=mdl, allow_fallback=(mdl is None))
            break
        except ContentRefused as e:
            last_refusal = e
            continue
    if raw is None:
        raise last_refusal or RuntimeError("acceptance read failed")
    out = extract_json(raw)
    # models occasionally emit the object wrapped in a list, or lead with the
    # issues array — normalize to the review dict or fail informatively
    if isinstance(out, list):
        out = next((x for x in out if isinstance(x, dict) and "verdict" in x),
                   next((x for x in out if isinstance(x, dict)), None))
    if not isinstance(out, dict) or "verdict" not in out:
        raise RuntimeError(f"Editor returned an unparseable review: {str(out)[:200]}")
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
        # expand toward the BOOK's own budget (target / chapters), not the
        # genre preset — a pinned chapter count makes chapters longer, and
        # repairing to the preset size would lock the shortfall in
        _n = len(ms.get("chapters") or []) or 1
        _target_total = int(ms.get("target_words") or 0)
        target_words = (max(600, round(_target_total / _n)) if _target_total
                        else int(preset.get("chapter_words", 3000)))
        targets = shortest_chapters(length, target_words)
        for i, idx in enumerate(targets):
            handle.progress(0.08 + 0.3 * i / max(1, len(targets)), "length",
                            f"Expanding short chapter {idx} to full length")
            # EXPAND in place — never redraft from the outline: a redraft
            # throws away every canon ruling and editor's fix in the chapter
            try:
                await revise_chapter(catalog, idx, [
                    f"This chapter is short. Bring it to about {target_words} words by DRAMATIZING "
                    "— add scene, action and dialogue that advance the same events; no rumination, "
                    "no recap. Keep every fact, name, date and line of the existing text; change "
                    "nothing that is already there except to extend it."], [], target_words=target_words)
            except Exception:
                continue
            report["length_repairs"].append(idx)
        ms = get_book_by_catalog(catalog)["data"].get("manuscript") or {}
        length = measure_length(ms, preset)
    report["length"] = length
    report["readability"] = readability(ms)

    # ── gate 2: continuity (cheap, always runs) ──────────────────
    handle.progress(0.4, "continuity", "Checking timelines, names and beats")
    from .quality import continuity_audit
    try:
        cont = await continuity_audit(catalog)
    except Exception:
        cont = {"contradictions": []}
    report["continuity"] = cont.get("contradictions", [])

    # ── gate 3: the editor ───────────────────────────────────────
    # ── the canon pass ───────────────────────────────────────────
    # A contradiction lives in several chapters at once. Fixing only the
    # first chapter settles the fact one way there and leaves the others
    # disagreeing — the verdict then oscillates for rounds. So: one ruling
    # per contradiction (the audit's fix), enforced identically in EVERY
    # chapter it names, before the editor reads.
    report["canon_rulings"] = []
    budget = MAX_CANON_REWRITES
    for con in report["continuity"]:
        chapters = []
        for tok in str(con.get("chapters", "")).replace("ch", "").replace("Ch", "").split(","):
            tok = "".join(ch for ch in tok if ch.isdigit())
            if tok:
                chapters.append(int(tok))
        ruling = (con.get("fix") or "").strip()
        if not chapters or not ruling:
            continue
        order = (f"CANON RULING (enforce exactly, in this chapter and consistent with "
                 f"the rest of the book): {ruling} Context of the contradiction: "
                 f"{con.get('problem','')} Change only what is needed to obey the ruling.")
        done = []
        for idx in chapters:
            if budget <= 0:
                break
            handle.progress(0.42, "canon", f"Enforcing one ruling in chapter {idx}")
            try:
                await revise_chapter(catalog, idx, [order], [])
                done.append(idx); budget -= 1
            except Exception:
                continue
        report["canon_rulings"].append({"chapters": done, "ruling": ruling})

    handle.progress(0.45, "editorial", "The managing editor is reading")
    review = await editorial_review(catalog)
    if review.get("issues"):
        review["verdict"] = review.get("verdict", "revise")

    if review.get("verdict") == "revise" and review.get("issues"):
        orders = review["issues"][:MAX_REVISE_ORDERS]
        for i, issue in enumerate(orders):
            if not isinstance(issue, dict):
                continue
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
        # every rewrite can reintroduce a contradiction: re-run the
        # mechanical check on the touched chapters before the editor re-reads
        handle.progress(0.86, "continuity", "Re-checking facts after the rewrites")
        try:
            cont2 = await continuity_audit(catalog)
            report["continuity"] = cont2.get("contradictions", [])
            budget2 = 6
            for con in report["continuity"]:
                chapters = [int("".join(ch for ch in tok if ch.isdigit())) for tok in str(con.get("chapters", "")).replace("ch", "").replace("Ch", "").split(",") if any(ch.isdigit() for ch in tok)]
                ruling = (con.get("fix") or "").strip()
                if not chapters or not ruling:
                    continue
                order = (f"CANON RULING (enforce exactly, in this chapter and consistent with the rest of the book): {ruling} "
                         f"Context: {con.get('problem','')} Change only what is needed to obey the ruling.")
                for idx in chapters:
                    if budget2 <= 0:
                        break
                    try:
                        await revise_chapter(catalog, idx, [order], [])
                        budget2 -= 1
                    except Exception:
                        continue
            if report["continuity"] and budget2 < 6:
                cont3 = await continuity_audit(catalog)
                report["continuity"] = cont3.get("contradictions", [])
        except Exception:
            pass
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


async def rulings_job(handle, catalog: str, rulings: list) -> dict:
    """The publisher's rulings: a named fix enforced identically in every
    chapter it touches, then the editor re-reads. For the cases the
    ordinary desk loop cannot settle — a fact that several chapters state
    differently, a truncated ending, a stub chapter — one pass, manuscript-
    wide, instead of another oscillating round.
    rulings: [{"chapters": [..], "ruling": "..."}]"""
    from .quality import gate_chapter, revise_chapter
    from ..database import update_book

    book = get_book_by_catalog(catalog)
    report = dict(book["data"].get("acceptance") or {})
    report.setdefault("canon_rulings", [])
    total = sum(len(r.get("chapters") or []) for r in rulings) or 1
    n = 0
    for r in rulings:
        ruling = (r.get("ruling") or "").strip()
        done = []
        for idx in r.get("chapters") or []:
            n += 1
            handle.progress(0.05 + 0.75 * n / total, "canon", f"Enforcing the ruling in chapter {idx}")
            order = (f"CANON RULING (enforce exactly, in this chapter and consistent with "
                     f"the rest of the book): {ruling} Change only what is needed to obey the ruling.")
            try:
                await revise_chapter(catalog, int(idx), [order], [])
                if r.get("gate"):
                    await gate_chapter(catalog, int(idx))
                done.append(int(idx))
            except Exception:
                continue
        report["canon_rulings"].append({"chapters": done, "ruling": ruling, "publisher": True})

    handle.progress(0.85, "editorial", "The managing editor re-reads")
    ms = get_book_by_catalog(catalog)["data"].get("manuscript") or {}
    report["readability"] = readability(ms)
    review = await editorial_review(catalog)
    report["review"] = review
    report["verdict"] = review.get("verdict", "revise")
    report["score"] = review.get("score")
    data = dict(get_book_by_catalog(catalog)["data"])
    data["acceptance"] = report
    update_book(book["id"], data)
    return {"verdict": report["verdict"], "score": report.get("score")}
