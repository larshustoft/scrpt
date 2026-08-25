"""
Advertising — budget in, profitable spend out.

Amazon's Ads API needs a separate approved developer account, so SCRPT plans
and measures campaigns rather than placing bids directly: it computes what a
click is actually worth for a given book, writes a ready-to-upload Sponsored
Products bulk sheet, then reads performance back from the downloaded ads
report and re-allocates budget toward what earns.

The economics, stated once:
    value of a reader  = royalty per sale
                       + KU share x royalty of a full read
                       + read-through value of the rest of the series
    max profitable CPC = value of a reader x conversion rate / safety multiple
"""

import csv
import io
import json
from datetime import date, timedelta
from typing import Optional

from ..database import get_book_by_catalog, get_connection, list_books
from .sales import book_economics
from .store import init as _init

# defaults calibrated to published indie benchmarks: 2-5% conversion on Amazon
# Ads, most KU-enrolled fiction earning the majority of income from page reads
DEFAULT_CONVERSION = 0.03
DEFAULT_KU_SHARE = 0.6
SAFETY = 1.5            # bid this much under break-even while learning
READ_THROUGH = 0.45     # share of book-1 readers who buy the next book


def _series_siblings(catalog: str) -> list[dict]:
    b = get_book_by_catalog(catalog)
    sid = ((b or {}).get("data", {}).get("series") or {}).get("series_id")
    if not sid:
        return []
    out = []
    for m in list_books(per_page=300)["books"]:
        s = m["data"].get("series") or {}
        if s.get("series_id") == sid and m["catalog_number"] != catalog:
            out.append({"catalog": m["catalog_number"], "title": m["title"],
                        "book_number": s.get("book_number")})
    return out


def reader_value(catalog: str, ku_share: float = DEFAULT_KU_SHARE,
                 read_through: float = READ_THROUGH) -> dict:
    """What one new reader of this book is worth across the series."""
    econ = book_economics(catalog)
    direct = (econ["royalty_per_sale"] * (1 - ku_share)
              + econ["royalty_per_full_read"] * ku_share)
    sibs = _series_siblings(catalog)
    later = [s for s in sibs if (s.get("book_number") or 0)
             > ((get_book_by_catalog(catalog)["data"].get("series") or {})
                .get("book_number") or 1)]
    chain, decay = 0.0, read_through
    for s in later:
        try:
            e = book_economics(s["catalog"])
        except ValueError:
            continue
        chain += decay * (e["royalty_per_sale"] * (1 - ku_share)
                          + e["royalty_per_full_read"] * ku_share)
        decay *= read_through
    return {**econ, "series_books_after": len(later),
            "value_direct": round(direct, 2),
            "value_read_through": round(chain, 2),
            "value_per_reader": round(direct + chain, 2)}


def bid_plan(catalog: str, daily_budget: float,
             conversion: float = DEFAULT_CONVERSION,
             ku_share: float = DEFAULT_KU_SHARE) -> dict:
    """Turn a budget into bids that cannot lose money at the assumed rates."""
    v = reader_value(catalog, ku_share)
    break_even_cpc = v["value_per_reader"] * conversion
    max_cpc = round(break_even_cpc / SAFETY, 2)

    from . import provenance as prov
    reasons = []
    if not v.get("has_real_sales"):
        reasons.append("no KDP sales data yet — reader value is an estimate")
    # conversion rate is always an assumption until an ads report proves it
    reasons.append(f"conversion rate {conversion:.0%} is an assumption "
                   "until an Amazon Ads report is imported")
    verdict = prov.gate(reasons)

    return {
        **v,
        "trust": verdict,
        "assumptions": {"conversion": conversion, "ku_share": ku_share,
                        "read_through": READ_THROUGH},
        "daily_budget": round(daily_budget, 2),
        "assumed_conversion": conversion,
        "break_even_cpc": round(break_even_cpc, 2),
        "max_cpc": max(0.02, max_cpc),
        "starting_bid": max(0.02, round(max_cpc * 0.75, 2)),
        # Amazon reports ACOS against RETAIL revenue, not our royalty, so the
        # ceiling is what a reader is worth divided by the book's price
        "break_even_acos": round(min(3.0, v["value_per_reader"]
                                     / max(v["ebook_price"], 0.99)), 2),
        "target_acos": round(min(2.0, (v["value_per_reader"]
                                       / max(v["ebook_price"], 0.99)) / SAFETY), 2),
        "note": ("Bid is set below break-even while the campaign learns; raise "
                 "it once the ads report shows real conversion."),
    }


def bulk_sheet(catalog: str, keywords: list[str], daily_budget: float,
               bid: Optional[float] = None, campaign_name: str = "") -> str:
    """Amazon Ads Sponsored Products bulk sheet (CSV) — upload as-is."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    plan = bid_plan(catalog, daily_budget)
    bid = bid or plan["starting_bid"]
    asin = ((book["data"].get("publishing") or {}).get("asin")
            or book["data"].get("asin") or "")
    name = campaign_name or f"{book['title'][:40]} - Auto-planned"
    ad_group = "Keywords"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Product", "Entity", "Operation", "Campaign Id", "Ad Group Id",
                "Campaign Name", "Ad Group Name", "Start Date", "Targeting Type",
                "State", "Daily Budget", "SKU/ASIN", "Ad Group Default Bid",
                "Bid", "Keyword Text", "Match Type", "Bidding Strategy"])
    start = date.today().strftime("%Y%m%d")
    w.writerow(["Sponsored Products", "Campaign", "Create", name, "", name, "",
                start, "Manual", "enabled", f"{daily_budget:.2f}", "", "", "",
                "", "", "Dynamic bids - down only"])
    w.writerow(["Sponsored Products", "Ad Group", "Create", name, ad_group,
                name, ad_group, "", "", "enabled", "", "", f"{bid:.2f}", "",
                "", "", ""])
    if asin:
        w.writerow(["Sponsored Products", "Product Ad", "Create", name, ad_group,
                    name, ad_group, "", "", "enabled", "", asin, "", "", "", "", ""])
    for kw in keywords[:200]:
        for match in ("exact", "phrase"):
            w.writerow(["Sponsored Products", "Keyword", "Create", name, ad_group,
                        name, ad_group, "", "", "enabled", "", "", "",
                        f"{bid:.2f}", kw, match, ""])
    return buf.getvalue()


def save_plan(catalog: str, daily_budget: float, keywords: list[str]) -> dict:
    _init()
    plan = bid_plan(catalog, daily_budget)
    plan["keywords"] = keywords[:200]
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO ad_plans (catalog, daily_budget, target_acos, max_cpc, "
            "plan) VALUES (?,?,?,?,?)",
            (catalog, daily_budget, plan.get("target_acos"), plan["max_cpc"],
             json.dumps(plan)))
        conn.commit()
        plan["id"] = cur.lastrowid
    finally:
        conn.close()
    return plan


def import_ads_report(content: bytes, filename: str = "ads.csv") -> dict:
    """Ingest an Amazon Ads campaign report so spend can be judged against
    royalties. Tolerant of column naming, like the KDP importer."""
    _init()
    import pandas as pd
    from .sales import _pick, _num, _numf
    df = (pd.read_excel(io.BytesIO(content)) if filename.lower().endswith((".xlsx", ".xls"))
          else pd.read_csv(io.BytesIO(content)))
    cols = list(df.columns)
    c_day = _pick(cols, "date")
    c_camp = _pick(cols, "campaign", "name") or _pick(cols, "campaign")
    c_spend = _pick(cols, "spend") or _pick(cols, "cost")
    c_sales = _pick(cols, "sales")
    c_clicks = _pick(cols, "clicks")
    c_impr = _pick(cols, "impressions")
    n = 0
    conn = get_connection()
    try:
        for _, r in df.iterrows():
            day = str(r.get(c_day, date.today()))[:10] if c_day else str(date.today())
            camp = str(r.get(c_camp, "") or "")[:120]
            if not camp:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO ad_spend (day, campaign, spend, sales, "
                "clicks, impressions) VALUES (?,?,?,?,?,?)",
                (day, camp, _numf(r.get(c_spend)) if c_spend else 0.0,
                 _numf(r.get(c_sales)) if c_sales else 0.0,
                 _num(r.get(c_clicks)) if c_clicks else 0,
                 _num(r.get(c_impr)) if c_impr else 0))
            n += 1
        conn.commit()
    finally:
        conn.close()
    return {"imported": n}


def allocate(total_daily_budget: float, days: int = 30) -> dict:
    """Split a pot of money across the catalogue by what actually earns.

    Read-through is the fitness signal: a series whose later books sell is
    worth feeding; one that stalls at book one is not.
    """
    _init()
    since = (date.today() - timedelta(days=days)).isoformat()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT catalog, SUM(royalty) r FROM sales_rows WHERE day >= ? "
            "AND catalog IS NOT NULL GROUP BY catalog", (since,)).fetchall()
        spend = {r[0]: r[1] for r in conn.execute(
            "SELECT catalog, SUM(spend) FROM ad_spend WHERE day >= ? "
            "AND catalog IS NOT NULL GROUP BY catalog", (since,)).fetchall()}
    finally:
        conn.close()

    earners = []
    for catalog, royalty in rows:
        s = float(spend.get(catalog) or 0)
        roas = (royalty / s) if s > 0 else None
        earners.append({"catalog": catalog, "royalty": round(royalty or 0, 2),
                        "spend": round(s, 2), "roas": round(roas, 2) if roas else None})

    # books with no history yet still deserve a starter slice
    starters = [b["catalog_number"] for b in list_books(per_page=300)["books"]
                if b["data"].get("publishing", {}).get("asin")
                and b["catalog_number"] not in {e["catalog"] for e in earners}]

    weights: dict[str, float] = {}
    for e in earners:
        # proven ROAS gets weight; unproven-but-selling gets a base weight
        weights[e["catalog"]] = max(0.2, (e["roas"] or 1.0)) * max(e["royalty"], 1.0)
    for c in starters:
        weights[c] = 1.0

    total_w = sum(weights.values()) or 1.0
    allocation = {c: round(total_daily_budget * w / total_w, 2)
                  for c, w in weights.items()}
    return {"total_daily_budget": round(total_daily_budget, 2),
            "window_days": days, "allocation": allocation,
            "performance": sorted(earners, key=lambda e: -(e["roas"] or 0))}
