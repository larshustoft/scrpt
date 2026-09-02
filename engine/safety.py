"""Is the work safe? Asked out loud, before a long run starts.

On 2026-09-02 a night's compute was lost, and it turned out the hourly
push to GitHub had failed 189 times in a row and the nightly backup had
failed for two days. Both wrote their failures to log files nobody reads.
Two days of work existed in exactly one folder, on one disk, behind a
permission macOS had quietly revoked.

The lesson is the same one the film line already learned: a check that
nobody calls protects nothing. So the question "is this work backed up?"
is now asked at the start of every long run, out loud, in the same place
the run reports everything else.

This never blocks. Losing an hour to a warning would be its own failure —
it tells the truth and lets the work proceed.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path


def _sh(args, cwd=None, timeout=20):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def push_status(repo: Path) -> dict:
    """Is every committed change also on GitHub?"""
    head = _sh(["git", "rev-parse", "HEAD"], cwd=repo)
    remote = _sh(["git", "rev-parse", "@{u}"], cwd=repo)
    dirty = _sh(["git", "status", "--porcelain"], cwd=repo)
    unpushed = _sh(["git", "log", "@{u}..HEAD", "--oneline"], cwd=repo)
    return {"head": head[:8], "in_sync": bool(head) and head == remote,
            "uncommitted": len([l for l in dirty.splitlines() if l.strip()]),
            "unpushed": len([l for l in unpushed.splitlines() if l.strip()])}


def backup_status(dest: str = "/Volumes/Disc 5/SCRPT-BACKUP") -> dict:
    """When did the catalogue last reach the backup disk?"""
    d = Path(dest)
    if not d.parent.exists():
        return {"disk_connected": False, "age_days": None}
    # the snapshots live in db/, and looking in the wrong place would make
    # a working backup report as no backup at all — a false alarm teaches
    # people to ignore the alarm
    snaps = sorted(d.glob("db/scrpt-*.db.gz"), key=lambda f: f.stat().st_mtime) \
        if d.exists() else []
    if not snaps:
        return {"disk_connected": True, "age_days": None}
    age = (time.time() - snaps[-1].stat().st_mtime) / 86400
    return {"disk_connected": True, "age_days": round(age, 1),
            "latest": snaps[-1].name}


def report(repo: Path, log=print) -> list:
    """Say plainly whether this work would survive losing the machine."""
    warnings = []
    p = push_status(repo)
    if not p["in_sync"] or p["uncommitted"] or p["unpushed"]:
        warnings.append(
            f"NOT ON GITHUB: {p['uncommitted']} uncommitted file(s), "
            f"{p['unpushed']} unpushed commit(s). This work exists only on "
            f"this disk.")
    b = backup_status()
    if not b["disk_connected"]:
        warnings.append("BACKUP DISK NOT CONNECTED — the catalogue has "
                        "nowhere to be copied to.")
    elif b["age_days"] is None:
        warnings.append("NO BACKUP HAS EVER COMPLETED to the backup disk.")
    elif b["age_days"] > 1.5:
        warnings.append(f"BACKUP IS {b['age_days']} DAYS OLD — the nightly "
                        f"backup is not running.")
    for w in warnings:
        log(f"⚠ {w}")
    if not warnings:
        log(f"work is safe: pushed to GitHub ({p['head']}), "
            f"backup {b.get('age_days')} days old")
    return warnings
