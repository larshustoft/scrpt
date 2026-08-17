"""
KDP report importer.

Amazon KDP has no public API; the supported path is the XLSX/CSV files from
kdpreports.amazon.com ("Generate and Download Report"). Sheet and column names
have shifted over the years, so this parser is deliberately tolerant: it scans
every sheet, finds a header row it recognizes, and normalizes what it can.

Normalized row: date, title, asin, marketplace, format, transaction_type,
units, kenp_pages, royalty, currency. Rows are deduplicated by content hash,
so re-importing an overlapping report is safe.
"""

import csv
import hashlib
import io
import json
from datetime import datetime

from ..database import get_connection

# header aliases -> canonical field
ALIASES = {
    "royalty date": "date", "date": "date", "order date": "date",
    "title": "title", "title name": "title",
    "asin": "asin", "asin/isbn": "asin", "isbn": "asin",
    "marketplace": "marketplace", "store": "marketplace",
    "royalty type": "royalty_type",
    "transaction type": "transaction_type",
    "units sold": "units", "net units sold": "units", "units": "units",
    "net units sold or kenp read": "units",
    "kindle edition normalized pages (kenp) read": "kenp_pages",
    "kenp read": "kenp_pages", "kenp": "kenp_pages",
    "royalty": "royalty", "royalty earned": "royalty", "estimated royalty": "royalty",
    "currency": "currency",
    "avg. list price without tax": "list_price", "avg. list price": "list_price",
    "avg. offer price without tax": "offer_price",
}

FORMAT_HINTS = {
    "ebook": "ebook", "kindle": "ebook", "paperback": "paperback",
    "hardcover": "hardcover", "kenp": "kenp", "free": "ebook",
}


def init_reports_table():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS royalty_rows (
                id TEXT PRIMARY KEY,          -- content hash (dedup)
                date TEXT,
                title TEXT,
                asin TEXT,
                marketplace TEXT,
                format TEXT,
                transaction_type TEXT,
                units REAL DEFAULT 0,
                kenp_pages REAL DEFAULT 0,
                royalty REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                source_file TEXT,
                imported_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_roy_date ON royalty_rows(date);
            CREATE INDEX IF NOT EXISTS idx_roy_asin ON royalty_rows(asin);
            CREATE INDEX IF NOT EXISTS idx_roy_title ON royalty_rows(title);
        """)
        conn.commit()
    finally:
        conn.close()


def _canon_headers(raw_headers: list) -> dict[int, str]:
    """Map column index -> canonical name for a candidate header row."""
    mapping = {}
    for i, h in enumerate(raw_headers):
        if h is None:
            continue
        key = str(h).strip().lower()
        if key in ALIASES:
            mapping[i] = ALIASES[key]
    return mapping


def _detect_format(sheet_name: str, row: dict) -> str:
    rt = (row.get("royalty_type") or "") + " " + (row.get("transaction_type") or "")
    hay = (sheet_name + " " + rt).lower()
    if row.get("kenp_pages"):
        return "kenp"
    for hint, fmt in FORMAT_HINTS.items():
        if hint in hay:
            return fmt
    return "unknown"


def _norm_date(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m", "%b %Y", "%B %Y"):
        try:
            return datetime.strptime(s[:19].split(" ")[0] if " " in s and fmt not in ("%b %Y", "%B %Y") else s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s[:10]


def _num(v) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except ValueError:
        return 0.0


def _ingest_rows(rows_iter, sheet_name: str, source_file: str) -> tuple[int, int]:
    """Feed raw rows; find a header row on the fly; insert normalized rows."""
    conn = get_connection()
    added = seen = 0
    mapping: dict[int, str] = {}
    try:
        for raw in rows_iter:
            cells = list(raw)
            if not mapping or len(_canon_headers(cells)) >= 3:
                candidate = _canon_headers(cells)
                if len(candidate) >= 3:
                    mapping = candidate
                    continue
            if not mapping:
                continue
            row = {name: cells[i] if i < len(cells) else None
                   for i, name in mapping.items()}
            if not (row.get("title") or row.get("asin")):
                continue
            norm = {
                "date": _norm_date(row.get("date", "")),
                "title": str(row.get("title") or "").strip(),
                "asin": str(row.get("asin") or "").strip(),
                "marketplace": str(row.get("marketplace") or "").strip(),
                "transaction_type": str(row.get("transaction_type")
                                        or row.get("royalty_type") or "").strip(),
                "units": _num(row.get("units")),
                "kenp_pages": _num(row.get("kenp_pages")),
                "royalty": _num(row.get("royalty")),
                "currency": str(row.get("currency") or "USD").strip() or "USD",
            }
            norm["format"] = _detect_format(sheet_name, {**row, **norm})
            if norm["units"] == 0 and norm["kenp_pages"] == 0 and norm["royalty"] == 0:
                continue
            row_id = hashlib.sha1(
                json.dumps(norm, sort_keys=True).encode()).hexdigest()[:20]
            seen += 1
            cur = conn.execute(
                """INSERT OR IGNORE INTO royalty_rows
                   (id, date, title, asin, marketplace, format, transaction_type,
                    units, kenp_pages, royalty, currency, source_file)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row_id, norm["date"], norm["title"], norm["asin"],
                 norm["marketplace"], norm["format"], norm["transaction_type"],
                 norm["units"], norm["kenp_pages"], norm["royalty"],
                 norm["currency"], source_file),
            )
            added += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return added, seen


def import_report(filename: str, content: bytes) -> dict:
    """Import a KDP report file (.xlsx or .csv). Returns counts per sheet."""
    init_reports_table()
    results = {}
    if filename.lower().endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        added, seen = _ingest_rows(csv.reader(io.StringIO(text)), "csv", filename)
        results["csv"] = {"added": added, "rows": seen}
    else:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        for ws in wb.worksheets:
            added, seen = _ingest_rows(ws.iter_rows(values_only=True), ws.title, filename)
            if seen:
                results[ws.title] = {"added": added, "rows": seen}
        wb.close()
    return {"file": filename, "sheets": results,
            "total_added": sum(s["added"] for s in results.values())}


# ── aggregation ──────────────────────────────────────────────────

def summary(months: int = 24) -> dict:
    init_reports_table()
    conn = get_connection()
    try:
        by_month = [dict(r) for r in conn.execute(
            """SELECT substr(date,1,7) AS month, format,
                      SUM(units) AS units, SUM(kenp_pages) AS kenp_pages,
                      SUM(royalty) AS royalty, currency
               FROM royalty_rows
               GROUP BY month, format, currency
               ORDER BY month DESC LIMIT ?""", (months * 8,)).fetchall()]
        by_marketplace = [dict(r) for r in conn.execute(
            """SELECT marketplace, SUM(units) AS units, SUM(royalty) AS royalty,
                      currency
               FROM royalty_rows GROUP BY marketplace, currency
               ORDER BY royalty DESC""").fetchall()]
        totals = dict(conn.execute(
            """SELECT COUNT(DISTINCT title) AS titles, SUM(units) AS units,
                      SUM(kenp_pages) AS kenp_pages, SUM(royalty) AS royalty
               FROM royalty_rows""").fetchone())
        return {"by_month": by_month, "by_marketplace": by_marketplace,
                "totals": totals}
    finally:
        conn.close()


def by_book() -> list[dict]:
    init_reports_table()
    conn = get_connection()
    try:
        rows = [dict(r) for r in conn.execute(
            """SELECT title, asin, format, SUM(units) AS units,
                      SUM(kenp_pages) AS kenp_pages, SUM(royalty) AS royalty,
                      currency, MIN(date) AS first_sale, MAX(date) AS last_sale
               FROM royalty_rows
               GROUP BY title, asin, format, currency
               ORDER BY royalty DESC""").fetchall()]
        # match to catalog books by exact title (case-insensitive)
        books = conn.execute("SELECT catalog_number, title FROM books").fetchall()
        title_map = {b["title"].strip().lower(): b["catalog_number"] for b in books}
        for r in rows:
            r["catalog_number"] = title_map.get((r["title"] or "").strip().lower())
        return rows
    finally:
        conn.close()


def series_readthrough() -> dict:
    """
    Per-series read-through funnel + ad-allocation recommendation.

    Read-through proxy: unit ratio book_n / book_(n-1) (KDP has no
    customer-level chains). value_per_first_sale = total series royalty per
    book-1 unit sold — the number that tells you what a book-1 ad click is
    actually worth. Allocation: proportional to value x recent velocity, with
    an exploration floor so unproven series keep getting discovery budget.
    """
    init_reports_table()
    conn = get_connection()
    try:
        books = conn.execute("SELECT catalog_number, title, data FROM books").fetchall()
        rows = conn.execute(
            """SELECT title, SUM(units) AS units, SUM(kenp_pages) AS kenp,
                      SUM(royalty) AS royalty,
                      SUM(CASE WHEN date >= date('now','-60 days')
                          THEN royalty ELSE 0 END) AS royalty_recent
               FROM royalty_rows GROUP BY LOWER(TRIM(title))""").fetchall()
    finally:
        conn.close()

    sales = {(r["title"] or "").strip().lower(): dict(r) for r in rows}

    series_map: dict[str, dict] = {}
    for b in books:
        data = json.loads(b["data"]) if isinstance(b["data"], str) else (b["data"] or {})
        ser = (data.get("series") or {})
        if not ser.get("series_id") or not data.get("manuscript"):
            continue
        sid = ser["series_id"]
        entry = series_map.setdefault(sid, {
            "series_title": ser.get("series_title", ""), "books": []})
        srow = sales.get((b["title"] or "").strip().lower(), {})
        entry["books"].append({
            "catalog_number": b["catalog_number"],
            "title": b["title"],
            "book_number": ser.get("book_number", 1),
            "units": float(srow.get("units") or 0),
            "kenp_pages": float(srow.get("kenp") or 0),
            "royalty": float(srow.get("royalty") or 0),
            "royalty_recent": float(srow.get("royalty_recent") or 0),
        })

    MIN_UNITS_PROVEN = 20   # below this, read-through is noise
    EXPLORE_POOL = 0.10     # share of budget reserved for unproven series

    out = []
    for sid, entry in series_map.items():
        bks = sorted(entry["books"], key=lambda x: x["book_number"])
        b1_units = bks[0]["units"] if bks else 0
        readthrough = []
        for i in range(1, len(bks)):
            prev, cur = bks[i - 1]["units"], bks[i]["units"]
            readthrough.append(round(cur / prev, 3) if prev >= 5 else None)
        total_royalty = sum(b["royalty"] for b in bks)
        value_per_first_sale = round(total_royalty / b1_units, 2) if b1_units >= 1 else None
        recent = sum(b["royalty_recent"] for b in bks)
        proven = b1_units >= MIN_UNITS_PROVEN
        out.append({
            "series_id": sid,
            "series_title": entry["series_title"],
            "books": bks,
            "readthrough": readthrough,
            "value_per_first_sale": value_per_first_sale,
            "royalty_total": round(total_royalty, 2),
            "royalty_recent_60d": round(recent, 2),
            "proven": proven,
        })

    # allocation: proven series split ~90% by value x velocity; explorers split the floor
    proven_series = [s for s in out if s["proven"] and s["value_per_first_sale"]]
    explorers = [s for s in out if not s["proven"]]
    scores = {
        s["series_id"]: max(0.01, (s["value_per_first_sale"] or 0))
        * max(1.0, s["royalty_recent_60d"])
        for s in proven_series
    }
    score_sum = sum(scores.values()) or 1
    main_pool = 1.0 - (EXPLORE_POOL if explorers else 0)
    for s in out:
        if s["series_id"] in scores:
            s["suggested_ad_share"] = round(main_pool * scores[s["series_id"]] / score_sum, 3)
        elif explorers:
            s["suggested_ad_share"] = round(EXPLORE_POOL / len(explorers), 3)
        else:
            s["suggested_ad_share"] = 0.0

    out.sort(key=lambda s: -(s["suggested_ad_share"] or 0))
    return {"series": out,
            "notes": {"min_units_proven": MIN_UNITS_PROVEN,
                      "explore_pool": EXPLORE_POOL}}
