"""Props get plates, exactly like characters do.

A thing the story keeps returning to — the stone that blocks the water, the
branch that traps the fireflies, the silver bell, the rope bridge — is drawn
ONCE as its own reference plate, and every shot that contains it is drawn
with that plate in front of the model. Pointing one shot at another shot is
not enough: each redraw drifts a little, and after a hundred and forty shots
"the rock" is a hundred and forty different rocks (Lars, 2026-09-01:
"consistency is important for objects, universes, scenes and characters").

A prop plate belongs to the UNIVERSE when the object recurs across episodes
(the bell, the bridge) and to the EPISODE when it belongs to one story (the
stone, the branch).
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from ..credits import OutOfCredits
from ..config import OUTPUT_DIR, OPENAI_API_KEY


def plate_path(catalog: str, key: str) -> Path:
    return Path(OUTPUT_DIR) / catalog / "trailer" / "props" / f"{key}.png"


def props_for(shot_text: str, props: dict) -> list:
    """Which props this shot contains, by the words it uses."""
    t = (shot_text or "").lower()
    out = []
    for key, spec in (props or {}).items():
        for w in (spec.get("words") or [key]):
            if re.search(rf"\b{re.escape(str(w).lower())}\b", t):
                out.append(key); break
    return out


async def draw_prop_plates(catalog: str, props: dict, style: str, handle=None) -> dict:
    """One plate per prop: the object alone, plainly lit, from a clear angle."""
    import httpx
    from ..cover.front_cover import _best_image_model
    from .plates import _draw

    if not OPENAI_API_KEY:
        raise RuntimeError("OpenAI is not configured — the prop plates need it")
    out = plate_path(catalog, "x").parent
    out.mkdir(parents=True, exist_ok=True)
    made, todo = {}, []
    for key, spec in (props or {}).items():
        f = plate_path(catalog, key)
        if f.exists():
            made[key] = f"props/{key}.png"
        else:
            todo.append((key, spec, f))
    if todo:
        gate = asyncio.Semaphore(4)

        async def one(client, model, key, spec, dest):
            async with gate:
                prompt = (f"{spec.get('look')} {style} The object completely alone on a plain "
                          "soft pale-grey background, in even daylight, seen from a clear "
                          "three-quarter angle, whole and unobstructed. No characters, no "
                          "scenery, no text.")
                got = await _draw(client, model, prompt, dest, size="1024x1024")
                if handle:
                    handle.progress(0.4, "props", f"drew {key}")
                return (key, f"props/{key}.png") if got else None

        async with httpx.AsyncClient(timeout=260) as client:
            model = await _best_image_model(client)
            failed = []
            for (k, _s, _f), r in zip(todo, await asyncio.gather(
                    *[one(client, model, k, s, f) for k, s, f in todo],
                    return_exceptions=True)):
                # THE STOP SIGNAL SURVIVES A GATHER; A MISSING PROP IS NAMED
                # (2026-09-02). An empty image account came back here as
                # "object plates: 3 of 4", which reads as a job done.
                if isinstance(r, OutOfCredits):
                    raise r
                if isinstance(r, tuple):
                    made[r[0]] = r[1]
                else:
                    failed.append(f"{k}: {r if isinstance(r, BaseException) else 'no picture'}")
            if failed:
                raise RuntimeError("these object plates could not be drawn — every shot "
                                   "that shows them would invent its own: "
                                   + "; ".join(str(x)[:120] for x in failed))
    return made
