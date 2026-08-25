"""
The cost ledger: every model call, priced, against the book it served.
"""
from __future__ import annotations

import contextvars
import datetime as dt
from ..database import get_connection

current_catalog: contextvars.ContextVar = contextvars.ContextVar("current_catalog", default=None)
current_job: contextvars.ContextVar = contextvars.ContextVar("current_job", default=None)

# USD per million tokens: input, output, cache read, cache write
PRICES = {
    "claude-fable-5":   (10.0, 50.0, 1.0, 12.5),
    "claude-opus-5":    (5.0, 25.0, 0.5, 6.25),
    "claude-opus-4-7":  (5.0, 25.0, 0.5, 6.25),
    "claude-sonnet-5":  (2.0, 10.0, 0.2, 2.5),     # intro pricing through 2026-08-31; 3/15 after
    "claude-sonnet-4-6": (3.0, 15.0, 0.3, 3.75),
    "claude-haiku-4-5": (1.0, 5.0, 0.1, 1.25),
}


def _init():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT, catalog TEXT, job_id TEXT, kind TEXT, model TEXT,
                input_tokens INTEGER, output_tokens INTEGER,
                cache_read INTEGER, cache_write INTEGER, usd REAL
            );
            CREATE INDEX IF NOT EXISTS idx_usage_catalog ON token_usage(catalog);
        """)
        conn.commit()
    finally:
        conn.close()


_ready = False


def record(model: str, usage, kind: str = "") -> float:
    global _ready
    if not _ready:
        _init(); _ready = True
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cw = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    key = next((k for k in PRICES if model and model.startswith(k)), None)
    pi, po, pcr, pcw = PRICES.get(key, (5.0, 25.0, 0.5, 6.25))
    usd = (inp * pi + out * po + cr * pcr + cw * pcw) / 1_000_000
    conn = get_connection()
    try:
        conn.execute("INSERT INTO token_usage (at, catalog, job_id, kind, model, input_tokens, output_tokens, cache_read, cache_write, usd) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (dt.datetime.now().isoformat(timespec="seconds"), current_catalog.get(), current_job.get(), kind, model, inp, out, cr, cw, round(usd, 6)))
        conn.commit()
    finally:
        conn.close()
    return usd


def book_cost(catalog: str) -> dict:
    global _ready
    if not _ready:
        _init(); _ready = True
    conn = get_connection()
    try:
        rows = conn.execute("SELECT model, SUM(input_tokens), SUM(output_tokens), SUM(cache_read), SUM(cache_write), SUM(usd), COUNT(*) FROM token_usage WHERE catalog=? GROUP BY model", (catalog,)).fetchall()
        by_kind = conn.execute("SELECT kind, SUM(usd), COUNT(*) FROM token_usage WHERE catalog=? GROUP BY kind ORDER BY 2 DESC", (catalog,)).fetchall()
    finally:
        conn.close()
    return {"catalog": catalog, "usd": round(sum(r[5] or 0 for r in rows), 3),
            "models": [{"model": r[0], "input": r[1], "output": r[2], "cache_read": r[3], "cache_write": r[4], "usd": round(r[5] or 0, 3), "calls": r[6]} for r in rows],
            "by_kind": [{"kind": r[0] or "—", "usd": round(r[1] or 0, 3), "calls": r[2]} for r in by_kind]}


def all_costs() -> dict:
    """catalog -> USD, for the shelf."""
    global _ready
    if not _ready:
        _init(); _ready = True
    conn = get_connection()
    try:
        rows = conn.execute("SELECT catalog, SUM(usd) FROM token_usage WHERE catalog IS NOT NULL GROUP BY catalog").fetchall()
    finally:
        conn.close()
    return {r[0]: round(r[1] or 0, 2) for r in rows}
