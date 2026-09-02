"""Shoot from a picture, not from a sentence.

The professional practice this borrows: nobody asks a video model to
invent a shot. You compose a still you approve — camera, character
placement, scale, the state of the world — and the model's only job is to
move it. Everything that drifted on Episode 1 (water returning to a dry
creek, a mother in a shot she had walked out of, a dragon twice his own
size, two shots opening identically) is a design decision the camera was
allowed to make because nobody made it first.

So each shot now gets:
  1. a STILL, drawn from the scene's plate + the shot's own description
     with the continuity state written in;
  2. that still handed to the camera as the FIRST FRAME.

Stills cost image credits — cents. Video costs Runway credits by the
second. Fixing a shot at the still stage is roughly a hundred times
cheaper than re-shooting it.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ..config import OUTPUT_DIR, OPENAI_API_KEY
from .continuity import shot_prompt_suffix


def _dir(catalog: str, sub: str) -> Path:
    d = Path(OUTPUT_DIR) / catalog / "trailer" / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def still_prompt(board: dict, pn: dict, cast: dict, style: str,
                 profile: dict, cast_handling: dict = None) -> str:
    """One frame, fully specified: the shot, the state, who is in it."""
    from .bible import apply_cast
    shot = apply_cast(str(pn.get("shot") or "").strip(), cast)
    framing = (pn.get("framing") or "").strip()
    # HOW FAR AWAY THE CAMERA IS, SAID IN SIZES (Lars, 2026-09-01: a close-up
    # of a dewdrop came back as a valley landscape). Naming a shot type is
    # not enough — the reference plates are wide paintings of a place, and a
    # picture drawn beside them copies their distance unless it is told, in
    # plain terms, how much of the frame the subject fills.
    frame_txt = {
        "wide": ("CAMERA DISTANCE — WIDE: the whole place is visible and the "
                 "characters are small in the frame, whole bodies, far away."),
        "medium": ("CAMERA DISTANCE — MEDIUM: the characters fill about half the "
                   "frame height, whole bodies, seen at eye level."),
        "close": ("CAMERA DISTANCE — CLOSE: the camera is RIGHT UP CLOSE. The "
                  "one thing this shot is about fills most of the frame — if "
                  "that is a character, one head from the top of the head to "
                  "the chest and no further; if it is an object, that object. "
                  "You cannot see the place around it, only a soft blur "
                  "behind. This is NOT a wide view."),
        "detail": ("CAMERA DISTANCE — DETAIL: the camera is RIGHT UP CLOSE on "
                   "ONE thing. That single object or that one small action "
                   "fills most of the frame. No landscape, no scenery, no "
                   "whole bodies. This is NOT a wide view."),
    }.get(framing.lower(), "")
    look = "" if (pn.get("look") or "") != "storybook" else \
        " Shown as an illustrated page from a storybook, with a soft painted border."
    # Built in plain pieces. The clever inline version had a stray operator
    # that threw for every shot with a prop — 140 of 146 drawings failed
    # silently and the run just kept reporting "missing" (2026-09-01).
    # The framing leads and it closes. These models weight the first and the
    # last instruction most, and everything between them is a description of
    # a place — which is exactly what pulls a close-up back out to a wide.
    parts = [f"{frame_txt} {shot} {style}{look}"]
    if (pn.get("continues") or ""):
        parts.append("THE REFERENCE IMAGES INCLUDE THIS SAME PLACE EARLIER IN THE STORY: "
                     "keep the same ground, the same plants, the same light and the same "
                     "objects, in the same positions. Only the characters and the camera "
                     "move. THE REFERENCES DO NOT DECIDE HOW CLOSE THE CAMERA IS: they "
                     "are wide paintings of a place, and copying their distance is wrong "
                     "unless this shot is itself a wide one.")
    if (pn.get("props") or []):
        parts.append("AN OBJECT IN THE REFERENCE IMAGES APPEARS IN THIS SHOT AND MUST LOOK "
                     "EXACTLY THE SAME: the same shape, the same colour, the same size and "
                     "the same markings, every time it is seen. "
                     # THE REFERENCE IS THE OBJECT, NOT AN INSTRUCTION TO ADD ONE
                     # (Lars, 2026-09-02: "there is an extra bell lying loose").
                     # A prop plate shows the thing on a plain background, and the
                     # model kept placing a SECOND copy of it on the ground beside
                     # the character already wearing it.
                     "That object exists ONCE in this picture, exactly where the shot "
                     "says it is — worn, carried or held by whoever has it. Never draw "
                     "a second copy of it, and never leave one lying loose on the "
                     "ground or floating in the scene.")
    parts.append("THE LINE-UP REFERENCE IMAGE IS ONLY A SIZE AND IDENTITY GUIDE: do not copy "
                 "its composition, and never add a character who is not named below.")
    parts.append(shot_prompt_suffix(board, pn, list(cast.keys()), profile))
    parts.append("No text or lettering anywhere in the picture.")
    for rule in ((profile.get("creatives") or {}).get("world_rules") or []):
        parts.append(str(rule))
    # WHAT THIS UNIVERSE HAS LEARNED. Mistakes that recurred across earlier
    # rounds and episodes come back as standing rules, so the second film
    # starts where the first one finished (2026-09-02).
    from .lessons import standing_rules
    for rule in standing_rules(profile):
        parts.append(rule)
    # HOW A CHARACTER HANDLES A THING is in the bible and belongs in any shot
    # where they touch one — otherwise a unicorn lifts a branch in whatever way
    # the model imagines (Lars, 2026-09-01: "Princess is lifting it in a weird
    # way").
    if (pn.get("props") or []) and (pn.get("present") or []):
        for name in (pn.get("present") or []):
            c = (cast_handling or {}).get(str(name))
            if c:
                parts.append(f"{name} handles things like this: {c}")
    parts.append("Whatever object is named, show the WHOLE object, not a fragment of it.")
    parts.append("A single still frame of a children's animated film.")
    if frame_txt:
        parts.append(frame_txt)          # last word on the camera
    return " ".join(x for x in parts if x).strip()


async def draw_shot_stills(catalog: str, board: dict, profile: dict,
                           handle=None, redraw: bool = False,
                           only: set = None) -> dict:
    """One approved still per shot. Cheap, and it is what gets animated."""
    import httpx
    from ..cover.front_cover import _best_image_model
    from .plates import _draw_with_refs
    from .bible import cast_of
    from ..database import get_book_by_catalog

    book = get_book_by_catalog(catalog)
    if not OPENAI_API_KEY:
        raise RuntimeError("OpenAI is not configured — the stills need it")
    # the world links are rebuilt before every drawing pass, never trusted
    from .world import apply_world
    apply_world(board)
    cast = cast_of(book)
    # how each character physically handles objects, straight from the bible
    _ch = (book["data"].get("childrens") or {}).get("bible") or {}
    handling = {c.get("name"): c.get("hold things)")
                for c in (_ch.get("characters") or []) if c.get("hold things)")}
    style = board.get("style") or ""
    out = _dir(catalog, "stills")
    panels = board.get("panels") or []
    todo, stills = [], {}
    for i, pn in enumerate(panels):
        n = str(pn.get("n") or i + 1)
        f = out / f"still-{n}.png"
        # `only` names the shots to draw again — the pictures a check
        # rejected. Every other shot keeps the picture that passed, so a
        # repair costs four drawings instead of a hundred and forty-six.
        if only is not None:
            if n in only:
                todo.append((n, pn, f))
            elif f.exists():
                stills[n] = f"stills/still-{n}.png"
            continue
        if f.exists() and not redraw:
            stills[n] = f"stills/still-{n}.png"
        else:
            todo.append((n, pn, f))
    if todo:
        gate = asyncio.Semaphore(int(os.environ.get('SCRPT_STILL_LANES', '8')))
        done = [0]

        # THE REFERENCE SHEET GOES IN FRONT OF EVERY STILL. The scale plate
        # shows all four characters at their true relative size; the cast
        # plates hold each face. A model that is SHOWN the sizes does not
        # have to be told them — and telling them was never enough
        # (2026-09-01: Moss doubled his own height between two scenes).
        root = Path(__file__).resolve().parents[2]
        uni_dir = None
        sp = (profile.get("creatives") or {}).get("scale_plate")
        for cand in ((root / "universe" / (profile.get("slug") or "")), ):
            if cand.exists():
                uni_dir = cand
        if uni_dir is None and profile.get("profile_path"):
            uni_dir = (root / profile["profile_path"]).parent
        base_refs = []
        if sp and uni_dir and (uni_dir / sp).exists():
            base_refs.append(uni_dir / sp)
        bible_dir = Path(OUTPUT_DIR) / catalog / "trailer" / "bible"

        # the place this shot happens in, drawn once for the whole series
        from .locations import plate_for

        async def one(client, model, n, pn, dest):
            async with gate:
                # A CLOSE SHOT DOES NOT GET THE PLACE (Lars, 2026-09-01: "the
                # third clip of the leaf... doesn't look anything like the
                # storyboard"). Every reference here is a WIDE painting — the
                # location plate, the scale line-up, the master shot this one
                # continues from — and a picture drawn beside them inherits
                # their camera distance no matter what the words ask for.
                # Saying "RIGHT UP CLOSE" in the prompt changed nothing; four
                # trial redraws came back wide anyway. So a close or detail
                # shot is drawn from identity alone: the faces of whoever is
                # in it and the object it is about. The place cannot drift in
                # a picture where the place is not visible.
                # ONLY A WIDE SHOT GETS THE WIDE REFERENCE. Measured, not
                # assumed: close and detail shots stopped coming back as
                # landscapes the moment the location plate was withheld
                # (3 of 4 trial redraws fixed). Medium shots were still
                # inheriting it, so they get identity references too — the
                # place is barely visible behind a character who fills half
                # the frame, and framing is what was actually breaking.
                _tight = str(pn.get("framing") or "").lower() in ("close", "detail", "medium")
                refs = [] if _tight else list(base_refs)
                lp = (plate_for(profile, uni_dir, pn.get("place") or "")
                      if uni_dir and not _tight else None)
                if lp:
                    refs.insert(0, lp)
                # CONTINUES FROM another shot: its still goes in as a reference,
                # so the same place and the same props carry across a cut. A
                # branch trapping fireflies in one shot must be THAT branch when
                # it is lifted two shots later (Lars, 2026-09-01).
                # a shot may continue from SEVERAL shots — its place, and the
                # prop the story keeps coming back to (the branch, the stone)
                cont = "" if _tight else (pn.get("continues") or "")
                names = ([str(x) for x in cont] if isinstance(cont, list)
                         else [x.strip() for x in str(cont).split(",")])
                # THE PROP PLATES COME FIRST: an object the story keeps
                # returning to is drawn from its own plate, never re-imagined
                for pk in (pn.get("props") or [])[:2]:
                    pp = Path(OUTPUT_DIR) / catalog / "trailer" / "props" / f"{pk}.png"
                    if pp.exists():
                        refs.insert(0, pp)
                for cname in [c for c in names if c][:2]:
                    prev = Path(OUTPUT_DIR) / catalog / "trailer" / "stills" / f"still-{cname}.png"
                    if prev.exists():
                        refs.insert(0, prev)
                # WHO IS IN THE PICTURE COMES FIRST. Identity is the one
                # thing that may never drift, so the faces lead the list and
                # are never the ones dropped if it has to be trimmed. The
                # place, the props and the shot this one continues from all
                # matter less than drawing the right characters.
                faces = []
                for who in (pn.get("present") or []):
                    f = bible_dir / f"{str(who).lower()}.png"
                    if f.exists():
                        faces.append(f)
                refs = faces + [r for r in refs if r not in faces]
                got = await _draw_with_refs(client, model,
                                            still_prompt(board, pn, cast, style, profile,
                                                         handling),
                                            refs, dest, size="1536x1024")
                done[0] += 1
                if handle:
                    handle.progress(0.05 + 0.35 * done[0] / max(1, len(todo)),
                                    "stills", f"drew the still for shot {n}")
                return (n, f"stills/still-{n}.png") if got else None

        async with httpx.AsyncClient(timeout=260) as client:
            model = await _best_image_model(client)
            failures = []
            drawn = 0
            for r in await asyncio.gather(*[one(client, model, n, pn, f)
                                            for n, pn, f in todo],
                                          return_exceptions=True):
                if isinstance(r, tuple):
                    stills[r[0]] = r[1]; drawn += 1
                elif isinstance(r, BaseException):
                    failures.append(repr(r)[:200])
                else:
                    failures.append("the draw returned nothing")
            # A STAGE THAT DREW NOTHING MUST SAY SO. A bad prompt builder threw
            # for 140 of 146 shots and the loop simply reported them "missing"
            # again on the next round, three times over (2026-09-01).
            # COUNT WHAT THIS PASS TRIED TO DRAW, NOT THE WHOLE FILM
            # (2026-09-01). The guard compared failures against every still
            # on the board, so during a repair of four pictures it could
            # never fire — and an empty image account read as four pictures
            # that simply did not improve.
            if failures and drawn < len(todo) * 0.75:
                raise RuntimeError(
                    f"the stills stage drew only {drawn} of {len(todo)} shots it "
                    f"was asked for — first error: {failures[0]}")
            if failures:
                print(f"[stills] {len(failures)} of {len(todo)} failed: {failures[0]}",
                      flush=True)
    for i, pn in enumerate(panels):
        n = str(pn.get("n") or i + 1)
        if stills.get(n):
            pn["still"] = stills[n]

    # SAVE ONLY WHAT THIS STAGE OWNS (2026-09-01). A long drawing run holds
    # its own copy of the board; writing that copy back at the end threw away
    # every note made while it was running. It now re-reads the live board and
    # sets nothing but the still paths.
    try:
        from ..database import get_book_by_catalog, update_book
        book2 = get_book_by_catalog(catalog)
        data = dict(book2["data"])
        mv = dict(data.get("movie") or {})
        live = mv.get("storyboard") or {}
        touched = 0
        for pn in (live.get("panels") or []):
            n = str(pn.get("n") or "")
            if stills.get(n) and pn.get("still") != stills[n]:
                pn["still"] = stills[n]; touched += 1
        if touched:
            mv["storyboard"] = live
            data["movie"] = mv
            update_book(book2["id"], data)
    except Exception:
        pass
    return {"stills": stills}
