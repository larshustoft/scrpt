"""
The slate planner: suggests a release schedule for every book and series.

Deterministic and explainable — every proposed date carries its reasons.
The rules encode what works on Amazon for indie fiction:

  1. Readiness first.   A title is schedulable when it has passed the
     acceptance desk (or is imported/finished); titles still in production
     get a forecast slot further out, marked as such.
  2. One window per launch.  Every release gets its own ~30-day
     new-release window, so launches are spaced, never stacked.
  3. Series cadence.    Books in a series go out in order, four weeks
     apart (genre-tunable), never less than three — the rapid-release
     rhythm that chains read-through. Book N+1 is never dated before N.
  4. Pen-name spacing.  The same author name doesn't launch twice within
     two weeks (author-page and also-bought dilution).
  5. Slate density.     At most one launch per calendar week across the
     house early on; never more than two per day (KDP's cap is three).
  6. Launch days.       Tuesday or Wednesday — retail convention, full
     weekday runway for the first ads and reviews; never Friday–Sunday.
  7. Lead time.         Earliest slot is ten days out: three for KDP's
     review plus a week for pre-order and launch prep.
  8. Seasonality.       Skip the dead zone (Dec 18 – Jan 3); nudge romance
     toward pre-Valentine and early summer, thrillers toward autumn, only
     when a slot is free either way.
  9. Pinned dates win.  Released titles and dates the publisher locked are
     anchors; the planner only fills what is open.
 10. Pre-orders.        For series books, the ebook pre-order opens on the
     previous book's launch day — emitted as a task on that date.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from ..database import list_books

CADENCE_DAYS = {            # between books of the same series
    "historical_romance": 28,
    "romance": 28,
    "action_thriller": 35,
    "thriller": 35,
    "default": 28,
}
MIN_SERIES_GAP = 21
PEN_NAME_GAP = 14
LEAD_DAYS = 10
LAUNCH_WEEKDAYS = (1, 2)    # Tue, Wed (Mon=0)
DEAD_ZONE = ((12, 18), (1, 3))
PRODUCTION_FORECAST_DAYS = 21   # per unfinished title, in queue order


def _cadence(genre: str) -> int:
    for k, v in CADENCE_DAYS.items():
        if k in (genre or ""):
            return v
    return CADENCE_DAYS["default"]


def _in_dead_zone(d: dt.date) -> bool:
    (m1, d1), (m2, d2) = DEAD_ZONE
    return (d.month == m1 and d.day >= d1) or (d.month == m2 and d.day <= d2)


def _next_launch_day(d: dt.date) -> dt.date:
    """Roll forward to the next allowed weekday outside the dead zone."""
    for _ in range(60):
        if d.weekday() in LAUNCH_WEEKDAYS and not _in_dead_zone(d):
            return d
        d += dt.timedelta(days=1)
    return d


def _ready(book: dict) -> tuple[bool, str]:
    d = book.get("data") or {}
    pub = d.get("publishing") or {}
    if pub.get("asin") or d.get("external"):
        return True, "already released"
    if (d.get("acceptance") or {}).get("verdict") == "accept":
        return True, "passed the acceptance desk"
    ms = d.get("manuscript") or {}
    chapters = ms.get("chapters") or []
    if chapters and all(c.get("blocks") for c in chapters) and d.get("interior"):
        return True, "written and typeset"
    return False, "still in production"


def suggest_schedule(today: Optional[dt.date] = None) -> dict:
    today = today or dt.date.today()
    books = list_books(per_page=500).get("books", [])
    earliest = today + dt.timedelta(days=LEAD_DAYS)

    # anchors: released titles and pinned plans occupy their dates
    taken_days: dict[dt.date, int] = {}
    pen_name_days: dict[str, list[dt.date]] = {}
    series_last: dict[str, tuple[int, dt.date]] = {}   # series -> (book_no, date)

    def occupy(date: dt.date, author: str, series: str, book_no: int):
        taken_days[date] = taken_days.get(date, 0) + 1
        pen_name_days.setdefault(author or "", []).append(date)
        if series:
            cur = series_last.get(series)
            if not cur or book_no >= cur[0]:
                series_last[series] = (book_no, date)

    proposals, anchors = [], []
    open_books = []
    for b in books:
        d = b.get("data") or {}
        rel = d.get("release") or {}
        series = (d.get("series") or {}).get("series_title") or ""
        book_no = int((d.get("series") or {}).get("book_number") or 0)
        author = d.get("author_name") or ""
        pub = d.get("publishing") or {}
        released = bool(pub.get("asin") or d.get("external"))
        pinned = bool(rel.get("locked")) or released
        if pinned and (rel.get("date") or pub.get("released_at")):
            date = dt.date.fromisoformat((rel.get("date") or pub.get("released_at"))[:10])
            occupy(date, author, series, book_no)
            anchors.append({"catalog": b["catalog_number"], "title": b["title"],
                            "date": date.isoformat(),
                            "why": ["released" if released else "date locked by the publisher"]})
        elif released:
            anchors.append({"catalog": b["catalog_number"], "title": b["title"],
                            "date": None, "why": ["released (date unknown)"]})
        else:
            open_books.append(b)

    # order: ready first, then by series and book number, then catalog
    def sort_key(b):
        d = b.get("data") or {}
        ready, _ = _ready(b)
        s = d.get("series") or {}
        return (0 if ready else 1, s.get("series_title") or "~", int(s.get("book_number") or 0), b["catalog_number"])
    open_books.sort(key=sort_key)

    week_load: dict[tuple[int, int], int] = {}
    for (date, _) in [(dd, n) for dd, n in taken_days.items()]:
        wk = date.isocalendar()[:2]
        week_load[wk] = week_load.get(wk, 0) + 1

    unready_rank = 0
    for b in open_books:
        d = b.get("data") or {}
        why = []
        series = (d.get("series") or {}).get("series_title") or ""
        book_no = int((d.get("series") or {}).get("book_number") or 0)
        author = d.get("author_name") or ""
        genre = d.get("genre_preset") or ""
        ready, reason = _ready(b)
        why.append(reason)

        candidate = earliest
        if not ready:
            unready_rank += 1
            candidate = today + dt.timedelta(days=LEAD_DAYS + PRODUCTION_FORECAST_DAYS * unready_rank)
            why.append(f"forecast: ~{PRODUCTION_FORECAST_DAYS * unready_rank} days of production ahead of it")

        # series cadence
        if series and series in series_last:
            prev_no, prev_date = series_last[series]
            if book_no > prev_no:
                gap = _cadence(genre)
                candidate = max(candidate, prev_date + dt.timedelta(days=gap))
                why.append(f"{gap} days after {series} #{prev_no} (series cadence)")
        elif series:
            why.append(f"opens {series}")

        # pen-name spacing
        for prev in pen_name_days.get(author, []):
            if abs((candidate - prev).days) < PEN_NAME_GAP:
                candidate = max(candidate, prev + dt.timedelta(days=PEN_NAME_GAP))
                why.append(f"{PEN_NAME_GAP} days clear of {author}'s previous launch")

        # slate density + launch day + dead zone
        for _ in range(120):
            candidate = _next_launch_day(candidate)
            wk = candidate.isocalendar()[:2]
            if taken_days.get(candidate, 0) >= 2:
                candidate += dt.timedelta(days=1); continue
            if week_load.get(wk, 0) >= 1:
                candidate += dt.timedelta(days=1); continue
            break
        why.append(candidate.strftime("%A") + " launch")
        if _in_dead_zone(candidate - dt.timedelta(days=1)):
            why.append("moved past the holiday dead zone")

        occupy(candidate, author, series, book_no)
        week_load[candidate.isocalendar()[:2]] = week_load.get(candidate.isocalendar()[:2], 0) + 1

        tasks = []
        if series and book_no > 1 and series in series_last:
            # the pre-order task sits on the previous book's launch day
            prev = next((p for p in proposals if p.get("series") == series and p.get("book_number") == book_no - 1), None)
            if prev:
                tasks.append({"date": prev["date"], "task": f"open ebook pre-order for {b['title']}"})
        proposals.append({
            "catalog": b["catalog_number"], "title": b["title"], "author": author,
            "series": series or None, "book_number": book_no or None,
            "genre": genre, "ready": ready,
            "current": (d.get("release") or {}).get("date"),
            "date": candidate.isoformat(), "why": why, "tasks": tasks,
        })

    proposals.sort(key=lambda p: p["date"])
    return {"today": today.isoformat(), "anchors": anchors, "proposals": proposals,
            "rules": {"cadence_days": CADENCE_DAYS, "min_series_gap": MIN_SERIES_GAP,
                      "pen_name_gap": PEN_NAME_GAP, "lead_days": LEAD_DAYS,
                      "launch_days": "Tue/Wed", "max_per_week": 1, "max_per_day": 2}}
