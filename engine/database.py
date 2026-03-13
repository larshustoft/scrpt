"""
SCRPT Database Layer
=====================
SQLite database with simple JSON metadata storage.
No ORM — just clean SQL with json_extract for queries.

Tables:
  - books:    All book projects with full metadata as JSON
  - niches:   Validated niche research results
  - settings: Key-value app settings
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DATABASE_PATH, CATALOG_PREFIX


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")     # Better concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database():
    """Create tables if they don't exist."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY,
                catalog_number TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                data JSON NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS niches (
                id TEXT PRIMARY KEY,
                keyword TEXT NOT NULL,
                status TEXT DEFAULT 'validated',
                data JSON NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value JSON NOT NULL
            );

            -- Indexes for common queries
            CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);
            CREATE INDEX IF NOT EXISTS idx_books_catalog ON books(catalog_number);
            CREATE INDEX IF NOT EXISTS idx_books_created ON books(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_niches_keyword ON niches(keyword);
            CREATE INDEX IF NOT EXISTS idx_niches_status ON niches(status);
        """)

        # Insert default settings if they don't exist
        defaults = {
            # Publisher identity
            "publisher_name": "",
            "author_name": "",
            "copyright_holder": "",
            "website": "",
            "kdp_email": "",
            # Standard book defaults
            "default_trim_size": "8.5x11",
            "default_paper_type": "white_bw",
            "default_description_template": "",
            "default_keywords": [],
            "default_categories": [],
            # Author pen names
            "author_pen_names": [],
            # Upload / automation
            "comfyui_url": "http://127.0.0.1:8188",
            "auto_upload": False,
            "daily_upload_limit": 3,
            "uploads_today": 0,
            "last_upload_date": "",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value))
            )

        conn.commit()
    finally:
        conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOOKS CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _next_catalog_number(conn: sqlite3.Connection) -> str:
    """Generate the next catalog number (BB-001, BB-002, etc.)."""
    row = conn.execute(
        "SELECT catalog_number FROM books ORDER BY catalog_number DESC LIMIT 1"
    ).fetchone()

    if row is None:
        return f"{CATALOG_PREFIX}-001"

    # Extract number from last catalog number
    last_num = int(row["catalog_number"].split("-")[1])
    return f"{CATALOG_PREFIX}-{last_num + 1:03d}"


def create_book(title: str, data: dict) -> dict:
    """Create a new book entry."""
    conn = get_connection()
    try:
        book_id = str(uuid.uuid4())
        catalog_number = _next_catalog_number(conn)
        now = datetime.utcnow().isoformat()

        conn.execute(
            """INSERT INTO books (id, catalog_number, title, status, data, created_at, updated_at)
               VALUES (?, ?, ?, 'draft', ?, ?, ?)""",
            (book_id, catalog_number, title, json.dumps(data), now, now)
        )
        conn.commit()

        return get_book(book_id)
    finally:
        conn.close()


def get_book(book_id: str) -> Optional[dict]:
    """Get a single book by ID."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM books WHERE id = ?", (book_id,)
        ).fetchone()

        if row is None:
            return None

        return _row_to_book(row)
    finally:
        conn.close()


def get_book_by_catalog(catalog_number: str) -> Optional[dict]:
    """Get a single book by catalog number."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM books WHERE catalog_number = ?", (catalog_number,)
        ).fetchone()

        if row is None:
            return None

        return _row_to_book(row)
    finally:
        conn.close()


def list_books(
    status: Optional[str] = None,
    book_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> dict:
    """List books with optional filtering and pagination."""
    conn = get_connection()
    try:
        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if book_type:
            conditions.append("json_extract(data, '$.book_type') = ?")
            params.append(book_type)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Get total count
        total = conn.execute(
            f"SELECT COUNT(*) FROM books {where}", params
        ).fetchone()[0]

        # Get page of results
        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""SELECT * FROM books {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        ).fetchall()

        return {
            "books": [_row_to_book(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    finally:
        conn.close()


def update_book(book_id: str, updates: dict) -> Optional[dict]:
    """Update a book's fields. Handles both top-level and data (JSON) fields."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM books WHERE id = ?", (book_id,)
        ).fetchone()

        if existing is None:
            return None

        # Parse existing data
        data = json.loads(existing["data"])
        now = datetime.utcnow().isoformat()

        # Top-level fields
        title = updates.pop("title", None) or existing["title"]
        status = updates.pop("status", None) or existing["status"]

        # Merge remaining updates into data JSON
        for key, value in updates.items():
            if value is not None:
                data[key] = value

        conn.execute(
            """UPDATE books
               SET title = ?, status = ?, data = ?, updated_at = ?
               WHERE id = ?""",
            (title, status, json.dumps(data), now, book_id)
        )
        conn.commit()

        return get_book(book_id)
    finally:
        conn.close()


def delete_book(book_id: str) -> bool:
    """Delete a book by ID."""
    conn = get_connection()
    try:
        result = conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def _row_to_book(row: sqlite3.Row) -> dict:
    """Convert a database row to a book dict."""
    return {
        "id": row["id"],
        "catalog_number": row["catalog_number"],
        "title": row["title"],
        "status": row["status"],
        "data": json.loads(row["data"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NICHES CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_niche(keyword: str, data: dict) -> dict:
    """Create a new niche entry."""
    conn = get_connection()
    try:
        niche_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        conn.execute(
            """INSERT INTO niches (id, keyword, status, data, created_at)
               VALUES (?, ?, 'validated', ?, ?)""",
            (niche_id, keyword, json.dumps(data), now)
        )
        conn.commit()

        return get_niche(niche_id)
    finally:
        conn.close()


def get_niche(niche_id: str) -> Optional[dict]:
    """Get a single niche by ID."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM niches WHERE id = ?", (niche_id,)
        ).fetchone()

        if row is None:
            return None

        return _row_to_niche(row)
    finally:
        conn.close()


def list_niches(status: Optional[str] = None) -> dict:
    """List all niches, optionally filtered by status."""
    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM niches WHERE status = ? ORDER BY created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM niches ORDER BY created_at DESC"
            ).fetchall()

        niches = [_row_to_niche(r) for r in rows]
        return {
            "niches": niches,
            "total": len(niches),
        }
    finally:
        conn.close()


def update_niche(niche_id: str, updates: dict) -> Optional[dict]:
    """Update a niche entry."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM niches WHERE id = ?", (niche_id,)
        ).fetchone()

        if existing is None:
            return None

        data = json.loads(existing["data"])
        status = updates.pop("status", None) or existing["status"]
        keyword = updates.pop("keyword", None) or existing["keyword"]

        for key, value in updates.items():
            if value is not None:
                data[key] = value

        conn.execute(
            "UPDATE niches SET keyword = ?, status = ?, data = ? WHERE id = ?",
            (keyword, status, json.dumps(data), niche_id)
        )
        conn.commit()

        return get_niche(niche_id)
    finally:
        conn.close()


def delete_niche(niche_id: str) -> bool:
    """Delete a niche by ID."""
    conn = get_connection()
    try:
        result = conn.execute("DELETE FROM niches WHERE id = ?", (niche_id,))
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def _row_to_niche(row: sqlite3.Row) -> dict:
    """Convert a database row to a niche dict."""
    return {
        "id": row["id"],
        "keyword": row["keyword"],
        "status": row["status"],
        "data": json.loads(row["data"]),
        "created_at": row["created_at"],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SETTINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_setting(key: str, default=None):
    """Get a single setting value."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()

        if row is None:
            return default

        return json.loads(row["value"])
    finally:
        conn.close()


def set_setting(key: str, value):
    """Set a single setting value."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, json.dumps(value))
        )
        conn.commit()
    finally:
        conn.close()


def get_all_settings() -> dict:
    """Get all settings as a dictionary."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        result = {}
        for row in rows:
            v = row["value"]
            if isinstance(v, str):
                result[row["key"]] = json.loads(v)
            else:
                result[row["key"]] = v
        return result
    finally:
        conn.close()


def update_settings(updates: dict):
    """Update multiple settings at once."""
    conn = get_connection()
    try:
        for key, value in updates.items():
            if value is not None:
                conn.execute(
                    """INSERT INTO settings (key, value) VALUES (?, ?)
                       ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                    (key, json.dumps(value))
                )
        conn.commit()
    finally:
        conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DASHBOARD STATS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_dashboard_stats() -> dict:
    """Get summary statistics for the dashboard."""
    conn = get_connection()
    try:
        # Total books
        total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]

        # Books by status
        status_rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM books GROUP BY status"
        ).fetchall()
        by_status = {row["status"]: row["count"] for row in status_rows}

        # Total niches
        total_niches = conn.execute("SELECT COUNT(*) FROM niches").fetchone()[0]
        validated_niches = conn.execute(
            "SELECT COUNT(*) FROM niches WHERE status = 'validated'"
        ).fetchone()[0]

        # Recent books (last 10)
        recent_rows = conn.execute(
            "SELECT * FROM books ORDER BY created_at DESC LIMIT 10"
        ).fetchall()

        # Recent niches (last 5)
        recent_niche_rows = conn.execute(
            "SELECT * FROM niches ORDER BY created_at DESC LIMIT 5"
        ).fetchall()

        return {
            "total_books": total,
            "books_by_status": by_status,
            "books_live": by_status.get("live", 0),
            "books_in_progress": (
                by_status.get("draft", 0) +
                by_status.get("generating", 0) +
                by_status.get("quality_check", 0) +
                by_status.get("ready", 0)
            ),
            "total_niches": total_niches,
            "validated_niches": validated_niches,
            "estimated_monthly_revenue": 0.0,  # Calculated when we have BSR data
            "average_bsr": None,
            "recent_books": [_row_to_book(r) for r in recent_rows],
            "recent_niches": [_row_to_niche(r) for r in recent_niche_rows],
        }
    finally:
        conn.close()
