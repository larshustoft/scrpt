"""
The royalties ledger: every KDP report, normalised into one table.

KDP has no public API; the supported path is the files from the Reports
tab (kdpreports.amazon.com). SCRPT reads all of them:

  Prior Months' Royalties  — FINAL numbers per month (the truth)
  Royalties Estimator      — this month and last, ESTIMATED (sheets per
                             format: Combined Sales, eBook/Paperback/
                             Hardcover Royalty, KENP Read)
  Orders                   — units ordered per day (velocity, not money)
  KENP Read                — pages read per day
  Payments                 — what Amazon actually paid, per marketplace

Sheet and column names have shifted over the years, so the parser scans
every sheet for a header row it recognises and normalises what it can.
Rows are keyed by a content hash, so re-importing an overlapping file is
safe; an ESTIMATE row for a month is superseded when a FINAL file for that
month arrives (estimates are deleted for months a final report covers).

Every amount keeps its native currency; totals are shown in the house's
base currency with a rates table the publisher can edit.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime, date

from ..database import get_connection, get_setting, set_setting

# header aliases -> canonical field
ALIASES = {
    "royalty date": "date", "date": "date", "order date": "date", "sales period": "date",
    "payment date": "payment_date",
    "title": "title", "title name": "title",
    "author name": "author", "author": "author",
    "asin": "asin", "asin/isbn": "asin", "isbn": "isbn",
    "earnings": "royalty", "payout plan": "transaction_type",
    "avg. manufacturing cost": "print_cost", "avg. delivery/manufacturing cost": "print_cost",
    "paid units": "units_sold", "paid units sold": "units_sold",
    "payout amount": "payout", "net earnings": "net_earnings", "accrued royalty": "accrued",
    "sales period - start date": "period_start", "sales period - end date": "period_end",
    "sales period": "period", "payment number": "payment_number",
    "marketplace": "marketplace", "store": "marketplace",
    "royalty type": "royalty_type",
    "transaction type": "transaction_type",
    "units sold": "units_sold", "units ordered": "units_sold", "paid units": "units_sold",
    "units refunded": "units_refunded", "units returned": "units_refunded",
    "net units sold": "net_units", "net units": "net_units", "units": "net_units",
    "net units sold or kenp read": "net_units",
    "free units": "free_units", "free units ordered": "free_units",
    "kindle edition normalized pages (kenp) read": "kenp_pages",
    "kindle edition normalized page (kenp) read": "kenp_pages",
    "kenp read": "kenp_pages", "kenp": "kenp_pages", "pages read": "kenp_pages",
    "royalty": "royalty", "royalty earned": "royalty", "estimated royalty": "royalty",
    "payment amount": "amount", "amount": "amount", "total": "amount",
    "currency": "currency", "payment currency": "currency",
    "avg. list price without tax": "list_price", "avg. list price": "list_price",
    "list price": "list_price",
    "avg. offer price without tax": "offer_price",
    "avg. delivery/printing cost": "print_cost", "avg. printing cost": "print_cost",
    "avg. delivery cost": "print_cost",
    "payment method": "method", "status": "status", "payment status": "status",
}

# default rates to the base currency are approximate; the publisher edits
# them in the Analytics page (Settings → rates). Stored as units of the
# named currency per 1 USD.
DEFAULT_RATES_PER_USD = {
    "USD": 1.0, "EUR": 0.92, "GBP": 0.78, "CAD": 1.36, "AUD": 1.50, "JPY": 150.0,
    "INR": 83.0, "BRL": 5.0, "MXN": 17.0, "SEK": 10.5, "PLN": 4.0,
}


def init_reports_table():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS royalty_rows (
                id TEXT PRIMARY KEY,
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
            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY,
                payment_date TEXT,
                period TEXT,
                marketplace TEXT,
                amount REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                method TEXT,
                status TEXT,
                source_file TEXT,
                imported_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS report_imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file TEXT, kind TEXT, rows INTEGER, added INTEGER,
                first_date TEXT, last_date TEXT,
                imported_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS sales_links (
                key TEXT PRIMARY KEY,         -- lower(title) or asin
                catalog_number TEXT
            );
        """)
        # columns added after the first release
        cols = {r[1] for r in conn.execute("PRAGMA table_info(royalty_rows)").fetchall()}
        for col, ddl in (("units_sold", "REAL DEFAULT 0"), ("units_refunded", "REAL DEFAULT 0"),
                         ("free_units", "REAL DEFAULT 0"), ("kind", "TEXT DEFAULT 'final'"),
                         ("author", "TEXT"), ("list_price", "REAL"), ("print_cost", "REAL"),
                         ("royalty_type", "TEXT"), ("isbn", "TEXT")):
            if col not in cols:
                conn.execute(f"ALTER TABLE royalty_rows ADD COLUMN {col} {ddl}")
        conn.commit()
    finally:
        conn.close()


# ── parsing ──────────────────────────────────────────────────────

def _canon_headers(raw_headers: list) -> dict[int, str]:
    mapping = {}
    for i, h in enumerate(raw_headers):
        if h is None:
            continue
        key = re.sub(r"\s+", " ", str(h).strip().lower())
        key = key.replace("*", "").strip()
        if key in ALIASES:
            mapping[i] = ALIASES[key]
    return mapping


def _kind(filename: str, sheet: str) -> str:
    """What this file is: final | estimate | orders | kenp | payments."""
    hay = f"{filename} {sheet}".lower()
    if "payment" in hay:
        return "payments"
    if "order" in hay:
        return "orders"
    if "kenp" in hay and "royalt" not in hay and "estimator" not in hay:
        return "kenp"
    if "prior" in hay or "pmr" in hay or "final" in hay:
        return "final"
    if "estimator" in hay or "dashboard" in hay:
        return "estimate"
    return "final"


def _detect_format(sheet_name: str, row: dict) -> str:
    hay = f"{sheet_name} {row.get('royalty_type') or ''} {row.get('transaction_type') or ''}".lower()
    if row.get("kenp_pages") and not row.get("units"):
        return "kenp"
    if "kenp" in hay:
        return "kenp"
    if "hardcover" in hay:
        return "hardcover"
    if "paperback" in hay or "print" in hay:
        return "paperback"
    if "ebook" in hay or "kindle" in hay or "e-book" in hay:
        return "ebook"
    if "free" in hay:
        return "ebook"
    # print royalties have printing costs; ebooks don't
    if row.get("print_cost"):
        return "paperback"
    return "ebook"


def _norm_date(v) -> str:
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m", "%b %Y", "%B %Y", "%Y-%m-%d %H:%M:%S", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    m = re.match(r"([A-Za-z]{3,9})\s+(\d{4})", s)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)[:3]} {m.group(2)}", "%b %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s[:10]


def _num(v) -> float:
    if v is None or v == "":
        return 0.0
    s = str(v).strip()
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        x = float(s) if s not in ("", "-", ".") else 0.0
    except ValueError:
        return 0.0
    return -x if neg else x


SKIP_SHEETS = {
    "estimate": {"report definitions", "summary", "ebook royalty", "paperback royalty",
                 "hardcover royalty", "ebook orders placed"},
    "final": {"total earnings"},
}


def _month_from_period(v) -> str:
    """'August 2026' -> '2026-08-01'."""
    s_ = str(v or "").strip()
    for fmt in ("%B %Y", "%b %Y", "%Y-%m", "%m/%Y"):
        try:
            return datetime.strptime(s_, fmt).strftime("%Y-%m-01")
        except ValueError:
            continue
    return ""


def _is_pmr(source_file: str) -> bool:
    return "prior" in (source_file or "").lower() or "pmr" in (source_file or "").lower()


def _ingest_rows(rows_iter, sheet_name: str, source_file: str, kind: str) -> dict:
    conn = get_connection()
    added = seen = 0
    first = last = None
    mapping: dict[int, str] = {}
    months_final = set()
    months_pmr = set()        # months this Prior Months' file covers — it outranks the estimator
    authoritative = _is_pmr(source_file)
    pmr_months_existing = set()
    if not authoritative:
        pmr_months_existing = {r[0] for r in conn.execute(
            "SELECT DISTINCT substr(date,1,7) FROM royalty_rows WHERE source_file LIKE '%Prior%' OR source_file LIKE '%pmr%'").fetchall()}
    period_date = ""          # Prior Months' sheets: the month lives in a "Sales Period" cell
    this_month = date.today().strftime("%Y-%m")
    try:
        for raw in rows_iter:
            cells = list(raw)
            if (not mapping and cells and str(cells[0] or "").strip().lower() == "sales period"
                    and len(cells) > 1 and cells[1]):
                period_date = _month_from_period(cells[1])
                if period_date and period_date[:7] >= this_month and kind == "final":
                    kind = "estimate"          # the current month is never final
                continue
            candidate = _canon_headers(cells)
            if len(candidate) >= 3 and (not mapping or len(candidate) > len(mapping) or "title" in candidate.values()):
                if not mapping or len(candidate) >= 3:
                    mapping = candidate
                    continue
            if not mapping:
                continue
            row = {name: cells[i] if i < len(cells) else None for i, name in mapping.items()}

            if kind == "payments" or ("payout" in row and "title" not in row) or ("amount" in row and "title" not in row):
                amt = _num(row.get("payout") if row.get("payout") not in (None, "") else row.get("amount"))
                if not amt or not row.get("marketplace"):      # detail sub-rows carry no marketplace
                    continue
                pdate = _norm_date(row.get("payment_date") or row.get("date"))
                period = (_norm_date(row.get("period_start"))[:7] if row.get("period_start")
                          else (_month_from_period(row.get("period")) or _norm_date(row.get("date")))[:7])
                norm = {"payment_date": pdate, "period": period,
                        "marketplace": str(row.get("marketplace") or "").strip(),
                        "amount": amt, "currency": str(row.get("currency") or "USD").strip() or "USD",
                        "method": str(row.get("method") or "").strip(), "status": str(row.get("status") or "").strip()}
                pid = hashlib.sha1(json.dumps(norm, sort_keys=True).encode()).hexdigest()[:20]
                seen += 1
                cur = conn.execute("""INSERT OR IGNORE INTO payments
                    (id, payment_date, period, marketplace, amount, currency, method, status, source_file)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (pid, norm["payment_date"], norm["period"], norm["marketplace"], norm["amount"],
                     norm["currency"], norm["method"], norm["status"], source_file))
                added += cur.rowcount
                first = min(first or pdate, pdate); last = max(last or pdate, pdate)
                continue

            if not (row.get("title") or row.get("asin") or row.get("isbn")):
                continue
            sold = _num(row.get("units_sold"))
            refunded = _num(row.get("units_refunded"))
            net = _num(row.get("net_units")) if row.get("net_units") not in (None, "") else (sold - refunded)
            free = _num(row.get("free_units"))
            norm = {
                "date": _norm_date(row.get("date")) if row.get("date") else period_date,
                "title": str(row.get("title") or "").strip(),
                "author": str(row.get("author") or "").strip(),
                "asin": str(row.get("asin") or "").strip(),
                "isbn": str(row.get("isbn") or "").strip(),
                "marketplace": str(row.get("marketplace") or "").strip(),
                "royalty_type": str(row.get("royalty_type") or "").strip(),
                "transaction_type": str(row.get("transaction_type") or row.get("royalty_type") or "").strip(),
                "units_sold": sold, "units_refunded": refunded, "units": net, "free_units": free,
                "kenp_pages": _num(row.get("kenp_pages")),
                "royalty": _num(row.get("royalty")),
                "list_price": _num(row.get("list_price")) or None,
                "print_cost": _num(row.get("print_cost")) or None,
                "currency": str(row.get("currency") or "USD").strip() or "USD",
                "kind": kind,
            }
            norm["format"] = _detect_format(sheet_name, norm)
            if norm["units"] == 0 and norm["kenp_pages"] == 0 and norm["royalty"] == 0 and norm["free_units"] == 0:
                continue
            if not authoritative and kind in ("estimate", "final") and norm["date"][:7] in pmr_months_existing:
                continue          # the Prior Months' report already covers this month
            if authoritative and norm["date"]:
                months_pmr.add(norm["date"][:7])
            if not norm["asin"] and norm["isbn"]:
                norm["asin"] = norm["isbn"]
            key_fields = {k: norm[k] for k in ("date", "title", "asin", "marketplace", "format",
                                                 "transaction_type", "units", "kenp_pages", "royalty",
                                                 "currency", "kind")}
            row_id = hashlib.sha1(json.dumps(key_fields, sort_keys=True).encode()).hexdigest()[:20]
            seen += 1
            cur = conn.execute(
                """INSERT OR IGNORE INTO royalty_rows
                   (id, date, title, author, asin, isbn, marketplace, format, royalty_type, transaction_type,
                    units_sold, units_refunded, units, free_units, kenp_pages, royalty,
                    list_price, print_cost, currency, kind, source_file)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row_id, norm["date"], norm["title"], norm["author"], norm["asin"], norm["isbn"], norm["marketplace"],
                 norm["format"], norm["royalty_type"], norm["transaction_type"],
                 norm["units_sold"], norm["units_refunded"], norm["units"], norm["free_units"],
                 norm["kenp_pages"], norm["royalty"], norm["list_price"], norm["print_cost"],
                 norm["currency"], norm["kind"], source_file))
            added += cur.rowcount
            d_ = norm["date"]
            if d_:
                first = min(first or d_, d_); last = max(last or d_, d_)
                if kind == "final":
                    months_final.add(d_[:7])
        # a final month supersedes its estimates; a Prior Months' file supersedes
        # estimator rows for the months it covers
        for m in months_final:
            conn.execute("DELETE FROM royalty_rows WHERE kind='estimate' AND substr(date,1,7)=?", (m,))
        for m in months_pmr:
            conn.execute("""DELETE FROM royalty_rows WHERE kind IN ('estimate','final') AND substr(date,1,7)=?
                            AND NOT (source_file LIKE '%Prior%' OR source_file LIKE '%pmr%')""", (m,))
        conn.commit()
    finally:
        conn.close()
    return {"added": added, "rows": seen, "first": first, "last": last}


def import_report(filename: str, content: bytes) -> dict:
    """Import one KDP report file (.xlsx or .csv)."""
    init_reports_table()
    results = {}
    if filename.lower().endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        kind = _kind(filename, "csv")
        results["csv"] = {**_ingest_rows(csv.reader(io.StringIO(text)), "csv", filename, kind), "kind": kind}
    else:
        import openpyxl
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        for ws in wb.worksheets:
            kind = _kind(filename, ws.title)
            file_kind = _kind(filename, "")
            if ws.title.strip().lower() in SKIP_SHEETS.get(file_kind, set()):
                continue          # per-format sheets duplicate the combined sheet
            if ws.title.strip().lower() in ("orders processed", "orders"):
                kind = "orders"
            if ws.title.strip().lower() == "kenp read":
                kind = "kenp"
            r = _ingest_rows(ws.iter_rows(values_only=True), ws.title, filename, kind)
            if r["rows"]:
                results[ws.title] = {**r, "kind": kind}
        wb.close()
    total_added = sum(s["added"] for s in results.values())
    total_rows = sum(s["rows"] for s in results.values())
    firsts = [s["first"] for s in results.values() if s.get("first")]
    lasts = [s["last"] for s in results.values() if s.get("last")]
    kinds = sorted({s["kind"] for s in results.values()})
    conn = get_connection()
    try:
        conn.execute("INSERT INTO report_imports (file, kind, rows, added, first_date, last_date) VALUES (?,?,?,?,?,?)",
                     (filename, "+".join(kinds), total_rows, total_added, min(firsts) if firsts else None,
                      max(lasts) if lasts else None))
        conn.commit()
    finally:
        conn.close()
    return {"file": filename, "sheets": results, "kinds": kinds, "total_added": total_added,
            "total_rows": total_rows, "first_date": min(firsts) if firsts else None,
            "last_date": max(lasts) if lasts else None}


# ── currency ─────────────────────────────────────────────────────

def rates() -> dict:
    stored = get_setting("fx_rates_per_usd", None)
    table = dict(DEFAULT_RATES_PER_USD)
    if stored:
        try:
            table.update({k.upper(): float(v) for k, v in (json.loads(stored) if isinstance(stored, str) else stored).items()})
        except Exception:
            pass
    return table


def base_currency() -> str:
    return (get_setting("base_currency", "") or "USD").upper()


def set_fx(base: str | None = None, table: dict | None = None) -> dict:
    if base:
        set_setting("base_currency", base.upper())
    if table:
        cur = rates()
        cur.update({k.upper(): float(v) for k, v in table.items() if v})
        set_setting("fx_rates_per_usd", json.dumps(cur))
    return {"base": base_currency(), "rates_per_usd": rates()}


def to_base(amount: float, currency: str, base: str | None = None, table: dict | None = None) -> float:
    table = table or rates()
    base = (base or base_currency()).upper()
    cur = (currency or "USD").upper()
    per_usd_from = table.get(cur)
    per_usd_to = table.get(base)
    if not per_usd_from or not per_usd_to:
        return float(amount or 0)
    return float(amount or 0) / per_usd_from * per_usd_to


# ── matching to the catalogue ────────────────────────────────────

def _catalogue_index() -> tuple[dict, dict, dict]:
    """asin/isbn -> catalog, lower(title) -> catalog, manual links."""
    conn = get_connection()
    try:
        books = conn.execute("SELECT catalog_number, title, data FROM books").fetchall()
        links = {r["key"]: r["catalog_number"] for r in conn.execute("SELECT key, catalog_number FROM sales_links").fetchall()}
    finally:
        conn.close()
    by_id, by_title, meta = {}, {}, {}
    for b in books:
        data = json.loads(b["data"]) if isinstance(b["data"], str) else (b["data"] or {})
        cat = b["catalog_number"]
        pub = data.get("publishing") or {}
        kdp = data.get("kdp") or {}
        for v in (pub.get("asin"), pub.get("paperback_asin"), pub.get("ebook_asin"), kdp.get("isbn"),
                  kdp.get("paperback_isbn"), data.get("isbn"), kdp.get("asin")):
            if v:
                by_id[str(v).strip().upper()] = cat
        by_title[(b["title"] or "").strip().lower()] = cat
        short = re.split(r"[:—\-]", b["title"] or "")[0].strip().lower()
        if short and short not in by_title:
            by_title[short] = cat
        ser = data.get("series") or {}
        meta[cat] = {"title": b["title"], "series": ser.get("series_title"), "book_number": ser.get("book_number"),
                     "genre": data.get("genre_preset"), "kind": data.get("kind") or (data.get("manuscript") or {}).get("kind"),
                     "external": bool(data.get("external"))}
    return {**by_id, **{k.upper(): v for k, v in links.items() if not k.islower()}}, \
           {**by_title, **{k: v for k, v in links.items() if k.islower()}}, meta


def match_catalog(title: str, asin: str, by_id: dict, by_title: dict, isbn: str = "") -> str | None:
    for ident in (asin, isbn):
        a = (ident or "").strip().upper()
        if a and a in by_id:
            return by_id[a]
    t = (title or "").strip().lower()
    if t in by_title:
        return by_title[t]
    short = re.split(r"[:—\-(]", t)[0].strip()
    return by_title.get(short)


def link_sale(key: str, catalog_number: str | None) -> dict:
    init_reports_table()
    conn = get_connection()
    try:
        k = key.strip()
        k = k.upper() if re.fullmatch(r"[A-Za-z0-9]{10}|\d{13}|\d{10}", k) else k.lower()
        if catalog_number:
            conn.execute("INSERT OR REPLACE INTO sales_links (key, catalog_number) VALUES (?,?)", (k, catalog_number))
        else:
            conn.execute("DELETE FROM sales_links WHERE key=?", (k,))
        conn.commit()
    finally:
        conn.close()
    return {"key": k, "catalog_number": catalog_number}


# ── aggregation ──────────────────────────────────────────────────

def _rows(where: str = "", params: tuple = ()) -> list[dict]:
    conn = get_connection()
    try:
        return [dict(r) for r in conn.execute(
            f"SELECT * FROM royalty_rows {('WHERE ' + where) if where else ''}", params).fetchall()]
    finally:
        conn.close()


def overview(months: int = 24) -> dict:
    """Everything the Analytics page shows, in the base currency."""
    init_reports_table()
    base = base_currency()
    table = rates()
    rows = _rows("kind IN ('final','estimate','kenp')")
    by_id, by_title, meta = _catalogue_index()
    today = date.today()
    this_m = today.strftime("%Y-%m")
    last_m = (today.replace(day=1) - __import__("datetime").timedelta(days=1)).strftime("%Y-%m")

    month_map: dict[str, dict] = {}
    mkt_map: dict[str, dict] = {}
    book_map: dict[str, dict] = {}
    kpi = {"this_month": 0.0, "last_month": 0.0, "last_90": 0.0, "trailing_12": 0.0, "all_time": 0.0,
           "units_30": 0.0, "kenp_30": 0.0, "units_all": 0.0, "kenp_all": 0.0}
    estimate_months = set()
    for r in rows:
        amt = to_base(r["royalty"], r["currency"], base, table)
        d_ = r["date"] or ""
        m = d_[:7]
        if r.get("kind") == "estimate":
            estimate_months.add(m)
        mm = month_map.setdefault(m, {"month": m, "royalty": 0.0, "units": 0.0, "kenp_pages": 0.0,
                                      "ebook": 0.0, "paperback": 0.0, "hardcover": 0.0, "kenp": 0.0, "estimate": False})
        mm["royalty"] += amt; mm["units"] += r["units"] or 0; mm["kenp_pages"] += r["kenp_pages"] or 0
        mm[r["format"] if r["format"] in ("ebook", "paperback", "hardcover", "kenp") else "ebook"] += amt
        if r.get("kind") == "estimate":
            mm["estimate"] = True
        mk = mkt_map.setdefault(r["marketplace"] or "—", {"marketplace": r["marketplace"] or "—", "royalty": 0.0, "units": 0.0, "kenp_pages": 0.0})
        mk["royalty"] += amt; mk["units"] += r["units"] or 0; mk["kenp_pages"] += r["kenp_pages"] or 0
        cat = match_catalog(r["title"], r["asin"], by_id, by_title, r.get("isbn") or "")
        bkey = cat or (r["title"] or r["asin"] or "").strip().lower()
        bk = book_map.setdefault(bkey, {"key": bkey, "catalog_number": cat, "title": (meta.get(cat) or {}).get("title") or r["title"],
                                        "asins": set(), "royalty": 0.0, "units": 0.0, "kenp_pages": 0.0, "free_units": 0.0,
                                        "royalty_30": 0.0, "royalty_prev_30": 0.0, "units_30": 0.0,
                                        "formats": {}, "first": d_, "last": d_, "marketplaces": set(),
                                        "series": (meta.get(cat) or {}).get("series"), "book_number": (meta.get(cat) or {}).get("book_number")})
        if r["asin"]:
            bk["asins"].add(r["asin"])
        bk["royalty"] += amt; bk["units"] += r["units"] or 0; bk["kenp_pages"] += r["kenp_pages"] or 0
        bk["free_units"] += r.get("free_units") or 0
        f = bk["formats"].setdefault(r["format"], {"royalty": 0.0, "units": 0.0, "kenp_pages": 0.0})
        f["royalty"] += amt; f["units"] += r["units"] or 0; f["kenp_pages"] += r["kenp_pages"] or 0
        bk["first"] = min(bk["first"] or d_, d_); bk["last"] = max(bk["last"] or d_, d_)
        if r["marketplace"]:
            bk["marketplaces"].add(r["marketplace"])
        # windows
        try:
            dd = date.fromisoformat(d_[:10])
        except ValueError:
            dd = None
        if dd:
            age = (today - dd).days
            if m == this_m: kpi["this_month"] += amt
            if m == last_m: kpi["last_month"] += amt
            if age <= 90: kpi["last_90"] += amt
            if age <= 365: kpi["trailing_12"] += amt
            if age <= 30:
                kpi["units_30"] += r["units"] or 0; kpi["kenp_30"] += r["kenp_pages"] or 0
                bk["royalty_30"] += amt; bk["units_30"] += r["units"] or 0
            elif age <= 60:
                bk["royalty_prev_30"] += amt
        kpi["all_time"] += amt; kpi["units_all"] += r["units"] or 0; kpi["kenp_all"] += r["kenp_pages"] or 0

    books = []
    for bk in book_map.values():
        bk["asins"] = sorted(bk["asins"]); bk["marketplaces"] = sorted(bk["marketplaces"])
        bk["royalty_per_unit"] = round(bk["royalty"] / bk["units"], 2) if bk["units"] else None
        prev = bk["royalty_prev_30"]
        bk["trend"] = round((bk["royalty_30"] - prev) / prev, 3) if prev > 0 else None
        for k in ("royalty", "royalty_30", "royalty_prev_30"):
            bk[k] = round(bk[k], 2)
        for f in bk["formats"].values():
            f["royalty"] = round(f["royalty"], 2)
        books.append(bk)
    books.sort(key=lambda b: -b["royalty"])

    by_month = sorted(month_map.values(), key=lambda x: x["month"])[-months:]
    for mm in by_month:
        for k in ("royalty", "ebook", "paperback", "hardcover", "kenp"):
            mm[k] = round(mm[k], 2)
    by_marketplace = sorted(mkt_map.values(), key=lambda x: -x["royalty"])
    for mk in by_marketplace:
        mk["royalty"] = round(mk["royalty"], 2)

    # payments
    conn = get_connection()
    try:
        pays = [dict(r) for r in conn.execute("SELECT * FROM payments ORDER BY payment_date DESC LIMIT 60").fetchall()]
        imports = [dict(r) for r in conn.execute("SELECT * FROM report_imports ORDER BY imported_at DESC LIMIT 400").fetchall()]
        unmatched = [dict(r) for r in conn.execute(
            "SELECT title, asin, SUM(royalty) AS royalty FROM royalty_rows GROUP BY title, asin").fetchall()]
    finally:
        conn.close()
    for p_ in pays:
        p_["amount_base"] = round(to_base(p_["amount"], p_["currency"], base, table), 2)
    paid_total = round(sum(p_["amount_base"] for p_ in pays), 2)
    unmatched = [u for u in unmatched if not match_catalog(u["title"], u["asin"], by_id, by_title)]

    # coverage: which months are final, which are estimates, where the gaps are.
    # A Prior Months' file that was downloaded but had no rows is a real
    # zero month, not a gap — the import log remembers the file.
    import re as _re
    covered_empty = set()
    for im in imports:
        m_ = _re.search(r"pmr-(\d{4}-\d{2})", im.get("file") or "")
        if m_:
            covered_empty.add(m_.group(1))
    months_seen = sorted(set(month_map.keys()) | covered_empty)
    coverage = []
    if months_seen:
        y, mth = map(int, months_seen[0].split("-"))
        end = today.strftime("%Y-%m")
        while f"{y:04d}-{mth:02d}" <= end:
            key = f"{y:04d}-{mth:02d}"
            coverage.append({"month": key, "state": ("estimate" if key in estimate_months else "final") if key in month_map
                             else ("final" if key in covered_empty else "missing")})
            mth += 1
            if mth > 12:
                mth = 1; y += 1

    return {
        "base": base, "rates_per_usd": table,
        "kpi": {k: round(v, 2) for k, v in kpi.items()},
        "by_month": by_month, "by_marketplace": by_marketplace, "books": books,
        "payments": pays, "paid_total": paid_total, "imports": imports,
        "unmatched": unmatched, "coverage": coverage,
        "has_data": bool(rows),
    }


# ── legacy endpoints (kept for the desk and the planner) ──────────

def summary(months: int = 24) -> dict:
    o = overview(months)
    return {"by_month": o["by_month"], "by_marketplace": o["by_marketplace"],
            "totals": {"titles": len(o["books"]), "units": o["kpi"]["units_all"],
                       "kenp_pages": o["kpi"]["kenp_all"], "royalty": o["kpi"]["all_time"]}}


def by_book() -> list[dict]:
    return overview()["books"]


def series_readthrough() -> dict:
    """
    Per-series read-through funnel + ad-allocation recommendation.

    Read-through proxy: unit ratio book_n / book_(n-1) (KDP has no
    customer-level chains). value_per_first_sale = total series royalty per
    book-1 unit sold — what a book-1 ad click is actually worth. Allocation:
    proportional to value x recent velocity, with an exploration floor so
    unproven series keep getting discovery budget.
    """
    init_reports_table()
    base = base_currency()
    table = rates()
    by_id, by_title, meta = _catalogue_index()
    conn = get_connection()
    try:
        books = conn.execute("SELECT catalog_number, title, data FROM books").fetchall()
        rows = conn.execute(
            """SELECT title, asin, currency, SUM(units) AS units, SUM(kenp_pages) AS kenp,
                      SUM(royalty) AS royalty,
                      SUM(CASE WHEN date >= date('now','-60 days') THEN royalty ELSE 0 END) AS royalty_recent
               FROM royalty_rows WHERE kind IN ('final','estimate','kenp')
               GROUP BY title, asin, currency""").fetchall()
    finally:
        conn.close()

    sales: dict[str, dict] = {}
    for r in rows:
        cat = match_catalog(r["title"], r["asin"], by_id, by_title)
        if not cat:
            continue
        s_ = sales.setdefault(cat, {"units": 0.0, "kenp": 0.0, "royalty": 0.0, "royalty_recent": 0.0})
        s_["units"] += r["units"] or 0; s_["kenp"] += r["kenp"] or 0
        s_["royalty"] += to_base(r["royalty"] or 0, r["currency"], base, table)
        s_["royalty_recent"] += to_base(r["royalty_recent"] or 0, r["currency"], base, table)

    series_map: dict[str, dict] = {}
    for b in books:
        data = json.loads(b["data"]) if isinstance(b["data"], str) else (b["data"] or {})
        ser = (data.get("series") or {})
        if not ser.get("series_id"):
            continue
        sid = ser["series_id"]
        entry = series_map.setdefault(sid, {"series_title": ser.get("series_title", ""), "books": []})
        srow = sales.get(b["catalog_number"], {})
        entry["books"].append({
            "catalog_number": b["catalog_number"], "title": b["title"],
            "book_number": ser.get("book_number", 1),
            "units": float(srow.get("units") or 0), "kenp_pages": float(srow.get("kenp") or 0),
            "royalty": round(float(srow.get("royalty") or 0), 2),
            "royalty_recent": round(float(srow.get("royalty_recent") or 0), 2),
        })

    MIN_UNITS_PROVEN = 20
    EXPLORE_POOL = 0.10
    out = []
    for sid, entry in series_map.items():
        bks = sorted(entry["books"], key=lambda x: x["book_number"] or 0)
        b1_units = bks[0]["units"] if bks else 0
        readthrough = []
        for i in range(1, len(bks)):
            prev, cur = bks[i - 1]["units"], bks[i]["units"]
            readthrough.append(round(cur / prev, 3) if prev >= 5 else None)
        total_royalty = sum(b["royalty"] for b in bks)
        value_per_first_sale = round(total_royalty / b1_units, 2) if b1_units >= 1 else None
        recent = sum(b["royalty_recent"] for b in bks)
        out.append({"series_id": sid, "series_title": entry["series_title"], "books": bks,
                    "readthrough": readthrough, "value_per_first_sale": value_per_first_sale,
                    "royalty_total": round(total_royalty, 2), "royalty_recent_60d": round(recent, 2),
                    "proven": b1_units >= MIN_UNITS_PROVEN})

    proven_series = [s_ for s_ in out if s_["proven"] and s_["value_per_first_sale"]]
    explorers = [s_ for s_ in out if not s_["proven"]]
    scores = {s_["series_id"]: max(0.01, (s_["value_per_first_sale"] or 0)) * max(1.0, s_["royalty_recent_60d"])
              for s_ in proven_series}
    score_sum = sum(scores.values()) or 1
    main_pool = 1.0 - (EXPLORE_POOL if explorers else 0)
    for s_ in out:
        if s_["series_id"] in scores:
            s_["suggested_ad_share"] = round(main_pool * scores[s_["series_id"]] / score_sum, 3)
        elif explorers:
            s_["suggested_ad_share"] = round(EXPLORE_POOL / len(explorers), 3)
        else:
            s_["suggested_ad_share"] = 0.0
    out.sort(key=lambda s_: -(s_["suggested_ad_share"] or 0))
    return {"series": out, "base": base,
            "notes": {"min_units_proven": MIN_UNITS_PROVEN, "explore_pool": EXPLORE_POOL}}
