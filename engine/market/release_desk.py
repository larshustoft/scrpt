"""THE RELEASE DESK — finished books leave the house on their own
(Lars, 2026-09-04: "make sure you have a release plan for each book, and that
SCRPT runs daily uploads when there are finished books to upload").

Two duties, once a day, inside the autopilot:

  plan()     every finished-or-nearly-finished book without a release date
             gets one from the slate planner (series cadence, pen-name gaps,
             Tuesday/Wednesday launches, ten days of lead); planned dates
             already on a book are never moved.
  run_due()  every planned book whose upload window has opened is pushed
             through the factory line — acceptance desk, continuity, interior,
             EPUB, cover, keywords, launch gate, paperback published on KDP,
             Kindle staged for its dated publish. Serial, at most MAX_PER_DAY
             titles a day (KDP's own limits), and the desk stops for the day
             the moment KDP asks for a sign-in — a person signs in, never
             SCRPT.

Everything it does is written to the settings ledger `release_desk_log` and to
the daily report, so the morning answer to "what left the house?" is a list,
not a guess.
"""
from __future__ import annotations

import json
import subprocess
import traceback
from datetime import date, datetime, timedelta

from ..database import get_book_by_catalog, get_setting, list_books, set_setting, update_book

def _max_per_day() -> int:
    """KDP titles started per day — a setting (Lars, 2026-09-11: "upload all
    the books to Amazon KDP over the coming days"); KDP's own ten-per-format-
    per-week quota (kdp_quota.can_create) still gates every start."""
    try:
        return max(1, int(get_setting("release_desk_max_per_day", "2") or 2))
    except ValueError:
        return 2


MAX_PER_DAY = 2            # default; the setting above overrides at run time
UPLOAD_WINDOW_DAYS = 14    # upload when the release date is this close
LEAD_DAYS = 10             # ...and no closer: the launch gate refuses fewer days of lead (launch_gate.LEAD_DAYS)


def _notify(title: str, text: str) -> None:
    try:
        subprocess.run(["osascript", "-e", f'display notification "{text[:180]}" with title "{title[:60]}"'],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def _log(entry: dict) -> None:
    try:
        raw = get_setting("release_desk_log", "") or "[]"
        log = json.loads(raw) if isinstance(raw, str) else (raw or [])
        log.append({"at": datetime.now().isoformat(timespec="minutes"), **entry})
        set_setting("release_desk_log", json.dumps(log[-200:]))
    except Exception:
        pass


def _on_kdp(d: dict) -> bool:
    """Published, in review or scheduled on KDP. A DRAFT is not on KDP
    (2026-09-07: The Companion's Clause sat as a KDP draft and the desk
    treated it as done — it would never have been uploaded)."""
    pub = d.get("publishing") or {}
    if pub.get("asin"):
        return True
    st = str(pub.get("kdp_status") or (d.get("kdp") or {}).get("status") or "").lower()
    return bool(pub.get("kdp_present")) and st not in ("", "draft", "draft_complete_awaiting_publish")


def _blocked(d: dict) -> str:
    if d.get("never_publish"):
        return "never_publish"
    if d.get("external"):
        return "external"
    # a film record (a short or an episode born through new_film) is not a book
    if d.get("short") or (d.get("movie") or {}).get("kind") in ("short", "episode"):
        return "film, not a book"
    return ""


def _is_workbook(d: dict) -> bool:
    return (d.get("book_type") or "") == "workbook" or bool((d.get("workbook") or {}).get("done"))


def _series_blocker(d: dict, books: list) -> str:
    """Why this book may not be dated yet because of its series: the name of
    an earlier book that is neither released nor dated. SERIES ORDER
    (2026-09-07): the desk dated Vector: Terminal Sky (book 2) while Zero
    Point (book 1) was still at 'revise'; the gate refused it every morning.
    A book gets a date only when every earlier book in its series is on KDP,
    or accepted and dated before it."""
    s = d.get("series") or {}
    title, no = s.get("series_title"), s.get("book_number")
    if not title or not no:
        return ""
    if _is_workbook(d):
        return ""          # activity books stand alone — they never wait for a story (Lars, 2026-09-10)
    for b in books:
        bd = b.get("data") or {}; bs = bd.get("series") or {}
        if bs.get("series_title") != title or not bs.get("book_number") or int(bs["book_number"]) >= int(no):
            continue
        if _on_kdp(bd):
            continue
        prev_rel = bd.get("release") or {}
        if (bd.get("acceptance") or {}).get("verdict") == "accept" and prev_rel.get("date") and prev_rel.get("status") in ("planned", "submitted", "released"):
            continue
        return f"{b.get('title')} (book {bs['book_number']}) is not ready"
    return ""


def plan(today: date | None = None) -> dict:
    """Give every plannable book a release date; keep the dates that exist."""
    from .scheduler import suggest_schedule, _next_launch_day
    today = today or date.today()
    s = suggest_schedule(today=today)
    books = list_books(per_page=500).get("books", [])
    planned, kept, skipped, moved, undated = [], [], [], [], []
    for p in s.get("proposals") or []:
        cat = p["catalog"]
        b = get_book_by_catalog(cat)
        if not b:
            continue
        d = dict(b["data"])
        if _on_kdp(d) or _blocked(d):
            skipped.append(cat); continue
        rel = dict(d.get("release") or {})
        why_not = _series_blocker(d, books)
        if why_not:
            if rel.get("date") and rel.get("status") == "planned" and not rel.get("locked"):
                rel.update({"date": None, "status": "waiting", "waiting_for": why_not,
                            "undated_at": datetime.now().isoformat(timespec="minutes")})
                d["release"] = rel; update_book(b["id"], d)
                undated.append((cat, why_not))
            else:
                skipped.append(cat)
            continue
        if rel.get("date") and rel.get("status") in ("submitted", "released"):
            kept.append((cat, rel["date"])); continue
        if rel.get("date") and rel.get("status") == "planned":
            # TOO CLOSE (2026-09-05): Fracture Point sat on 8 Sep with four days of lead; the desk
            # rebuilt the interior three mornings in a row and the gate refused it each time
            # ("release date set ≥ 10 days out"). A planned date that has slid inside the lead
            # window is moved to the planner's next lawful day, once, and written to the ledger.
            try:
                rd = date.fromisoformat(str(rel["date"])[:10])
            except ValueError:
                rd = today
            if (rd - today).days >= LEAD_DAYS or rel.get("locked"):
                kept.append((cat, rel["date"])); continue
            new_date = p["date"] if p.get("date") and (date.fromisoformat(p["date"][:10]) - today).days >= LEAD_DAYS \
                else _next_launch_day(today + timedelta(days=LEAD_DAYS)).isoformat()
            rel.update({"date": new_date, "status": "planned", "planned_by": "release-desk",
                        "planned_at": datetime.now().isoformat(timespec="minutes"),
                        "why": [f"moved from {rd.isoformat()}: fewer than {LEAD_DAYS} days of lead"] + (p.get("why") or [])[:3]})
            d["release"] = rel
            update_book(b["id"], d)
            moved.append((cat, rd.isoformat(), new_date)); continue
        if not p.get("ready"):
            skipped.append(cat); continue          # still in production: no date until it is a book
        rel.update({"date": p["date"], "mode": "scheduled", "status": "planned",
                    "planned_by": "release-desk", "planned_at": datetime.now().isoformat(timespec="minutes"),
                    "why": (p.get("why") or [])[:4]})
        d["release"] = rel
        update_book(b["id"], d)
        planned.append((cat, p["date"]))
    out = {"planned": planned, "kept": kept, "skipped": skipped, "moved": moved, "undated": undated}
    _log({"duty": "plan", **{k: v for k, v in out.items() if v}})
    return out


def due(today: date | None = None) -> list[dict]:
    """Planned books whose upload window is open and that are not on KDP yet."""
    today = today or date.today()
    out = []
    for b in list_books(per_page=500).get("books", []):
        d = b.get("data") or {}
        rel = d.get("release") or {}
        if not rel.get("date") or rel.get("status") in ("submitted", "released"):
            continue
        if _on_kdp(d) or _blocked(d):
            continue
        try:
            rd = date.fromisoformat(str(rel["date"])[:10])
        except ValueError:
            continue
        # WORKBOOKS LEAVE AT ONCE (Lars, 2026-09-10: "make sure all the
        # workbooks get uploaded to KDP as soon as they are done"): a finished
        # activity book with a lawful date is due now, not when its window opens.
        if _is_workbook(d) and rd - today >= timedelta(days=LEAD_DAYS):
            out.append({"catalog": b["catalog_number"], "title": b.get("title"), "release_date": rd.isoformat(),
                        "days_to_release": (rd - today).days, "workbook": True})
            continue
        if timedelta(days=LEAD_DAYS) <= rd - today <= timedelta(days=UPLOAD_WINDOW_DAYS):
            out.append({"catalog": b["catalog_number"], "title": b.get("title"), "release_date": rd.isoformat(),
                        "days_to_release": (rd - today).days})
    out.sort(key=lambda x: x["release_date"])
    return out


async def run_due(handle=None, max_per_day: int = 0, publish: bool = True, only_workbooks: bool = False) -> dict:
    """Push the due books through the line, serially, at most max_per_day.
    ONE DESK AT A TIME (2026-09-04): the daily duty and a manual run fired in
    the same minute and both started the line on the same book. A lock in
    the settings (with its time) keeps a second run out for three hours."""
    from .line import run_line
    from . import kdp as kdp_mod
    max_per_day = max_per_day or _max_per_day()
    if not in_upload_window():
        _log({"duty": "run", "note": "outside the upload window"})
        return {"due": [t["catalog"] for t in due()], "ran": [], "stopped": "outside the upload window"}
    lock = get_setting("release_desk_running", "") or ""
    if lock:
        try:
            age_h = (datetime.now() - datetime.fromisoformat(lock)).total_seconds() / 3600
        except ValueError:
            age_h = 99
        if age_h < 3:
            return {"due": [], "ran": [], "stopped": f"the desk is already running (since {lock[:16]})"}
    set_setting("release_desk_running", datetime.now().isoformat(timespec="minutes"))
    try:
        return await _run_due_locked(handle, max_per_day, publish, only_workbooks)
    finally:
        set_setting("release_desk_running", "")


def upload_window() -> tuple[int, int] | None:
    """The hours KDP work may happen, from the setting release_desk_window
    ("00:00-06:00"); empty = any time. Lars, 2026-09-11: "do all the uploads
    between midnight and 06.00"."""
    raw = (get_setting("release_desk_window", "") or "").strip()
    if not raw:
        return None
    try:
        a, b = raw.split("-"); return int(a.split(":")[0]), int(b.split(":")[0])
    except Exception:
        return None


def in_upload_window(now: datetime | None = None) -> bool:
    w = upload_window()
    if not w:
        return True
    h = (now or datetime.now()).hour
    a, b = w
    return a <= h < b if a < b else (h >= a or h < b)


async def reupload_pass(room: int, handle=None) -> list:
    """Books whose files changed after submission (a cover pulled inside
    KDP's safe zone) are re-sent through the line, inside the window, from
    the setting release_desk_reupload."""
    raw = get_setting("release_desk_reupload", "") or "[]"
    try:
        todo = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        todo = []
    if not todo or room <= 0:
        return []
    from .line import run_line
    ran = []
    # a title KDP holds in review is tried again after six hours, not every pass
    try:
        defer = json.loads(get_setting("release_desk_reupload_defer", "") or "{}")
    except Exception:
        defer = {}
    now_iso = datetime.now().isoformat(timespec="minutes")
    for cat in [c for c in todo if (defer.get(c) or "") <= now_iso][:room]:
        if not in_upload_window():        # a pass that began inside the window stops at its edge (Fracture Point ran 06:02-09:01, 2026-09-12)
            _log({"duty": "reupload", "note": "window closed; the rest wait for tonight"}); break
        try:
            r = await run_line(cat, handle=handle, publish=True)
            ok = not r.get("stopped_at")
            detail = str((r.get("kdp") or {}).get("error") or "")
            _log({"duty": "reupload", "catalog": cat, "ok": ok, "stopped_at": r.get("stopped_at"), "error": detail[:160]})
            ran.append({"catalog": cat, "ok": ok, "stopped_at": r.get("stopped_at"), "error": detail[:100]})
            if ok:
                todo.remove(cat); set_setting("release_desk_reupload", json.dumps(todo))
            elif "locked" in detail or "review" in detail.lower():
                defer[cat] = (datetime.now() + timedelta(hours=6)).isoformat(timespec="minutes")
                set_setting("release_desk_reupload_defer", json.dumps(defer))
        except Exception as e:
            _log({"duty": "reupload", "catalog": cat, "ok": False, "error": str(e)[:160]}); ran.append({"catalog": cat, "ok": False, "error": str(e)[:100]})
    return ran


def started_today() -> int:
    """KDP titles the desk started today, from its own ledger."""
    raw = get_setting("release_desk_log", "") or "[]"
    try:
        log = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        return 0
    today = date.today().isoformat()
    return sum(1 for e in log if e.get("duty") == "run" and e.get("ok") and str(e.get("at", ""))[:10] == today)


async def workbook_pass(handle=None) -> dict:
    """Every autopilot pass: date any finished workbook, then push the due
    ones out at once — within the day's KDP allowance."""
    p = plan()
    if not in_upload_window():
        return {"plan": p, "run": {"due": [], "ran": [], "stopped": "outside the upload window"}}
    room = _max_per_day() - started_today()
    if room <= 0:
        return {"plan": p, "run": {"due": [], "ran": [], "stopped": "today's KDP allowance is used"}}
    re = await reupload_pass(room, handle)
    r = await run_due(handle=handle, max_per_day=room, only_workbooks=True)
    r["reuploaded"] = re
    return {"plan": p, "run": r}


async def _run_due_locked(handle, max_per_day, publish, only_workbooks=False) -> dict:
    from .line import run_line
    from . import kdp as kdp_mod
    todo = [t for t in due() if not only_workbooks or t.get("workbook")]
    report = {"due": [t["catalog"] for t in todo], "ran": [], "stopped": ""}
    if not todo:
        _log({"duty": "run", "note": "nothing due"})
        return report
    try:
        st = await kdp_mod.session_status()
        if not st.get("signed_in"):
            report["stopped"] = "KDP is not signed in — a person must sign in (SCRPT never types a password)"
            _notify("SCRPT release desk", f"{len(todo)} book(s) are due for KDP but KDP is signed out. Sign in and the desk continues tomorrow.")
            _log({"duty": "run", "stopped": report["stopped"], "due": report["due"]})
            return report
    except Exception as e:
        report["stopped"] = f"could not read the KDP session: {str(e)[:120]}"
        _log({"duty": "run", "stopped": report["stopped"]})
        return report
    for t in todo[:max_per_day]:
        cat = t["catalog"]
        if not in_upload_window():
            report["stopped"] = "the upload window closed — the rest wait for tonight"
            _log({"duty": "run", "note": report["stopped"]}); break
        try:
            from .kdp_quota import can_create
            ok_pb, why_pb = can_create("paperback"); ok_kd, why_kd = can_create("kindle")
            if not (ok_pb and ok_kd):
                report["stopped"] = f"KDP's weekly title quota is used up ({why_pb if not ok_pb else why_kd}) — the rest wait"
                _log({"duty": "run", "stopped": report["stopped"]}); break
            r = await run_line(cat, handle=handle, publish=publish)
            ok = not r.get("stopped_at")
            entry = {"catalog": cat, "title": t["title"], "ok": ok, "stopped_at": r.get("stopped_at"),
                     "steps": [(s["step"], s["ok"], (s.get("detail") or "")[:80]) for s in r.get("steps", [])]}
            report["ran"].append(entry)
            _log({"duty": "run", **entry})
            if any("sign" in str(s.get("detail", "")).lower() and not s["ok"] for s in r.get("steps", [])):
                report["stopped"] = f"KDP asked for a sign-in during {cat} — stopped for today"
                _notify("SCRPT release desk", f"KDP asked for a sign-in while uploading {t['title']}. Sign in; the desk continues tomorrow.")
                break
        except Exception as e:
            entry = {"catalog": cat, "ok": False, "error": str(e)[:200]}
            report["ran"].append(entry)
            _log({"duty": "run", **entry, "trace": traceback.format_exc()[-400:]})
    started = sum(1 for e in report["ran"] if e.get("ok"))
    if started:
        _notify("SCRPT release desk", f"{started} book(s) went to KDP today: " + ", ".join(e.get("title") or e["catalog"] for e in report["ran"] if e.get("ok")))
    return report


def prep_candidates() -> list[dict]:
    """Finished books the desk should get ready BEFORE their window opens:
    first the ones holding a series back (their successors sit 'waiting'),
    then dated books the gate still refuses. PREP (2026-09-07): the desk
    only ever worked a book once it was due, so a 'revise' verdict was
    discovered ten days before launch and the whole series behind it waited."""
    from .launch_gate import launch_gate
    books = list_books(per_page=500).get("books", [])
    blocking: dict[str, str] = {}
    for b in books:
        rel = (b.get("data") or {}).get("release") or {}
        if rel.get("status") == "waiting" and rel.get("waiting_for"):
            blocking[rel["waiting_for"].split(" (book")[0]] = b["catalog_number"]
    out = []
    for b in books:
        d = b.get("data") or {}
        if _on_kdp(d) or _blocked(d):
            continue
        ms = d.get("manuscript") or {}
        written = bool(ms.get("chapters") and all(c.get("blocks") for c in ms["chapters"]))
        written = written or bool((d.get("childrens") or {}).get("spreads")) or bool((d.get("workbook") or {}).get("done"))
        if not written:
            continue                                   # not written yet: not the desk's job
        rel = d.get("release") or {}
        holds = b.get("title") in blocking
        dated = bool(rel.get("date")) and rel.get("status") == "planned"
        # every finished book is the desk's business (Lars, 2026-09-08: "get as
        # many books out as possible") — dated and series-holding ones first
        try:
            g = launch_gate(b["catalog_number"])
        except Exception:
            continue
        if g.get("ready"):
            continue
        fails = [c["name"] for c in g.get("checks", []) if c.get("blocking") and not c.get("ok")]
        # blockers the desk cannot work on: the publisher's read, series order, the calendar
        if fails and all(f in ("Chapter one read by the publisher", "Series order respected", "Release date set ≥ 10 days out") for f in fails):
            continue
        out.append({"catalog": b["catalog_number"], "title": b.get("title"), "holds_up": blocking.get(b.get("title")),
                    "date": rel.get("date"), "blocked_by": fails, "priority": 0 if holds else (1 if dated else 2)})
    # nearest launch first (it is the one the calendar promised), then the
    # books holding a series back, then the rest by date
    soon = (date.today() + timedelta(days=45)).isoformat()
    out.sort(key=lambda x: (0 if (x["date"] and x["date"] <= soon) else 1, x["priority"], x["date"] or "9999"))
    return out


async def prep(handle=None, max_per_day: int = 1) -> dict:
    """Run the line WITHOUT publishing on the books that need readying:
    acceptance rounds, continuity, interior, wrap, keywords, gate. One a day
    (each round costs model time); the setting release_desk_prep=0 turns it off."""
    from .line import run_line
    if (get_setting("release_desk_prep", "1") or "1") != "1":
        return {"skipped": "release_desk_prep=0"}
    cands = prep_candidates()
    report = {"candidates": [(c["catalog"], c["title"], c["blocked_by"]) for c in cands], "ran": []}
    for c in cands[:max_per_day]:
        try:
            r = await run_line(c["catalog"], handle=handle, publish=False)
            entry = {"catalog": c["catalog"], "title": c["title"], "ready": bool(r.get("ok")), "stopped_at": r.get("stopped_at"),
                     "steps": [(s["step"], s["ok"], (s.get("detail") or "")[:80]) for s in r.get("steps", [])]}
        except Exception as e:
            entry = {"catalog": c["catalog"], "title": c["title"], "ready": False, "error": str(e)[:200]}
        report["ran"].append(entry)
        _log({"duty": "prep", **entry})
    if not cands:
        _log({"duty": "prep", "note": "nothing to ready"})
    return report


async def daily(handle=None) -> dict:
    """The desk's day: plan, upload what is due, then ready what is next."""
    p = plan()
    r = await run_due(handle=handle)
    try:
        prep_n = int(get_setting("release_desk_prep_per_day", "3") or 3)
    except ValueError:
        prep_n = 3
    pr = await prep(handle=handle, max_per_day=prep_n)
    p2 = plan()                                   # a book readied today may take its date now
    set_setting("release_desk_last_run", datetime.now().isoformat(timespec="minutes"))
    return {"plan": p, "run": r, "prep": pr, "replan": p2}


def status() -> dict:
    """What the desk sees right now: the plan and the queue, for the UI and the morning report."""
    raw = get_setting("release_desk_log", "") or "[]"
    try:
        log = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        log = []
    rows = []
    for b in list_books(per_page=500).get("books", []):
        d = b.get("data") or {}
        rel = d.get("release") or {}
        pub = d.get("publishing") or {}
        rows.append({"catalog": b["catalog_number"], "title": b.get("title"), "release_date": rel.get("date"),
                     "release_status": rel.get("status"), "on_kdp": _on_kdp(d), "asin": pub.get("asin"),
                     "blocked": _blocked(d), "acceptance": (d.get("acceptance") or {}).get("verdict")})
    try:
        nxt = prep_candidates()[:5]
    except Exception:
        nxt = []
    return {"last_run": get_setting("release_desk_last_run", ""), "due": due(), "prep_next": nxt, "books": rows, "log": log[-30:]}
