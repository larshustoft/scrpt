"""
The series line — an approved series is written one book at a time.

"Approve book series" (Lars, 2026-09-08) commissions every planned book as a
record, but the house writes them in order: book two starts when book one's
manuscript is drafted, and so on. One draft at a time per series keeps the
spend paced (each book carries its own daily cap) and lets every later book
be plotted against the finished one before it.

Only series flagged series.auto_advance (set at approval) are advanced;
older hand-built series are never touched.
"""
from __future__ import annotations

from ..database import get_connection, get_setting, list_books, update_book
from ..jobs import list_jobs, start_job

STARTED = {"drafting", "drafted", "editing", "locked", "complete"}   # manuscript.status values past the idea stage


def _drafting_now() -> set[str]:
    return {j.get("book_catalog") for j in list_jobs(active_only=True)
            if j.get("kind") in ("full_draft", "childrens_book", "workbook") and j.get("book_catalog")}


def advance(max_starts: int = 2) -> dict:
    """Start the next book of every auto-advancing series whose previous
    book is drafted. Returns what was started and what is waiting."""
    from ..writing import pipeline as wp
    cap = int(get_setting("line_max_drafting") or 4)
    active = _drafting_now()
    started, waiting = [], []
    by_series: dict[str, list[dict]] = {}
    for b in list_books(per_page=1000).get("books", []):
        d = b.get("data") or {}
        s = d.get("series") or {}
        if s.get("series_id") and s.get("auto_advance") and b.get("status") not in ("cancelled", "deleted", "archived"):
            by_series.setdefault(s["series_id"], []).append(b)
    for sid, members in by_series.items():
        members.sort(key=lambda b: int((b["data"].get("series") or {}).get("book_number") or 0))
        if any(m["catalog_number"] in active for m in members):
            continue                                  # one book at a time per series
        prev = None
        is_wb = any((m["data"].get("book_type") or "") == "workbook" for m in members)
        def _done(m):
            d = m["data"]
            if (d.get("book_type") or "") == "workbook":
                return bool((d.get("workbook") or {}).get("done"))
            return ((d.get("manuscript") or {}).get("status") or "") in ("drafted", "editing", "locked", "complete")
        def _started(m):
            d = m["data"]
            if (d.get("book_type") or "") == "workbook":
                return bool((d.get("workbook") or {}).get("pages")) or bool((d.get("workbook") or {}).get("done")) or m["catalog_number"] in active
            return ((d.get("manuscript") or {}).get("status") or "idea") in STARTED or m.get("status") == "generating"
        for m in members:
            if _started(m):
                prev = m; continue
            # first unstarted book: its predecessor must be finished
            if prev is None or not _done(prev):
                waiting.append({"catalog": m["catalog_number"], "title": m["title"], "after": prev["title"] if prev else None})
                break
            if len(active) >= cap or len(started) >= max_starts:
                waiting.append({"catalog": m["catalog_number"], "title": m["title"], "reason": f"{len(active)} books drafting (cap {cap})"})
                break
            cat = m["catalog_number"]
            if is_wb:
                from ..writing.workbook import write_workbook
                job_id = start_job("workbook", lambda h, c=cat: write_workbook(c, h), book_catalog=cat)
            else:
                job_id = start_job("full_draft", lambda h, c=cat: wp.full_draft_job(h, c), book_catalog=cat)
            active.add(cat)
            started.append({"catalog": cat, "title": m["title"], "job_id": job_id, "after": prev["title"]})
            break
    return {"started": started, "waiting": waiting}
