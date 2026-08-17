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
from ..prose.models import (
    BookKind, Chapter, ChapterStatus, Character, ConceptBible, GENRE_PRESETS,
    Manuscript, ManuscriptStatus, StoryBible,
)
from ..craft import craft
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
        raw = await complete(_fiction_system(ms), prompt, max_tokens=10000)
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
        raw = await complete(_nonfiction_system(ms), prompt, max_tokens=10000)
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
                "the per-book formula (what a new entry looks like), and any "
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
                                   else _nonfiction_system(ms), t_prompt, max_tokens=300)
            real_title = str(extract_json(raw_t).get("title", "")).strip()
        if real_title and len(real_title) <= 120:
            update_book(book["id"], {"title": real_title})


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

    genre_structure = p.get("structure", "")
    craft_txt = craft(ms.genre_preset, "OUTLINE")

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
        'memorable scene"}]}'
    )
    ms.arc_map = extract_json(await complete(system, arch_prompt,
                                             max_tokens=8000))
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
    while len(chapters) < n_chapters:
        start = len(chapters) + 1
        end = min(n_chapters, len(chapters) + wave)
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
            f"{ms.target_words} words (≈{p['chapter_words']} words per "
            f"chapter). {shape}\n"
            f"GENRE STRUCTURE (non-negotiable): {genre_structure}\n"
            f"{craft_txt}\n"
            f"Outline chapters {start} through {end} ONLY — exactly "
            f"{end - start + 1} chapters, sitting at "
            f"{round(100 * start / n_chapters)}%–{round(100 * end / n_chapters)}% "
            "of the whole story. Every chapter advances at least one named "
            "thread — no filler chapter survives this outline.\n"
            "Return JSON only:\n"
            '[{"title": "...", "summary": "120-200 words on what happens / what it teaches", '
            '"beats": ["beat 1", "beat 2", "beat 3", "beat 4", "beat 5"]}]'
        )
        raw = await complete(system, prompt, max_tokens=12000)
        got = extract_json(raw)
        if not isinstance(got, list) or not got:
            raise RuntimeError(
                f"Outline wave {start}-{end} returned no chapters")
        chapters.extend(got[:end - start + 1])
    chapters = chapters[:n_chapters]

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
    prompt = (
        f"BIBLE:\n{_bible_digest(ms)}\n\n"
        f"FULL OUTLINE:\n{_outline_digest(ms)}\n\n"
        f"STORY SO FAR:\n{prev_summaries}\n{prev_tail}\n"
        f"NOW WRITE CHAPTER {index}: \"{ch.title}\"\n"
        f"Chapter brief: {ch.outline_summary}\nBeats to hit:\n{beats}\n\n"
        f"{arc_note}"
        f"Length: {p['chapter_words']}-{int(p['chapter_words']*1.25)} words. {dialect}\n"
        f"{craft(ms.genre_preset, 'CHAPTER')}"
        "Write the chapter text only — no chapter number/title header, no commentary.\n"
        "Then, after the chapter, output exactly one line starting with '@@META@@ ' "
        "followed by JSON: {\"rolling_summary\": \"150-250 words: everything a future "
        "chapter must know about what just happened\", \"new_facts\": [\"new canon fact "
        "established in this chapter\"]}"
    )

    raw = await complete(system, prompt, max_tokens=14000)

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
        '"keywords": ["7 KDP backend search phrases, 2-4 words each"], '
        f'"categories": ["3 specific Amazon browse category paths"]{teaser_field}}}'
    )
    raw = await complete(system, prompt, max_tokens=2500)
    pkg = extract_json(raw)

    book, ms = _load(catalog)
    ms.blurb = str(pkg.get("description", ""))
    ms.tagline = str(pkg.get("tagline", ""))
    if pkg.get("next_in_series_teaser"):
        ms.back_matter.next_in_series_cta = str(pkg["next_in_series_teaser"])
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
    """market check -> bible -> outline -> every chapter -> blurb."""
    book, ms = _load(catalog)

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

    handle.progress(0.94, "blurb", "Writing the listing copy")
    await generate_blurb(catalog)

    # automatic front cover — a failure here must not fail the manuscript
    handle.progress(0.97, "cover", "Painting the front cover")
    cover_error = ""
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
