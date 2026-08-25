"""
SCRPT Writing Pipeline
=======================
Idea -> plot options -> bible -> outline -> chapter drafts -> blurb.

Fiction gets a StoryBible (continuity canon); non-fiction a ConceptBible
(framework + terminology + a hard no-fabricated-evidence policy).

All stages persist into book.data["manuscript"] after every step, so progress
survives restarts and the frontend can render live.
"""

import json
import uuid
from typing import Optional

from ..database import get_book_by_catalog, update_book, get_setting
from ..jobs import JobHandle
from . import storygrid as _sg
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
    # Re-read before writing: cover variants (and other jobs) run in PARALLEL
    # with drafting, and a stale snapshot here would wipe their writes.
    fresh = get_book_by_catalog(book["catalog_number"])
    data = dict(fresh["data"]) if fresh else dict(book["data"])
    data["manuscript"] = ms.model_dump(mode="json")
    if status:
        update_book(book["id"], {"status": status, **data})
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
        "SERIES DOCTRINE (non-negotiable): every book stands alone. Same "
        "main character(s), same universe - but the current book is a "
        "complete story in itself: a reader who starts here follows "
        "everything and gets a full arc with a real ending, strong enough "
        "to be adapted as its own film. Weave needed background in "
        "organically through scene and dialogue - never recap-dump, never "
        "make this plot depend on events of other books, never end the "
        "main plot on a cliffhanger. Series-long threads simmer in the "
        "background only. The series timeline always moves FORWARD: each "
        "book's present-day story takes place after the previous book's - "
        "book 3 never happens before book 2. Referencing past events is "
        "fine; setting the current story earlier than a previous book is "
        "not, unless the series bible explicitly plans it as a strategic "
        "move.\n"
    )


def _fiction_system(ms: Manuscript) -> str:
    p = _preset(ms)
    return (
        "You are a master commercial novelist writing a "
        f"{p['comps']}. You write clean, propulsive, sensory prose for adult readers. "
        "You never mention real living people as characters, never use trademarked "
        "franchises, and never imitate any single author's protected expression — "
        "you write in the genre's tradition with an original voice. "
        "Institutions are INVENTED: fictional agencies, bureaus and companies "
        "(never NSA, CIA, FBI or other real organizations as story engines — "
        "invent equivalents with their own names, the way most published "
        "thrillers do). "
        "HOUSE READING STYLE (non-negotiable): these are books people FINISH. "
        "Write for effortless, fun reading: mostly short and medium sentences, "
        "everyday words (a vivid image beats a rare word), dialogue-forward "
        "scenes, one idea per sentence. PLAIN WORDS: prefer the common word "
        "every time — 'use' not 'utilize', 'start' not 'commence', 'enough' "
        "not 'sufficient'; a word of three or more syllables only when no "
        "plain word will do (the house measures this: under one word in ten). "
        "Interiority in quick strokes — never "
        "long rumination. Every scene runs on visible want and friction; every "
        "chapter ends with a reason to start the next. If a sentence would "
        "make a tired reader re-read it, rewrite it simpler. "
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


def _bible_digest(ms: Manuscript, include_facts: bool = True) -> str:
    if ms.kind == BookKind.FICTION and ms.story_bible:
        b = ms.story_bible
        chars = "\n".join(
            f"  - {c.name} ({c.role}): {c.description} Arc: {c.arc} Voice: {c.voice}"
            for c in b.characters
        )
        facts = ("\nESTABLISHED CANON FACTS:\n"
                 + "\n".join(f"  - {f}" for f in b.facts[-40:])) if include_facts else ""
        return (
            f"LOGLINE: {b.logline}\nPREMISE: {b.premise}\nTONE: {b.tone}\n"
            f"POV: {b.pov} | TENSE: {b.tense}\nSETTING: {b.setting} ({b.time_period})\n"
            f"THEMES: {', '.join(b.themes)}\nSTYLE: {b.style_notes}\n"
            f"ENDING (must land here): {b.ending}\n"
            f"CHARACTERS:\n{chars}{facts}"
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
            "TITLES: short, punchy, ownable — one to three words for thrillers "
            "(think of the great franchise one-worders); never generic, never "
            "explanatory.\n"
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
            "TITLES: a two-to-four word concept the reader can own, plus the "
            "subtitle doing the promising (the modern bestseller pattern: short "
            "evocative title, benefit-rich subtitle).\n"
            "Return JSON only:\n"
            '[{"title": "...", "logline": "the promise in one sentence", '
            '"synopsis": "400-600 words: thesis, the named framework and its steps, '
            'who it serves, why now"}]'
        )
        system = _nonfiction_system(ms)

    raw = await complete(system, prompt, max_tokens=16000)
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
    # no plot options (auto-draft): the idea is the synopsis, NEVER the title
    plot = ms.plot_options[chosen] if ms.plot_options else {"title": "", "synopsis": ms.idea}
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
        raw = await complete(_fiction_system(ms), prompt, max_tokens=16000)
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
        raw = await complete(_nonfiction_system(ms), prompt, max_tokens=16000)
        ms.concept_bible = ConceptBible.model_validate(extract_json(raw))

    ms.status = ManuscriptStatus.BIBLE
    _save(book, ms)

    # book 1 of a series with no series bible yet: write it from the story
    # bible and propagate to every member — the same main characters carry
    # the series (thriller same-hero model; romance shared-world model)
    series = book["data"].get("series") or {}
    if (series.get("series_id") and not series.get("series_bible")
            and ms.kind == BookKind.FICTION and ms.story_bible):
        try:
            sb_prompt = (
                f"STORY BIBLE OF BOOK {series.get('book_number', 1)}:\n"
                f"{_bible_digest(ms)}\n\n"
                f"Write the SERIES BIBLE for \"{series.get('series_title')}\" "
                f"({series.get('total_planned', 3)} books planned) — the canon "
                "document every later book must honor. 250-350 words covering: "
                "the recurring protagonist(s) as the series brand (who returns "
                "every book), recurring supporting cast, world rules and tone, "
                "the per-book formula (each entry a SELF-CONTAINED story a newcomer "
                "can start with - recurring cast and world are the connective "
                "tissue, never required prior reading), the timeline rule "
                "(the series moves forward in time: each book takes place "
                "after the previous one), and any "
                "long arcs that grow across books. Plain text."
            )
            series_bible = await complete(_fiction_system(ms), sb_prompt,
                                          max_tokens=2000)
            sid = series["series_id"]
            all_books = get_book_by_catalog  # placeholder to keep imports obvious
            from ..database import list_books as _list_books
            for member in _list_books(per_page=200)["books"]:
                mdata = member["data"]
                if (mdata.get("series") or {}).get("series_id") == sid:
                    d = dict(mdata)
                    d["series"]["series_bible"] = series_bible.strip()[:4000]
                    update_book(member["id"], d)
        except Exception:
            pass  # series bible is enhancement, never a blocker

    # give the book its real title the moment the bible exists — the title and
    # author are baked into cover art, so a placeholder must never survive
    # past this stage. Prefer the chosen plot's title; otherwise Claude titles
    # the book from the bible under the house title craft bar.
    placeholder = (not book["title"] or book["title"].startswith("Untitled")
                   or len(book["title"]) > 120 or "\n" in book["title"])
    if placeholder:
        real_title = (plot.get("title") or "").strip()
        if not real_title:
            bar = ("one to three words, ownable, franchise-grade — never "
                   "generic, never explanatory"
                   if ms.kind == BookKind.FICTION and "thriller" in ms.genre_preset
                   else "short and evocative in the genre's bestseller register "
                        "— never generic, never explanatory")
            series_ctx = book["data"].get("series") or {}
            t_prompt = (
                f"{_bible_digest(ms)}\n\n"
                + (f"This is book {series_ctx.get('book_number')} of the series "
                   f"\"{series_ctx.get('series_title')}\".\n" if series_ctx.get("series_title") else "")
                + f"Title this {p['label'].lower()}. The bar: {bar}. "
                'Return JSON only: {"title": "..."}'
            )
            raw_t = await complete(_fiction_system(ms) if ms.kind == BookKind.FICTION
                                   else _nonfiction_system(ms), t_prompt, max_tokens=300, mechanical=True)
            real_title = str(extract_json(raw_t).get("title", "")).strip()
        if real_title and len(real_title) <= 120:
            update_book(book["id"], {"title": real_title})

    # the tagline is cover copy, and covers are made while the book is still
    # being written — so it's born here with the bible, from THIS book's
    # story, never inherited from an earlier installment
    if not ms.tagline and ms.kind == BookKind.FICTION:
        try:
            book = get_book_by_catalog(catalog)
            ms.tagline = await _fresh_tagline(book, ms)
            if ms.tagline:
                _save(book, ms)
        except Exception:
            pass  # tagline is enhancement — the blurb stage fills it later


def _taglines_in_use(exclude_id=None) -> list[str]:
    """Every tagline already on a book in the catalog — a new one must never
    repeat any of them (each cover line belongs to exactly one book)."""
    from ..database import list_books
    out = []
    for b in list_books(per_page=500)["books"]:
        if exclude_id is not None and b["id"] == exclude_id:
            continue
        t = ((b["data"].get("manuscript") or {}).get("tagline") or "").strip()
        if t:
            out.append(t)
    return out


async def _fresh_tagline(book: dict, ms: Manuscript) -> str:
    """Write this book's cover tagline — house register, unique in the catalog."""
    used = _taglines_in_use(book["id"])
    avoid = ("\nTaglines already used in this catalog — yours must not repeat "
             "or closely echo ANY of them:\n"
             + "\n".join(f"- {t}" for t in used[:40]) + "\n") if used else ""
    tl_prompt = (
        f"{_bible_digest(ms)}\n\n"
        f"Write the cover tagline for \"{book['title']}\". Cover type, "
        "not a summary: maximum 8 words, staccato fragments in the "
        "genre register — the shape of 'Five days. One truth. No way "
        "down.' — never an explanatory sentence." + avoid +
        'Return JSON only: {"tagline": "..."}'
    )
    used_lower = {t.lower() for t in used}
    for attempt in range(2):
        raw_tl = await complete(_fiction_system(ms), tl_prompt, max_tokens=300, mechanical=True)
        tagline = str(extract_json(raw_tl).get("tagline", "")).strip()[:80]
        if tagline and tagline.lower() not in used_lower:
            return tagline
        tl_prompt += "\nYour previous attempt duplicated an existing tagline. Write a NEW one."
    return ""


# ── stage 3: outline ─────────────────────────────────────────────

def _chapter_budget(ms, preset, n_chapters: int = 0) -> int:
    """How many words each chapter should carry.

    The book's TARGET decides this, not the genre preset: if the publisher
    pins the shape ("4 parts, ~42 chapters") the chapters simply have to be
    longer to reach the target. Falling back to the preset here is what made
    a 98k-word brief come out at 54k — 42 chapters were each told to be a
    preset-sized 1,300 words."""
    n = n_chapters or len(ms.chapters)
    if n and ms.target_words:
        return max(600, round(ms.target_words / n))
    return preset["chapter_words"]


async def build_outline(catalog: str, on_progress=None) -> None:
    book, ms = _load(catalog)
    p = _preset(ms)
    # the publisher's brief can pin the shape (e.g. "4 parts, ~42 chapters");
    # otherwise the genre preset's chapter length decides how many there are
    pinned = book["data"].get("chapter_count")
    n_chapters = (int(pinned) if pinned
                  else max(6, round(ms.target_words / p["chapter_words"])))

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

    genre_structure = p.get("structure", "")
    craft_txt = ("Apply the current bestselling craft standards of this genre — structure beats at their proven percentages, retention mechanics, and the language norms of its top authors.")

    # Stage 1 — STORY ARCHITECTURE. At 25-30 chapters a book lives or dies
    # on its spine, so the whole arc is designed before a single chapter is
    # outlined: acts, structure beats pinned to exact chapter numbers,
    # named threads with payoff chapters, planted setups, and the cinematic
    # set pieces that make the book optionable for screen. Waves then fill
    # chapters INTO this blueprint instead of improvising the middle.
    arch_prompt = (
        f"BIBLE:\n{_bible_digest(ms)}\n\n"
        f"Design the STORY ARCHITECTURE for a {n_chapters}-chapter, "
        f"{ms.target_words}-word {p['label'].lower()} — a blueprint strong "
        "enough that a producer could option it for the screen: every "
        "chapter load-bearing, no sag anywhere.\n"
        f"{shape}\nGENRE STRUCTURE (non-negotiable): {genre_structure}\n"
        f"{craft_txt}\n"
        "Return JSON only:\n"
        '{"acts": [{"name": "...", "chapters": "e.g. 1-8", "purpose": "..."}], '
        '"pinned_beats": [{"chapter": N, "beat": "inciting incident | first '
        'turn | midpoint reversal | all-is-lost | climax | resolution (and '
        'genre-specific beats)", "what_happens": "concrete event"}], '
        '"threads": [{"name": "...", "type": "main arc | relationship | '
        'subplot", "arc": "how it builds, turns and resolves across the '
        'chapters", "payoff_chapter": N}], '
        '"setups_payoffs": [{"setup_chapter": N, "payoff_chapter": N, '
        '"element": "what is planted and how it pays off"}], '
        '"set_pieces": [{"chapter": N, "scene": "a vivid, cinematic, '
        'memorable scene"}]}\n'
        "BE TERSE so the whole blueprint fits: purpose ≤40 words, "
        "what_happens ≤25 words, arc ≤40 words, scene ≤20 words. Every key "
        "is REQUIRED — an architecture without pinned_beats, threads and "
        "set_pieces is invalid."
    )

    def _arc_ok(am: dict) -> bool:
        if not (am.get("acts") and am.get("pinned_beats") and am.get("threads")):
            return False
        pinned = [b.get("chapter") or 0 for b in am["pinned_beats"]]
        # beats must reach deep into the book — a truncated blueprint stops early
        return max(pinned, default=0) >= int(n_chapters * 0.85)

    if on_progress:
        on_progress("Designing the story architecture — acts, beats, threads")
    ms.arc_map = {}
    for attempt in range(2):
        candidate = extract_json(await complete(system, arch_prompt,
                                                max_tokens=16000, mechanical=True))
        if _arc_ok(candidate):
            ms.arc_map = candidate
            break
    if not ms.arc_map:
        raise RuntimeError(
            "Story architecture came back incomplete twice (missing beats/"
            "threads or truncated) — refusing to outline without a spine")
    _save(book, ms)

    arc_for_waves = json.dumps({
        "acts": ms.arc_map.get("acts", []),
        "pinned_beats": ms.arc_map.get("pinned_beats", []),
        "threads": ms.arc_map.get("threads", []),
        "set_pieces": ms.arc_map.get("set_pieces", []),
    })[:4000]

    # Stage 2 — outline in enforced waves. A single request for 25-30 chapters gets
    # silently shortened by the model (observed: 12 returned of 30 asked —
    # a 90k-word book heading for 36k). Waves of ≤10 keep each response
    # honest, and the loop guarantees the full count.
    chapters: list = []
    wave = 10
    total_waves = -(-n_chapters // wave)
    while len(chapters) < n_chapters:
        start = len(chapters) + 1
        end = min(n_chapters, len(chapters) + wave)
        # never leave a runt final wave: asking for a single chapter invites a
        # bare object (or nothing) instead of a list. Absorb a 1-2 chapter
        # remainder into this wave instead.
        if 0 < n_chapters - end <= 2:
            end = n_chapters
        if on_progress:
            on_progress(f"Outline wave {(start - 1) // wave + 1} of {total_waves} — chapters {start}–{end} of {n_chapters}")
        so_far = ""
        if chapters:
            done = "\n".join(
                f"{i + 1}. {c.get('title', '')}: {str(c.get('summary', ''))[:160]}"
                for i, c in enumerate(chapters))
            so_far = ("CHAPTERS ALREADY OUTLINED (continue the arc, never "
                      f"repeat):\n{done}\n\n")
        prompt = (
            f"BIBLE:\n{_bible_digest(ms)}\n\n"
            f"STORY ARCHITECTURE (the approved blueprint — every pinned beat, "
            f"set piece, setup and payoff in your range MUST land on its "
            f"exact chapter number):\n{arc_for_waves}\n\n{so_far}"
            f"The complete book has exactly {n_chapters} chapters totalling "
            f"{ms.target_words} words (≈{_chapter_budget(ms, p, n_chapters)} words per "
            f"chapter). {shape}\n"
            f"GENRE STRUCTURE (non-negotiable): {genre_structure}\n"
            f"{_sg.obligatory_block(ms.genre_preset)}\n\n"
            f"{_sg.STORY_EVENT_RULE}\n"
            f"{craft_txt}\n"
            f"Outline chapters {start} through {end} ONLY — exactly "
            f"{end - start + 1} chapters, sitting at "
            f"{round(100 * start / n_chapters)}%–{round(100 * end / n_chapters)}% "
            "of the whole story. Every chapter advances at least one named "
            "thread — no filler chapter survives this outline.\n"
            "Return JSON only:\n"
            '[{"title": "...", "summary": "120-200 words on what happens / what it teaches", '
            '"story_event": "ONE sentence: what happens, and which value shifts from what to what "'
            '"(e.g. \'Luc breaks into the archive and learns his friend was murdered — safety to danger\')", '
            '"crisis": "the dilemma this chapter forces: two bad options, or two goods that cannot both be had", '
            '"beats": ["beat 1", "beat 2", "beat 3", "beat 4", "beat 5"]}]'
        )
        got = None
        for attempt in range(3):
            raw = await complete(system, prompt, max_tokens=20000)
            got = extract_json(raw)
            # a one-chapter wave often comes back as a bare object
            if isinstance(got, dict) and got.get("title"):
                got = [got]
            if isinstance(got, list) and got:
                break
            got = None
        if not got:
            raise RuntimeError(
                f"Outline wave {start}-{end} returned no chapters after 3 attempts")
        chapters.extend(got[:end - start + 1])
    chapters = chapters[:n_chapters]

    ms.chapters = [
        Chapter(
            id=uuid.uuid4().hex[:10],
            index=i + 1,
            title=str(ch.get("title", f"Chapter {i+1}")),
            story_event=str(ch.get("story_event", "") or "")[:400],
            crisis=str(ch.get("crisis", "") or "")[:400],
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

    # this chapter's duties from the story architecture, if one exists
    arc_note = ""
    am = ms.arc_map or {}
    if am:
        duties = []
        pins = [b for b in am.get("pinned_beats", []) if b.get("chapter") == index]
        if pins:
            duties.append("STRUCTURAL BEAT — this chapter IS: " + "; ".join(
                f"{b.get('beat', '')} ({b.get('what_happens', '')})" for b in pins))
        pieces = [s for s in am.get("set_pieces", []) if s.get("chapter") == index]
        if pieces:
            duties.append("SET PIECE — stage it cinematically: " + "; ".join(
                s.get("scene", "") for s in pieces))
        sp = am.get("setups_payoffs", [])
        plants = [x.get("element", "") for x in sp if x.get("setup_chapter") == index]
        pays = [x.get("element", "") for x in sp if x.get("payoff_chapter") == index]
        if plants:
            duties.append("PLANT subtly here: " + "; ".join(plants))
        if pays:
            duties.append("PAY OFF here: " + "; ".join(pays))
        if duties:
            arc_note = ("ARCHITECTURE DUTIES FOR THIS CHAPTER (non-negotiable):\n"
                        + "\n".join(f"- {d}" for d in duties) + "\n\n")

    system = _fiction_system(ms) if ms.kind == BookKind.FICTION else _nonfiction_system(ms)
    stable_context = (
        f"BIBLE:\n{_bible_digest(ms, include_facts=False)}\n\n"
        f"FULL OUTLINE:\n{_outline_digest(ms)}"
    )
    facts_block = ""
    if ms.kind == BookKind.FICTION and ms.story_bible and ms.story_bible.facts:
        facts_block = ("ESTABLISHED CANON FACTS:\n"
                       + "\n".join(f"  - {f}" for f in ms.story_bible.facts[-40:])
                       + "\n\n")
    opening_rule = (
        "THIS IS CHAPTER ONE — it sells the book. Open IN SCENE, mid-motion: no weather, "
        "no waking up, no history lesson. Within the first 300 words the reader must feel "
        "the story's question or a live tension and know what the protagonist wants right "
        "now. The first paragraph sets the tone of the whole book. End on a pull that makes "
        "chapter two unavoidable. Short paragraphs; a first line that could be quoted.\n\n"
        if index == 1 else "")
    prompt = (
        f"{opening_rule}"
        f"{facts_block}"
        f"STORY SO FAR:\n{prev_summaries}\n{prev_tail}\n"
        f"NOW WRITE CHAPTER {index}: \"{ch.title}\"\n"
        f"Chapter brief: {ch.outline_summary}\nBeats to hit:\n{beats}\n\n"
        f"{arc_note}"
        f"Length: {_chapter_budget(ms, p)}-{int(_chapter_budget(ms, p) * 1.25)} words. {dialect}\n"
        f"\n{_sg.craft_block(ms.genre_preset, getattr(ch, 'story_event', '') or '')}\n"
        f"{('THE CRISIS THIS CHAPTER TURNS ON: ' + ch.crisis + chr(10)) if getattr(ch, 'crisis', '') else ''}"

        "Write the chapter text only — no chapter number/title header, no commentary.\n"
        "Then, after the chapter, output exactly one line starting with '@@META@@ ' "
        "followed by JSON: {\"rolling_summary\": \"150-250 words: everything a future "
        "chapter must know about what just happened\", \"new_facts\": [\"new canon fact "
        "established in this chapter\"]}"
    )

    raw = await complete(system, prompt, max_tokens=20000,
                         cached_context=stable_context)

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

    series = book["data"].get("series") or {}
    in_series = bool(series.get("series_title"))
    wants_teaser = in_series and series.get("book_number", 1) < series.get("total_planned", 1)
    teaser_field = (
        ', "next_in_series_teaser": "60-90 words for the back of THIS book: a teaser '
        f"pointing the reader to book {series.get('book_number', 1) + 1} of "
        f"{series.get('series_title', '')} — hook them without spoiling, end with an "
        'invitation to continue the series"' if wants_teaser else "")
    prompt = (
        f"BIBLE:\n{_bible_digest(ms)}\n\nOUTLINE:\n{_outline_digest(ms)}\n\n"
        f"OPENING OF THE BOOK:\n{opening}\n\n"
        f"Write the Amazon listing package for \"{book['title']}\". The description must "
        "hook in the first line (it shows above the fold), tease without spoiling, and "
        "end with a call to action. 150-200 words, short paragraphs.\n"
        "Return JSON only:\n"
        '{"tagline": "cover type, not a summary: maximum 8 words, staccato fragments in the genre register — the shape of \'Five days. One truth. No way down.\' — never an explanatory sentence", '
        '"description": "the Amazon book description", '
        '"back_cover": "the PRINT back-cover copy. Small trims (5x8, 5.25x8) take 120-140 words in at most 7 paragraphs; larger trims take 150-180 words. This is SALES '
        'copy a browser reads in ten seconds: sentences under 15 words, plain '
        'everyday language a 12-year-old follows, no nested clauses, no words '
        'like unbeknownst. Name the hero, name the want, name the obstacle. '
        'Short paragraphs, some one line. END on a question or cliff that '
        'makes them open the book.", '
        '"keywords": ["7 KDP backend search phrases, 2-4 words each"], '
        f'"categories": ["3 specific Amazon browse category paths"]{teaser_field}}}'
    )
    raw = await complete(system, prompt, max_tokens=2500, mechanical=True)
    pkg = extract_json(raw)

    book, ms = _load(catalog)
    ms.blurb = str(pkg.get("description", ""))
    # a tagline born at the bible stage may already be baked into cover art —
    # never let the blurb stage contradict the cover
    if not ms.tagline:
        candidate = str(pkg.get("tagline", "")).strip()[:80]
        if candidate and candidate.lower() in {t.lower() for t in _taglines_in_use(book["id"])}:
            candidate = await _fresh_tagline(book, ms)  # unique or empty
        ms.tagline = candidate
    if pkg.get("next_in_series_teaser"):
        ms.back_matter.next_in_series_cta = str(pkg["next_in_series_teaser"])
    _save(book, ms)
    if pkg.get("back_cover"):
        fresh = get_book_by_catalog(catalog)
        data = dict(fresh["data"])
        data["back_cover_blurb"] = str(pkg["back_cover"])
        update_book(fresh["id"], data)
    update_book(book["id"], {
        "description": ms.blurb,
        "keywords": [str(k) for k in pkg.get("keywords", [])][:7],
        "categories": [str(c) for c in pkg.get("categories", [])][:3],
    })
    return pkg


# ── orchestrated full-draft job ──────────────────────────────────

async def full_draft_job(handle: JobHandle, catalog: str, chosen_plot: int = 0,
                         edits: str = "") -> dict:
    """market check -> bible -> outline -> every chapter -> blurb."""
    book, ms = _load(catalog)
    from .client import set_model_override
    set_model_override(book["data"].get("writing_model_override"))

    # standing stage: verify length + trim against the LIVE market before a
    # single word is drafted. House presets are templates; the market decides.
    if not book["data"].get("market_check"):
        handle.progress(0.01, "market", "Checking the live market: length, format, trim")
        try:
            from .market import apply_market_check, market_check
            check = await market_check(book, ms)
            data = dict(get_book_by_catalog(catalog)["data"])
            adjustments = apply_market_check(data, ms, check)
            check["adjustments"] = adjustments
            data["market_check"] = check
            data["manuscript"] = ms.model_dump(mode="json")
            update_book(book["id"], data)
            book, ms = _load(catalog)
        except Exception:
            pass  # market check must never block production

    if ms.status in (ManuscriptStatus.IDEA, ManuscriptStatus.PLOTTING):
        handle.progress(0.02, "bible", "Building the book bible")
        await build_bible(catalog, chosen_plot, edits)
    if handle.cancelled():
        return {}

    _, ms = _load(catalog)
    if not ms.chapters:
        handle.progress(0.06, "outline", "Designing the chapter outline")
        await build_outline(
            catalog,
            on_progress=lambda d: handle.progress(0.06, "outline", d))
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
        base = 0.08 + 0.82 * (n / max(1, len(remaining)))
        handle.progress(base, "drafting", f"Chapter {idx}/{total}: {ch.title}")
        await draft_chapter(catalog, idx)
        # quality gate: audit against the playbook, one rewrite if below bar
        handle.progress(base + 0.4 / max(1, len(remaining)), "quality",
                        f"Quality gate — chapter {idx}/{total}")
        try:
            from .quality import gate_chapter
            await gate_chapter(catalog, idx)
        except Exception:
            pass  # the gate must never kill a draft

    handle.progress(0.92, "audit", "Whole-book quality audit")
    try:
        from .quality import book_audit
        book_audit(catalog)
    except Exception:
        pass

    # the acceptance desk: length gate + managing-editor read, with bounded
    # automated repair. A failure here must not kill the draft — the verdict
    # (including "revise") is stored and gates the Production Queue instead.
    handle.progress(0.93, "acceptance", "The acceptance desk takes the manuscript")
    try:
        from .acceptance import acceptance_job

        class _Sub:
            """Scale acceptance progress into the 0.93-0.96 window."""
            def progress(self, frac, stage, detail):
                handle.progress(0.93 + 0.03 * frac, stage, detail)
            def cancelled(self):
                return handle.cancelled()

        await acceptance_job(_Sub(), catalog)
    except Exception as e:
        # never kill the draft, but never lose the reason either — a silent
        # pass here leaves a finished book with no verdict and no explanation
        fresh = get_book_by_catalog(catalog)
        data = dict(fresh["data"])
        data["acceptance"] = {"verdict": "not_run", "error": str(e)[:500]}
        update_book(fresh["id"], data)

    handle.progress(0.96, "blurb", "Writing the listing copy")
    await generate_blurb(catalog)

    # automatic front cover — a failure here must not fail the manuscript.
    # Never replace an existing cover: publisher uploads, a chosen variant,
    # or the commission-time variants (the publisher picks from those).
    cover_error = ""
    existing_cover = (get_book_by_catalog(catalog)["data"].get("cover") or {})
    if (existing_cover.get("mode") == "upload"
            or existing_cover.get("selected_variant")
            or existing_cover.get("cover_front_png")
            or existing_cover.get("variants")):
        handle.progress(0.97, "cover", "Cover already in hand — keeping it")
    else:
        handle.progress(0.97, "cover", "Creating the front cover")
        try:
            from ..cover.front_cover import generate_front_cover
            await generate_front_cover(catalog)
        except Exception as e:
            cover_error = str(e)[:300]

    book, ms = _load(catalog)
    ms.status = ManuscriptStatus.DRAFTED
    _save(book, ms, status="draft")
    result = {"chapters": len(ms.chapters), "words": ms.word_count}
    if cover_error:
        result["cover_error"] = cover_error
    return result
