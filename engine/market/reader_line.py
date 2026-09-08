"""
The reader line — every finished book gets its print file built by itself.

Lars, 2026-09-08: "I want the Read the book section built in on every book
that is finished. It should show up automatically once the book is written
and has a cover." So this duty runs on every autopilot pass: a book whose
manuscript is written and whose cover exists, but whose print file is
missing, gets its interior built (novels through the print engine, picture
books through the children's interior, workbooks through the workbook line).
The build is local rendering — no model spend.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import OUTPUT_DIR
from ..database import list_books

WRITTEN = {"drafted", "accepted", "editing", "locked", "ready", "complete"}


def _written(d: dict) -> bool:
    ms = d.get("manuscript") or {}
    if (ms.get("status") or "") in WRITTEN or (d.get("acceptance") or {}).get("verdict"):
        return True
    ch = ms.get("chapters") or []
    if ch and all((c.get("blocks") or c.get("text")) for c in ch):
        return True
    if d.get("kind") == "childrens":
        rec = d.get("childrens") or {}
        return bool(rec.get("spreads")) and len(rec.get("art") or {}) >= len(rec.get("spreads") or []) or bool((d.get("workbook") or {}).get("done"))
    return False


def _has_cover(d: dict) -> bool:
    return bool((d.get("cover") or {}).get("cover_front_png"))


def candidates() -> list[dict]:
    out = []
    for b in list_books(per_page=1000).get("books", []):
        if b.get("status") in ("cancelled", "deleted", "archived"):
            continue
        d = b.get("data") or {}
        if b.get("status") == "generating" or ((d.get("manuscript") or {}).get("status") or "") in ("drafting", "idea", "plotting", "bible", "outlined"):
            continue                       # still being written
        if not (_written(d) and _has_cover(d)):
            continue
        if (Path(OUTPUT_DIR) / b["catalog_number"] / "interior.pdf").exists():
            continue
        out.append(b)
    return out


async def build_one(b: dict) -> dict:
    cat, d = b["catalog_number"], b.get("data") or {}
    if (d.get("book_type") or "") == "workbook" or (d.get("workbook") or {}).get("done"):
        from ..writing.workbook import build_workbook_interior
        return await asyncio.to_thread(build_workbook_interior, cat)
    if d.get("kind") == "childrens":
        from ..interior.childrens_interior import build_interior
        return await build_interior(cat, None)
    from ..interior.print_service import export_interior
    return await export_interior(cat)


async def run(max_builds: int = 3) -> dict:
    built, failed = [], []
    for b in candidates()[:max_builds]:
        try:
            await build_one(b)
            built.append(b["title"])
        except Exception as e:
            failed.append({"title": b["title"], "error": str(e)[:160]})
    return {"built": built, "failed": failed}
