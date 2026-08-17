"""
SCRPT Writing Pipeline
=======================
Idea -> plot options -> bible -> outline -> chapter drafts -> blurb.

Fiction gets a StoryBible (continuity canon); non-fiction a ConceptBible
(framework + terminology + a hard no-fabricated-evidence policy).

All stages persist into book.data["manuscript"] after every step, so progress
survives restarts and the frontend can render live.
"""

import uuid
from typing import Optional

from ..database import get_book_by_catalog, update_book, get_setting
from ..jobs import JobHandle
from ..prose.models import (
    BookKind, Chapter, ChapterStatus, Character, ConceptBible, GENRE_PRESETS,
    Manuscript, ManuscriptStatus, StoryBible,
)
from .client import complete, extract_json
from .parsing import parse_chapter_text, count_words

# Tail of the previous chapter fed verbatim for voice continuity
PREV_TAIL_WORDS = 500


# ── persistence helpers ──────────────────────────────────────────

def _load(catalog: str) -> tuple[dict, Manuscript]:
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError(f"Book {catalog} not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    return book, ms


def _save(book: dict, ms: Manuscript, status: Optional[str] = None):
    data = dict(book["data"])
    data["manuscript"] = ms.model_dump(mode="json")
    if status:
        data["status"] = status  # popped out below
        update_book(book["id"], {"status": status, **{k: v for k, v in data.items() if k != "status"}})
    else:
        update_book(book["id"], data)


# ── prompt fragments ─────────────────────────────────────────────

def _preset(ms: Manuscript) -> dict:
    return GENRE_PRESETS.get(ms.genre_preset, GENRE_PRESETS["action_thriller"])


def _series_context(book: dict) -> str:
    series = book["data"].get("series") or {}
    if not series.get("series_title"):
        return ""
    return (
        f"\nSERIES CONTEXT: This is book {series.get('book_number', 1)} of "
        f"{series.get('total_planned', 1)} in the series \"{series['series_title']}\".\n"
        f"Series bible (canon across all books — never contradict it):\n"
        f"{series.get('series_bible', '(not yet written)')}\n"
    )


def _fiction_system(ms: Manuscript) -> str:
    p = _preset(ms)
    return (
        "You are a master commercial novelist writing a "
        f"{p['comps']}. You write clean, propulsive, sensory prose for adult readers. "
        "You never mention real living people as characters, never use trademarked "
        "franchises, and never imitate any single author's protected expression — "
        "you write in the genre's tradition with an original voice. "
        "Write in English."
    )


def _nonfiction_system(ms: Manuscript) -> str:
    p = _preset(ms)
    policy = ms.concept_bible.evidence_policy if ms.concept_bible else ""
    return (
        f"You are an expert non-fiction author writing a {p['comps']}. "
        "Your writing is concrete, warm, and immediately actionable. "
        f"EVIDENCE POLICY (absolute): {policy} "
        "Write in English."
    )


def _bible_digest(ms: Manuscript) -> str:
    if ms.kind == BookKind.FICTION and ms.story_bible:
        b = ms.story_bible
        chars = "\n".join(
            f"  - {c.name} ({c.role}): {c.description} Arc: {c.arc} Voice: {c.voice}"
            for c in b.characters
        )
        facts = "\n".join(f"  - {f}" for f in b.facts[-40:])
        return (
            f"LOGLINE: {b.logline}\nPREMISE: {b.premise}\nTONE: {b.tone}\n"
            f"POV: {b.pov} | TENSE: {b.tense}\nSETTING: {b.setting} ({b.time_period})\n"
            f"THEMES: {', '.join(b.themes)}\nSTYLE: {b.style_notes}\n"
            f"ENDING (must land here): {b.ending}\n"
            f"CHARACTERS:\n{chars}\nESTABLISHED CANON FACTS:\n{facts}"
        )
    if ms.concept_bible:
        c = ms.concept_bible
        steps = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(c.framework_steps))
        terms = "\n".join(f"  - {k}: {v}" for k, v in c.terminology.items())
        return (
            f"THESIS: {c.thesis}\nPROMISE TO READER: {c.promise}\nAUDIENCE: {c.audience}\n"
            f"FRAMEWORK: {c.framework_name}\n{steps}\nTERMINOLOGY (use consistently):\n{terms}\n"
            f"TONE: {c.tone}\nSTYLE: {c.style_notes}"
        )
    return ""


def _outline_digest(ms: Manuscript) -> str:
    return "\n".join(
        f"  Ch{c.index}: {c.title} — {c.outline_summary}" for c in ms.chapters
    )


# ── stage 1: plot / framework options ────────────────────────────

async def generate_plot_options(catalog: str) -> list[dict]:
    book, ms = _load(catalog)
    p = _preset(ms)
    series = _series_context(book)

    if ms.kind == BookKind.FICTION:
        prompt = (
            f"Book idea from the publisher:\n\"\"\"\n{ms.idea}\n\"\"\"\n{series}\n"
            f"Develop THREE distinct, commercially compelling plot directions for this "
            f"{p['label'].lower()}. Make them genuinely different in engine (what drives "
            "the story), not cosmetic variations. Each must have a complete arc with a "
            "satisfying ending.\n\n"
            "Return JSON only:\n"
            '[{"title": "...", "logline": "one sentence", '
            '"synopsis": "400-600 words, full arc including the ending"}]'
        )
        system = _fiction_system(ms)
    else:
        prompt = (
            f"Book idea from the publisher:\n\"\"\"\n{ms.idea}\n\"\"\"\n{series}\n"
            f"Develop THREE distinct angles for this {p['label'].lower()} book. Each needs "
            "a sharp thesis, a named original framework (an ownable mental model like the "
            "great franchise non-fiction books have), and a clear reader transformation.\n\n"
            "Return JSON only:\n"
            '[{"title": "...", "logline": "the promise in one sentence", '
            '"synopsis": "400-600 words: thesis, the named framework and its steps, '
            'who it serves, why now"}]'
        )
        system = _nonfiction_system(ms)

    raw = await complete(system, prompt, max_tokens=6000)
    options = extract_json(raw)
    ms.plot_options = options[:3]
    ms.status = ManuscriptStatus.PLOTTING
    _save(book, ms)
    return ms.plot_options


# ── stage 2: bible ───────────────────────────────────────────────

async def build_bible(catalog: str, chosen: int = 0, edits: str = "") -> None:
    book, ms = _load(catalog)
    p = _preset(ms)
    series = _series_context(book)
    plot = ms.plot_options[chosen] if ms.plot_options else {"title": ms.idea, "synopsis": ms.idea}
    ms.chosen_plot = chosen
    user_notes = f"\nPublisher notes to incorporate:\n{edits}\n" if edits else ""

    if ms.kind == BookKind.FICTION:
        prompt = (
            f"Chosen plot for the novel \"{plot.get('title','')}\":\n{plot.get('synopsis','')}\n"
            f"{series}{user_notes}\n"
            f"POV convention for this genre: {p['pov']}.\n"
            "Build the complete STORY BIBLE for drafting. Return JSON only:\n"
            '{"logline": "...", "premise": "...", "tone": "...", "pov": "...", '
            '"tense": "past", "setting": "...", "time_period": "...", '
            '"characters": [{"name": "...", "role": "...", "description": "...", '
            '"arc": "...", "voice": "..."}], '
            '"locations": ["..."], "themes": ["..."], '
            '"style_notes": "sentence rhythm, chapter endings, violence/romance heat level", '
            '"ending": "precisely where the book must land"}'
        )
        raw = await complete(_fiction_system(ms), prompt, max_tokens=6000)
        data = extract_json(raw)
        data["genre"] = p["label"]
        ms.story_bible = StoryBible.model_validate(data)
    else:
        prompt = (
            f"Chosen direction for the book \"{plot.get('title','')}\":\n{plot.get('synopsis','')}\n"
            f"{series}{user_notes}\n"
            "Build the complete CONCEPT BIBLE for drafting. Return JSON only:\n"
            '{"thesis": "...", "promise": "...", "audience": "...", '
            '"framework_name": "...", "framework_steps": ["..."], '
            '"terminology": {"term": "definition"}, "tone": "...", '
            '"style_notes": "chapter formula, story/example policy, exercise style"}'
        )
        raw = await complete(_nonfiction_system(ms), prompt, max_tokens=6000)
        ms.concept_bible = ConceptBible.model_validate(extract_json(raw))

    ms.status = ManuscriptStatus.BIBLE
    _save(book, ms)

    # adopt the chosen plot's title if the book still has a placeholder title
    if plot.get("title") and (not book["title"] or book["title"].startswith("Untitled")):
        update_book(book["id"], {"title": plot["title"]})


# ── stage 3: outline ─────────────────────────────────────────────

async def build_outline(catalog: str) -> None:
    book, ms = _load(catalog)
    p = _preset(ms)
    n_chapters = max(6, round(ms.target_words / p["chapter_words"]))

    if ms.kind == BookKind.FICTION:
        system = _fiction_system(ms)
        shape = (
            "Structure with rising stakes, a midpoint reversal, an all-is-lost moment "
            "around the 75% mark, and a climax that pays off every planted setup. "
            "Every chapter must END with a reason to keep reading (question, threat, "
            "reveal, or decision)."
        )
    else:
        system = _nonfiction_system(ms)
        shape = (
            "Chapter 1 names the problem and the promise. Middle chapters each own ONE "
            "step of the framework. The final chapter is integration — what life looks "
            "like on the other side. Each chapter: one idea, stories/examples, "
            "application, a closing exercise."
        )

    prompt = (
        f"BIBLE:\n{_bible_digest(ms)}\n\n"
        f"Create the chapter outline: exactly {n_chapters} chapters, total length "
        f"{ms.target_words} words (≈{p['chapter_words']} words per chapter). {shape}\n\n"
        "Return JSON only:\n"
        '[{"title": "...", "summary": "120-200 words on what happens / what it teaches", '
        '"beats": ["beat 1", "beat 2", "beat 3", "beat 4", "beat 5"]}]'
    )
    raw = await complete(system, prompt, max_tokens=8000)
    chapters = extract_json(raw)

    ms.chapters = [
        Chapter(
            id=uuid.uuid4().hex[:10],
            index=i + 1,
            title=str(ch.get("title", f"Chapter {i+1}")),
            outline_summary=str(ch.get("summary", "")),
            beats=[str(b) for b in ch.get("beats", [])],
            status=ChapterStatus.OUTLINED,
        )
        for i, ch in enumerate(chapters)
    ]
    ms.status = ManuscriptStatus.OUTLINED
    _save(book, ms)


# ── stage 4: chapter drafting ────────────────────────────────────

async def draft_chapter(catalog: str, index: int) -> None:
    book, ms = _load(catalog)
    p = _preset(ms)
    ch = next(c for c in ms.chapters if c.index == index)
    ch.status = ChapterStatus.DRAFTING
    _save(book, ms, status="generating")

    prev_summaries = "\n".join(
        f"  Ch{c.index} ({c.title}): {c.rolling_summary}"
        for c in ms.chapters if c.index < index and c.rolling_summary
    ) or "  (this is the opening chapter)"

    prev_tail = ""
    if index > 1:
        prev = next((c for c in ms.chapters if c.index == index - 1), None)
        if prev and prev.blocks:
            words: list[str] = []
            for b in reversed(prev.blocks):
                words = b.text.split() + words
                if len(words) >= PREV_TAIL_WORDS:
                    break
            prev_tail = (
                f"\nFINAL {min(len(words), PREV_TAIL_WORDS)} WORDS OF PREVIOUS CHAPTER "
                f"(match this voice; do not repeat it):\n...{' '.join(words[-PREV_TAIL_WORDS:])}\n"
            )

    beats = "\n".join(f"  - {b}" for b in ch.beats)
    dialect = (
        "FORMAT: plain paragraphs separated by blank lines; '***' alone on a line for a "
        "scene break; *asterisks* for italics."
        if ms.kind == BookKind.FICTION
        else "FORMAT: plain paragraphs separated by blank lines; '## ' subheads; '- ' "
        "bullet lists; '> ' pull-quotes; ':::callout Title' ... ':::' for a boxed key "
        "idea; ':::exercise Title' ... ':::' for the closing action step; *asterisks* "
        "for italics."
    )

    system = _fiction_system(ms) if ms.kind == BookKind.FICTION else _nonfiction_system(ms)
    prompt = (
        f"BIBLE:\n{_bible_digest(ms)}\n\n"
        f"FULL OUTLINE:\n{_outline_digest(ms)}\n\n"
        f"STORY SO FAR:\n{prev_summaries}\n{prev_tail}\n"
        f"NOW WRITE CHAPTER {index}: \"{ch.title}\"\n"
        f"Chapter brief: {ch.outline_summary}\nBeats to hit:\n{beats}\n\n"
        f"Length: {p['chapter_words']}-{int(p['chapter_words']*1.25)} words. {dialect}\n"
        "Write the chapter text only — no chapter number/title header, no commentary.\n"
        "Then, after the chapter, output exactly one line starting with '@@META@@ ' "
        "followed by JSON: {\"rolling_summary\": \"150-250 words: everything a future "
        "chapter must know about what just happened\", \"new_facts\": [\"new canon fact "
        "established in this chapter\"]}"
    )

    raw = await complete(system, prompt, max_tokens=10000)

    meta = {"rolling_summary": "", "new_facts": []}
    text = raw
    if "@@META@@" in raw:
        text, _, meta_line = raw.rpartition("@@META@@")
        try:
            meta = extract_json(meta_line)
        except ValueError:
            pass

    # reload before writing: another chapter may have saved while we generated
    book, ms = _load(catalog)
    ch = next(c for c in ms.chapters if c.index == index)
    ch.blocks = parse_chapter_text(text.strip())
    ch.word_count = count_words(ch.blocks)
    ch.rolling_summary = str(meta.get("rolling_summary", ""))[:2000]
    ch.status = ChapterStatus.DRAFTED
    if ms.kind == BookKind.FICTION and ms.story_bible is not None:
        for fact in meta.get("new_facts", [])[:10]:
            if fact and fact not in ms.story_bible.facts:
                ms.story_bible.facts.append(str(fact))
    ms.word_count = sum(c.word_count for c in ms.chapters)
    _save(book, ms)


# ── stage 5: blurb & listing copy ────────────────────────────────

async def generate_blurb(catalog: str) -> dict:
    book, ms = _load(catalog)
    system = _fiction_system(ms) if ms.kind == BookKind.FICTION else _nonfiction_system(ms)
    opening = ""
    if ms.chapters and ms.chapters[0].blocks:
        opening = " ".join(b.text for b in ms.chapters[0].blocks[:6])[:1500]

    prompt = (
        f"BIBLE:\n{_bible_digest(ms)}\n\nOUTLINE:\n{_outline_digest(ms)}\n\n"
        f"OPENING OF THE BOOK:\n{opening}\n\n"
        f"Write the Amazon listing package for \"{book['title']}\". The description must "
        "hook in the first line (it shows above the fold), tease without spoiling, and "
        "end with a call to action. 150-200 words, short paragraphs.\n"
        "Return JSON only:\n"
        '{"tagline": "one punchy line for the cover", '
        '"description": "the Amazon book description", '
        '"keywords": ["7 KDP backend search phrases, 2-4 words each"], '
        '"categories": ["3 specific Amazon browse category paths"]}'
    )
    raw = await complete(system, prompt, max_tokens=2500)
    pkg = extract_json(raw)

    book, ms = _load(catalog)
    ms.blurb = str(pkg.get("description", ""))
    ms.tagline = str(pkg.get("tagline", ""))
    _save(book, ms)
    update_book(book["id"], {
        "description": ms.blurb,
        "keywords": [str(k) for k in pkg.get("keywords", [])][:7],
        "categories": [str(c) for c in pkg.get("categories", [])][:3],
    })
    return pkg


# ── orchestrated full-draft job ──────────────────────────────────

async def full_draft_job(handle: JobHandle, catalog: str, chosen_plot: int = 0,
                         edits: str = "") -> dict:
    """bible -> outline -> every chapter -> blurb, with progress reporting."""
    book, ms = _load(catalog)

    if ms.status in (ManuscriptStatus.IDEA, ManuscriptStatus.PLOTTING):
        handle.progress(0.02, "bible", "Building the book bible")
        await build_bible(catalog, chosen_plot, edits)
    if handle.cancelled():
        return {}

    _, ms = _load(catalog)
    if not ms.chapters:
        handle.progress(0.06, "outline", "Designing the chapter outline")
        await build_outline(catalog)
    if handle.cancelled():
        return {}

    _, ms = _load(catalog)
    total = len(ms.chapters)
    remaining = [c.index for c in ms.chapters if c.status in
                 (ChapterStatus.OUTLINED, ChapterStatus.DRAFTING)]
    ms.status = ManuscriptStatus.DRAFTING
    _save(book, ms, status="generating")

    for n, idx in enumerate(remaining):
        if handle.cancelled():
            return {}
        _, cur = _load(catalog)
        ch = next(c for c in cur.chapters if c.index == idx)
        handle.progress(
            0.08 + 0.86 * (n / max(1, len(remaining))),
            "drafting",
            f"Chapter {idx}/{total}: {ch.title}",
        )
        await draft_chapter(catalog, idx)

    handle.progress(0.96, "blurb", "Writing the listing copy")
    await generate_blurb(catalog)

    book, ms = _load(catalog)
    ms.status = ManuscriptStatus.DRAFTED
    _save(book, ms, status="draft")
    return {"chapters": len(ms.chapters), "words": ms.word_count}
