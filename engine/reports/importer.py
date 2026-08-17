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
