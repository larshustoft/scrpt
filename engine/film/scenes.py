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
                           cast: dict, plates: dict = None) -> Optional[Path]:
    """A staging frame that shows EXACTLY what the finished shot should look
    like. Lars's law (2026-08-27): no faceless boards — the cast's TRUE faces,
    composited from their locked photo plates via reference edit, facing the
    camera whenever the shot has a line. The frame is the shot's target, not a
    blocking diagram; a faceless frame lets the camera invent a new person.

    If a frame already exists on disk it is reused as the STAGING reference
    (approved geography and light) while the faces are recast from the plates.
    """
    import base64
    import httpx
    from ..config import OPENAI_API_KEY
    from ..cover.front_cover import _best_image_model
    out = Path(OUTPUT_DIR) / catalog / "film" / f"scene-{scene_n:02d}"
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"frame-{shot['k']:02d}.png"
    if dest.exists() and not shot.get("reframe"):
        return dest

    # the locked plates of everyone in the shot ride along as image refs
    files, ref_note, n_ref = [], "", 0
    for name in (shot.get("characters") or []):
        rel = (plates or {}).get(name)
        p = Path(OUTPUT_DIR) / catalog / "trailer" / rel if rel else None
        if p and p.exists():
            views = [p] + sorted(p.parent.glob(f"{p.stem}-angle-*.png"))[:3]
            a = n_ref + 1
            for v in views:
                n_ref += 1
                files.append(("image[]", (f"plate-{n_ref}.png", v.read_bytes(), "image/png")))
            span = (f"image {a}" if a == n_ref
                    else f"images {a} through {n_ref} (the same person, different angles)")
            ref_note += (f"\n{name} IS the person in reference {span} — "
                         f"reproduce that EXACT face, hair, age and build, "
                         f"photorealistically, unmistakably the same human.")
    staging = dest if dest.exists() else None
    if staging:
        files.append(("image[]", ("staging.png", staging.read_bytes(), "image/png")))
        ref_note += ("\nThe LAST reference image is the approved staging: keep its "
                     "location, architecture, camera angle and light, but restage "
                     "the people as directed.")

    speaks = bool(((shot.get("line") or {}).get("text") or "").strip())
    who = "".join(f"\n{n}: {cast[n]}" for n in (shot.get("characters") or []) if cast.get(n))
    prompt = (
        f"A cinematic film still — the target frame for a shot. "
        f"THE SHOT: {shot.get('framing','')}: {shot.get('action','')}\n"
        + (f"\nWHO IS IN IT: {who}\n{ref_note}\n" if who else "")
        + ("\nThe speaking character faces the camera directly, eyes to the lens, "
           "mid-sentence, warm and natural — never turned away, never from behind.\n"
           if speaks and n_ref else "")
        + f"\nWORLD AND PALETTE: {style}\n\n"
        "Photorealistic, 16:9. No text, no borders, no captions."
    )
    tmp = out / f"frame-{shot['k']:02d}.new.png"
    async with httpx.AsyncClient(timeout=320) as c:
        model = await _best_image_model(c)
        for _ in range(2):
            try:
                if files:
                    r = await c.post(
                        "https://api.openai.com/v1/images/edits",
                        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                        files=files,
                        data={"model": model, "prompt": prompt[:3800],
                              "size": "1536x1024", "quality": "high", "n": "1"})
                else:
                    r = await c.post(
                        "https://api.openai.com/v1/images/generations",
                        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                        json={"model": model, "prompt": prompt[:3800],
                              "size": "1536x1024", "quality": "high", "n": 1})
            except Exception:
                continue
            if r.status_code == 200:
                tmp.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"]))
                tmp.replace(dest)
                shot.pop("reframe", None)
                return dest
            if r.status_code < 500:
                return dest if dest.exists() else None
    return dest if dest.exists() else None


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

    # the cast plates (locked photos), with short-name aliases — as trailers.
    # A character's bible may hold ANGLE plates beside the locked portrait
    # (<slug>-angle-*.png — the same person from other angles, Lars's ask):
    # every one of them rides along, so identity is stated from several views.
    plates = with_short_names((await draw_cast_plates(catalog, handle)).get("plates") or {})
    char_uris: dict = {}
    for name, rel in plates.items():
        if name in char_uris:
            continue
        p = Path(OUTPUT_DIR) / catalog / "trailer" / rel
        views = ([p] if p.exists() else []) + sorted(
            p.parent.glob(f"{p.stem}-angle-*.png"))
        uris = []
        for v in views[:4]:
            try:
                uris.append(await runway.upload_file(v))
            except Exception:
                pass
        if uris:
            char_uris[name] = uris

    credits_before = await runway.credit_balance()

    # frames first (cheap, parallel), then the shoot
    if handle:
        handle.progress(0.10, "board", f"framing scene {scene_n}")
    frames = await asyncio.gather(
        *[_draw_shot_frame(catalog, scene_n, sh, style, cast, plates) for sh in shots],
        return_exceptions=True)

    gate = asyncio.Semaphore(4)
    done = [0]

    async def shoot(idx: int, sh: dict):
        clip = sdir / f"shot-{sh['k']:02d}.mp4"
        if clip.exists() and clip.stat().st_size > 200_000:
            return clip
        # The FRAME leads: it is the shot's target image and now carries the
        # cast's true faces (composited from the locked plates), so identity
        # survives even when moderation strips the portrait refs. Plates ride
        # behind it as reinforcement.
        frame_ref, who = None, ""
        fr = frames[idx]
        if isinstance(fr, Path) and fr.exists():
            try:
                frame_ref = await runway.upload_file(fr)
                who += (" The FIRST reference image is the target frame for this "
                        "shot: match it exactly — the people's faces, hair and "
                        "build, the composition, buildings and light. The video "
                        "opens on this framing and the same humans.")
            except Exception:
                pass
        face_refs = []
        for name in (sh.get("characters") or []):
            uris = char_uris.get(name) or []
            if uris:
                a = (1 if frame_ref else 0) + len(face_refs) + 1
                face_refs.extend(uris)
                b = (1 if frame_ref else 0) + len(face_refs)
                span = f"image {a}" if a == b else f"images {a} through {b}"
                who += (f" Reference {span} show {name} from different angles — "
                        f"one and the same person: exactly that face, hair, age "
                        f"and build in this scene.")
        refs = ([frame_ref] if frame_ref else []) + face_refs
        action = apply_cast(f"{sh.get('framing','')}: {sh.get('action','')}", cast)
        snd = (sh.get("sound") or "").strip()
        ln = sh.get("line") or {}
        speak = bool((ln.get("text") or "").strip())
        if speak:
            # Written as SCRPT, spoken as "Script" — house rule since the
            # commercial. The model reads the line aloud, so the spoken text
            # gets the pronunciation, never the wordmark's spelling.
            spoken = ln["text"].replace("SCRPT", "Script")
            # Her lines are PERFORMED on camera: Seedance generates the voice
            # and the lip sync together (Lars's law — she speaks to us, face
            # to the lens, never her back). ElevenLabs cues stay for off-
            # camera VO only.
            sh["native_dialogue"] = True
            # Both the staging sentence and the voice are per-shot overridable:
            # the guide's default carries the tour, but e.g. the audiobook
            # narrator speaks on camera too, and he is neither female nor
            # looking into the lens.
            stage_sent = sh.get("speech_stage") or (
                "She looks straight into the camera, smiling warmly, and says clearly:")
            vdesc = sh.get("voice_desc") or (
                "a warm friendly professional female voice in her mid-thirties")
            prompt = (f"{action} {stage_sent} \"{spoken}\" — natural, "
                      f"accurate lip sync, {vdesc}. {style}"
                      + (f" Background sound: {snd}. No music." if snd else " No music.")
                      + " The only visible lettering anywhere is her small brass name badge, which reads exactly: SCRPT — spelled S-C-R-P-T, never \"Script\". No other text on screen." + who)
        else:
            prompt = (f"{action} {style} No text or lettering on screen."
                      + (f" Sound: {snd}. No music, no speech." if snd else "") + who)
        # Seedance shoots up to 30 s — long enough for a scene to be ONE
        # continuous take (Lars's cut law: one clip per speaking scene, the
        # dialogue never chopped across re-castings).
        secs = max(4, min(30, int(sh.get("seconds") or 6)))
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
                                                      model="seedance2_5", audio=speak)
                result = await runway.wait_for(task["id"], timeout_s=1500)
                url = (result.get("output") or [None])[0] if result.get("status") == "SUCCEEDED" else None
                if url:
                    await runway.download(url, clip)
                    done[0] += 1
                    return clip
                fail = json.dumps(result.get("failure") or result.get("failureCode") or "")
                if "moderation" in fail.lower() or "third_party" in fail.lower():
                    moderation += 1
                # Degrade in STAGES. Moderation objects to photoreal faces,
                # not to faceless storyboard frames — dropping everything
                # threw away the composition too, and the camera invented a
                # different studio (a mission-revival gate, on our deco lot).
                # First sacrifice the faces and KEEP the frame; only if the
                # gate still refuses does the shot fall to words alone.
                if moderation >= 6 and face_refs and len(live) > (1 if frame_ref else 0):
                    live = [frame_ref] if frame_ref else []
                    sh["refs_dropped"] = "faces"
                elif moderation >= 12 and live:
                    live = []
                    sh["refs_dropped"] = "all"
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
        # keep the take's own audio — for dialogue shots it carries her
        # lip-synced voice; a silent track is laid where none exists
        raw = sdir / f"segraw-{sh['k']:02d}.mp4"
        _run(["-y", "-ss", "0.000", "-i", str(clip), "-t", f"{max(0.2, need):.3f}",
              "-vf", f"scale={W}:{H},fps=24,format=yuv420p",
              "-c:v", "libx264", "-preset", "fast", "-crf", "18",
              "-c:a", "aac", "-ar", "48000", "-ac", "2", str(raw)], "cut+audio")
        import subprocess as _sp
        import imageio_ffmpeg as _iff
        probe = _sp.run([_iff.get_ffmpeg_exe(), "-i", str(raw)],
                        capture_output=True, text=True)
        if "Audio:" not in probe.stderr:
            _run(["-y", "-i", str(raw), "-f", "lavfi",
                  "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
                  "-c:v", "copy", "-c:a", "aac", "-ar", "48000", str(seg)], "silent track")
        else:
            import shutil as _sh
            _sh.copyfile(raw, seg)
        segs.append(seg)
        ln = sh.get("line")
        if ln and (ln.get("text") or "").strip() and not sh.get("native_dialogue"):
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

    # A continuous ambience bed under the whole scene — the world breathing,
    # not just event cues. Outdoors especially: the lot must HUM (Lars).
    amb = (scene.get("ambience") or "").strip()
    if amb:
        alen = min(20.0, max(8.0, t))
        acue = await _record_sfx(catalog, amb, alen,
                                 f"film-amb-{_h(amb)}", f"film-amb-{_h(amb)}.mp3")
        if acue:
            pos = 0.0
            while pos < t:
                sfx.append((acue, pos, 0.7))
                pos += alen

    lst = sdir / "list.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segs))
    silent = sdir / "picture-silent.mp4"
    _run(["-y", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c:v", "copy", "-c:a", "aac", "-ar", "48000", str(silent)], "scene concat")
    # The segments carry no audio (shots are cut with -an), so the mixer's
    # ambience input [0:a] would match no stream and the whole mix dies at
    # the finish line. Lay a silent bed under the picture first — the world's
    # sound arrives from the per-shot cues, the dialogue from the cast.
    picture = sdir / "picture.mp4"
    import shutil as _sh2
    _sh2.copyfile(silent, picture)      # segments already carry audio tracks

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
