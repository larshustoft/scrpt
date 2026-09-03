"""Location plates: the world drawn once, then reused all season.

A universe has a handful of places, and they do not change between
episodes. Drawing them fresh for every shot is how a forest path ends up
a different forest path in episode four — and it is the slowest step in
the line. So each place is drawn ONCE per universe, checked by eye, and
handed to every still set there as the base reference.

The gain is both kinds: the world stops drifting, and an episode stops
paying to invent scenery it already owns.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..config import OUTPUT_DIR, OPENAI_API_KEY


def plates_dir(universe_dir: Path) -> Path:
    d = universe_dir / "locations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def plate_for(profile: dict, universe_dir: Path, place_key: str):
    """The drawn plate for a place, if the universe has one."""
    places = (profile.get("creatives") or {}).get("locations") or {}
    rel = places.get(str(place_key or "").strip().lower())
    if not rel:
        return None
    f = universe_dir / rel
    return f if f.exists() else None


async def draw_location_plates(universe_dir: Path, profile: dict,
                               places: dict, style: str, handle=None,
                               refs: list = None, quality: str = "high") -> dict:
    """places = {"spring": "the description of the place, and its light"}
    refs = pictures shown to the model for every place (the approved valley
    plate keeps a whole atlas in one palette and one light — 2026-09-03)."""
    import httpx
    from ..cover.front_cover import _best_image_model
    from .plates import _draw, _draw_with_refs

    if not OPENAI_API_KEY:
        raise RuntimeError("OpenAI is not configured — the plates need it")
    out = plates_dir(universe_dir)
    made = {}
    todo = [(k, v) for k, v in places.items()
            if not (out / f"{k}.png").exists()]
    for k in places:
        if (out / f"{k}.png").exists():
            made[k] = f"locations/{k}.png"
    if todo:
        gate = asyncio.Semaphore(6)

        async def one(client, model, key, desc):
            async with gate:
                prompt = (f"{desc} {style} A place in a children's animated "
                          "film, with NO characters in it at all — no unicorns, "
                          "no bird, no dragon, nobody. No text or lettering "
                          "anywhere. The time of day and the light are exactly "
                          "as described.")
                if refs:
                    got = await _draw_with_refs(client, model, prompt + " Same painting style, palette and light as the reference pictures.",
                                                list(refs), out / f"{key}.png", size="1536x1024", quality=quality)
                else:
                    got = await _draw(client, model, prompt, out / f"{key}.png",
                                      size="1536x1024")
                if handle:
                    handle.progress(0.5, "locations", f"drew {key}")
                return (key, f"locations/{key}.png") if got else None

        async with httpx.AsyncClient(timeout=260) as client:
            model = await _best_image_model(client)
            failed = []
            for (k, _v), r in zip(todo, await asyncio.gather(
                    *[one(client, model, k, v) for k, v in todo],
                    return_exceptions=True)):
                if isinstance(r, tuple):
                    made[r[0]] = r[1]
                else:
                    failed.append(f"{k}: {r if isinstance(r, BaseException) else 'no picture'}")
            # A PLACE THAT DID NOT GET DRAWN MUST SAY SO. Dropping it here
            # left the universe short a plate, and every shot set there was
            # invented again from a sentence (2026-09-01).
            if failed:
                raise RuntimeError("these places could not be drawn: "
                                   + "; ".join(str(f)[:120] for f in failed))

    prof_path = universe_dir / "profile.json"
    prof = json.loads(prof_path.read_text())
    # MERGE, NEVER REPLACE (2026-09-02). A repair that redrew ONE plate
    # wrote back a registry of one, and the other nine places silently
    # became unregistered — every shot set in them would have been drawn
    # from a sentence again. What is drawn is added to what is known.
    reg = dict(prof.setdefault("creatives", {}).get("locations") or {})
    reg.update(made)
    prof["creatives"]["locations"] = reg
    prof_path.write_text(json.dumps(prof, indent=2, ensure_ascii=False))
    return made
