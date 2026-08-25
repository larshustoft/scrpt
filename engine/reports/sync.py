"""
Weekly KDP report sync.

Once a week SCRPT opens the publisher's own signed-in browser session (the
persistent profile at ~/.scrpt/browser-profile), downloads the reports from
kdpreports.amazon.com and imports them into the ledger:

  Royalties Estimator      — the live month
  Prior Months' Royalties  — last month (final) and the current month; on
                             the first run every month back to the start
  Payments                 — the payout ledger

House rule, absolute: SCRPT never types credentials and never touches a
CAPTCHA. If the session has expired, the run records "needs sign-in" and
the Analytics page asks the publisher to sign in once, by hand.
"""

from __future__ import annotations

import asyncio
import json
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

from ..config import OUTPUT_DIR
from ..database import get_setting, set_setting
from .importer import import_report, init_reports_table

BASE = "https://kdpreports.amazon.com"
REPORT_DIR = Path(OUTPUT_DIR).parent / "data" / "kdp-reports"
MAX_BACKFILL_MONTHS = 36


def settings() -> dict:
    raw = get_setting("kdp_sync", "") or ""
    try:
        cfg = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
    except Exception:
        cfg = {}
    return {"enabled": bool(cfg.get("enabled", True)),
            "weekday": int(cfg.get("weekday", 0)),        # 0 = Monday
            "hour": int(cfg.get("hour", 7)),
            "last_run": cfg.get("last_run"),
            "last_result": cfg.get("last_result"),
            "backfilled": bool(cfg.get("backfilled", False))}


def _save(cfg: dict):
    set_setting("kdp_sync", json.dumps(cfg))


def _month_label(d: date) -> str:
    return d.strftime("%B %Y")


def _months_back(n: int) -> list[date]:
    d = date.today().replace(day=1)
    out = []
    for _ in range(n):
        out.append(d)
        d = (d - timedelta(days=1)).replace(day=1)
    return out


async def _download(page, dest_dir: Path, prefix: str) -> Path | None:
    btn = page.get_by_role("button", name="Download report").first
    async with page.expect_download(timeout=45000) as dl:
        await btn.click()
    d = await dl.value
    dest = dest_dir / f"{prefix}-{d.suggested_filename}"
    await d.save_as(str(dest))
    return dest


async def _pick_month(page, label: str) -> bool:
    """Choose a month on the Prior Months' page. Returns False if unavailable."""
    await page.locator(".filter-month").first.click()
    await page.wait_for_timeout(1200)
    try:
        opt = page.get_by_text(label, exact=True).last
        await opt.click(timeout=8000)
    except Exception:
        await page.keyboard.press("Escape")
        return False
    await page.wait_for_timeout(3500)
    sel = (await page.locator(".pmr-selected-month").first.inner_text()).strip()
    return sel == label


async def run_sync(backfill: bool | None = None) -> dict:
    """Download and import. Never signs in."""
    from ..market.browser import Page
    init_reports_table()
    cfg = settings()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    result = {"at": datetime.now().isoformat(timespec="minutes"), "signed_in": True,
              "files": [], "imported": 0, "errors": []}
    do_backfill = (not cfg["backfilled"]) if backfill is None else backfill
    try:
        async with Page(persistent=True) as page:
            await page.goto(f"{BASE}/royalties", timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(6000)
            if "signin" in page.url or "ap/signin" in page.url:
                result["signed_in"] = False
                result["errors"].append("KDP session expired — sign in once by hand (Analytics → Sign in to KDP)")
                cfg["last_run"] = result["at"]; cfg["last_result"] = result; _save(cfg)
                return result

            async def grab(section: str, prefix: str, month: str | None = None):
                try:
                    if page.url.rstrip("/") != f"{BASE}/{section}":
                        await page.goto(f"{BASE}/{section}", timeout=60000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(6000)
                    if month:
                        try:
                            ok = await _pick_month(page, month)
                        except Exception:
                            # the page sometimes re-renders under the picker: reload, try once more
                            await page.goto(f"{BASE}/{section}", timeout=60000, wait_until="domcontentloaded")
                            await page.wait_for_timeout(6000)
                            ok = await _pick_month(page, month)
                        if not ok:
                            result["errors"].append(f"{section}: month {month} not offered")
                            return
                    f = await _download(page, REPORT_DIR, prefix)
                    if f:
                        r = import_report(f.name.split("-", 2)[-1] if f.name.count("-") >= 2 else f.name, f.read_bytes())
                        result["files"].append({"file": f.name, "added": r["total_added"], "rows": r["total_rows"],
                                                "kinds": r["kinds"], "first": r["first_date"], "last": r["last_date"]})
                        result["imported"] += r["total_added"]
                except Exception as e:
                    result["errors"].append(f"{section}{' ' + month if month else ''}: {str(e)[:160]}")

            await grab("royalties", f"{stamp}-estimator")
            await grab("payments", f"{stamp}-payments")
            months = _months_back(MAX_BACKFILL_MONTHS if do_backfill else 2)
            empty_streak = 0
            for m in months:
                before = result["imported"]
                await grab("pmr", f"{stamp}-pmr-{m:%Y-%m}", _month_label(m))
                if do_backfill:
                    # stop the backfill after three months in a row with nothing new
                    # AND no rows at all in the file (before the catalogue existed)
                    last = result["files"][-1] if result["files"] else None
                    if last and last.get("rows", 0) == 0:
                        empty_streak += 1
                    else:
                        empty_streak = 0
                    if empty_streak >= 3:
                        break
            if do_backfill and not result["errors"]:
                cfg["backfilled"] = True
    except Exception as e:
        result["errors"].append(f"sync failed: {str(e)[:200]}")
        traceback.print_exc()
    cfg["last_run"] = result["at"]
    cfg["last_result"] = {k: v for k, v in result.items() if k != "files"} | {"files": result["files"][:12]}
    _save(cfg)
    return result


def due() -> bool:
    cfg = settings()
    if not cfg["enabled"]:
        return False
    now = datetime.now()
    if now.weekday() != cfg["weekday"] or now.hour < cfg["hour"]:
        return False
    last = (cfg["last_run"] or "")[:10]
    return last != now.date().isoformat()


def configure(body: dict) -> dict:
    cfg = settings()
    for k in ("enabled", "weekday", "hour"):
        if k in body and body[k] is not None:
            cfg[k] = body[k]
    _save(cfg)
    return settings()
