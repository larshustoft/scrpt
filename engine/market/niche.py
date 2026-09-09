"""
The niche meter — what a shelf on Amazon actually sells, measured.

Lars, 2026-09-09: "I want books that sell, so it needs to be built on the
market research and on what books actually sell. The same method that
Bookbeam is using." That method: take the books ranking on the first page
for a niche, read each one's Best Sellers Rank, turn BSR into estimated
sales with a known curve, add it up, and set it against how many titles
compete. Nothing here is a model's opinion; every number is read off Amazon.

BSR → sales/day (Amazon.com Books, print+Kindle blended, 2025-26 curves as
published by the estimator tools; conservative side):
  rank      1 ≈ 3,500/day   ·   100 ≈ 350   ·   1,000 ≈ 65   ·   5,000 ≈ 17
  10,000 ≈ 9  ·  50,000 ≈ 2.2  ·  100,000 ≈ 1.1  ·  500,000 ≈ 0.2  ·  1M ≈ 0.08
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import math
import re
import urllib.parse
from typing import Optional

from ..database import get_connection

_CURVE = [(1, 3500), (10, 1500), (100, 350), (1000, 65), (5000, 17), (10000, 9),
          (50000, 2.2), (100000, 1.1), (500000, 0.2), (1000000, 0.08), (5000000, 0.01)]


def bsr_to_daily(bsr: Optional[int]) -> float:
    """Log-log interpolation on the curve above."""
    if not bsr or bsr < 1:
        return 0.0
    for (r0, s0), (r1, s1) in zip(_CURVE, _CURVE[1:]):
        if bsr <= r1:
            t = (math.log(bsr) - math.log(r0)) / (math.log(r1) - math.log(r0))
            return math.exp(math.log(s0) + t * (math.log(s1) - math.log(s0)))
    return 0.01


_ASIN_RE = re.compile(r'data-asin="([A-Z0-9]{10})"')
_COUNT_RE = re.compile(r"(?:over\s+)?([\d,]+)\s*results", re.I)


def _init():
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS niche_data (seed TEXT PRIMARY KEY, measured_at TEXT, data JSON)")
        conn.commit()
    finally:
        conn.close()


def cached(seed: str, max_days: int = 14) -> Optional[dict]:
    _init()
    conn = get_connection()
    try:
        row = conn.execute("SELECT measured_at, data FROM niche_data WHERE seed=?", (seed.lower().strip(),)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        if (dt.datetime.now() - dt.datetime.fromisoformat(row[0])).days > max_days:
            return None
        return json.loads(row[1])
    except Exception:
        return None


async def measure(seed: str, store: str = "stripbooks", top_n: int = 10) -> dict:
    """First-page books for `seed`, each read for BSR, price and reviews."""
    from .browser import Page
    from .rank import snapshot
    hit = cached(seed)
    if hit:
        return hit
    out = {"seed": seed, "store": store, "competing_titles": None, "top": [], "error": None}
    try:
        async with Page() as page:
            await page.goto("https://www.amazon.com/s?" + urllib.parse.urlencode({"k": seed, "i": store}),
                            timeout=45000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)
            html = await page.content()
            m = _COUNT_RE.search(html)
            if m:
                out["competing_titles"] = int(m.group(1).replace(",", ""))
            asins, seen = [], set()
            for a in _ASIN_RE.findall(html):
                if a not in seen and not a.startswith("B0") or (a not in seen):
                    seen.add(a); asins.append(a)
            asins = [a for a in asins if a][:top_n]
            # titles by ASIN, from the result cards
            titles = await page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('div[data-component-type="s-search-result"]')]
                .map(d => [d.getAttribute('data-asin'), ((d.querySelector('h2')||{}).innerText||'').trim()]))""")
    except Exception as e:
        out["error"] = f"search: {str(e)[:120]}"
        return out
    for a in asins:
        try:
            s = await snapshot(a)
        except Exception as e:
            s = {"asin": a, "error": str(e)[:80]}
        daily = bsr_to_daily(s.get("bsr"))
        price = None
        try:
            price = float(re.sub(r"[^\d.]", "", str(s.get("price") or "")) or 0) or None
        except ValueError:
            price = None
        out["top"].append({"asin": a, "title": (titles or {}).get(a, "")[:90], "bsr": s.get("bsr"), "price": price,
                           "reviews": s.get("reviews"), "rating": s.get("rating"), "units_day": round(daily, 2)})
    ranked = [t for t in out["top"] if t.get("bsr")]
    units = [t["units_day"] for t in ranked]
    prices = [t["price"] for t in ranked if t.get("price")]
    out["measured"] = len(ranked)
    out["units_month_top"] = round(sum(units) * 30) if units else 0
    out["median_units_month"] = round(sorted(units)[len(units) // 2] * 30) if units else 0
    out["avg_price"] = round(sum(prices) / len(prices), 2) if prices else None
    out["revenue_month_top"] = round(sum(t["units_day"] * (t.get("price") or (out["avg_price"] or 0)) * 30 for t in ranked)) if ranked else 0
    # a NEW book that lands mid-page (ranks 5-10): the median of the lower half, at a third of that
    lower = sorted(units)[: max(1, len(units) // 2)]
    med_lower = sorted(lower)[len(lower) // 2] if lower else 0
    out["new_book_units_month"] = {"conservative": round(med_lower * 30 * 0.1), "realistic": round(med_lower * 30 * 0.35), "stretch": round(med_lower * 30)}
    out["measured_at"] = dt.datetime.now().isoformat(timespec="minutes")
    _init()
    conn = get_connection()
    try:
        conn.execute("INSERT OR REPLACE INTO niche_data (seed, measured_at, data) VALUES (?,?,?)",
                     (seed.lower().strip(), out["measured_at"], json.dumps(out)))
        conn.commit()
    finally:
        conn.close()
    return out


async def measure_many(seeds: list[str], store: str = "stripbooks", parallel: int = 1) -> dict[str, dict]:
    """The profile lock serialises the browser anyway; one at a time keeps
    Amazon calm. ~30-60 s per niche."""
    res = {}
    for s in seeds:
        res[s] = await measure(s, store)
    return res


def brief(data: dict[str, dict]) -> str:
    """The measured table the acquisitions editor must reason from."""
    lines = ["MEASURED NICHES (live Amazon, Books store, first-page titles, BSR read from each product page; "
             "units/day from the BSR curve):"]
    for seed, d in data.items():
        if d.get("error") or not d.get("measured"):
            lines.append(f"- {seed}: not measured ({d.get('error') or 'no ranked titles'})"); continue
        nb = d["new_book_units_month"]
        lines.append(f"- {seed}: {d['competing_titles'] or '?'} competing titles · top {d['measured']} sell ≈{d['units_month_top']} units/month "
                     f"(≈${d['revenue_month_top']}/month) · median title ≈{d['median_units_month']}/month · avg price ${d['avg_price']} · "
                     f"a NEW title landing mid-page: {nb['conservative']}/{nb['realistic']}/{nb['stretch']} units/month (cons/real/stretch). "
                     f"Leaders: " + "; ".join(f"{t['title'][:50]} (BSR {t['bsr']:,}, ${t['price']})" for t in d['top'][:3] if t.get('bsr')))
    return "\n".join(lines)
