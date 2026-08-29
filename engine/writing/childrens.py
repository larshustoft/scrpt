"""
Children's books — a third kind, not a variant of fiction.

The unit is a SPREAD, not a chapter: a facing pair of pages carrying a little
text and one picture. That changes everything downstream. Length is set by
reading age rather than market word count, the text is written to be read
aloud, and every spread must earn its illustration by giving the artist
something new to draw.

Story Grid still applies — a picture book has a value shift like anything
else, and the good ones turn on a real crisis at a child's scale. What does
not apply is chapter architecture: fourteen spreads cannot carry four acts.

Illustration consistency is the hard part, and it is harder here than in the
trailers: a character must be the same DRAWING every time, not merely the same
description. The cure is the same cast sheet the trailers use, plus a locked
art-style line repeated verbatim on every single spread prompt.
"""

import re as _re
from typing import Optional

from ..prose.models import CHILDRENS_PRESETS

# The shape a children's story actually needs. Not three acts — a want, a
# wall, a wobble, and a way through, which is what a small child can hold.
STORY_SHAPE = (
    "THE SHAPE (non-negotiable):\n"
    "  1. We meet someone we like, doing something that shows who they are.\n"
    "  2. They want something, clearly and concretely — a child must be able to "
    "say what it is.\n"
    "  3. Something gets in the way, and it gets worse — three times, each "
    "bigger than the last.\n"
    "  4. The lowest moment: it looks like they cannot have what they wanted.\n"
    "  5. THEY solve it themselves. Never a grown-up, never luck, never magic "
    "that was not set up.\n"
    "  6. The ending gives back warmth, and a last line that lands like a "
    "kiss goodnight.\n"
    "A VALUE must shift across the book — lonely to loved, afraid to brave, "
    "small to capable. Name it and hold to it."
)

CRAFT = (
    "HOW IT IS WRITTEN:\n"
    "  · Read every line aloud in your head. If it stumbles, rewrite it.\n"
    "  · Concrete nouns, active verbs, real rhythm. Repetition is a feature: a "
    "phrase that returns is the part a child joins in with.\n"
    "  · One idea per spread. The page turn is the punctuation.\n"
    "  · Show feeling through what a character DOES, never by naming it.\n"
    "  · No moral tacked on the end. The story is the lesson.\n"
    "  · No adult irony, no winking over the child's head, no brand names.\n"
    "  · Never describe what the picture already shows — the words and the "
    "picture should do different jobs."
)


def plain_language_rule(p: dict) -> str:
    """How simple the words have to be, for this age band, in numbers.

    'Write simply' is advice a model can agree with and then ignore. A word
    limit per sentence and a ban on long words is a rule it can actually be
    held to — and for a three-year-old being read to, sentence length is the
    single thing that decides whether the book works.
    """
    age = str(p.get("age") or "3-5")
    if age.startswith("3"):
        max_sent, max_letters, allow = 10, 7, "one or two syllables"
    elif age.startswith("5"):
        max_sent, max_letters, allow = 12, 8, "one, two or three syllables"
    else:
        max_sent, max_letters, allow = 16, 10, "words a nine-year-old reads easily"
    return (
        "PLAIN LANGUAGE — THESE ARE HARD LIMITS, NOT PREFERENCES:\n"
        f"  · No sentence longer than {max_sent} words. Most should be shorter. "
        "Short sentences are the whole craft at this age.\n"
        f"  · Almost every word {allow}. Avoid any word longer than "
        f"{max_letters} letters unless a child that age truly says it.\n"
        "  · Use the plain word every time: 'shook' not 'trembled', 'said' not "
        "'answered', 'dark' not 'darkness', 'held on' not 'gripping', 'stairs' "
        "not 'stairwell', 'went out' not 'flickered', 'screamed' not "
        "'shrieked'.\n"
        "  · One thought per sentence. No semicolons. No em-dashes holding two "
        "clauses together. No subordinate clauses stacked up.\n"
        "  · A grown-up should be able to read any line aloud, first time, "
        "without stumbling — and the child should understand it without "
        "asking what a word means."
    )

SAFETY = (
    "SUITABLE FOR CHILDREN (absolute): nothing frightening beyond gentle, "
    "resolvable jeopardy; no violence, cruelty, death, peril to a parent, or "
    "cliff-edge endings; no romance; no eating disorders, dieting or body "
    "shame; no religion or politics; no unsupervised danger a child might copy "
    "(matches, water, roads, strangers, heights). Any conflict resolves warmly "
    "and completely by the last spread."
)


def preset(name: str) -> dict:
    return CHILDRENS_PRESETS.get(name) or CHILDRENS_PRESETS["picture_book"]


def system_prompt(p: dict) -> str:
    return (
        f"You are a celebrated picture-book author writing for ages {p['age']} "
        f"({p['reading']}). Your voice is {p['voice']}. You write few words and "
        "make every one earn its place. You have never once talked down to a "
        "child."
    )


def art_style_line(p: dict, style_note: str = "") -> str:
    """One locked sentence repeated on EVERY spread prompt. Consistency in
    illustration comes from never varying these words."""
    base = (style_note or
            "Soft, warm children's picture-book illustration: gouache and coloured-pencil "
            "texture, gentle rounded shapes, generous white space, a bright friendly palette, "
            "even storybook lighting, no harsh shadows")
    return f"{base}. Consistent style across every page of the book. No text, no lettering, no words in the image."


def reading_check(spreads: list, p: dict) -> dict:
    """Measure what was actually written, not what was asked for.

    The model agrees to 'write simply' and then writes 'the great lamp
    flickered, once, twice, then steadied'. This counts long sentences and
    long words so the pipeline can send it back rather than ship a book a
    three-year-old cannot follow.
    """
    import re as _r
    age = str(p.get("age") or "3-5")
    max_sent = 10 if age.startswith("3") else 12 if age.startswith("5") else 16
    max_len = 7 if age.startswith("3") else 8 if age.startswith("5") else 10
    long_s, long_w = [], set()
    for sp_ in spreads:
        text = str(sp_.get("text") or "")
        for sent in [x.strip() for x in _r.split(r"[.!?]+", text) if x.strip()]:
            n = len(sent.split())
            if n > max_sent:
                long_s.append({"spread": sp_.get("n"), "words": n,
                               "text": sent[:90]})
        for w in _r.findall(r"[A-Za-z']+", text):
            if len(w) > max_len:
                long_w.add(w.lower())
    return {"max_sentence_words": max_sent, "max_word_letters": max_len,
            "long_sentences": long_s, "long_words": sorted(long_w),
            "clean": not long_s and not long_w}


def outline_prompt(book: dict, ms, p: dict, story: str) -> str:
    n = p["spreads"]
    return (
        f"BOOK: \"{book['title']}\" — a {p['label'].lower()} for ages {p['age']}.\n\n"
        f"THE IDEA:\n{story}\n\n"
        f"{STORY_SHAPE}\n\n{CRAFT}\n\n{plain_language_rule(p)}\n\n{SAFETY}\n\n"
        f"Plan the book as exactly {n} SPREADS. Across the whole book the text "
        f"totals roughly {p['target_words']} words — about {p['words_per_spread']} "
        f"words per spread. Going long is the commonest mistake in this "
        f"category; short is almost always better.\n\n"
        "For each spread give:\n"
        "  · `text` — the actual words on the page, final and read-aloud ready.\n"
        "  · `picture` — what the illustration shows: who is in it, what they are "
        "doing, where, and the feeling. Describe it so an illustrator who has not "
        "read the book could draw it. Do NOT restate the text.\n"
        "  · `turn` — the reason a child turns the page (a question, a surprise, a "
        "reveal). The last spread has none.\n\n"
        "Return JSON only:\n"
        '{"value_shift": "e.g. afraid -> brave", '
        '"characters": [{"name": "...", "look": "a complete physical description an '
        'illustrator can draw from every time: species or age, build, hair or fur, '
        'colours, and the ONE outfit they wear throughout"}], '
        '"art_style": "one sentence describing the illustration style for the whole book", '
        '"spreads": [{"n": 1, "text": "...", "picture": "...", "turn": "..."}]}'
    )


# ── the job ──────────────────────────────────────────────────────

async def write_childrens_book(catalog: str, handle=None) -> dict:
    """Idea -> spreads, with the cast locked for the illustrator.

    One call writes the whole book: at this length the story has to be held
    in one head at once, and splitting it across calls is what makes picture
    books read like a list of events instead of a story.
    """
    from ..database import get_book_by_catalog, update_book
    from .client import complete, extract_json, set_model_override, writing_model
    from ..prose.models import Manuscript

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = dict(book["data"])
    ms = Manuscript.model_validate(d.get("manuscript", {}))
    p = preset(ms.genre_preset)
    story = (ms.idea or "").strip()
    if not story:
        raise RuntimeError("The book has no idea to write from")

    if handle:
        handle.progress(0.15, "writing", f"writing {p['spreads']} spreads for ages {p['age']}")
    set_model_override(writing_model())
    try:
        raw = await complete(system_prompt(p), outline_prompt(book, ms, p, story),
                             max_tokens=8000)
    finally:
        set_model_override(None)
    data = extract_json(raw) or {}
    spreads = [s for s in (data.get("spreads") or [])
               if isinstance(s, dict) and (s.get("text") or "").strip()]
    if len(spreads) < 6:
        raise RuntimeError("The book came back too short to be a picture book")

    style = art_style_line(p, str(data.get("art_style") or ""))
    cast = {str(c.get("name", "")).strip(): str(c.get("look", "")).strip()
            for c in (data.get("characters") or [])
            if isinstance(c, dict) and c.get("name") and c.get("look")}

    out = []
    for i, s in enumerate(spreads, 1):
        picture = str(s.get("picture") or "").strip()
        # The cast sheet, verbatim, on every prompt — this is the whole trick.
        # Match short forms too: a spread says "Elsie" where the sheet says
        # "Keeper Elsie", and without this the description silently never
        # arrives and the illustrator invents a different person.
        who_parts = []
        for n, look in cast.items():
            names = {n} | {w for w in _re.sub(r"[^A-Za-z ]", " ", n).split() if len(w) > 2}
            if any(_re.search(rf"\b{_re.escape(x)}\b", picture) for x in names):
                who_parts.append(f"{n} is {look}.")
        who = " ".join(who_parts)
        out.append({
            "n": i,
            "text": str(s["text"]).strip(),
            "picture": picture,
            "turn": str(s.get("turn") or "").strip(),
            "art_prompt": f"{picture} {who} {style}".strip(),
        })

    words = sum(len(s["text"].split()) for s in out)
    rec = {"preset": ms.genre_preset, "age": p["age"], "label": p["label"],
           "spreads": out, "characters": cast, "art_style": style,
           "value_shift": str(data.get("value_shift") or "")[:120],
           "words": words, "target_words": p["target_words"]}
    # `d` was read before minutes of writing — re-read and touch only the
    # sections this job owns, so cover/interior writes that landed mid-job
    # survive
    fresh = get_book_by_catalog(catalog)
    fd = dict(fresh["data"])
    fd["childrens"] = rec
    fresh_ms = Manuscript.model_validate(fd.get("manuscript", {}))
    fresh_ms.word_count = words
    fd["manuscript"] = fresh_ms.model_dump(mode="json")
    update_book(fresh["id"], fd, sections=["childrens", "manuscript"])
    if handle:
        handle.progress(0.9, "written", f"{len(out)} spreads · {words} words")
    return rec


# ── the pictures ─────────────────────────────────────────────────
# Illustrations come from OpenAI's newest image engine — asked live, the same
# picker the covers use, so the day a better model ships the books get it.
# The hard problem is that a character must be the same DRAWING on every
# spread, and a text prompt alone will not hold a face. So spread 1 is drawn
# first and becomes the REFERENCE: every later spread is generated as an EDIT
# against it, which carries the character design and the palette forward.

async def illustrate(catalog: str, only: Optional[int] = None, handle=None,
                    hard_air: bool = False) -> dict:
    """Draw the spreads. Spread 1 sets the look; the rest follow it."""
    import asyncio, base64
    from pathlib import Path
    import httpx
    from ..config import OPENAI_API_KEY, OUTPUT_DIR
    from ..database import get_book_by_catalog, update_book

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    rec = dict(book["data"].get("childrens") or {})
    spreads = rec.get("spreads") or []
    if not spreads:
        raise RuntimeError("Write the book before illustrating it")
    if not OPENAI_API_KEY:
        raise RuntimeError("OpenAI is not configured — the illustrator needs it")

    # ORDER IS LOAD-BEARING. The cover is the look of the book: it is generated
    # first, one is chosen, and the bible is written FROM it so every spread
    # inherits an approved style. Drawing the interior first means the cover
    # has to match the interior instead, which is backwards — and when this
    # runs unattended there is no one to notice it went out of order.
    cover = (book["data"].get("cover") or {})
    if not (cover.get("selected_variant") or cover.get("mode") == "upload"):
        raise RuntimeError(
            "Pick the front cover first. The cover sets the look and the bible "
            "is written from it — generate cover options, choose one, then "
            "illustrate the interior.")
    bible_now = (book["data"].get("childrens") or {}).get("bible") or {}
    if not (bible_now.get("characters") or bible_now.get("settings")):
        raise RuntimeError(
            "Build the character and scenery bibles first — they carry the "
            "approved cover's look into every spread.")

    art_dir = Path(OUTPUT_DIR) / catalog / "spreads"
    art_dir.mkdir(parents=True, exist_ok=True)
    ref_path = art_dir / "spread-01.png"

    # The bibles are the canon. Every prompt carries the art direction, and
    # each spread additionally carries the full entry for the characters and
    # places IT contains — so the same bear, the same kitchen, every time.
    from .childrens_bible import canon_block, style_block
    bible = rec.get("bible") or {}
    art_direction = style_block(bible)
    plate_dir = Path(OUTPUT_DIR) / catalog / "bible"

    from ..cover.front_cover import _best_image_model

    def air_ok(png: bytes, n: int, words: int) -> bool:
        """The AIR QC GATE: the region reserved for text must actually BE
        light empty paper in the finished art — measured, not assumed. A
        spread that ignored the reservation gets redrawn (Lars, 2026-08-29:
        a full-bleed spread left the words with nowhere readable to go)."""
        from PIL import Image
        import io as _io
        im = Image.open(_io.BytesIO(png)).convert("L")
        W, H = im.size
        left = (n % 2 == 1)
        frac_w = 0.47 if words >= 45 else 0.34
        x0, x1 = (int(W*0.03), int(W*frac_w)) if left else (int(W*(1-frac_w)), int(W*0.97))
        region = im.crop((x0, int(H*0.04), x1, int(H*0.46))).resize((60, 40))
        px = list(region.getdata())
        mean = sum(px)/len(px)
        var = sum((v-mean)**2 for v in px)/len(px)
        return mean > 218 and var ** 0.5 < 30

    async def draw(prompt: str, reference: Optional[bytes]) -> bytes:
        async with httpx.AsyncClient(timeout=300) as c:
            model = await _best_image_model(c)
            for attempt in range(3):
                try:
                    if reference:
                        r = await asyncio.wait_for(c.post(
                            "https://api.openai.com/v1/images/edits",
                            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                            files={"image[]": ("ref.png", reference, "image/png")},
                            data={"model": model, "prompt": prompt[:3800],
                                  "size": "1536x1024", "quality": "high", "n": "1"}),
                            timeout=240)
                    else:
                        r = await asyncio.wait_for(c.post(
                            "https://api.openai.com/v1/images/generations",
                            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                            json={"model": model, "prompt": prompt[:3800],
                                  "size": "1536x1024", "quality": "high", "n": 1}),
                            timeout=240)
                except (httpx.HTTPError, asyncio.TimeoutError):
                    await asyncio.sleep(4 * (attempt + 1)); continue
                if r.status_code == 200:
                    return base64.b64decode(r.json()["data"][0]["b64_json"])
                if r.status_code < 500:
                    raise RuntimeError(f"Illustration refused ({r.status_code}): {r.text[:180]}")
                await asyncio.sleep(4 * (attempt + 1))
        raise RuntimeError("Illustration failed after 3 attempts")

    targets = [s for s in spreads if only is None or s["n"] == only]
    # spread 1 must exist before any other can reference it
    if only is not None and only != 1 and not ref_path.exists():
        targets = [spreads[0]] + targets

    def prompt_for(s):
        n = s["n"]
        canon = canon_block(bible, f"{s.get('picture','')} {s.get('text','')}")
        # THE AIR RULE (Lars, from the Nordqvist books): the illustration is a
        # vignette that leaves the paper itself as the text's home. One region
        # per spread stays pure white; the side alternates so the book
        # breathes left-right as it turns.
        side = "LEFT" if n % 2 else "RIGHT"
        w = len((s.get("text") or "").split())
        area = ("half" if w >= 85 else "third" if w >= 45 else "quarter")
        air = (f"COMPOSITION: a generous picture-book illustration that FILLS "
               f"most of the image with life, story and detail — the scene is "
               f"large and immersive, never a small drawing lost on a white "
               f"page. It is still a vignette: its outer edges dissolve "
               f"softly into the paper instead of ending in a hard rectangle. "
               f"The {side} {area} of the image — the upper {side} region — "
               f"stays as light open air: white paper with at most the "
               f"faintest wash, reserved for the story text. One or two tiny "
               f"story details (a butterfly, a flower sprig, a small side "
               f"character) may sit near the margins so no corner feels "
               f"empty. In the spirit of classic Scandinavian picture books.")
        if hard_air:
            air += (f" CRITICAL, NON-NEGOTIABLE: the {side} half of the image "
                    f"is completely EMPTY pale watercolor paper — no "
                    f"characters, no animals, no objects, no flowers there at "
                    f"all. Every character stands in the "
                    f"{'RIGHT' if side == 'LEFT' else 'LEFT'} half only.")
        head = "\n\n".join(x for x in (art_direction, air, canon) if x)
        if n == 1:
            prompt = (f"A children's picture-book illustration, landscape, for a book for ages "
                      f"{rec.get('age','3-5')}. {s['art_prompt']}")
            # a character turnaround sheet is a far stronger anchor than a
            # finished scene: it shows the design, not one pose of it
            sheet = sorted(plate_dir.glob("char-*.png")) if plate_dir.exists() else []
            ref = sheet[0].read_bytes() if sheet else None
            if ref:
                prompt = ("Draw a scene from a children's picture book using the character "
                          "design in the reference sheet. The character must look identical "
                          f"to the sheet. Scene: {s['art_prompt']}")
        else:
            prompt = ("Draw the NEXT illustration in this same picture book. Keep the EXACT same "
                      "art style, palette, line quality and character designs as the reference "
                      f"image — the same characters must look identical. New scene: {s['art_prompt']}")
            ref = ref_path.read_bytes() if ref_path.exists() else None
        return (f"{prompt}\n\n{head}" if head else prompt), ref

    done = []
    # Spread 1 is the reference every other spread is drawn against, so it goes
    # first and alone. The rest only depend on IT, not on each other — drawing
    # them one at a time made a fourteen-spread book take a quarter of an hour.
    first = [s for s in targets if s["n"] == 1]
    rest = [s for s in targets if s["n"] != 1]
    for s in first:
        if handle:
            handle.progress(0.1, "illustrating", "drawing spread 1 — the reference")
        pr, ref = prompt_for(s)
        w1 = len((s.get("text") or "").split())
        png = await draw(pr, ref)
        for _retry in range(2):
            if air_ok(png, 1, w1):
                break
            png = await draw(pr, ref)
        (art_dir / "spread-01.png").write_bytes(png)
        done.append(1)

    if rest:
        gate = asyncio.Semaphore(4)
        finished = [0]

        async def one(s):
            async with gate:
                try:
                    pr, ref = prompt_for(s)
                    png = await draw(pr, ref)
                    for _retry in range(2):
                        if air_ok(png, s["n"], len((s.get("text") or "").split())):
                            break
                        png = await draw(pr, ref)
                except Exception:
                    return None          # a refused spread must not kill the book
                (art_dir / f"spread-{s['n']:02d}.png").write_bytes(png)
                finished[0] += 1
                if handle:
                    handle.progress(0.1 + 0.85 * finished[0] / len(rest), "illustrating",
                                    f"drew {finished[0]} of {len(rest)} spreads")
                return s["n"]

        got = await asyncio.gather(*(one(s) for s in rest), return_exceptions=True)
        done += [g for g in got if isinstance(g, int)]

    art_map = {str(s["n"]): f"spreads/spread-{s['n']:02d}.png"
               for s in spreads if (art_dir / f"spread-{s['n']:02d}.png").exists()}
    rec["art"] = art_map
    # merge onto the freshly-read childrens record — `rec` is from job start,
    # and this job only owns the art map
    fresh = get_book_by_catalog(catalog)
    d = dict(fresh["data"])
    frec = dict(d.get("childrens") or rec)
    frec["art"] = art_map
    d["childrens"] = frec
    update_book(fresh["id"], d, sections=["childrens"])
    return {"drawn": done, "total": len(spreads), "art": art_map}
