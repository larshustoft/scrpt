"""Dailies: somebody looks at every shot before it enters the cut.

In a real animation house this is a person whose whole job is noticing
that the creek has water in it when the story says it is dry, that a
character is in a shot she walked out of two scenes ago, or that two
shots open on the same picture. We do it with a vision model and a
similarity check, for a fraction of a cent per shot, BEFORE the cut is
assembled — which is the only time a finding is cheap.
"""
from __future__ import annotations

import asyncio
import os
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np

from ..config import OUTPUT_DIR
from .continuity import state_for


def _frame(video: Path, at: float, dest: Path, w: int = 512) -> bool:
    FF = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([FF, "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", f"scale={w}:-1", str(dest)],
                       capture_output=True)
    return dest.exists() and r.returncode == 0


def _gray(path: Path, size=(96, 54)) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(path).convert("L").resize(size), dtype=float)


def repetition_report(shots: list) -> list:
    """Two shots in a row that look the same. Cheap, and it catches the
    thing a checklist never does: the same valley twice."""
    out = []
    prev = None
    for n, img in shots:
        if img is None:
            prev = None
            continue
        g = _gray(img)
        if prev is not None:
            a, b = prev[1], g
            d = float(np.abs(a - b).mean())
            if d < 12.0:
                out.append({"shot": n, "kind": "repetition",
                            "note": f"opens almost identically to shot {prev[0]} "
                                    f"(difference {d:.1f} of 255)"})
        prev = (n, g)
    return out


async def review_shots(catalog: str, board: dict, handle=None,
                       limit: int = 0) -> dict:
    """Look at every filmed shot: does it match its own description and the
    state of the world at that moment?"""
    from ..writing.client import complete_vision, extract_json
    tdir = Path(OUTPUT_DIR) / catalog / "trailer"
    frames_dir = tdir / "dailies"
    frames_dir.mkdir(parents=True, exist_ok=True)
    panels = board.get("panels") or []
    if limit:
        panels = panels[:limit]

    stills = []
    for i, pn in enumerate(panels):
        n = str(pn.get("n") or i + 1)
        seg = tdir / f"sb-seg-{i}.mp4"
        dest = frames_dir / f"day-{n}.jpg"
        stills.append((n, dest if (dest.exists() or (seg.exists() and _frame(seg, 1.0, dest))) else None))

    notes = repetition_report(stills)

    async def one(n, pn, img):
        if img is None:
            return None
        state = state_for(board, pn.get("scene")) or "nothing special"
        present = ", ".join(pn.get("present") or []) or "unspecified"
        try:
            raw = await complete_vision(
                "You are the continuity supervisor on a children's animated film. "
                "You answer in JSON and you are strict.",
                f"This is one frame from shot {n}.\n"
                f"THE SHOT SHOULD SHOW: {pn.get('shot')}\n"
                f"CHARACTERS ALLOWED ON SCREEN: {present}\n"
                f"THE STATE OF THE WORLD RIGHT NOW: {state}\n\n"
                "Answer JSON only: {\"matches\": true/false, \"problems\": "
                "[\"...\"]}. Report ONLY these: a character on screen who is "
                "not allowed; the state of the world contradicted (for example "
                "water where the story says it is dry); a mouth open as if "
                "speaking; a character whose size is obviously wrong next to "
                "another; the picture showing a page of a book instead of the "
                "scene itself. Say nothing about style or beauty.",
                Path(img).read_bytes())
            d = extract_json(raw) or {}
            return [{"shot": n, "kind": "continuity", "note": p}
                    for p in (d.get("problems") or [])][:3]
        except Exception:
            return None

    gate = asyncio.Semaphore(int(os.environ.get('SCRPT_VISION_LANES', '6')))

    async def guarded(n, pn, img):
        async with gate:
            return await one(n, pn, img)

    done = 0
    for r in await asyncio.gather(*[guarded(n, pn, img)
                                    for (n, img), pn in zip(stills, panels)],
                                  return_exceptions=True):
        done += 1
        if isinstance(r, list):
            notes += r
        if handle and done % 15 == 0:
            handle.progress(0.95, "dailies", f"reviewed {done} shots")
    return {"notes": notes, "reviewed": len(stills)}
