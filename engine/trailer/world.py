"""The world links, applied fresh every time anything is drawn.

place, props and `continues` are what make a hundred and forty-six pictures
one film. They were wiped twice by stale saves, and the drawings that
followed had no plates behind them at all — which is invisible until you
look at a picture and it makes no sense (Lars, 2026-09-01, on shot 10).

So they are no longer something that is set once and hoped for. This runs
before every drawing pass and rebuilds them from the story itself.
"""
from __future__ import annotations

import re

# scene -> the place it happens in
PLACES = {
    1: "forest-path-morning", 2: "forest-path-morning",
    3: "moonwater-spring",
    4: "forest-path-dust", 5: "forest-path-dust",
    6: "forest-path-quiet", 7: "forest-path-quiet",
    8: "rope-bridge",
    9: "spring-dry", 10: "spring-outlet",
    11: "inside-the-cave",
    12: "spring-restored",
    13: "path-home-dusk",
}

# the objects the story keeps returning to, and the words that name them
PROPS = {
    "white-stone": ["white stone", "round stone", "the stone", "boulder"],
    "fallen-branch": ["branch"],
    "glitter-bell": ["silver bell", "her bell", "mama\'s bell", "bell"],
}


# Some shots do not happen where their scene happens. The stone rolls into
# the spring outlet while the story is on the path home, and the story
# returns to that same hole twice more — it is ONE place, drawn once
# (Lars, 2026-09-01: "is it the same hole?").
SHOT_PLACES = {
    "21": "spring-outlet", "21b": "spring-outlet", "21b-2": "spring-outlet",
    "56b": "spring-outlet", "57": "spring-outlet", "57b": "spring-outlet",
    "58": "spring-outlet", "58b": "spring-outlet", "59": "spring-outlet",
}


def apply_world(board: dict) -> dict:
    """Give every shot its place, its objects, and its place's master shot.

    THE MAP BELONGS TO THE EPISODE, NOT TO THIS FILE (2026-09-01). These
    constants are episode one of Princess. Every later episode — and every
    other universe — carries its own map on the board as `board["world"]`,
    and only falls back to the constants when it has none. Without this,
    episode two would silently be shot in episode one's places, which is
    the same class of mistake as a film shot from last week's pictures.
    """
    w = board.get("world") or {}
    places_map = {int(k): v for k, v in (w.get("places") or {}).items()} or PLACES
    shot_places = w.get("shot_places") or ({} if w.get("places") else SHOT_PLACES)
    props_map = w.get("props") or ({} if w.get("places") else PROPS)
    # SHOT-LEVEL PROPS (2026-09-02). Some objects are in a shot without being
    # named in its words — the stone wedged in the opening while the line
    # only says "the dark crack". The board says so per shot; those are
    # added to, never replaced by, what the words name.
    shot_props = w.get("shot_props") or {}
    panels = board.get("panels") or []
    masters = {}
    counts = {"place": 0, "props": 0, "continues": 0}
    for pn in panels:
        place = shot_places.get(str(pn.get("n"))) or places_map.get(pn.get("scene"))
        if place:
            pn["place"] = place
            counts["place"] += 1
            if place not in masters:
                masters[place] = str(pn.get("n"))
                pn["continues"] = pn.get("continues") or ""
            elif not pn.get("continues"):
                pn["continues"] = masters[place]
                counts["continues"] += 1
        text = (pn.get("shot") or "").lower()
        found = [k for k, words in props_map.items()
                 if any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)]
        for extra in (shot_props.get(str(pn.get("n"))) or []):
            if extra not in found:
                found.append(extra)
        # PROPS COME FROM THE MAP AND NOTHING ELSE (2026-09-02). Leaving an
        # old list in place when the map names nothing kept the stone's plate
        # attached to eight shots on the forest path long after the map had
        # been corrected. Empty means empty.
        pn["props"] = found[:3]
        if found:
            counts["props"] += 1
    return counts
