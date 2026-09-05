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

MAX_PER_DAY = 2            # KDP titles started per day
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
    pub = d.get("publishing") or {}
    return bool(pub.get("asin") or pub.get("kdp_present"))


def _blocked(d: dict) -> str:
    if d.get("never_publish"):
        return "never_publish"
    if d.get("external"):
        return "external"
    return ""


def plan(today: date | None = None) -> dict:
    """Give every plannable book a release date; keep the dates that exist."""
    from .scheduler import suggest_schedule, _next_launch_day
    today = today or date.today()
    s = suggest_schedule(today=today)
    planned, kept, skipped, moved = [], [], [], []
    for p in s.get("proposals") or []:
        cat = p["catalog"]
        b = get_book_by_catalog(cat)
        if not b:
            continue
        d = dict(b["data"])
        if _on_kdp(d) or _blocked(d):
            skipped.append(cat); continue
        rel = dict(d.get("release") or {})
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
    out = {"planned": planned, "kept": kept, "skipped": skipped, "moved": moved}
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
        if timedelta(days=LEAD_DAYS) <= rd - today <= timedelta(days=UPLOAD_WINDOW_DAYS):
            out.append({"catalog": b["catalog_number"], "title": b.get("title"), "release_date": rd.isoformat(),
                        "days_to_release": (rd - today).days})
    out.sort(key=lambda x: x["release_date"])
    return out


async def run_due(handle=None, max_per_day: int = MAX_PER_DAY, publish: bool = True) -> dict:
    """Push the due books through the line, serially, at most max_per_day.
    ONE DESK AT A TIME (2026-09-04): the daily duty and a manual run fired in
    the same minute and both started the line on the same book. A lock in
    the settings (with its time) keeps a second run out for three hours."""
    from .line import run_line
    from . import kdp as kdp_mod
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
        return await _run_due_locked(handle, max_per_day, publish)
    finally:
        set_setting("release_desk_running", "")


async def _run_due_locked(handle, max_per_day, publish) -> dict:
    from .line import run_line
    from . import kdp as kdp_mod
    todo = due()
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
        try:
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


async def daily(handle=None) -> dict:
    """The desk's day: plan, then upload what is due."""
    p = plan()
    r = await run_due(handle=handle)
    set_setting("release_desk_last_run", datetime.now().isoformat(timespec="minutes"))
    return {"plan": p, "run": r}


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
    return {"last_run": get_setting("release_desk_last_run", ""), "due": due(), "books": rows, "log": log[-30:]}
