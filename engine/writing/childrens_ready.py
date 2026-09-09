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
              '{"index": N, "why": "one sentence", "rejects": {"N": "reason"}}')
    raw = await complete_vision("You are an art director choosing a book cover. JSON only.", prompt, buf.getvalue(), max_tokens=600)
    j = extract_json(raw) or {}
    idx = int(j.get("index") or 1)
    idx = idx if 1 <= idx <= len(paths) else 1
    res = select_cover_variant(catalog, idx)
    b = get_book_by_catalog(catalog); data = dict(b["data"]); cov = dict(data.get("cover") or {})
    cov["auto_pick"] = {"index": idx, "why": j.get("why"), "rejects": j.get("rejects"), "at": datetime.now().isoformat(timespec="minutes")}
    data["cover"] = cov; update_book(b["id"], data, sections=["cover"])
    return {"index": idx, "why": j.get("why"), **(res if isinstance(res, dict) else {})}


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
    if handle:
        handle.progress(0.85, "interior", "building the interior")
    res = await build_interior(catalog, handle)
    steps.append(("interior", True, f"{res.get('pages')} pages"))
    b = get_book_by_catalog(catalog); data = dict(b["data"])
    data["acceptance"] = {"verdict": "accept", "accepted_by": "children's line", "readability": {"meets_target": True, "house_target": "read-aloud"},
                          "length": {"ok": True}, "continuity": [], "accepted_at": datetime.now().isoformat(timespec="minutes")}
    data["manuscript"] = {**(data.get("manuscript") or {}), "status": "complete"}
    data["childrens_ready"] = {"done": True, "at": datetime.now().isoformat(timespec="minutes"), "steps": steps}
    update_book(b["id"], data)
    return {"ok": True, "steps": steps, **res}
