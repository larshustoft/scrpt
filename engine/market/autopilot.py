"""
Autopilot — the business running itself.

Once a day, unattended:
    1. rank sweep over every published book
    2. pull KDP sales reports and import them
    3. pull Amazon Ads spend (API when connected, browser upload otherwise)
    4. steer ad budgets inside the ceiling the publisher set
    5. write the daily report

Design rule: every automatic action either costs nothing or SAVES money.
Spending more, publishing a book, or raising the ceiling stays deliberate.
"""

import asyncio
import json
import traceback
from datetime import date, datetime
from typing import Optional

from ..database import get_connection, get_setting, set_setting
from .store import init as _init


def settings() -> dict:
    return {
        "enabled": (get_setting("autopilot_enabled", "0") or "0") == "1",
        "hour": int(get_setting("autopilot_hour", "7") or 7),
        "ads_ceiling": float(get_setting("ads_daily_ceiling", "0") or 0),
        "apply_ad_changes": (get_setting("autopilot_apply_ads", "1") or "1") == "1",
        "last_run": get_setting("autopilot_last_run", "") or None,
    }


def configure(enabled: Optional[bool] = None, hour: Optional[int] = None,
              ads_ceiling: Optional[float] = None,
              apply_ad_changes: Optional[bool] = None) -> dict:
    if enabled is not None:
        set_setting("autopilot_enabled", "1" if enabled else "0")
    if hour is not None:
        set_setting("autopilot_hour", str(max(0, min(23, int(hour)))))
    if ads_ceiling is not None:
        set_setting("ads_daily_ceiling", str(max(0.0, float(ads_ceiling))))
    if apply_ad_changes is not None:
        set_setting("autopilot_apply_ads", "1" if apply_ad_changes else "0")
    return settings()


async def daily_cycle(force: bool = False) -> dict:
    """One full pass. Every step is independent: a failure is recorded and the
    cycle carries on, because a broken ads report must not cost us the report."""
    _init()
    cfg = settings()
    steps: dict = {}

    async def step(name: str, coro):
        try:
            steps[name] = await coro
        except Exception as e:
            steps[name] = {"error": str(e)[:300]}

    # 1. ranks
    from . import rank as rank_mod
    await step("rank", rank_mod.track_all())

    # 2. KDP sales
    from . import kdp as kdp_mod
    from . import sales as sales_mod

    async def kdp_sales():
        res = await kdp_mod.download_reports()
        imported = []
        for path in res.get("files", []):
            with open(path, "rb") as fh:
                imported.append(sales_mod.import_report(fh.read(), path))
        return {**res, "imported": imported}

    await step("sales", kdp_sales())

    # 3 + 4. advertising: pull spend, then steer within the ceiling
    from . import amazon_ads as aads
    if aads.configured().get("refresh_token"):
        await step("ad_spend", aads.sync_spend(7))
        if cfg["ads_ceiling"] > 0:
            await step("ad_optimize", aads.optimize(
                cfg["ads_ceiling"], apply_changes=cfg["apply_ad_changes"]))
        else:
            steps["ad_optimize"] = {"skipped": "no daily ceiling set"}
    else:
        steps["ad_spend"] = {"skipped": "Amazon Ads API not connected"}

    # 5. the report
    from . import report as report_mod
    rep = report_mod.daily()
    steps["report"] = {"date": rep["date"], "net_today": rep["net_today"]}

    set_setting("autopilot_last_run", datetime.now().isoformat(timespec="seconds"))
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS autopilot_runs ("
                     "id INTEGER PRIMARY KEY AUTOINCREMENT, ran_at TEXT, "
                     "result JSON)")
        conn.execute("INSERT INTO autopilot_runs (ran_at, result) VALUES (?,?)",
                     (datetime.now().isoformat(timespec="seconds"),
                      json.dumps(steps)))
        conn.commit()
    finally:
        conn.close()
    return {"ran_at": datetime.now().isoformat(timespec="seconds"),
            "steps": steps, "report_text": report_mod.as_text(rep)}


async def scheduler():
    """Background loop started with the engine. Checks every 15 minutes and
    runs the cycle once per day at the configured hour."""
    await asyncio.sleep(30)
    while True:
        try:
            cfg = settings()
            if cfg["enabled"]:
                now = datetime.now()
                last = (cfg["last_run"] or "")[:10]
                if now.hour >= cfg["hour"] and last != now.date().isoformat():
                    print(f"  ⚙ autopilot: daily cycle at {now:%H:%M}")
                    await daily_cycle()
        except Exception:
            print("  autopilot cycle failed:\n" + traceback.format_exc()[-600:])
        try:
            # dated Kindle publishes: a finished draft whose release day has come
            from ..database import list_books as _lb, get_setting as _gs
            from datetime import date as _date
            for b in _lb(per_page=500).get("books", []):
                dd = b.get("data") or {}
                k = dd.get("kdp") or {}
                when = k.get("kindle_publish_on")
                if (k.get("kindle_status") == "draft_complete_awaiting_publish" and when
                        and _date.fromisoformat(when) <= _date.today() and not k.get("kindle_publish_attempted")):
                    from ..market.kdp_ebook import publish_kindle_only
                    from ..database import get_book_by_catalog as _gb, update_book as _ub
                    fresh = _gb(b["catalog_number"]); data = dict(fresh["data"])
                    data["kdp"] = {**(data.get("kdp") or {}), "kindle_publish_attempted": datetime.now().isoformat(timespec="minutes")}
                    _ub(fresh["id"], data)
                    print(f"  ⚙ kindle: dated publish for {b['catalog_number']}")
                    res = await publish_kindle_only(b["catalog_number"])
                    print(f"  kindle publish {b['catalog_number']}: {res.get('ok')} {res.get('message') or ''}")
        except Exception:
            print("  dated kindle publish failed:\n" + traceback.format_exc()[-600:])
        try:
            # THE RELEASE DESK (Lars, 2026-09-04): once a day, plan every
            # finished book and push the due ones through the line to KDP.
            from ..database import get_setting as _gs2, set_setting as _ss2
            _today = datetime.now().date().isoformat()
            if settings()["enabled"] and datetime.now().hour >= settings()["hour"] and (_gs2("release_desk_last_day", "") or "") != _today:
                _ss2("release_desk_last_day", _today)
                from .release_desk import daily as _desk_daily
                print(f"  ⚙ release desk: daily duty at {datetime.now():%H:%M}")
                _res = await _desk_daily()
                print(f"  release desk: planned {len(_res['plan']['planned'])}, due {len(_res['run']['due'])}, ran {len(_res['run']['ran'])}" + (f" — stopped: {_res['run']['stopped']}" if _res['run'].get('stopped') else ""))
        except Exception:
            print("  release desk failed:\n" + traceback.format_exc()[-600:])
        try:
            from ..reports.sync import due as _sync_due, run_sync as _run_sync
            if _sync_due():
                print("  ⚙ kdp reports: weekly sync")
                await _run_sync()
        except Exception:
            print("  kdp report sync failed:\n" + traceback.format_exc()[-600:])
        await asyncio.sleep(900)


def history(limit: int = 14) -> list[dict]:
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS autopilot_runs ("
                     "id INTEGER PRIMARY KEY AUTOINCREMENT, ran_at TEXT, "
                     "result JSON)")
        rows = conn.execute("SELECT ran_at, result FROM autopilot_runs "
                            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"ran_at": r[0], "result": json.loads(r[1] or "{}")} for r in rows]
    finally:
        conn.close()
