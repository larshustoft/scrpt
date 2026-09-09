"""
The cover line — every titled book gets its cover made, by the house.

Lars, 2026-09-09: "Create book covers for all of these books." A book that
has a real title and no cover yet (a later book of an approved series, a
book whose cover job died when the image account ran dry) gets its four
variants drawn on the autopilot pass, then the judge picks one — the same
path a commissioned book takes. Picture books pick through their own line
(cover → bible → art), so here the variants are drawn and, for a
children's book, the judge's pick is installed at once.

When the image account has no credits, the pass records that and waits an
hour before trying again, so it never hammers a dead account.
"""
from __future__ import annotations

import datetime as dt

from ..database import get_setting, list_books, set_setting
from ..jobs import list_jobs, start_job


def candidates() -> list[dict]:
    out = []
    active = {j.get("book_catalog") for j in list_jobs(active_only=True) if j.get("kind") in ("cover_variants", "childrens_ready", "childrens_book", "workbook")}
    for b in list_books(per_page=1000).get("books", []):
        if b.get("status") in ("cancelled", "deleted", "archived"):
            continue
        t = (b.get("title") or "").strip()
        if not t or t.lower().startswith("untitled") or len(t) > 120:
            continue
        d = b.get("data") or {}
        if (d.get("cover") or {}).get("cover_front_png") or d.get("external"):
            continue
        if (d.get("kind") or "fiction") not in ("fiction", "nonfiction", "childrens") or (d.get("book_type") or "") in ("film", "episode", "trailer"):
            continue                              # films and formats are not books
        if d.get("film") or d.get("short") or d.get("never_publish") or (d.get("movie") or {}).get("kind") in ("short", "episode"):
            continue                              # a film record, the release desk's test
        if (d.get("book_type") or "") == "workbook":
            continue                              # the workbook line designs its own cover
        if b["catalog_number"] in active:
            continue
        out.append(b)
    # newest first: today's books before the March leftovers (Lars, 2026-09-09:
    # "Create covers for all the books currently in the bookshelf that don't have any cover")
    out.sort(key=lambda b: b.get("created_at") or "", reverse=True)
    return out


async def run(max_starts: int = 2) -> dict:
    paused = get_setting("cover_line_paused_until", "") or ""
    if paused and paused > dt.datetime.now().isoformat(timespec="minutes"):
        return {"skipped": f"image account paused until {paused}"}
    from ..cover.front_cover import generate_cover_variants
    started, failed = [], []
    for b in candidates()[:max_starts]:
        cat = b["catalog_number"]

        async def job(handle, c=cat, kind=(b.get("data") or {}).get("kind")):
            try:
                res = await generate_cover_variants(c, 4, "", on_progress=lambda f, d: handle.progress(f, "creating", d))
            except Exception as e:
                msg = str(e)
                if "429" in msg or "credits" in msg.lower() or "quota" in msg.lower():
                    set_setting("cover_line_paused_until", (dt.datetime.now() + dt.timedelta(hours=1)).isoformat(timespec="minutes"))
                raise
            if kind == "childrens":
                from ..writing.childrens_ready import pick_cover
                await pick_cover(c)
            return res
        started.append({"catalog": cat, "title": b["title"], "job_id": start_job("cover_variants", job, book_catalog=cat)})
    return {"started": started, "failed": failed}
