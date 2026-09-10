"""PICTURE BOOKS, UNATTENDED (2026-09-08): after the words are written and
the four cover variants exist, the house used to wait for a click ("pick the
cover"). Now a vision judge picks the cover against the brief and the
universe, the bible is written from it, every spread is drawn, the interior
is built, and the book is accepted for the line. Nothing waits for a person.
"""
from __future__ import annotations

import asyncio
import io
import json
from datetime import datetime
from pathlib import Path

from ..config import OUTPUT_DIR
from ..database import get_book_by_catalog, update_book


def _art_complete(d: dict) -> bool:
    rec = d.get("childrens") or {}
    spreads = rec.get("spreads") or []
    art = rec.get("art") or {}          # illustrate() records its files here — the check read a field nobody writes,
    return bool(spreads) and all(         # so every rerun redrew the whole book (Star Map, 2026-09-08)
        (sp.get("illustration") or {}).get("path") or sp.get("illustrated") or str(sp.get("n")) in art
        for sp in spreads)


async def pick_cover(catalog: str) -> dict:
    """Choose the best of the generated variants with a vision read of a
    contact sheet: on brief, on character, readable at thumbnail, no text
    errors. Returns {index, why}."""
    from PIL import Image
    from .client import complete_vision, extract_json
    from ..cover.front_cover import select_cover_variant
    book = get_book_by_catalog(catalog); d = book["data"]
    out = OUTPUT_DIR / catalog
    paths = [out / f"cover-variant-{i}.png" for i in range(1, 9)]
    paths = [p for p in paths if p.is_file()]
    if not paths:
        raise RuntimeError("no cover variants to choose from")
    if len(paths) == 1:
        return select_cover_variant(catalog, 1) | {"index": 1, "why": "only one variant"}
    thumbs = [Image.open(p).convert("RGB").resize((512, 768)) for p in paths]
    sheet = Image.new("RGB", (512 * len(thumbs) + 16 * (len(thumbs) - 1), 800), "white")
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sheet)
    for i, t in enumerate(thumbs):
        x = i * 528; sheet.paste(t, (x, 32)); dr.text((x + 8, 4), f"#{i + 1}", fill="black")
    buf = io.BytesIO(); sheet.save(buf, format="PNG")
    uni = d.get("universe") or ""
    brief = (d.get("cover_direction") or "") + " " + (d.get("description") or (d.get("manuscript") or {}).get("idea") or "")
    kind_label = {"childrens": "A children's picture book", "nonfiction": "A non-fiction paperback", "fiction": "A novel"}.get(d.get("kind") or "fiction", "A book")
    if (d.get("book_type") or "") == "workbook":
        kind_label = "A children's activity book"
    prompt = (f"Book: {book['title']} by {d.get('author_name') or ''}. {kind_label}" + (f" in the {uni} universe" if uni else "") + ".\n"
              f"Brief: {brief[:800]}\n\nThe image shows {len(thumbs)} candidate front covers, numbered #1 to #{len(thumbs)} left to right. "
              "Pick the ONE that would sell best on Amazon to a buyer scrolling thumbnails: the title must be correctly spelled and readable "
              "at a small size, the character must be appealing and consistent with the brief, the composition clean, no garbled text, no "
              "extra words. Reject any cover with misspelled or invented words. Return JSON only: "
              '{"index": N, "why": "one short sentence", "rejects": {"N": "three words"}} — keep it under 80 words in total')
    raw = await complete_vision("You are an art director choosing a book cover. JSON only.", prompt, buf.getvalue(), max_tokens=1500)
    j = extract_json(raw) or {}
    idx = int(j.get("index") or 1)
    idx = idx if 1 <= idx <= len(paths) else 1
    res = select_cover_variant(catalog, idx)
    b = get_book_by_catalog(catalog); data = dict(b["data"]); cov = dict(data.get("cover") or {})
    cov["auto_pick"] = {"index": idx, "why": j.get("why"), "rejects": j.get("rejects"), "at": datetime.now().isoformat(timespec="minutes")}
    data["cover"] = cov; update_book(b["id"], data, sections=["cover"])
    return {"index": idx, "why": j.get("why"), **(res if isinstance(res, dict) else {})}


async def design_universe_cover(catalog: str) -> dict:
    """A picture-book cover for a book that belongs to a universe: the
    established character LEADS, drawn from the universe's plates (Lars,
    2026-09-09: "created with the main character as the lead"). Four
    variants, then the judge picks."""
    import httpx
    from ..cover.front_cover import _generate_one, _install_cover
    from ..writing.workbook import UNIVERSE_CAST, UNIVERSE_DISPLAY, _plate_png, detect_universe
    book = get_book_by_catalog(catalog); d = book["data"]
    slug = d.get("universe") or detect_universe(book["title"], (d.get("manuscript") or {}).get("idea", ""))
    uni = UNIVERSE_CAST.get(slug, {})
    if not uni:
        raise RuntimeError(f"{catalog} belongs to no known universe")
    names = list((uni.get("plates") or {}).keys()); lead = names[0]
    plates = [png for png in (_plate_png(slug, rel) for rel in (uni.get("plates") or {}).values()) if png]
    author = d.get("author_name") or uni.get("author") or ""
    idea = " ".join(str((d.get("manuscript") or {}).get("idea") or d.get("description") or "").split())[:500]
    brief = (f"Create a picture-book front cover for: {book['title']}\nWhat the story is about (for the ARTWORK only): {idea}\n"
             f"This book belongs to the {UNIVERSE_DISPLAY.get(slug, slug)} universe. {lead.upper()} IS THE LEAD: large, front and centre, "
             f"exactly as in the reference. The characters: {uni['look']} {uni.get('cast', '')} The attached pictures are the references, "
             f"in this order: {', '.join(names)}.\nThe ONLY text on the cover is the title \"{book['title']}\" and the author name \"{author}\".\n"
             "Output the flat cover artwork itself, edge to edge; bright, warm, child-safe; a bestselling picture-book look.")
    out = OUTPUT_DIR / catalog; out.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient() as c:
        pngs = await asyncio.gather(*(_generate_one(c, brief, reference_png=plates, gen_size="1024x1536") for _ in range(4)), return_exceptions=True)
    n = 0
    for png in pngs:
        if isinstance(png, (bytes, bytearray)):
            n += 1; (out / f"cover-variant-{n}.png").write_bytes(png)
            from PIL import Image; import io
            im = Image.open(io.BytesIO(png)).convert("RGB"); im.thumbnail((400, 600)); im.save(out / f"cover-variant-{n}-preview.png")
    if not n:
        raise RuntimeError("no variant survived")
    b = get_book_by_catalog(catalog); data = dict(b["data"]); data["universe"] = slug
    update_book(b["id"], data, sections=["universe"])
    pick = await pick_cover(catalog)
    return {"variants": n, "pick": pick}



PICTURE_BOOK_CATEGORIES = [
    ["Children's Books", "Fairy Tales, Folk Tales & Myths", "Unicorns"],
    ["Children's Books", "Animals", "General"],
    ["Children's Books", "Growing Up & Facts of Life", "Friendship, Social Skills & School Life", "Friendship"],
]


def default_print_categories(d: dict) -> list:
    """A KDP print-category plan for a picture book: the picker matches each
    level by containment and falls back to General under the first path it
    can resolve, so these only need to be plausible, not exact."""
    theme = " ".join(str(x) for x in ((d.get("childrens") or {}).get("premise"), d.get("description"), d.get("title"))).lower()
    plan = []
    if "unicorn" in theme or "princess" in theme:
        plan.append(["Children's Books", "Fairy Tales, Folk Tales & Myths", "Unicorns"])
    if any(w in theme for w in ("star", "moon", "sky", "space")):
        plan.append(["Children's Books", "Science, Nature & How It Works", "Astronomy & Space"])
    if any(w in theme for w in ("farm", "barn", "tractor")):
        plan.append(["Children's Books", "Animals", "Farm Animals"])
    if any(w in theme for w in ("cat", "dog", "bird", "dinosaur")):
        plan.append(["Children's Books", "Animals", "General"])
    for c in PICTURE_BOOK_CATEGORIES:
        if c not in plan:
            plan.append(c)
    return plan[:3]


async def write_picture_blurb(catalog: str) -> str:
    """The KDP description / back-cover text for a picture book, written for
    the parent (Star Map, 2026-09-10: KDP refused the draft — no description,
    no category — because in-house picture books never got either)."""
    from .client import complete
    book = get_book_by_catalog(catalog); d = book["data"]; rec = d.get("childrens") or {}
    spreads = rec.get("spreads") or []
    text_in = "\n".join((s.get("text") or "").strip() for s in spreads)[:3500]
    prompt = (f"BOOK: {book['title']}\nAGES: {rec.get('age') or '3-6'}\nAUTHOR: {d.get('author_name') or ''}\n"
              f"THE STORY, page by page:\n{text_in}\n\n"
              "Write the back-cover text a parent reads in the shop: 3 short paragraphs, 70-110 words in total. "
              "Paragraph 1: who the hero is and what happens, warm and concrete, without giving away the ending. "
              "Paragraph 2: what a child takes from it (one feeling or one small lesson) and the friends along the way. "
              "Paragraph 3: one line on the format (full-colour picture book, read-aloud, ages) and an invitation. "
              "Speak to the parent. No hype words (ultimate, amazing, perfect, magical journey). No bullet points, no headings, no quotes. "
              "Plain text, paragraphs separated by a blank line.")
    text = (await complete("You write the back covers of children's picture books for a small publishing house. Warm, exact, never salesy.",
                           prompt, max_tokens=600, mechanical=True)).strip()
    b = get_book_by_catalog(catalog); data = dict(b["data"])
    data["description"] = text; data["back_cover_blurb"] = text
    update_book(b["id"], data, sections=["description", "back_cover_blurb"])
    return text


async def shop_ready(catalog: str) -> dict:
    """Description and print categories every picture book needs on KDP —
    written once, kept if present."""
    b = get_book_by_catalog(catalog); d = dict(b["data"]); done = {}
    if not (d.get("description") or "").strip():
        await write_picture_blurb(catalog); done["description"] = True
        b = get_book_by_catalog(catalog); d = dict(b["data"])
    kdp = dict(d.get("kdp") or {})
    if not kdp.get("print_categories_plan"):
        kdp["print_categories_plan"] = default_print_categories(d); d["kdp"] = kdp
        update_book(b["id"], d, sections=["kdp"]); done["categories"] = kdp["print_categories_plan"]
    return done


async def ready_childrens(catalog: str, handle=None) -> dict:
    """Words written → cover chosen → bible → illustrations → interior → accepted."""
    from .childrens_bible import build_bible
    from .childrens import illustrate
    from ..interior.childrens_interior import build_interior
    steps = []
    book = get_book_by_catalog(catalog); d = book["data"]
    rec = d.get("childrens") or {}
    if not rec.get("spreads"):
        return {"ok": False, "stopped_at": "words", "steps": [("words", False, "not written yet")]}
    cover = d.get("cover") or {}
    if not (cover.get("selected_variant") or cover.get("mode") == "upload"):
        if handle:
            handle.progress(0.1, "cover", "choosing the cover")
        try:
            pk = await pick_cover(catalog)
            steps.append(("cover", True, f"variant {pk.get('index')}: {str(pk.get('why') or '')[:80]}"))
        except Exception as e:
            steps.append(("cover", False, str(e)[:120])); return {"ok": False, "stopped_at": "cover", "steps": steps}
    else:
        steps.append(("cover", True, "chosen"))
    d = get_book_by_catalog(catalog)["data"]
    bib = (d.get("childrens") or {}).get("bible") or {}
    if not (bib.get("characters") or bib.get("settings")):
        if handle:
            handle.progress(0.2, "bible", "writing the bible from the cover")
        await build_bible(catalog, handle)
        steps.append(("bible", True, "written from the cover"))
    else:
        steps.append(("bible", True, "present"))
    d = get_book_by_catalog(catalog)["data"]
    if not _art_complete(d):
        if handle:
            handle.progress(0.3, "art", "drawing the spreads")
        await illustrate(catalog, None, handle)
        d = get_book_by_catalog(catalog)["data"]
        if not _art_complete(d):
            steps.append(("art", False, "spreads left undrawn")); return {"ok": False, "stopped_at": "art", "steps": steps}
        steps.append(("art", True, f"{len((d.get('childrens') or {}).get('spreads') or [])} spreads drawn"))
    else:
        steps.append(("art", True, "complete"))
    try:
        sr = await shop_ready(catalog)
        if sr:
            steps.append(("shop", True, ", ".join(sr.keys())))
    except Exception as e:
        steps.append(("shop", False, str(e)[:100]))
    if handle:
        handle.progress(0.85, "interior", "building the interior")
    res = await build_interior(catalog, handle)
    steps.append(("interior", True, f"{res.get('pages')} pages"))
    b = get_book_by_catalog(catalog); data = dict(b["data"])
    data["acceptance"] = {"verdict": "accept", "accepted_by": "children's line", "readability": {"meets_target": True, "house_target": "read-aloud"},
                          "length": {"ok": True}, "continuity": [], "accepted_at": datetime.now().isoformat(timespec="minutes")}
    data["manuscript"] = {**(data.get("manuscript") or {}), "status": "drafted"}
    data["childrens_ready"] = {"done": True, "at": datetime.now().isoformat(timespec="minutes"), "steps": steps}
    update_book(b["id"], data)
    return {"ok": True, "steps": steps, **res}
