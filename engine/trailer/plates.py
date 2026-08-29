"""Reference pictures for the trailer: the cast sheet, and the board.

A written cast sheet cannot hold a face. The video model reads "a compact,
weathered man of about 58" and invents someone; the next shot reads the same
words and invents someone else. Nine shots, nine strangers — which is exactly
what the last Fracture Point trailer came back as.

So the bible is DRAWN. Each character gets a reference portrait built from the
front cover's world and their own look line, and that picture is handed to the
camera for every shot the character appears in. The shot prompt then says "the
man in reference image 2" instead of describing a stranger from scratch.

The board is drawn for the same reason a director boards a film: so the shots
can be judged before they are paid for.

Both are made with OpenAI's best available image engine, from the plot and the
front cover — the cover being the visual contract the whole trailer must match.
"""

from __future__ import annotations

import asyncio
import base64
import re
from pathlib import Path
from typing import Optional

from ..config import OPENAI_API_KEY, OUTPUT_DIR
from ..database import get_book_by_catalog, update_book


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "unnamed"


def series_canon(book: dict) -> dict:
    """Characters this series has already established, by name.

    A recurring lead belongs to the SERIES, not to whichever book happened to
    be written first. Left per-book, each cast sheet is written fresh from its
    own cover and invents a new man: Luc Reyer came out 58 and weathered in
    Fracture Point and mid-forties with a scarred eyebrow in Point Dume — four
    books, four leads. So before writing or drawing anyone, ask the rest of the
    series who they already are, earliest book first, and treat that as canon.

    Returns {name: {"look":…, "plate":…, "from":…, "catalog":…}}.
    """
    from ..database import list_books
    d = book.get("data") or {}
    series = (d.get("series") or {}).get("series_title")
    if not series:
        return {}
    mine = book.get("catalog_number") or book.get("catalog")
    found: dict = {}
    try:
        siblings = [b for b in (list_books(per_page=500) or {}).get("books", [])
                    if ((b.get("data") or {}).get("series") or {}).get("series_title") == series
                    and (b.get("catalog_number") or b.get("catalog")) != mine]
    except Exception:
        return {}
    siblings.sort(key=lambda b: ((b.get("data") or {}).get("series") or {}).get("book_number") or 99)
    for b in siblings:
        cat = b.get("catalog_number") or b.get("catalog")
        for kind in ("main", "supporting"):
            for c in (((b.get("data") or {}).get("bibles") or {}).get(kind) or {}).get("characters") or []:
                name = (c.get("name") or "").strip()
                if not name or name in found:
                    continue            # earliest book in the series wins
                plate = c.get("plate")
                drawn = (Path(OUTPUT_DIR) / cat / "trailer" / plate) if plate else None
                found[name] = {"look": c.get("look") or "", "from": b.get("title"),
                               "catalog": cat,
                               "plate": str(drawn) if drawn and drawn.exists() else None}
    return found


def _dir(catalog: str, leaf: str) -> Path:
    p = Path(OUTPUT_DIR) / catalog / "trailer" / leaf
    p.mkdir(parents=True, exist_ok=True)
    return p


async def _draw(client, model: str, prompt: str, dest: Path,
                size: str = "1024x1024", tries: int = 3,
                quality: str = "high", on_stage=None) -> Optional[Path]:
    """One picture, retried, never allowed to hang the whole run.

    With `on_stage`, the image STREAMS: partial renders arrive as the model
    paints, each written to dest and reported as real progress — the ring
    moves with the generation itself, and the last partial's replacement by
    the final frame is the honest 100% (Lars, 2026-08-29)."""
    import httpx, json as _json
    for _ in range(tries):
        try:
            if on_stage is None:
                r = await asyncio.wait_for(client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json={"model": model, "prompt": prompt[:3800],
                          "size": size, "quality": quality, "n": 1}),
                    timeout=240)
                if r.status_code == 200:
                    dest.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"]))
                    return dest
                if r.status_code < 500:
                    return None          # refused: skip rather than hang
                continue
            # streaming: real milestones from the paint itself
            got_final = False
            async with client.stream(
                    "POST", "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json={"model": model, "prompt": prompt[:3800],
                          "size": size, "quality": quality, "n": 1,
                          "stream": True, "partial_images": 2},
                    timeout=240) as r:
                if r.status_code != 200:
                    if r.status_code < 500:
                        return None
                    continue
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        ev = _json.loads(line[5:].strip())
                    except Exception:
                        continue
                    b64 = ev.get("b64_json")
                    t = ev.get("type") or ""
                    if b64 and "partial" in t:
                        dest.write_bytes(base64.b64decode(b64))
                        idx = int(ev.get("partial_image_index") or 0)
                        on_stage(0.45 + 0.25 * idx)
                    elif b64:
                        dest.write_bytes(base64.b64decode(b64))
                        got_final = True
                        on_stage(0.98)
            if got_final or dest.exists():
                return dest
        except (asyncio.TimeoutError, httpx.HTTPError):
            continue
    return None


# NOTE (2026-08-26, final): there is NO painted variant of anything. Lars's
# rule is absolute — plates are photographs, in the bible and to the camera.
# Runway's likeness moderation sometimes rejects photo references (9/9 panels
# on one run), but its failures are free and demonstrably RANDOM (the SCRPT
# commercial's ladder test passed at level 5 and failed at level 2), so the
# answer is PATIENCE in the shoot's retry loop, never a change of medium.


def _cast_prompt(ch: dict, style: str, title: str) -> str:
    """A reference portrait, not a poster.

    Plain background and even light on purpose: this picture exists to fix a
    face, and a dramatic composition would fight the shot it is referenced
    into. The cover's world sets colouring and costume; nothing else.
    """
    return (
        f"A character reference portrait for the film of \"{title}\".\n\n"
        f"THE PERSON: {ch.get('look') or ''}\n\n"
        f"WORLD AND PALETTE (match exactly): {style}\n\n"
        "Head-and-shoulders to waist, facing the camera, neutral expression, "
        "even soft light, plain uncluttered background. Photographic and "
        "realistic — a professional casting photograph of a real human being, "
        "sharp focus on the face. (House decision 2026-08-26: plates are "
        "PHOTOS, not paintings — Lars's call, made knowing Runway's likeness "
        "moderation sometimes rejects photoreal references; the shoot logs "
        "every panel that loses its refs as `refs_dropped`, so the rejection "
        "rate is measured rather than feared.) No text, no logos, no borders, "
        "no collage, no multiple views — one person, one frame."
    )


async def draw_cast_plates(catalog: str, handle=None, redraw: bool = False) -> dict:
    """Draw a reference portrait for every character on the cast sheet."""
    import httpx
    from ..cover.front_cover import _best_image_model

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    if not OPENAI_API_KEY:
        raise RuntimeError("OpenAI is not configured — the cast sheet needs it")
    d = dict(book["data"])
    bibles = d.get("bibles") or {}
    if not bibles.get("main"):
        raise RuntimeError("Write the character bible before drawing it")

    style = (bibles.get("main") or {}).get("style") or ""
    people: list = []
    for kind in ("main", "supporting"):
        for ch in ((bibles.get(kind) or {}).get("characters") or []):
            if ch.get("name"):
                people.append(ch)

    out = _dir(catalog, "bible")

    # A face this series has already established is copied in, never redrawn.
    # Redrawing a recurring lead from a fresh prompt produces a different man
    # even when the words match, which is the whole failure this exists to
    # stop — the reader of book three must meet the same person as book one.
    canon = series_canon(book)
    import shutil
    for ch in people:
        c = canon.get(ch.get("name") or "")
        dest = out / f"{slug(ch['name'])}.png"
        if c and c.get("plate") and not dest.exists():
            try:
                shutil.copyfile(c["plate"], dest)
                ch["look"] = c["look"] or ch.get("look")     # canon words too
                if handle:
                    handle.progress(0.1, "cast",
                                    f"{ch['name']} kept from {c['from']}")
            except Exception:
                pass

    # A locked face is never redrawn, whatever else this run is doing.
    people_open = [c for c in people if not c.get("locked")]
    todo = [c for c in people_open
            if redraw or not (out / f"{slug(c['name'])}.png").exists()]
    plates = {c["name"]: f"bible/{slug(c['name'])}.png"
              for c in people if (out / f"{slug(c['name'])}.png").exists()}

    if todo:
        gate = asyncio.Semaphore(3)
        done = [0]

        async def one(client, model, ch):
            async with gate:
                dest = out / f"{slug(ch['name'])}.png"
                got = await _draw(client, model, _cast_prompt(ch, style, book["title"]), dest)
                done[0] += 1
                if handle:
                    handle.progress(0.1 + 0.7 * done[0] / max(1, len(todo)),
                                    "cast", f"drew {ch['name']}")
                return (ch["name"], f"bible/{slug(ch['name'])}.png") if got else None

        async with httpx.AsyncClient(timeout=260) as client:
            model = await _best_image_model(client)
            for r in await asyncio.gather(*[one(client, model, c) for c in todo],
                                          return_exceptions=True):
                if isinstance(r, tuple):
                    plates[r[0]] = r[1]


    # remember on the bible so the shoot can find the pictures
    for kind in ("main", "supporting"):
        b = bibles.get(kind)
        if not b:
            continue
        for ch in (b.get("characters") or []):
            if plates.get(ch.get("name")):
                ch["plate"] = plates[ch["name"]]
                # The first drawing is a proposal that becomes canon by
                # default — locked, so nothing redraws it behind your back,
                # but visibly so, and openable when you want other options.
                ch.setdefault("variants", [ch["plate"]])
                ch.setdefault("locked", True)
    d["bibles"] = bibles
    update_book(book["id"], d)
    # House rule: everything is photographic — the bible AND what the camera
    # receives. No painted derivatives of any kind (Lars, 2026-08-26, final).
    return {"plates": with_short_names(plates), "drawn": len(todo)}


async def draw_series_logo(catalog: str, n: int = 3, handle=None) -> dict:
    """A wordmark for the series, drawn from its genre and its covers.

    The opening card already prefers artwork over type it sets itself, so a
    mark dropped here replaces the letterspaced lockup everywhere the series
    appears — every trailer, every book. That is the point of a series logo:
    book four inherits the recognition book one earned, and a reader knows
    what they are looking at before a word is spoken.

    Drawn as options, never auto-chosen: a logo is an identity, and it is the
    publisher's to pick.
    """
    import httpx
    from ..cover.front_cover import _best_image_model

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = book.get("data") or {}
    series = d.get("series") or {}
    title = (series.get("series_title") or "").strip()
    sid = (series.get("series_id") or "").strip()
    if not title or not sid:
        raise RuntimeError("This book is not part of a series")
    if not OPENAI_API_KEY:
        raise RuntimeError("OpenAI is not configured")

    genre = (d.get("genre_preset") or "").replace("_", " ")
    style = (((d.get("bibles") or {}).get("main") or {}).get("style") or "")
    prompt = (
        f"A series logo — a typographic wordmark — reading exactly: {title.upper()}\n\n"
        f"GENRE: {genre}. The mark must feel like the spine of that shelf.\n"
        f"WORLD AND PALETTE: {style}\n\n"
        "A publisher's series mark, not a poster and not an illustration: the "
        "words are the design. Elegant, restrained, built to sit over a dark "
        "film frame and over a book cover. One colour only — warm off-white — "
        "on a fully transparent background. Crisp edges, generous letterspacing, "
        "balanced on two lines at most. A single small rule or ornament is "
        "allowed if it earns its place. No photograph, no scene, no border box, "
        "no drop shadow, no extra words of any kind."
    )

    out = Path.home() / ".scrpt" / "house" / "series"
    out.mkdir(parents=True, exist_ok=True)
    made = []
    async with httpx.AsyncClient(timeout=260) as client:
        model = await _best_image_model(client)
        gate = asyncio.Semaphore(3)

        async def one(i: int):
            async with gate:
                dest = out / f"{sid}-logo-v{i}.png"
                for _ in range(2):
                    try:
                        r = await asyncio.wait_for(client.post(
                            "https://api.openai.com/v1/images/generations",
                            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                            json={"model": model, "prompt": prompt[:3800],
                                  "size": "1536x1024", "quality": "high", "n": 1,
                                  "background": "transparent", "output_format": "png"}),
                            timeout=240)
                    except (asyncio.TimeoutError, httpx.HTTPError):
                        continue
                    if r.status_code == 200:
                        dest.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"]))
                        if handle:
                            handle.progress(0.2 + 0.7 * i / max(1, n), "logo",
                                            f"drew option {i}")
                        return f"{sid}-logo-v{i}.png"
                    if r.status_code < 500:
                        return None
                return None

        for r in await asyncio.gather(*[one(i + 1) for i in range(n)],
                                      return_exceptions=True):
            if isinstance(r, str):
                made.append(r)
    return {"series": title, "series_id": sid, "options": made,
            "chosen": f"{sid}-logo.png" if (out / f"{sid}-logo.png").exists() else None}


def choose_series_logo(series_id: str, option_file: str) -> dict:
    """Make one option the series mark. Every trailer picks it up from here."""
    import shutil
    out = Path.home() / ".scrpt" / "house" / "series"
    src = out / option_file
    if not src.exists():
        raise ValueError("That logo option is not on file")
    shutil.copyfile(src, out / f"{series_id}-logo.png")
    return {"series_id": series_id, "chosen": f"{series_id}-logo.png"}


def _find_character(book: dict, name: str):
    """The character record itself, so it can be edited in place."""
    d = book.get("data") or {}
    for kind in ("main", "supporting"):
        for c in (((d.get("bibles") or {}).get(kind) or {}).get("characters") or []):
            if (c.get("name") or "").strip().lower() == (name or "").strip().lower():
                return kind, c
    return None, None


async def draw_variants(catalog: str, name: str, n: int = 3, handle=None) -> dict:
    """Draw alternative looks for one character, to choose between.

    Only ever called on an UNLOCKED character. A locked face is the series'
    canon — book three must show the reader the same man as book one — so it
    is not re-rolled by a background job that happens to run again. Unlocking
    is a deliberate act, and it is the only door to this function.
    """
    import httpx
    from ..cover.front_cover import _best_image_model

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    kind, ch = _find_character(book, name)
    if not ch:
        raise ValueError(f"{name} is not on the cast sheet")
    if ch.get("locked"):
        raise RuntimeError(f"{name} is locked for the series — unlock to draw alternatives")
    if not OPENAI_API_KEY:
        raise RuntimeError("OpenAI is not configured")

    style = (((book["data"].get("bibles") or {}).get("main") or {}).get("style") or "")
    out = _dir(catalog, "bible")
    have = list(ch.get("variants") or [])
    base = slug(name)
    start = len(have)

    async with httpx.AsyncClient(timeout=260) as client:
        model = await _best_image_model(client)
        gate = asyncio.Semaphore(3)

        async def one(k: int):
            async with gate:
                dest = out / f"{base}-v{k}.png"
                got = await _draw(client, model, _cast_prompt(ch, style, book["title"]), dest)
                if got and handle:
                    handle.progress(0.2 + 0.7 * (k - start) / max(1, n), "cast",
                                    f"drew an alternative for {name}")
                return f"bible/{base}-v{k}.png" if got else None

        drawn = await asyncio.gather(*[one(start + i + 1) for i in range(n)],
                                     return_exceptions=True)

    for r in drawn:
        if isinstance(r, str):
            have.append(r)
    d = dict(book["data"])
    _, live = _find_character({"data": d}, name)
    if live is not None:
        live["variants"] = have
    update_book(book["id"], d)
    return {"name": name, "variants": have, "chosen": ch.get("plate")}


def choose_variant(catalog: str, name: str, variant: str, lock: bool = True) -> dict:
    """Pick a look and, by default, lock it for the whole series.

    Locking writes the choice to every book in the series that has this
    character, because a face that is canon in one book and open in another is
    not canon at all — the next book would quietly draw someone else.
    """
    import shutil
    from ..database import list_books

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    kind, ch = _find_character(book, name)
    if not ch:
        raise ValueError(f"{name} is not on the cast sheet")

    src = Path(OUTPUT_DIR) / catalog / "trailer" / variant
    if not src.exists():
        raise ValueError("That picture is not on file")
    canonical = _dir(catalog, "bible") / f"{slug(name)}.png"
    if src.resolve() != canonical.resolve():
        shutil.copyfile(src, canonical)

    d = dict(book["data"])
    _, live = _find_character({"data": d}, name)
    live["plate"] = f"bible/{slug(name)}.png"
    live["chosen_variant"] = variant
    live["locked"] = bool(lock)
    update_book(book["id"], d)

    spread = []
    if lock:
        series = (d.get("series") or {}).get("series_title")
        mine = book.get("catalog_number") or book.get("catalog")
        for b in ((list_books(per_page=500) or {}).get("books", []) if series else []):
            bd = b.get("data") or {}
            cat = b.get("catalog_number") or b.get("catalog")
            if cat == mine or ((bd.get("series") or {}).get("series_title")) != series:
                continue
            _, sib = _find_character(b, name)
            if sib is None:
                continue
            dest = _dir(cat, "bible") / f"{slug(name)}.png"
            try:
                shutil.copyfile(canonical, dest)
            except Exception:
                continue
            nd = dict(bd)
            _, target = _find_character({"data": nd}, name)
            target["plate"] = f"bible/{slug(name)}.png"
            target["look"] = live.get("look") or target.get("look")
            target["locked"] = True
            update_book(b["id"], nd)
            spread.append(b.get("title"))
    return {"name": name, "plate": live["plate"], "locked": bool(lock),
            "also_updated": spread}


def set_lock(catalog: str, name: str, locked: bool) -> dict:
    """Lock or unlock a face. Unlocking is what allows new looks to be drawn."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = dict(book["data"])
    kind, ch = _find_character({"data": d}, name)
    if not ch:
        raise ValueError(f"{name} is not on the cast sheet")
    ch["locked"] = bool(locked)
    update_book(book["id"], d)
    return {"name": name, "locked": bool(locked)}


def with_short_names(plates: dict) -> dict:
    """Register "Luc" alongside "Luc Reyer", pointing at the same portrait.

    A board writes the short form — the cast sheet holds the full one — and the
    shoot looks the picture up by whatever the board wrote. Without the alias
    every panel naming "Luc" finds nothing and shoots him from words again,
    which looks exactly like having no cast sheet at all. `cast_of` already
    does this for the written description; the pictures have to match it, and
    only where a short form points at exactly one person.
    """
    STOP = {"mr", "mrs", "dr", "sir", "lady", "the", "ret", "justice",
            "senator", "captain", "colonel", "professor"}
    short: dict = {}
    for name, path in plates.items():
        for part in re.sub(r"[^A-Za-z ]", " ", name).split():
            if len(part) < 3 or part.lower() in STOP:
                continue
            short.setdefault(part, set()).add(path)
    out = dict(plates)
    for part, paths in short.items():
        if len(paths) == 1 and part not in out:      # unambiguous only
            out[part] = next(iter(paths))
    return out


def _panel_prompt(pn: dict, style: str, cast: dict, title: str) -> str:
    """The frame directs composition ONLY — house rule, every time.

    At shoot time each panel carries two kinds of reference: the cast plates
    (identity) and this frame (staging). A frame with a readable face in it is
    a second, unauthorised casting document — drawn before or beside the
    plates, its face can win over the real one and the lead changes mid-film.
    So the people in a frame are staged as figures: right build, right
    wardrobe, right position in the composition, and no face to compete with.
    """
    who = ""
    for name in (pn.get("characters") or []):
        if cast.get(name):
            who += f"\n{name}: {cast[name]}"
    # WORLD RULES: the title is context, never content. Without this, a
    # no-cast establishing frame for "Princess and the Hidden Spring" grew a
    # human princess and a castle from the title alone (2026-08-29).
    world = ("\nWORLD RULES: the ONLY characters that exist in this world "
             "are: " + ", ".join(f"{n2} ({str(v)[:80]})" for n2, v in list(cast.items())[:8])
             + ". NEVER add people, characters or creatures that are not "
             "listed in THE SHOT — a shot with no one named shows only the "
             "world itself. Words in the title are NOT scene content.\n"
             ) if cast else ""
    # the TITLE never enters the prompt: "Princess and the Hidden Spring"
    # grew a human princess in two consecutive establishing frames. The shot
    # text and cast sheet carry all real content; the title carries traps.
    return (
        f"A storyboard frame for an animated family film.\n{world}\n"
        f"THE SHOT: {pn.get('shot') or pn.get('title') or ''}\n"
        + (f"\nWHO IS IN IT — and we SEE them: faces visible and expressive, "
           f"in three-quarter or front view wherever the shot allows, matched "
           f"EXACTLY to the cast sheet below — never a new design, never a "
           f"character shown only from behind (Lars, 2026-08-29: the audience "
           f"meets the faces).{who}\n" if who else "")
        + f"\nWORLD AND PALETTE (match exactly): {style}\n\n"
        "Cinematic film still, 16:9 composition, natural light for the scene. "
        "No readable faces anywhere in the frame. "
        "No text, no captions, no panel borders, no watermark."
    )


async def draw_board_plates(catalog: str, board: dict, handle=None,
                            redraw: bool = False) -> dict:
    """Draw one frame per storyboard panel, so the board can be seen."""
    import httpx
    from ..cover.front_cover import _best_image_model
    from .bible import cast_of

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    if not OPENAI_API_KEY:
        raise RuntimeError("OpenAI is not configured — the board needs it")
    panels = board.get("panels") or []
    if not panels:
        return {"frames": {}}
    style = (board.get("style") or ""
             or ((book["data"].get("bibles") or {}).get("main") or {}).get("style") or "")
    cast = cast_of(book)
    out = _dir(catalog, "board")

    frames = {}
    todo = []
    for i, pn in enumerate(panels):
        n = str(pn.get("n") or i + 1)
        f = out / f"panel-{n}.png"
        if f.exists() and not redraw:
            frames[n] = f"board/panel-{n}.png"
        else:
            todo.append((n, pn, f))

    if todo:
        gate = asyncio.Semaphore(3)
        done = [0]

        async def one(client, model, n, pn, dest):
            async with gate:
                got = await _draw(client, model,
                                  _panel_prompt(pn, style, cast, book["title"]),
                                  dest, size="1536x1024")
                done[0] += 1
                if handle:
                    handle.progress(0.1 + 0.8 * done[0] / max(1, len(todo)),
                                    "board", f"drew panel {n}")
                return (n, f"board/panel-{n}.png") if got else None

        async with httpx.AsyncClient(timeout=260) as client:
            model = await _best_image_model(client)
            for r in await asyncio.gather(*[one(client, model, n, pn, f) for n, pn, f in todo],
                                          return_exceptions=True):
                if isinstance(r, tuple):
                    frames[r[0]] = r[1]

    for i, pn in enumerate(panels):
        n = str(pn.get("n") or i + 1)
        if frames.get(n):
            pn["frame"] = frames[n]
    return {"frames": frames}
