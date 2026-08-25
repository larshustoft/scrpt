"""Schema for the growth engine (keywords, ranks, sales, ad plans)."""

from ..database import get_connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS kw_studies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog TEXT, seed TEXT, store TEXT,
    result JSON, created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS rank_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog TEXT, asin TEXT, marketplace TEXT DEFAULT 'US',
    bsr INTEGER, category_ranks JSON, price REAL, reviews INTEGER,
    rating REAL, captured_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rank_catalog ON rank_history(catalog, captured_at);
CREATE TABLE IF NOT EXISTS sales_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT, catalog TEXT, asin TEXT, title TEXT, marketplace TEXT,
    format TEXT,                      -- ebook | paperback | audiobook
    units INTEGER DEFAULT 0,
    kenp INTEGER DEFAULT 0,
    royalty REAL DEFAULT 0,
    source TEXT DEFAULT 'kdp_report',
    UNIQUE(day, asin, marketplace, format, source)
);
CREATE INDEX IF NOT EXISTS idx_sales_day ON sales_rows(day);
CREATE TABLE IF NOT EXISTS ad_spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT, catalog TEXT, campaign TEXT,
    spend REAL DEFAULT 0, sales REAL DEFAULT 0,
    clicks INTEGER DEFAULT 0, impressions INTEGER DEFAULT 0,
    UNIQUE(day, campaign)
);
CREATE TABLE IF NOT EXISTS ad_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog TEXT, daily_budget REAL, target_acos REAL, max_cpc REAL,
    plan JSON, status TEXT DEFAULT 'draft',
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def init():
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
