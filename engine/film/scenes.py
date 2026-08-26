"""Shooting a screenplay scene.

Same contract as the trailers — the camera receives the cast's photo plates,
a faceless frame per shot, and words; never the cover — but none of the
trailer's furniture: no narrator, no series card, no end card, no sixty-second
limit. A scene is as long as its shots, its sound is the world plus dialogue,
and the score arrives later, at assembly, laid across whole sequences.

Each scene renders to its own file and is versioned, so the editing room can
re-shoot scene 23 without touching scene 22.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from ..config import OUTPUT_DIR
from ..database import get_book_by_catalog, update_book
from ..trailer import runway
from ..trailer.bible import cast_of, world_of, apply_cast
from ..trailer.plates import draw_cast_plates, with_short_names, slug
from ..trailer.producer import (_cut_segment, _mix_narration, _probe_seconds,
                                _record_line, _record_sfx, _run, _h)
from .screenplay import _film, _save_film

# Dialogue casting: every named character speaks with one voice for the whole
# film. Chosen once from the house roster by apparent gender/age in the look
# line, then pinned on the bible so it never drifts between scenes.
HOUSE_VOICES = {
    "male": "nPczCjzI2devNBz1zQrb",      # Brian
    "female": "cgSgspJ2msm6clMCkdW9",    # Jessica
    "female_warm": "pFZP5JQG7iQjIQuC4Bku",  # Lily
}


def _voice_for(book: dict, name: str) -> str:
    bibles = book["data"].get("bibles") or {}
    for kind in ("main", "supporting"):
        for c in ((bibles.get(kind) or {}).get("characters") or []):
            if (c.get("name") or "").strip().lower() == name.strip().lower():
                if c.get("voice_id"):
                    return c["voice_id"]
                look = (c.get("look") or "").lower()
                fem = any(w in look for w in (" woman", " her ", "she ", "braid", "bob,"))
                return HOUSE_VOICES["female" if fem else "male"]
    return HOUSE_VOICES["male"]


async def _draw_shot_frame(catalog: str, scene_n: int, shot: dict, style: str,
                           cast: dict) -> Optional[Path]:
    """A faceless staging frame for one shot — same rule as trailer boards."""
    import base64
    import httpx
    from ..config import OPENAI_API_KEY
    from ..cover.front_cover import _best_image_model
    out = Path(OUTPUT_DIR) / catalog / "film" / f"scene-{scene_n:02d}"
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"frame-{shot['k']:02d}.png"
    if dest.exists():
        return dest
    who = "".join(f"\n{n}: {cast[n]}" for n in (shot.get("characters") or []) if cast.get(n))
    prompt = (
        f"A storyboard frame. THE SHOT: {shot.get('framing','')}: {shot.get('action','')}\n"
        + (f"\nWHO IS IN IT — stage by build, wardrobe and position, every face "
           f"UNREADABLE (turned, shadowed, or distant): {who}\n" if who else "")
        + f"\nWORLD AND PALETTE: {style}\n\n"
        "Cinematic film still, 16:9. No readable faces. No text, no borders."
    )
    async with httpx.AsyncClient(timeout=260) as c:
        model = await _best_image_model(c)
        for _ in range(2):
            try:
                r = await asyncio.wait_for(c.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json={"model": model, "prompt": prompt[:3800],
                          "size": "1536x1024", "quality": "high", "n": 1}),
                    timeout=240)
            except Exception:
                continue
            if r.status_code == 200:
                dest.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"]))
                return dest
            if r.status_code < 500:
                return None
    return None


async def produce_scene(catalog: str, scene_n: int, handle=None) -> dict:
    """Shoot one scene of the film, shot by shot, and mix its sound."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    film = _film(book)
    scene = (film.get("scenes") or {}).get(str(scene_n))
    if not scene or not scene.get("shots"):
        raise RuntimeError(f"Scene {scene_n} has no screenplay yet — write it first")
    shots = scene["shots"]
    genre = book["data"].get("genre_preset") or ""
    cast = cast_of(book)
    style = (world_of(book) or {}).get("style", "")

    sdir = Path(OUTPUT_DIR) / catalog / "film" / f"scene-{scene_n:02d}"
    sdir.mkdir(parents=True, exist_ok=True)

    # the cast plates (locked photos), with short-name aliases — as trailers
    plates = with_short_names((await draw_cast_plates(catalog, handle)).get("plates") or {})
    char_uris = {}
    for name, rel in plates.items():
        p = Path(OUTPUT_DIR) / catalog / "trailer" / rel
        if p.exists() and name not in char_uris:
            try:
                char_uris[name] = await runway.upload_file(p)
            except Exception:
                pass

    credits_before = await runway.credit_balance()

    # frames first (cheap, parallel), then the shoot
    if handle:
        handle.progress(0.10, "board", f"framing scene {scene_n}")
    frames = await asyncio.gather(
        *[_draw_shot_frame(catalog, scene_n, sh, style, cast) for sh in shots],
        return_exceptions=True)

    gate = asyncio.Semaphore(4)
    done = [0]

    async def shoot(idx: int, sh: dict):
        clip = sdir / f"shot-{sh['k']:02d}.mp4"
        if clip.exists() and clip.stat().st_size > 200_000:
            return clip
        refs, who = [], ""
        for name in (sh.get("characters") or []):
            if char_uris.get(name):
                refs.append(char_uris[name])
                who += (f" {name} is the person in reference image {len(refs)} — "
                        f"exactly the same face, hair and build, in this scene.")
        fr = frames[idx]
        if isinstance(fr, Path) and fr.exists():
            try:
                refs.append(await runway.upload_file(fr))
                who += (f" Reference image {len(refs)} is the storyboard frame: match "
                        f"its composition and light; faces come from the earlier images.")
            except Exception:
                pass
        action = apply_cast(f"{sh.get('framing','')}: {sh.get('action','')}", cast)
        snd = (sh.get("sound") or "").strip()
        prompt = (f"{action} {style} No text or lettering on screen."
                  + (f" Sound: {snd}. No music, no speech." if snd else "") + who)
        secs = max(4, min(12, int(sh.get("seconds") or 6)))
        async with gate:
            if handle:
                handle.progress(0.2 + 0.5 * idx / max(1, len(shots)), "shooting",
                                f"scene {scene_n} shot {sh['k']}")
            moderation = 0
            live = list(refs)
            # free, random rejections: hold the photo refs — patience, not paintings
            for attempt in range(16):
                task = await runway.generate_seedance(prompt, live, seconds=secs,
                                                      ratio="1280:720",
                                                      model="seedance2_5", audio=False)
                result = await runway.wait_for(task["id"], timeout_s=1500)
                url = (result.get("output") or [None])[0] if result.get("status") == "SUCCEEDED" else None
                if url:
                    await runway.download(url, clip)
                    done[0] += 1
                    return clip
                fail = json.dumps(result.get("failure") or result.get("failureCode") or "")
                if "moderation" in fail.lower() or "third_party" in fail.lower():
                    moderation += 1
                if moderation >= 12 and live:
                    live = []
                    sh["refs_dropped"] = True
                await asyncio.sleep(8 * (attempt + 1))
            raise RuntimeError(f"scene {scene_n} shot {sh['k']} could not be filmed")

    clips = await asyncio.gather(*[shoot(i, sh) for i, sh in enumerate(shots)])

    # cut and join at each shot's screenplay length
    segs, t, cues, sfx = [], 0.0, [], []
    W = H = None
    from ..trailer.producer import _probe_size
    for i, (sh, clip) in enumerate(zip(shots, clips)):
        if W is None:
            W, H = _probe_size(clip)
        need = float(sh.get("seconds") or 6)
        seg = sdir / f"seg-{sh['k']:02d}.mp4"
        _cut_segment(clip, 0.0, need, seg, W, H)
        segs.append(seg)
        ln = sh.get("line")
        if ln and (ln.get("text") or "").strip():
            voice = _voice_for(book, ln.get("speaker") or "")
            lf = await _record_line(catalog, ln["text"], genre,
                                    f"film-{scene_n}-{sh['k']}-{_h(ln['text'])}",
                                    f"film-line-{scene_n:02d}-{sh['k']:02d}.mp3",
                                    speed=1.0, voice_override=voice)
            if lf:
                cues.append((lf, t + 0.5, 1.25))
        snd = (sh.get("sound") or "").strip()
        if snd:
            cue = await _record_sfx(catalog, snd, min(4.0, need),
                                    f"film-sfx-{_h(snd)}", f"film-sfx-{_h(snd)}.mp3")
            if cue:
                sfx.append((cue, t + 0.1, 0.8))
        t += need

    lst = sdir / "list.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segs))
    picture = sdir / "picture.mp4"
    _run(["-y", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c", "copy", str(picture)], "scene concat")

    out = sdir / "scene.mp4"
    if handle:
        handle.progress(0.9, "sound", "mixing the scene")
    if not _mix_narration(picture, cues, out, score=None, sfx=sfx):
        import shutil
        shutil.copy2(picture, out)

    credits_after = await runway.credit_balance()
    record = {"n": scene_n, "file": f"film/scene-{scene_n:02d}/scene.mp4",
              "seconds": round(_probe_seconds(out) or t, 1), "shots": len(shots),
              "credits_used": max(0, credits_before - credits_after),
              "refs_dropped": [sh["k"] for sh in shots if sh.get("refs_dropped")]}
    film = _film(get_book_by_catalog(catalog))
    film.setdefault("scenes", {}).setdefault(str(scene_n), {}).update(
        {"shots": shots, "produced": record})
    _save_film(catalog, film)
    return record
