"""
Character bibles — the cast, held as canon.

The single hardest problem in generated film is consistency: the same character
has to be the same character in every shot, and the same room has to be the
same room. The fix is not cleverer prompting shot by shot — it is a CAST SHEET
that every shot draws from, word for word.

A bible is uploaded as an image (the way a real production hands one round) and
transcribed once into structured records. From then on, any panel that names a
character gets that character's canonical description injected verbatim, so the
wording never drifts between shots or between a trailer and the film.

Two bibles per book, by the publisher's convention:
  main       — the lead, described in the most detail
  supporting — everyone else, plus locations and the visual world
"""

import io
import json
from pathlib import Path
from typing import Optional

from ..config import OUTPUT_DIR
from ..database import get_book_by_catalog, update_book

KINDS = ("main", "supporting")


def _png_bytes(image_bytes: bytes) -> bytes:
    """complete_vision declares image/png — normalise whatever was uploaded."""
    from PIL import Image
    buf = io.BytesIO()
    Image.open(io.BytesIO(image_bytes)).convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


async def parse_bible(image_bytes: bytes, book: dict, kind: str) -> dict:
    """Read a character-bible sheet into cast records a video model can use."""
    from ..writing.client import complete_vision, extract_json

    who = ("the MAIN character (there may be only one; describe them in the "
           "greatest detail)" if kind == "main"
           else "the SUPPORTING cast (every character other than the lead)")
    prompt = (
        f"This is a character bible for the book \"{book['title']}\". Transcribe "
        f"{who}, plus the world it describes.\n\n"
        "For EACH character give a `look` line that is a complete, self-contained "
        "physical description a video model can film from without ever seeing this "
        "sheet: apparent age, build, hair, facial hair, distinguishing features, and "
        "their default wardrobe. Write it as a noun phrase that can be dropped "
        "straight into a shot description — for example \"a rugged man in his "
        "mid-forties with a short dark beard, weathered face, dark beanie and dark "
        "jacket\". No sentences, no back-story in the `look` line: only what a camera "
        "would see. Put personality, role and arc in the other fields.\n\n"
        "Only transcribe what the sheet actually shows — do not invent characters, "
        "and do not invent details a reader could not see or read on it.\n\n"
        "Return JSON only:\n"
        '{"characters": [{"name": "...", "role": "...", "look": "...", '
        '"age": "...", "traits": "...", "arc": "..."}], '
        '"locations": [{"name": "...", "look": "one sentence a camera could film"}], '
        '"style": "the visual world: look, palette, light, camera handling", '
        '"tone": "the register of the story in one line"}'
    )
    raw = await complete_vision(
        "You are a film production designer reading a character bible into a "
        "cast sheet that will be used to keep every generated shot consistent.",
        prompt, _png_bytes(image_bytes), max_tokens=6000)
    data = extract_json(raw) or {}

    chars = []
    for c in (data.get("characters") or []):
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        look = str(c.get("look") or "").strip()
        if not name or not look:
            continue
        chars.append({"name": name, "role": str(c.get("role") or "")[:120],
                      "look": look, "age": str(c.get("age") or "")[:40],
                      "traits": str(c.get("traits") or "")[:400],
                      "arc": str(c.get("arc") or "")[:400]})
    if not chars:
        raise RuntimeError("No characters could be read from that sheet")

    locs = []
    for l in (data.get("locations") or []):
        if isinstance(l, dict) and (l.get("name") or "").strip():
            locs.append({"name": str(l["name"]).strip()[:80],
                         "look": str(l.get("look") or "")[:300]})
    return {"kind": kind, "characters": chars, "locations": locs,
            "style": str(data.get("style") or "")[:600],
            "tone": str(data.get("tone") or "")[:300]}


def save_bible(catalog: str, kind: str, record: dict, source_name: str = "") -> dict:
    book = get_book_by_catalog(catalog)
    data = dict(book["data"])
    bibles = dict(data.get("bibles") or {})
    bibles[kind] = {**record, "source": source_name}
    data["bibles"] = bibles
    update_book(book["id"], data)
    return bibles[kind]


def cast_of(book: dict) -> dict:
    """{name -> canonical look} across both bibles. The main bible wins on a
    name clash, because the lead is described in more detail there.

    A board writes "Luc", not "Luc Reyer", so short forms are registered too —
    first name and surname — but only when they point at exactly one person.
    Without this the description silently fails to inject and the face drifts.
    """
    bibles = (book.get("data") or {}).get("bibles") or {}
    cast, short = {}, {}
    for kind in ("supporting", "main"):          # main applied last = wins
        for c in ((bibles.get(kind) or {}).get("characters") or []):
            name, look = (c.get("name") or "").strip(), (c.get("look") or "").strip()
            if not name or not look:
                continue
            cast[name] = look
            import re as _re
            for part in _re.sub(r"[^A-Za-z ]", " ", name).split():
                if len(part) < 3 or part.lower() in ("mr", "mrs", "dr", "sir", "lady",
                                                     "the", "ret", "justice", "senator",
                                                     "captain", "colonel", "professor"):
                    continue
                short.setdefault(part, set()).add(look)
    for part, looks in short.items():
        if len(looks) == 1 and part not in cast:      # unambiguous only
            cast[part] = next(iter(looks))
    return cast


def world_of(book: dict) -> dict:
    bibles = (book.get("data") or {}).get("bibles") or {}
    style = ((bibles.get("main") or {}).get("style")
             or (bibles.get("supporting") or {}).get("style") or "")
    locs = {}
    for kind in KINDS:
        for l in ((bibles.get(kind) or {}).get("locations") or []):
            if l.get("name"):
                locs[l["name"].strip()] = (l.get("look") or "").strip()
    return {"style": style, "locations": locs}


def apply_cast(text: str, cast: dict) -> str:
    """Swap a bare character name in a shot description for their canonical
    look, once per shot — "Cassandra walks in" becomes "Cassandra, a woman in
    her late twenties with…, walks in". Later mentions stay as the plain name
    so the prompt does not turn into a list of repeated descriptions."""
    if not text or not cast:
        return text
    out = text
    for name, look in sorted(cast.items(), key=lambda kv: -len(kv[0])):
        if not name or name not in out:
            continue
        if look.lower().startswith(name.lower()):
            replacement = look
        else:
            replacement = f"{name}, {look},"
        # only the FIRST mention carries the description
        i = out.find(name)
        already = out[max(0, i - 2):i + len(name) + 2]
        if "," in already and look[:18].lower() in out.lower():
            continue
        out = out[:i] + replacement + out[i + len(name):]
    return out


# ── building a bible with no sheet at all ────────────────────────
# The publisher should not have to draw a cast sheet. Everything needed is
# already in the house: the front cover says what the world looks like, and
# the manuscript says who is in it. Read both, and the bible writes itself.

def _story_digest(book: dict, limit: int = 6000) -> str:
    d = book.get("data") or {}
    ms = d.get("manuscript") or {}
    bits = []
    if ms.get("blurb"):
        bits.append("BACK COVER:\n" + ms["blurb"])
    if d.get("back_cover_blurb"):
        bits.append("PRINT BACK COVER:\n" + d["back_cover_blurb"])
    sb = ms.get("story_bible") or {}
    if isinstance(sb, dict):
        if sb.get("premise"):
            bits.append("PREMISE:\n" + str(sb["premise"]))
        if sb.get("setting"):
            bits.append(f"SETTING: {sb['setting']} ({sb.get('time_period','')})")
        chars = sb.get("characters") or []
        if chars:
            lines = []
            for c in chars[:12]:
                if isinstance(c, dict):
                    lines.append(f"  - {c.get('name','')}: {c.get('role','')} — "
                                 f"{str(c.get('description',''))[:220]}")
            if lines:
                bits.append("CHARACTERS FROM THE STORY BIBLE:\n" + "\n".join(lines))
        if sb.get("style_notes"):
            bits.append("STYLE NOTES: " + str(sb["style_notes"])[:400])
    # A CHILDREN'S BOOK lives in its spreads, not in chapters — without this
    # the writers received nothing and invented a story from the title
    # (the phantom princess, 2026-08-29)
    ch = d.get("childrens") or {}
    spreads = ch.get("spreads") or []
    if spreads:
        story = " ".join(str(sp.get("text") or "").strip()
                         for sp in spreads if sp.get("text"))
        if story:
            bits.append("THE COMPLETE STORY (every spread, in order):\n" + story)
        bible = ch.get("bible") or {}
        cast = bible.get("characters") or []
        if cast:
            lines = [f"  - {c.get('name','')}: {str(c.get('look') or c.get('description') or '')[:200]}"
                     for c in cast if isinstance(c, dict)]
            if lines:
                bits.append("THE CAST (the ONLY characters that exist):\n" + "\n".join(lines))
    if not bits and ms.get("idea"):
        bits.append("IDEA:\n" + str(ms["idea"]))
    return "\n\n".join(bits)[:limit]


async def auto_bible(catalog: str, kind: str = "main") -> dict:
    """Write the cast sheet from the FRONT COVER plus the story itself.

    The cover is the visual contract with the reader — its palette, era and
    light are what the trailer has to match — so the look is read from the
    picture, not invented. Who exists, and what they are, comes from the book.
    """
    from ..writing.client import complete_vision, extract_json
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    cover = OUTPUT_DIR / catalog / "cover-front.png"
    if not cover.exists():
        raise RuntimeError("The book has no front cover yet — the bible is built from it")

    story = _story_digest(book)
    if not story.strip():
        raise RuntimeError("The book has no blurb or story bible yet to build a cast from")

    who = ("ONLY the single main character — the lead the story follows"
           if kind == "main" else
           "the SUPPORTING cast: every named character EXCEPT the lead")

    # Anyone this series has already established arrives with their look fixed.
    # Without this each book writes its own lead from its own cover, and a
    # recurring character ages and changes wardrobe between books.
    from .plates import series_canon
    canon = series_canon(book)
    canon_txt = ""
    if canon:
        canon_txt = (
            "\n\nCHARACTERS THIS SERIES HAS ALREADY ESTABLISHED — if one of these "
            "appears in this book, copy the `look` line EXACTLY as given. It is "
            "canon from an earlier book and the reader has already met them. Do "
            "not restyle, re-age or re-dress them, however this cover looks:\n"
            + "\n".join(f"  - {n}: {c['look']}" for n, c in canon.items() if c.get("look"))
        )
    prompt = (
        f"This is the front cover of \"{book['title']}\". Study its world — palette, "
        f"era, light, costume, mood — then read the story below.\n\n{story}\n\n"
        f"Write the character bible for {who}.{canon_txt}\n\n"
        "For EACH character give a `look` line: a complete, self-contained physical "
        "description a video model can film from, as a noun phrase that drops "
        "straight into a shot — apparent age, build, hair, facial hair, "
        "distinguishing features, default wardrobe. For example: \"a rugged man in "
        "his mid-forties with a short dark beard, weathered face, dark beanie and "
        "dark jacket\". Only what a camera sees; no back-story in `look`. The "
        "costume and colouring must be TRUE TO THE COVER and the period.\n"
        "Base every character on the story. Do not invent people the book does not "
        "have. If the story names only a few, return only those.\n\n"
        "Also describe the recurring LOCATIONS the story actually uses, and the "
        "visual STYLE of the cover as a direction line for every shot.\n\n"
        "Return JSON only:\n"
        '{"characters": [{"name": "...", "role": "...", "look": "...", '
        '"age": "...", "traits": "...", "arc": "..."}], '
        '"locations": [{"name": "...", "look": "one sentence a camera could film"}], '
        '"style": "look, palette, light, camera handling — matched to the cover", '
        '"tone": "the register of the story in one line"}'
    )
    raw = await complete_vision(
        "You are a film production designer building a cast sheet that will keep "
        "every generated shot consistent with the book and its cover.",
        prompt, cover.read_bytes(), max_tokens=6000)
    data = extract_json(raw) or {}

    chars = []
    for c in (data.get("characters") or []):
        if isinstance(c, dict) and (c.get("name") or "").strip() and (c.get("look") or "").strip():
            chars.append({"name": str(c["name"]).strip(), "role": str(c.get("role") or "")[:120],
                          "look": str(c["look"]).strip(), "age": str(c.get("age") or "")[:40],
                          "traits": str(c.get("traits") or "")[:400],
                          "arc": str(c.get("arc") or "")[:400]})
    if not chars:
        raise RuntimeError(f"Could not build a {kind} character bible from the cover and story")
    locs = [{"name": str(l["name"]).strip()[:80], "look": str(l.get("look") or "")[:300]}
            for l in (data.get("locations") or [])
            if isinstance(l, dict) and (l.get("name") or "").strip()]
    rec = {"kind": kind, "characters": chars, "locations": locs,
           "style": str(data.get("style") or "")[:600],
           "tone": str(data.get("tone") or "")[:300]}
    save_bible(catalog, kind, rec, "auto — cover + story")
    return rec


async def ensure_bibles(catalog: str, handle=None) -> dict:
    """Both bibles, built if the book has none. Never re-writes one that
    exists: an uploaded or hand-corrected sheet is the publisher's, not ours."""
    book = get_book_by_catalog(catalog)
    have = (book["data"].get("bibles") or {})
    for kind in KINDS:
        if have.get(kind):
            continue
        if handle:
            handle.progress(0.1, "bible", f"writing the {kind} character bible from the cover")
        try:
            await auto_bible(catalog, kind)
        except Exception as e:
            if kind == "main":
                raise
            # a book may genuinely have no supporting cast worth sheeting
            if handle:
                handle.progress(0.1, "bible", f"no supporting bible: {str(e)[:80]}")
    return (get_book_by_catalog(catalog)["data"].get("bibles") or {})


# ── the storyboard, written from the bible ───────────────────────

async def auto_storyboard(catalog: str, panels: int = 9, handle=None) -> dict:
    """Board the trailer from the cast sheet and the story.

    The bible comes first on purpose: the board names characters the cast
    sheet already defines, so when the shots are filmed every face is already
    canon. The board carries the narration AND any line a character speaks.
    """
    from ..writing.client import complete, extract_json, set_model_override, writing_model
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    bibles = book["data"].get("bibles") or {}
    if not bibles.get("main"):
        raise RuntimeError("Build the character bible before the storyboard")

    cast = cast_of(book)
    world = world_of(book)
    cast_txt = "\n".join(f"  - {n}: {look}" for n, look in cast.items())
    loc_txt = "\n".join(f"  - {n}: {look}" for n, look in (world.get("locations") or {}).items())
    from .producer import _genre_label
    genre = _genre_label(book)

    # Action grammar. A romance trailer breathes; a thriller trailer runs.
    # Ours were all cut to the romance clock — nine even beats, a narrator
    # wall to wall — which is why they felt like slideshows next to the real
    # thing (study: Mission: Impossible and Jack Ryan cut 25–40 shots a
    # minute, accelerating to under a second, with the CHARACTERS carrying
    # the story and the narrator almost silent).
    _kids = ((book["data"].get("kind") or book["data"].get("book_type") or "")
             == "childrens" or (book["data"].get("genre_preset") or "")
             in ("picture_book", "early_reader", "chapter_book"))
    _fast = (not _kids) and any(
        k in (book["data"].get("genre_preset") or "").lower()
        for k in ("thriller", "crime", "action", "mystery"))
    if _fast:
        panels = max(panels, 13)
    action_rules = (
        "\nACTION GRAMMAR — this is a thriller, so the trailer accelerates:\n"
        f"A. Build in three movements: SETUP (panels 1-4, durs 3-4, let it "
        "breathe), ESCALATION (middle, durs 2-3, each shot raises the "
        "pressure), then a CLIMAX MONTAGE — the last 4 panels before the end "
        "run at dur 1.5-2 each, pure movement, NO vo on any of them: pursuit, "
        "impact, weather, machinery, bodies in motion.\n"
        "B. MOVEMENT in every shot from the escalation on. Nobody stands "
        "still; something is always travelling through the frame.\n"
        "C. The CHARACTERS carry the story: use `line` on up to THREE panels "
        "— short, urgent, in-world sentences. Narration is sparse: `vo` on at "
        "most half the panels, never over 10 words, none in the montage.\n"
        "D. One panel of near-silence directly before the montage — a held "
        "breath. Its `sound` is a single quiet detail.\n"
    ) if _fast else ""
    kids_rules = (
        "\nMAGICAL WONDER GRAMMAR — this is a children's book, so the trailer "
        "is a family-movie trailer in the classic Disney register: a warm, "
        "wonder-filled invitation into a magical world.\n"
        "A. The NARRATOR is a beloved storyteller opening a storybook: warm, "
        "smiling, full of wonder — never dramatic, never urgent. Lines like "
        "'In a forest where rainbows are born...' — enchantment, plain warm "
        "words, gentle humor welcome.\n"
        "B. NOTHING is scary. Stakes are matters of the heart (finding home, "
        "helping a friend, being brave), phrased with hope — 'and maybe, just "
        "maybe...' — never as danger or threat. A dark moment is a gentle "
        "mystery, on at most ONE panel, resolved by warmth in the next.\n"
        "C. Build as: WELCOME to the world (panels 1-2, wide wonder), MEET "
        "the friends (each introduced doing something delightful), the "
        "ADVENTURE begins (the wish or the little problem), a JOYFUL MONTAGE "
        "of magical moments (2-3 quick panels of pure delight), then a warm "
        "closing promise.\n"
        "D. `sound` is gentle magic: chimes, birdsong, a bell, giggles, "
        "sparkling water — never rumbles, impacts or braams.\n"
        "E. `line` on one or two panels: something kind, funny or brave a "
        "character says — the sort of line a child repeats afterwards.\n"
    ) if _kids else ""

    prompt = (
        f"BOOK: \"{book['title']}\" — a {genre} novel.\n\n"
        f"{_story_digest(book, 4500)}\n\n"
        f"CAST (use these names EXACTLY; never invent a character):\n{cast_txt}\n\n"
        f"LOCATIONS:\n{loc_txt or '  (none listed)'}\n\n"
        f"VISUAL STYLE: {world.get('style','')}\n\n"
        f"Board a {panels}-panel trailer for this book.\n\n"
        "RULES OF THE HOUSE:\n"
        "1. Panel 1 is an ESTABLISHING shot of the world with NO people — it plays "
        "under music alone before the narrator speaks.\n"
        "2. Every panel is ONE shot. Say the framing (wide / medium / close), what "
        "happens, and the light. Refer to characters by their cast NAME only — "
        "their description is added automatically, so never re-describe them.\n"
        "3. NEVER repeat a composition. Two characters face to face may appear ONCE "
        "in the whole trailer. Vary framing, subject and location every panel.\n"
        "4. The voice-over tells the story in order: the world, who they are, what "
        "they want, the turn, what stands against them, the stakes, and a closing "
        "question. Spoken sentences, plain words, no rhetorical flourish.\n"
        "5. Keep each `vo` under 20 words. A long line forces an overlong shot — "
        "split the thought across two panels instead.\n"
        "6. The last panel is the emotional peak, NOT a title card: the cover ending "
        "is added afterwards.\n"
        "7. `dur` is seconds, 3 to 5, long enough to hold the shot and its line "
        "(the ACTION GRAMMAR below overrides this where it says so).\n"
        "8. `line` is OPTIONAL: a single short sentence a character says out loud, "
        "with the speaker's cast name. Use it at most twice in the trailer "
        "(three, where the ACTION GRAMMAR applies).\n"
        "9. `characters` lists, by their EXACT cast-sheet names, everyone visible "
        "in that panel — empty only for a shot with no people in it. This is not "
        "decoration: each name here sends that character's reference portrait to "
        "the camera, and a face that arrives without one is redrawn from scratch "
        "and comes back as a different person from the shot before.\n"
        "10. `sound` is the panel's key DIEGETIC sound — what the world itself is "
        "doing: wind over ice, a buckle tightening, boots on frost, a distant "
        "siren. One concrete sound per panel, five to ten words, no music and no "
        "voices. This is what makes the film feel real rather than scored "
        "silence, so give every panel one.\n"
        + action_rules + kids_rules +
        "\nReturn JSON only:\n"
        '{"panels": [{"n": "1", "title": "3 words", "dur": 4, "shot": "...", '
        '"characters": ["Cast Name"], "sound": "...", '
        '"vo": "...", "line": {"speaker": "Name", "text": "..."}}], '
        '"music": "a score brief: instrumentation, mood, tempo, and \\"no vocals\\""}'
    )
    if handle:
        handle.progress(0.2, "board", "boarding the trailer from the cast sheet")
    set_model_override(writing_model())
    try:
        raw = await complete(
            "You are a trailer director. You board in single shots, never repeat a "
            "composition, and write narration that is spoken aloud, not read.",
            prompt, max_tokens=6000)
    finally:
        set_model_override(None)
    data = extract_json(raw) or {}
    out = []
    for i, p in enumerate(data.get("panels") or [], 1):
        if not isinstance(p, dict) or not (p.get("shot") or "").strip():
            continue
        try:
            dur = float(p.get("dur") or 4)
        except (TypeError, ValueError):
            dur = 4.0
        panel = {"n": str(i), "title": str(p.get("title") or "")[:60],
                 "dur": max(1.5, min(8.0, dur)), "shot": str(p["shot"]).strip(),
                 "vo": str(p.get("vo") or "").strip(),
                 # the panel's key diegetic sound — kept explicitly, because
                 # this whitelist is exactly where `characters` used to vanish
                 "sound": str(p.get("sound") or "").strip()[:160]}
        # Who is in the shot, kept. Rebuilding the panel from a whitelist that
        # omitted this quietly discarded the cast on every board, so no shot
        # ever received a reference portrait and the lead was reinvented nine
        # times over. Names are matched against the cast sheet — an invented
        # one has no portrait behind it and would only mislead the camera.
        known = {n.lower(): n for n in cast}
        picked = [known[str(x).strip().lower()]
                  for x in (p.get("characters") or [])
                  if isinstance(x, str) and str(x).strip().lower() in known]
        if picked:
            panel["characters"] = list(dict.fromkeys(picked))
        ln = p.get("line")
        if isinstance(ln, dict) and (ln.get("text") or "").strip():
            panel["line"] = {"text": str(ln["text"]).strip()[:200],
                             "speaker": str(ln.get("speaker") or "")[:60],
                             "gap": 0.35}
        out.append(panel)
    if len(out) < 4:
        raise RuntimeError("The board came back too short to cut a trailer from")
    board = {"style": world.get("style", ""), "music": str(data.get("music") or "")[:600],
             "cover_ref": False, "panels": out}
    fresh = get_book_by_catalog(catalog)
    d = dict(fresh["data"]); tr = dict(d.get("trailer") or {})
    tr["storyboard"] = board
    d["trailer"] = tr
    update_book(fresh["id"], d)
    return board


async def rewrite_board_script(catalog: str, brief: str = "", handle=None) -> dict:
    """Rewrite ONLY the words of the stored storyboard — vo, lines, sounds,
    music — from the book itself. Every shot, duration and cast list is
    LOCKED. This is what 'Rewrite full script' means in a storyboard-first
    house (Lars, 2026-08-29)."""
    from ..writing.client import complete, extract_json, set_model_override, writing_model
    from ..database import get_book_by_catalog, update_book
    import json as _json
    book = get_book_by_catalog(catalog)
    if not book:
        raise RuntimeError("Book not found")
    d = book["data"]
    tr = dict(d.get("trailer") or {})
    sb = tr.get("storyboard") or {}
    panels = (sb.get("panels") if isinstance(sb, dict) else sb) or []
    if not panels:
        raise RuntimeError("No storyboard yet — board the trailer first")
    _kids = ((d.get("kind") or d.get("book_type") or "") == "childrens"
             or (d.get("genre_preset") or "") in ("picture_book", "early_reader", "chapter_book"))
    register = (
        "REGISTER: a family-movie trailer in the classic Disney spirit — the "
        "narrator is a warm storyteller full of wonder, never dramatic. "
        "Nothing scary; stakes are matters of the heart phrased with hope. "
        "Character lines are kind, funny or brave — the sort a child repeats."
        if _kids else
        "REGISTER: spoken sentences, plain words, no rhetorical flourish; "
        "narration sparse and under 20 words a line.")
    locked = [{"n": p.get("n"), "title": p.get("title"), "shot": p.get("shot"),
               "dur": p.get("dur"), "characters": p.get("characters") or []}
              for p in panels]
    prompt = (
        f"BOOK: \"{book['title']}\"\n\n{_story_digest(book, 4500)}\n\n"
        "THE STORYBOARD (shots are LOCKED — do not change, reorder or "
        f"re-describe them):\n{_json.dumps(locked, indent=1)}\n\n"
        + register + "\n"
        + (f"\nTHE PUBLISHER'S DIRECTION: {brief.strip()}\n" if brief.strip() else "")
        + "\nWrite the WORDS for these exact panels: `vo` per panel (may be "
        "empty), at most two `line`s across the whole board (speaker must be "
        "a listed character of that panel), one diegetic `sound` per panel "
        "(five to ten words, no music, no voices), and one `music` brief. "
        "Everything must come from the book above — never invent characters, "
        "places or events.\n\nReturn JSON only: "
        '{"panels": [{"n": "1", "vo": "...", "sound": "...", '
        '"line": {"speaker": "Name", "text": "..."}}], "music": "..."}')
    if handle:
        handle.progress(0.3, "script", "rewriting the words on the locked board")
    set_model_override(writing_model())
    try:
        raw = await complete(
            "You are a trailer narrator's writer. The shots are locked; you "
            "write only the spoken and heard words, faithful to the book.",
            prompt, max_tokens=4000)
    finally:
        set_model_override(None)
    out = extract_json(raw) or {}
    by_n = {str(p.get("n")): p for p in (out.get("panels") or []) if isinstance(p, dict)}
    changed = 0
    for p in panels:
        new = by_n.get(str(p.get("n")))
        if not new:
            continue
        p["vo"] = str(new.get("vo") or "").strip()
        p["sound"] = str(new.get("sound") or p.get("sound") or "").strip()[:160]
        ln = new.get("line")
        if isinstance(ln, dict) and (ln.get("text") or "").strip():
            p["line"] = {"speaker": str(ln.get("speaker") or "")[:60],
                         "text": str(ln["text"]).strip()[:200]}
        else:
            p.pop("line", None)
        changed += 1
    if isinstance(sb, dict) and out.get("music"):
        sb["music"] = str(out["music"])[:400]
    fresh = get_book_by_catalog(catalog)
    fd = dict(fresh["data"]); ftr = dict(fd.get("trailer") or {})
    ftr["storyboard"] = sb if isinstance(sb, dict) else {"panels": panels}
    fd["trailer"] = ftr
    update_book(fresh["id"], fd)
    return {"panels_rewritten": changed, "music": out.get("music")}
