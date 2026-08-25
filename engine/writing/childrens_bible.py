"""The character bible and the scenery bible for a children's book.

A picture book lives or dies on whether the child believes it is the same
bear on page 3 and page 27. A *series* — and an animated episode cut from
it — needs that to hold across books that may be written months apart.

A one-line cast sheet ("Pip is a small round child in yellow pyjamas") is
not enough for that. It leaves the illustrator to reinvent Pip's house, the
colour of the door, whether the cat is grey or ginger — and it reinvents
them differently every time.

So SCRPT writes two documents before it draws anything:

  · the CHARACTER BIBLE — every character's face, hair, build, clothing,
    exact colours, props, home and how they move;
  · the SCENERY BIBLE — every location's exterior, interior, palette,
    light and fixed details, plus the world's overall art direction.

Both are authored once, stored on the book, and INHERITED by every later
book in the same series, so book four draws the same kitchen as book one.
Every illustration prompt then carries the relevant entries verbatim. The
same two documents are what an animation studio needs, which is why they
are written as production documents rather than as prose notes.
"""

from __future__ import annotations

import re as _re
from typing import Optional

from .childrens import preset


# ── what the bible must contain ──────────────────────────────────
# Written as an art-department brief, because that is what it is: the
# answers here are the ones an illustrator or an animator would otherwise
# have to invent, and inventing them twice is what breaks continuity.

BIBLE_SYSTEM = (
    "You are the art director of a children's publishing house, writing the "
    "production bible that every illustrator and animator on the series will "
    "work from. You are ruthlessly specific. You never write 'a nice dress' "
    "where you could write 'a knee-length pinafore in mustard yellow with two "
    "square patch pockets'. You give colours as plain names AND hex values. "
    "You answer the questions an artist would otherwise have to guess."
)

_CHAR_FIELDS = (
    "name, role (who they are in the story), species (human/animal/creature), "
    "age_look (how old they read), build (height next to the other characters, "
    "body shape), face (shape, nose, notable features), eyes (shape and colour), "
    "hair (colour, length, exactly how it is worn), skin_or_fur (colour and "
    "texture), clothing (every garment, with colours and hex), palette (2-4 hex "
    "colours that identify them at a glance), props (what they always carry), "
    "home (where they live and what it looks like inside), movement (how they "
    "walk, sit, hold things), expressions (their happy / worried / delighted "
    "face), never (things an illustrator must never do with them)"
)

_SET_FIELDS = (
    "name, what (what the place is), exterior (shape, materials, colours with "
    "hex, roof, door, windows), interior (layout, furniture, floor, walls, the "
    "objects that are always there), palette (3-5 hex), light (time of day and "
    "quality of light here), sounds_and_weather, fixed_details (small things "
    "that must appear every time — a crooked shutter, a red kettle), never"
)


def bible_prompt(book: dict, p: dict, rec: dict, inherited: Optional[dict]) -> str:
    story = (rec.get("premise") or "").strip()
    spreads = rec.get("spreads") or []
    scenes = "\n".join(
        f"  {s['n']}. {s.get('text','')[:110]}  [picture: {s.get('picture','')[:160]}]"
        for s in spreads[:24]
    )
    cast_hint = ", ".join((rec.get("characters") or {}).keys())

    head = (
        f"SERIES/BOOK: \"{book.get('title','')}\" — a {p['label'].lower()} for "
        f"ages {p['age']}.\n\n"
    )
    if story:
        head += f"THE STORY:\n{story}\n\n"
    if scenes:
        head += f"THE SPREADS AS WRITTEN:\n{scenes}\n\n"
    if cast_hint:
        head += f"CHARACTERS THAT APPEAR: {cast_hint}\n\n"

    if inherited:
        head += (
            "THIS BOOK IS PART OF AN EXISTING SERIES. The bible below is already "
            "canon and is NOT up for revision — copy every existing entry through "
            "UNCHANGED, word for word, and only ADD entries for characters and "
            "places this book introduces. Changing an established look is the one "
            "unforgivable error.\n\n"
            f"EXISTING SERIES BIBLE:\n{_compact(inherited)}\n\n"
        )

    return head + (
        "Write the production bible. Return ONLY JSON:\n"
        "{\n"
        '  "style": {"medium": "...", "line": "...", "colour": "...", '
        '"light": "...", "composition": "...", "influences": "...", '
        '"rules": ["..."]},\n'
        '  "palette": [{"name": "...", "hex": "#RRGGBB", "use": "..."}],\n'
        f'  "characters": [{{{_fields_json(_CHAR_FIELDS)}}}],\n'
        f'  "settings": [{{{_fields_json(_SET_FIELDS)}}}],\n'
        '  "continuity": ["the rules that must never break across the series"]\n'
        "}\n\n"
        "Every character who appears in any spread gets an entry. Every place "
        "gets an entry, including each character's home even if the story only "
        "visits it once. Be concrete enough that two different illustrators "
        "working from this alone would draw the same thing."
    )


def _fields_json(fields: str) -> str:
    return ", ".join(f'"{f.split(" (")[0].strip()}": "..."'
                     for f in fields.split(", "))


def _compact(bible: dict) -> str:
    """The bible as flat text — for prompts, and for the animation hand-off."""
    out = []
    st = bible.get("style") or {}
    if st:
        out.append("ART DIRECTION: " + "; ".join(
            f"{k}: {v}" for k, v in st.items() if isinstance(v, str) and v.strip()))
        for r in (st.get("rules") or []):
            out.append(f"  rule: {r}")
    pal = bible.get("palette") or []
    if pal:
        out.append("PALETTE: " + ", ".join(
            f"{c.get('name','')} {c.get('hex','')} ({c.get('use','')})" for c in pal))
    for c in bible.get("characters") or []:
        out.append("CHARACTER " + _entry_text(c))
    for s in bible.get("settings") or []:
        out.append("PLACE " + _entry_text(s))
    for r in bible.get("continuity") or []:
        out.append(f"CONTINUITY: {r}")
    return "\n".join(out)


def _entry_text(e: dict) -> str:
    name = str(e.get("name") or "").strip()
    bits = [f"{k}: {v}" for k, v in e.items()
            if k != "name" and isinstance(v, str) and v.strip()]
    for k, v in e.items():
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            bits.append(f"{k}: {', '.join(v)}")
    return f"{name} — " + "; ".join(bits)


# ── building it ──────────────────────────────────────────────────

def _series_sibling_bible(book: dict) -> Optional[dict]:
    """The canon from the earliest book in this series that has one."""
    from ..database import list_books
    ser = (book.get("data") or {}).get("series") or {}
    sid = ser.get("series_id")
    if not sid:
        return None
    sibs = [b for b in (list_books(limit=500).get("books") or [])
            if ((b.get("data") or {}).get("series") or {}).get("series_id") == sid
            and b.get("id") != book.get("id")]
    sibs.sort(key=lambda b: (b["data"]["series"].get("book_number") or 0))
    for b in sibs:
        bib = ((b.get("data") or {}).get("childrens") or {}).get("bible")
        if bib and (bib.get("characters") or bib.get("settings")):
            return bib
    return None


COVER_READ = (
    "You are looking at the APPROVED front cover of this children's book. It is "
    "the agreed look — the whole interior must match it. Describe, precisely "
    "enough that an illustrator could reproduce it without seeing the cover:\n"
    "  · the art medium and technique (gouache? vector? ink and wash? 3D?)\n"
    "  · the line quality, edge treatment and level of texture\n"
    "  · the palette, as colour names AND hex values\n"
    "  · the lighting and how shadows are handled\n"
    "  · how characters are drawn: proportions, head-to-body ratio, eye style, "
    "how faces are simplified\n"
    "  · every character visible, by appearance: species, colouring, markings, "
    "clothing, and any prop they hold\n"
    "Write it as an art-direction brief, not as a description of a picture."
)


async def read_cover(catalog: str) -> str:
    """The approved cover, read as an art-direction brief.

    This is what makes 'pick the cover, then build the book' work: the look is
    chosen once, in the one image the buyer actually sees, and everything
    inside inherits it instead of inventing a second style.
    """
    from pathlib import Path as _P
    from ..config import OUTPUT_DIR
    from .client import complete_vision
    for name in ("cover-front.png", "cover-art.png"):
        pth = _P(OUTPUT_DIR) / catalog / name
        if pth.exists():
            try:
                return (await complete_vision(BIBLE_SYSTEM, COVER_READ,
                                              pth.read_bytes(), max_tokens=2000)).strip()
            except Exception:
                return ""
    return ""


async def build_bible(catalog: str, handle=None, rebuild: bool = False) -> dict:
    """Author (or extend) the character and scenery bibles for one book."""
    from ..database import get_book_by_catalog, update_book
    from ..prose.models import Manuscript
    from .client import complete, extract_json, set_model_override, writing_model

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = dict(book["data"])
    rec = dict(d.get("childrens") or {})
    if not rec:
        raise RuntimeError("This is not a children's book yet")
    if rec.get("bible") and not rebuild:
        return rec["bible"]

    ms = Manuscript.model_validate(d.get("manuscript", {}))
    p = preset(rec.get("preset") or ms.genre_preset)
    rec.setdefault("premise", (ms.idea or "").strip())

    inherited = _series_sibling_bible(book)
    if handle:
        handle.progress(0.1, "bible", "reading the approved cover")
    cover_brief = await read_cover(catalog)
    if handle:
        handle.progress(0.2, "bible",
                        "extending the series bible" if inherited
                        else "writing the character and scenery bibles")

    prompt = bible_prompt(book, p, rec, inherited)
    if cover_brief:
        prompt = ("THE APPROVED COVER — this look is already signed off and the "
                  "whole book must match it. Carry it into `style` and into every "
                  "character's appearance verbatim; do not invent a different "
                  f"style:\n{cover_brief}\n\n" + prompt)
    set_model_override(writing_model())
    try:
        raw = await complete(BIBLE_SYSTEM, prompt, max_tokens=12000)
    finally:
        set_model_override(None)

    bible = extract_json(raw) or {}
    if not (bible.get("characters") or bible.get("settings")):
        raise RuntimeError("The bible came back empty")
    if cover_brief:
        bible["cover_brief"] = cover_brief
        bible.setdefault("style", {})["source"] = "approved front cover"
    bible["_text"] = _compact(bible)

    rec["bible"] = bible
    d["childrens"] = rec
    update_book(book["id"], d)
    if handle:
        handle.progress(0.95, "bible",
                        f"{len(bible.get('characters') or [])} characters · "
                        f"{len(bible.get('settings') or [])} places")
    return bible


# ── using it on every prompt ─────────────────────────────────────

def _names_of(entry: dict) -> set:
    n = str(entry.get("name") or "")
    parts = {w for w in _re.sub(r"[^A-Za-z' ]", " ", n).split() if len(w) > 2}
    return ({n} | parts) - {""}


def canon_block(bible: dict, scene_text: str) -> str:
    """The bible entries this scene actually needs, verbatim.

    Only what the scene mentions: sending the whole bible on every prompt
    buries the two characters that matter under twelve that do not. Short
    forms count — a spread says "Pip" where the bible says "Pip Marchetti",
    and without matching that the description silently never arrives.
    """
    if not bible:
        return ""
    hay = scene_text or ""
    out = []
    for c in bible.get("characters") or []:
        if any(_re.search(rf"\b{_re.escape(x)}\b", hay, _re.I) for x in _names_of(c)):
            out.append("CHARACTER — " + _entry_text(c))
    for s in bible.get("settings") or []:
        if any(_re.search(rf"\b{_re.escape(x)}\b", hay, _re.I) for x in _names_of(s)):
            out.append("PLACE — " + _entry_text(s))
    if not out:
        return ""
    return ("These are fixed and already drawn this way elsewhere in the series. "
            "Match them exactly:\n" + "\n".join(out))


def style_block(bible: dict) -> str:
    st = (bible or {}).get("style") or {}
    if not st:
        return ""
    bits = "; ".join(f"{k}: {v}" for k, v in st.items()
                     if isinstance(v, str) and v.strip())
    pal = ", ".join(f"{c.get('name','')} {c.get('hex','')}"
                    for c in (bible.get("palette") or [])[:6])
    line = f"ART DIRECTION (identical on every page): {bits}"
    if pal:
        line += f". Series palette: {pal}"
    return line


# ── reference plates ─────────────────────────────────────────────
# A turnaround sheet per character and a plate per location. These are what
# get fed to the illustrator as image references, and they are also the
# hand-off an animator asks for on day one.

def plate_jobs(bible: dict) -> list:
    jobs = []
    style = style_block(bible)
    for c in bible.get("characters") or []:
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        jobs.append({
            "kind": "character", "name": name,
            "file": f"char-{_slug(name)}.png",
            "prompt": (
                f"Character turnaround reference sheet for a children's book. "
                f"The SAME character drawn four times against a plain off-white "
                f"background: front view, three-quarter view, side view, and back "
                f"view, all standing, all the same height, evenly spaced in a row. "
                f"Beneath them three small head studies: happy, worried, delighted.\n\n"
                f"{_entry_text(c)}\n\n{style}\n\n"
                f"Model-sheet style, clean and evenly lit, no background scenery, "
                f"no text, no labels, no lettering, no words anywhere."),
        })
    for s in bible.get("settings") or []:
        name = str(s.get("name") or "").strip()
        if not name:
            continue
        jobs.append({
            "kind": "setting", "name": name,
            "file": f"place-{_slug(name)}.png",
            "prompt": (
                f"Location reference plate for a children's book. One wide "
                f"establishing view of this place with no characters in it, drawn "
                f"so an illustrator can redraw it from any angle.\n\n"
                f"{_entry_text(s)}\n\n{style}\n\n"
                f"No characters, no text, no lettering, no words anywhere."),
        })
    return jobs


def _slug(s: str) -> str:
    return _re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "x"


async def draw_plates(catalog: str, only: Optional[str] = None, handle=None) -> dict:
    """Draw the turnaround sheets and location plates."""
    import asyncio
    import base64
    from pathlib import Path

    import httpx

    from ..config import OPENAI_API_KEY, OUTPUT_DIR
    from ..cover.front_cover import _best_image_model
    from ..database import get_book_by_catalog, update_book

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = dict(book["data"])
    rec = dict(d.get("childrens") or {})
    bible = rec.get("bible") or {}
    if not bible:
        raise RuntimeError("Build the bible before drawing the reference plates")
    if not OPENAI_API_KEY:
        raise RuntimeError("OpenAI is not configured — the illustrator needs it")

    out_dir = Path(OUTPUT_DIR) / catalog / "bible"
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = [j for j in plate_jobs(bible) if only is None or j["name"] == only]
    todo = [j for j in jobs
            if only is not None or not (out_dir / j["file"]).exists()]
    drawn = [j["file"] for j in jobs if j not in todo]

    # These are independent pictures. Drawing them one after another made a
    # seven-plate book take five to seven minutes, and a single stalled
    # request blocked the rest indefinitely — so: concurrent, with a timeout.
    gate = asyncio.Semaphore(4)
    done = [0]

    async def draw(c, model, j):
        async with gate:
            for attempt in range(3):
                try:
                    r = await asyncio.wait_for(c.post(
                        "https://api.openai.com/v1/images/generations",
                        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                        json={"model": model, "prompt": j["prompt"][:3800],
                              "size": "1536x1024", "quality": "high", "n": 1}),
                        timeout=240)
                except (asyncio.TimeoutError, httpx.HTTPError):
                    continue
                if r.status_code == 200:
                    (out_dir / j["file"]).write_bytes(
                        base64.b64decode(r.json()["data"][0]["b64_json"]))
                    done[0] += 1
                    if handle:
                        handle.progress(0.1 + 0.85 * done[0] / max(1, len(todo)),
                                        "plates", f"drew {j['name']}")
                    return j["file"]
                if r.status_code < 500:
                    return None          # refused: skip it, do not hang the book
                await asyncio.sleep(3 * (attempt + 1))
            return None

    async with httpx.AsyncClient(timeout=300) as c:
        model = await _best_image_model(c)
        got = await asyncio.gather(*(draw(c, model, j) for j in todo),
                                   return_exceptions=True)
    drawn += [g for g in got if isinstance(g, str)]

    rec["plates"] = drawn
    d["childrens"] = rec
    update_book(book["id"], d)
    return {"drawn": drawn, "count": len(drawn)}
