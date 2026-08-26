"""How many titles KDP will still let us create this week.

Amazon caps title CREATION, not publishing:

    "we limit the number of titles you can create at the same time to
     10 per book format each week"

Two consequences worth holding onto, because both have already cost us:

  · A draft that was created and abandoned still spends a slot. A failed
    stage that got far enough for KDP to mint a title id has burned one,
    whatever we do next.
  · Editing a title we already created is free. Re-staging a draft, fixing
    its keywords, uploading a new interior — none of it counts.

So the number to watch is not "books uploaded" but "title ids minted in the
last seven days", per format. That is what this records, and it is a rolling
window rather than a calendar week: Amazon's wording is "each week", and the
safe reading of an unclear rule is the stricter one.
"""

from __future__ import annotations

import datetime as dt
import json

from ..database import get_setting, set_setting

KEY = "kdp_title_creations"
WEEKLY_LIMIT = 10          # per format, per Amazon's help page
FORMATS = ("paperback", "kindle")


def _load() -> list[dict]:
    raw = get_setting(KEY, "[]")
    try:
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        rows = []
    return [r for r in rows if isinstance(r, dict) and r.get("at")]


def _within_week(rows: list[dict]) -> list[dict]:
    cutoff = dt.datetime.now() - dt.timedelta(days=7)
    out = []
    for r in rows:
        try:
            if dt.datetime.fromisoformat(r["at"]) >= cutoff:
                out.append(r)
        except Exception:
            continue
    return out


def record_creation(catalog: str, fmt: str, title_id: str = "") -> dict:
    """Called the moment KDP hands back a title id we did not have before."""
    fmt = "kindle" if "kindle" in (fmt or "").lower() else "paperback"
    rows = _load()
    # the same title id twice is a re-stage, not a new creation
    if title_id and any(r.get("title_id") == title_id for r in rows):
        return usage()
    rows.append({"at": dt.datetime.now().isoformat(timespec="seconds"),
                 "catalog": catalog, "format": fmt, "title_id": title_id})
    set_setting(KEY, json.dumps(rows[-400:]))
    return usage()


def usage() -> dict:
    """What the week looks like right now, per format."""
    recent = _within_week(_load())
    out = {}
    for fmt in FORMATS:
        used = [r for r in recent if r.get("format") == fmt]
        oldest = min((r["at"] for r in used), default=None)
        free_at = None
        if oldest and len(used) >= WEEKLY_LIMIT:
            # a slot frees exactly seven days after the oldest creation
            free_at = (dt.datetime.fromisoformat(oldest)
                       + dt.timedelta(days=7)).isoformat(timespec="minutes")
        out[fmt] = {"used": len(used), "limit": WEEKLY_LIMIT,
                    "remaining": max(0, WEEKLY_LIMIT - len(used)),
                    "titles": [{"catalog": r.get("catalog"), "at": r.get("at")} for r in used],
                    "next_slot_at": free_at}
    return out


def can_create(fmt: str) -> tuple[bool, str]:
    """Ask before minting a NEW title. Re-staging an existing one is free."""
    fmt = "kindle" if "kindle" in (fmt or "").lower() else "paperback"
    u = usage()[fmt]
    if u["remaining"] > 0:
        return True, f"{u['remaining']} of {WEEKLY_LIMIT} {fmt} creations left this week"
    return False, (f"KDP's weekly limit of {WEEKLY_LIMIT} new {fmt} titles is used up. "
                   f"A slot frees at {u['next_slot_at']}. Existing drafts can still be "
                   f"edited and published — only NEW titles are blocked.")
