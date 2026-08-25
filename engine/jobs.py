"""
SCRPT Job Queue
================
Minimal async job system for long-running work (book drafting, TTS, exports).

Jobs run as asyncio tasks inside the FastAPI event loop; state persists to
SQLite so the frontend can poll progress and survive engine restarts (jobs
that were 'running' at startup are marked 'interrupted').
"""

import asyncio
import json
import traceback
import uuid
from datetime import datetime
from typing import Awaitable, Callable, Optional

from .database import get_connection

_running_tasks: dict[str, asyncio.Task] = {}

# The production line writes at most 4 books at once; further commissions
# queue and start automatically when a slot frees. Other job kinds
# (covers, audio, exports) are quick and unlimited.
MAX_PARALLEL_BOOKS = 4
_semaphores: dict[str, asyncio.Semaphore] = {}


def _kind_semaphore(kind: str) -> Optional[asyncio.Semaphore]:
    if kind != "full_draft":
        return None
    if kind not in _semaphores:
        _semaphores[kind] = asyncio.Semaphore(MAX_PARALLEL_BOOKS)
    return _semaphores[kind]


def init_jobs_table():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                book_catalog TEXT,
                status TEXT DEFAULT 'queued',   -- queued|running|done|error|cancelled|interrupted
                progress REAL DEFAULT 0.0,      -- 0..1
                stage TEXT DEFAULT '',
                detail TEXT DEFAULT '',
                result JSON,
                error TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_book ON jobs(book_catalog);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        """)
        # Anything left 'running' from a previous process is dead.
        conn.execute(
            "UPDATE jobs SET status='interrupted', updated_at=datetime('now') "
            "WHERE status IN ('queued','running')"
        )
        conn.commit()
    finally:
        conn.close()


def _update(job_id: str, **fields):
    conn = get_connection()
    try:
        sets = ", ".join(f"{k} = ?" for k in fields)
        vals = [json.dumps(v) if k == "result" else v for k, v in fields.items()]
        conn.execute(
            f"UPDATE jobs SET {sets}, updated_at = datetime('now') WHERE id = ?",
            vals + [job_id],
        )
        conn.commit()
    finally:
        conn.close()


class JobHandle:
    """Passed into job coroutines for progress reporting and cancellation checks."""

    def __init__(self, job_id: str):
        self.id = job_id

    def progress(self, fraction: float, stage: str = "", detail: str = ""):
        fields = {"progress": max(0.0, min(1.0, fraction))}
        if stage:
            fields["stage"] = stage
        if detail:
            fields["detail"] = detail[:500]
        _update(self.id, **fields)

    def cancelled(self) -> bool:
        job = get_job(self.id)
        return bool(job and job["status"] == "cancelled")


def start_job(
    kind: str,
    coro_factory: Callable[[JobHandle], Awaitable[dict]],
    book_catalog: Optional[str] = None,
) -> str:
    """Create a job row and schedule the coroutine on the event loop."""
    job_id = str(uuid.uuid4())[:8]
    sem = _kind_semaphore(kind)
    initial_status = "queued" if sem and sem.locked() else "running"
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO jobs (id, kind, book_catalog, status) VALUES (?, ?, ?, ?)",
            (job_id, kind, book_catalog, initial_status),
        )
        conn.commit()
    finally:
        conn.close()

    handle = JobHandle(job_id)

    async def runner():

        from .writing.ledger import current_catalog as _cc, current_job as _cj

        _cc.set(book_catalog); _cj.set(job_id)
        try:
            if sem:
                if sem.locked():
                    _update(job_id, status="queued",
                            detail=f"Waiting for a free slot (max {MAX_PARALLEL_BOOKS} books at once)")
                async with sem:
                    if handle.cancelled():
                        return
                    _update(job_id, status="running", detail="")
                    result = await coro_factory(handle)
            else:
                result = await coro_factory(handle)
            if handle.cancelled():
                return
            _update(job_id, status="done", progress=1.0, result=result or {})
        except asyncio.CancelledError:
            _update(job_id, status="cancelled")
        except Exception as e:
            _update(job_id, status="error", error=f"{e}\n{traceback.format_exc()[-1500:]}")
        finally:
            _running_tasks.pop(job_id, None)

    _running_tasks[job_id] = asyncio.get_event_loop().create_task(runner())
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get("result"):
            try:
                d["result"] = json.loads(d["result"])
            except (TypeError, ValueError):
                pass
        return d
    finally:
        conn.close()


def _reap_dead(conn) -> None:
    """A job whose task is gone but whose row still says 'running' will sit at
    its last percentage for ever, and looks exactly like slow work. Nothing
    detected that, so a dead job simply hung the UI until someone noticed.
    Sweep them on every read: no live task, and no progress for two minutes,
    means it died."""
    rows = conn.execute(
        "SELECT id, updated_at FROM jobs WHERE status IN ('queued','running')"
    ).fetchall()
    for r in rows:
        jid = r["id"]
        task = _running_tasks.get(jid)
        if task is not None and not task.done():
            continue                      # genuinely working
        stale = conn.execute(
            "SELECT (julianday('now') - julianday(updated_at)) * 86400 AS age "
            "FROM jobs WHERE id = ?", (jid,)).fetchone()
        if stale and (stale["age"] or 0) > 120:
            conn.execute(
                "UPDATE jobs SET status='error', "
                "error='The job stopped without finishing (no progress for two "
                "minutes and no live task). Start it again.', "
                "updated_at=datetime('now') WHERE id = ?", (jid,))
    conn.commit()


def list_jobs(book_catalog: Optional[str] = None, active_only: bool = False) -> list[dict]:
    conn = get_connection()
    try:
        _reap_dead(conn)
        conditions, params = [], []
        if book_catalog:
            conditions.append("book_catalog = ?")
            params.append(book_catalog)
        if active_only:
            conditions.append("status IN ('queued','running')")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(
            f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT 50", params
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def cancel_job(job_id: str) -> bool:
    task = _running_tasks.get(job_id)
    _update(job_id, status="cancelled")
    if task and not task.done():
        task.cancel()
        return True
    return False
