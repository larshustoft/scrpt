"""What a universe has learned about drawing itself.

Episode one took a hundred and forty-six pictures through six repair rounds
(2026-09-01/02). Every rejection was written to a log and forgotten, so the
same mistakes — a spare bell on the ground, a boulder in the spring, a
close-up drawn as a landscape — were made again on the next round, and would
have been made again on the next episode.

This is the memory. Each rejection is recorded against the universe. When a
kind of mistake keeps recurring, it becomes a standing rule in every future
drawing prompt for that universe, so the second episode starts where the
first one finished rather than where it began.

Lessons are learned per universe, not per film: Princess's forest and
Freddie's farm have different things that go wrong.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

# How a rejection reason is recognised, and what rule it teaches once it
# has recurred. Order matters: the first match wins.
PATTERNS = [
    ("extra_object",
     r"extra|second|spare|lying loose|duplicate|another copy",
     "Every object exists once. Never draw a spare or second copy of any "
     "prop lying on the ground or anywhere in the scene."),
    ("cave",
     r"\bcaves?\b|\bden\b|\btunnel\b|\bburrow\b|\bhollow\b|dark opening",
     "No caves, dens, tunnels or dark openings in rock or earth anywhere, "
     "unless the shot itself names one."),
    ("boulder",
     r"boulder|standing stone|large pale rounded|rounded stone",
     "No large rounded boulders or standing stones decorating the scene, "
     "unless the shot itself names one."),
    ("camera_distance",
     r"wrong distance|wide landscape|landscape (view|shot|composition)|"
     r"drawn as a wide|too far|full-body wide",
     "A close or detail shot fills the frame with its subject; the place is "
     "not visible behind it. Never widen a close shot into a landscape."),
    ("missing_character",
     r"missing|only one|only a single|not shown|is absent|should show both",
     "Every character named in the shot is visible, whole, in the picture."),
    ("extra_character",
     r"not (in|mentioned in) the (line|shot)|extra (unicorn|character|pony)|"
     r"additional character|who is not",
     "Nobody who is not named in the shot appears in it."),
    ("open_mouth",
     r"open mouth|speaking|mouth open",
     "All mouths closed. Nobody is drawn speaking, laughing or braying."),
    ("human",
     r"\bhuman\b|\bperson\b|\bgirl\b|\bboy\b",
     "There are no humans in this world. No person, hand or face."),
    ("text",
     r"\btext\b|lettering|\bwords?\b|caption",
     "No text, lettering or numbers anywhere in the picture."),
]

# a lesson becomes a standing rule once it has been taught this many times
THRESHOLD = 3


def _file(profile: dict) -> Path:
    return Path(profile.get("profile_path") or ".").parent / "lessons.json"


def classify(reason: str) -> str:
    r = str(reason or "")
    for key, pat, _ in PATTERNS:
        if re.search(pat, r, re.I):
            return key
    return "other"


def record(profile: dict, catalog: str, flagged: dict, round_n: int) -> dict:
    """Write this round's rejections into the universe's memory."""
    f = _file(profile)
    try:
        data = json.loads(f.read_text()) if f.exists() else {"entries": []}
    except Exception:
        data = {"entries": []}
    stamp = time.strftime("%Y-%m-%d")
    for shot, reasons in (flagged or {}).items():
        for reason in reasons:
            if str(reason).startswith("could not be checked"):
                continue                     # not a lesson, an outage
            data["entries"].append({
                "date": stamp, "episode": catalog, "shot": str(shot),
                "round": round_n, "kind": classify(reason),
                "reason": str(reason)[:200]})
    try:
        f.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    except Exception:
        pass
    return summary(profile)


def summary(profile: dict) -> dict:
    """How often each kind of mistake has been made in this universe."""
    f = _file(profile)
    try:
        entries = (json.loads(f.read_text()) if f.exists() else {}).get("entries") or []
    except Exception:
        entries = []
    counts: dict = {}
    for e in entries:
        counts[e.get("kind", "other")] = counts.get(e.get("kind", "other"), 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def standing_rules(profile: dict) -> list:
    """The rules this universe has earned — what goes into every prompt."""
    counts = summary(profile)
    rules = []
    for key, _pat, rule in PATTERNS:
        if counts.get(key, 0) >= THRESHOLD:
            rules.append(rule)
    return rules
