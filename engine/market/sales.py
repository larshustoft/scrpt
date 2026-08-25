"""
Sales & royalties — the ScribeCount half of the growth engine.

Amazon publishes no sales API for KDP, so the truth comes from KDP's own
report files (Dashboard -> Reports -> Download). This importer is deliberately
tolerant: KDP's column names differ by report type and marketplace, so columns
are matched by meaning rather than by exact header.
"""

import io
import re
from datetime import date, timedelta
from typing import Optional

from ..database import get_connection, list_books
from .store import init as _init

# what a full Kindle Unlimited read pays, per page (KDP's global fund rate;
# override in settings when Amazon publishes a new month)
DEFAULT_KENP_RATE = 0.0045


def kenp_rate() -> float:
    from ..database import get_setting
    try:
        return float(get_setting("kenp_rate", "") or DEFAULT_KENP_RATE)
    except (TypeError, ValueError):
        return DEFAULT_KENP_RATE


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", str(s).lower())


def _pick(cols: list[str], *needles: str) -> Optional[str]:
    """First column whose normalized name contains all needles."""
    for c in cols:
        n = _norm(c)
        if all(_norm(x) in n for x in needles):
            return c
    return None


def _asin_map() -> dict[str, str]:
    """ASIN -> catalog number, so imported rows attach to SCRPT's books."""
    out = {}
    for b in list_books(per_page=500)["books"]:
        pub = b["data"].get("publishing") or {}
        for key in ("asin", "asin_ebook", "asin_paperback", "asin_audiobook"):
            v = pub.get(key) or b["data"].get(key)
            if v:
                out[str(v).strip().upper()] = b["catalog_number"]
    return out


def import_report(content: bytes, filename: str = "report.xlsx") -> dict:
    """Ingest a KDP royalty/sales report (xlsx or csv). Idempotent per row."""
    _init()
    import pandas as pd

    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        sheets = pd.read_excel(io.BytesIO(content), sheet_name=None)
    else:
        sheets = {"csv": pd.read_csv(io.BytesIO(content))}

    amap = _asin_map()
    rate = kenp_rate()
    imported, skipped, unmatched = 0, 0, set()
    conn = get_connection()
    try:
        for sheet_name, df in sheets.items():
            if df is None or df.empty:
                continue
            cols = list(df.columns)
            c_date = _pick(cols, "date") or _pick(cols, "royaltydate")
            c_asin = _pick(cols, "asin") or _pick(cols, "isbn")
            c_title = _pick(cols, "title")
            c_units = (_pick(cols, "netunitssold") or _pick(cols, "unitssold")
                       or _pick(cols, "units"))
            c_kenp = _pick(cols, "kenp") or _pick(cols, "pagesread")
            c_roy = _pick(cols, "royalty") or _pick(cols, "earnings")
            c_mkt = _pick(cols, "marketplace") or _pick(cols, "store")
            c_fmt = _pick(cols, "format") or _pick(cols, "type")
            if not (c_asin or c_title):
                continue

            for _, row in df.iterrows():
                asin = str(row.get(c_asin, "") or "").strip().upper()
                title = str(row.get(c_title, "") or "").strip()
                day = str(row.get(c_date, "") or "")[:10] if c_date else str(date.today())
                units = _num(row.get(c_units)) if c_units else 0
                kenp = _num(row.get(c_kenp)) if c_kenp else 0
                royalty = _numf(row.get(c_roy)) if c_roy else 0.0
                if not royalty and kenp:
                    royalty = round(kenp * rate, 4)
                if not (units or kenp or royalty):
                    skipped += 1
                    continue
                fmt = _format_of(str(row.get(c_fmt, "")) if c_fmt else "",
                                 sheet_name)
                catalog = amap.get(asin)
                if not catalog and asin:
                    unmatched.add(asin)
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO sales_rows (day, catalog, asin, "
                        "title, marketplace, format, units, kenp, royalty, source) "
                        "VALUES (?,?,?,?,?,?,?,?,?, 'kdp_report')",
                        (day, catalog, asin, title,
                         str(row.get(c_mkt, "US") or "US")[:24], fmt,
                         int(units), int(kenp), float(royalty)))
                    imported += 1
                except Exception:
                    skipped += 1
        conn.commit()
    finally:
        conn.close()
    return {"imported": imported, "skipped": skipped,
            "unmatched_asins": sorted(unmatched)[:25]}


def _num(v) -> int:
    try:
        if v is None or (isinstance(v, float) and v != v):
            return 0
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _numf(v) -> float:
    try:
        if v is None or (isinstance(v, float) and v != v):
            return 0.0
        return float(re.sub(r"[^\d.\-]", "", str(v)) or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_of(raw: str, sheet: str) -> str:
    blob = f"{raw} {sheet}".lower()
    if "audio" in blob:
        return "audiobook"
    if "paperback" in blob or "print" in blob or "pod" in blob:
        return "paperback"
    return "ebook"


def summary(days: int = 30) -> dict:
    """Money in, by book and by format, over a window."""
    _init()
    conn = get_connection()
    try:
        since = (date.today() - timedelta(days=days)).isoformat()
        total = conn.execute(
            "SELECT COALESCE(SUM(royalty),0), COALESCE(SUM(units),0), "
            "COALESCE(SUM(kenp),0) FROM sales_rows WHERE day >= ?",
            (since,)).fetchone()
        by_book = conn.execute(
            "SELECT catalog, title, SUM(units) u, SUM(kenp) k, SUM(royalty) r "
            "FROM sales_rows WHERE day >= ? GROUP BY COALESCE(catalog, title) "
            "ORDER BY r DESC LIMIT 50", (since,)).fetchall()
        by_format = conn.execute(
            "SELECT format, SUM(royalty) r FROM sales_rows WHERE day >= ? "
            "GROUP BY format", (since,)).fetchall()
        return {
            "days": days,
            "royalty": round(total[0] or 0, 2),
            "units": total[1] or 0,
            "kenp": total[2] or 0,
            "by_book": [{"catalog": r[0], "title": r[1], "units": r[2],
                         "kenp": r[3], "royalty": round(r[4] or 0, 2)}
                        for r in by_book],
            "by_format": {r[0]: round(r[1] or 0, 2) for r in by_format},
        }
    finally:
        conn.close()


def book_economics(catalog: str, days: int = 90) -> dict:
    """What one book earns per sale and per KU read — the numbers ad bidding
    must respect. Falls back to list price when there is no history yet."""
    from ..database import get_book_by_catalog
    _init()
    b = get_book_by_catalog(catalog)
    if not b:
        raise ValueError("Book not found")
    price = float(b["data"].get("list_price") or 4.99)
    ebook_price = min(9.99, max(2.99, round(price * 0.5, 2)))
    ms = b["data"].get("manuscript") or {}
    words = sum(c.get("word_count", 0) for c in (ms.get("chapters") or []))
    kenp_pages = int(words / 250) if words else 0     # ~250 words per KENP page
    conn = get_connection()
    try:
        since = (date.today() - timedelta(days=days)).isoformat()
        row = conn.execute(
            "SELECT COALESCE(SUM(royalty),0), COALESCE(SUM(units),0), "
            "COALESCE(SUM(kenp),0) FROM sales_rows WHERE catalog=? AND day>=?",
            (catalog, since)).fetchone()
    finally:
        conn.close()
    royalty, units, kenp = row[0], row[1], row[2]
    per_sale = round(ebook_price * 0.70, 2)
    full_read = round(kenp_pages * kenp_rate(), 2)
    observed = round(royalty / units, 2) if units else None
    has_real_sales = bool(units or kenp)
    from . import provenance as prov
    sources = {
        # price and word count are SET by us — known exactly
        "ebook_price": prov.SET,
        "kenp_pages": prov.SET,
        # royalty-per-unit is REPORTED once KDP sales exist, else an ESTIMATE
        "royalty_per_unit": prov.REPORTED if has_real_sales else prov.ESTIMATE,
        # the KENP fund rate is a published Amazon figure we store — REPORTED
        "royalty_per_full_read": prov.REPORTED,
    }
    return {
        "catalog": catalog, "title": b["title"],
        "ebook_price": ebook_price,
        "royalty_per_sale": per_sale,
        "kenp_pages": kenp_pages,
        "royalty_per_full_read": full_read,
        "observed_royalty_per_unit": observed,
        "window_royalty": round(royalty, 2), "window_units": units,
        "window_kenp": kenp,
        "has_real_sales": has_real_sales,
        "data_sources": sources,
    }
