"""The adaptation desk: the book becomes a film.

A film is not the book with pictures. Ninety minutes holds perhaps a third of
a novel, so the adaptation is allowed to be ruthless — compress subplots,
merge minor characters, restructure — as long as what reaches the screen is a
STRONG telling: an opening that makes us care, a middle that tightens, an
ending that pays off what the opening promised. The treatment is where those
decisions are made and argued; the screenplay only executes them.

Everything binds to the same canon as the trailers: the character bible's
names and looks, the world's locations and style. The film is the same
universe, scene by scene.

Data lives on the book under `data.film`:
  treatment    — logline, three acts, beat sheet, scene list
  scenes       — {n: {slugline, cast, synopsis, action/dialogue blocks, ...}}
"""

from __future__ import annotations

from typing import Optional

from ..database import get_book_by_catalog, update_book

MAX_MINUTES = 90
OPENING_MINUTES = 10        # the proving ground: the first reel


def _film(book: dict) -> dict:
    return dict((book["data"].get("film")) or {})


def _save_film(catalog: str, film: dict):
    book = get_book_by_catalog(catalog)
    d = dict(book["data"])
    d["film"] = film
    update_book(book["id"], d)


def _source_digest(book: dict, limit: int = 9000) -> str:
    """Everything the adapter needs to know about the book, in one text."""
    d = book["data"]
    ms = d.get("manuscript") or {}
    bible = ms.get("story_bible") or {}
    parts = [
        f"TITLE: {book['title']}",
        f"GENRE: {d.get('genre_preset') or ''}",
        f"LOGLINE: {bible.get('logline') or ''}",
        f"THEMES: {', '.join(bible.get('themes') or [])}",
        f"BLURB:\n{d.get('description') or d.get('back_cover_blurb') or ''}",
    ]
    chapters = ms.get("chapter_summaries") or ms.get("chapters") or []
    if isinstance(chapters, list) and chapters:
        lines = []
        for i, ch in enumerate(chapters, 1):
            if isinstance(ch, dict):
                lines.append(f"Ch{i}: {ch.get('summary') or ch.get('synopsis') or ''}")
            else:
                lines.append(f"Ch{i}: {ch}")
        parts.append("CHAPTERS:\n" + "\n".join(lines))
    canon = (d.get("acceptance") or {}).get("canon_rulings") or bible.get("canon_facts")
    if canon:
        import json as _j
        parts.append("CANON FACTS (must hold on screen):\n" + _j.dumps(canon)[:2000])
    return "\n\n".join(p for p in parts if p.strip())[:limit]


def _cast_sheet(book: dict) -> str:
    bibles = book["data"].get("bibles") or {}
    out = []
    for kind in ("main", "supporting"):
        for c in ((bibles.get(kind) or {}).get("characters") or []):
            out.append(f"  - {c.get('name')}: {c.get('role')} — {c.get('look')}")
    return "\n".join(out)


async def adapt(catalog: str, handle=None) -> dict:
    """Write the treatment: the film's argument, before a scene is written.

    Three acts inside {MAX_MINUTES} minutes, a beat sheet, and a scene list
    where every scene carries its emotional job. This is the document a
    studio would greenlight from — and the one the publisher edits before
    the screenplay spends words on the wrong structure.
    """
    from ..writing.client import complete, extract_json, set_model_override, writing_model
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    if not (book["data"].get("bibles") or {}).get("main"):
        raise RuntimeError("Build the character bible first — the film casts from it")

    prompt = (
        f"{_source_digest(book)}\n\n"
        f"CAST (these names are canon; the film uses them exactly):\n{_cast_sheet(book)}\n\n"
        f"Adapt this novel into a feature film of AT MOST {MAX_MINUTES} minutes.\n\n"
        "You are adapting, not transcribing. Cut and compress ruthlessly: fold "
        "subplots, merge minor characters, reorder events — whatever makes the "
        "STRONGEST film of this story. Protect two things absolutely: the "
        "emotional spine (we must come to love the leads and fear for them) "
        "and the canon facts.\n\n"
        "Structure:\n"
        "1. ACT I — the opening (about a quarter of the runtime): meet the "
        "world and the leads at eye level; make us care before anything is "
        "asked of us; end on the turn that starts the story.\n"
        "2. ACT II — the pressure: rising stakes, the midpoint reversal, the "
        "lowest point.\n"
        "3. ACT III — the payoff: the climax the opening promised, and an "
        "ending with an afterglow.\n\n"
        "Write a SCENE LIST covering the whole film. Scenes run 1-4 minutes; "
        f"the total must stay inside {MAX_MINUTES}. For each scene: slugline "
        "(INT/EXT, location, day/night), the cast present (canon names only), "
        "a 2-3 sentence synopsis of what HAPPENS, the emotional beat (what the "
        "audience feels), and minutes as a decimal.\n\n"
        "Return JSON only:\n"
        '{"logline": "...", "acts": [{"n": 1, "intent": "..."}, ...], '
        '"beats": ["..."], '
        '"scenes": [{"n": 1, "act": 1, "slugline": "EXT. ... — NIGHT", '
        '"cast": ["Name"], "synopsis": "...", "beat": "...", "minutes": 2.5}]}'
    )
    if handle:
        handle.progress(0.1, "treatment", "adapting the book into a film")
    set_model_override(writing_model())
    try:
        raw = await complete(
            "You are a veteran screenwriter adapting novels into films that "
            "audiences love. Structure is your religion; sentiment earned, "
            "never begged.", prompt, max_tokens=16000)
    finally:
        set_model_override(None)
    data = extract_json(raw) or {}
    scenes = [s for s in (data.get("scenes") or [])
              if isinstance(s, dict) and (s.get("synopsis") or "").strip()]
    if not scenes:
        raise RuntimeError("The adapter returned no scenes — nothing was saved")
    total = sum(float(s.get("minutes") or 2) for s in scenes)
    treatment = {"logline": data.get("logline") or "",
                 "acts": data.get("acts") or [],
                 "beats": data.get("beats") or [],
                 "scenes": scenes, "total_minutes": round(total, 1)}
    film = _film(book)
    film["treatment"] = treatment
    film.setdefault("scenes", {})
    _save_film(catalog, film)
    return {"scenes": len(scenes), "total_minutes": round(total, 1),
            "logline": treatment["logline"]}


async def write_scene(catalog: str, n: int, handle=None) -> dict:
    """One scene, written for the camera we actually have.

    The hard constraint is honest: the video model cannot lip-sync, so spoken
    lines are staged the way trailers stage them — over reactions, from
    behind, off-frame, faces listening. The screenplay bakes that in rather
    than leaving the shoot to discover it.
    """
    from ..writing.client import complete, extract_json, set_model_override, writing_model
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    film = _film(book)
    treatment = film.get("treatment") or {}
    plan = next((s for s in treatment.get("scenes") or []
                 if int(s.get("n") or 0) == int(n)), None)
    if not plan:
        raise ValueError(f"Scene {n} is not in the treatment")
    prev = next((s for s in treatment.get("scenes") or []
                 if int(s.get("n") or 0) == int(n) - 1), None)

    prompt = (
        f"FILM: \"{book['title']}\" — {treatment.get('logline','')}\n"
        f"CAST:\n{_cast_sheet(book)}\n\n"
        + (f"PREVIOUS SCENE (for continuity): {prev.get('slugline')} — "
           f"{prev.get('synopsis')}\n\n" if prev else "")
        + f"WRITE SCENE {n}: {plan.get('slugline')}\n"
        f"CAST PRESENT: {', '.join(plan.get('cast') or [])}\n"
        f"WHAT HAPPENS: {plan.get('synopsis')}\n"
        f"EMOTIONAL BEAT: {plan.get('beat')}\n"
        f"TARGET LENGTH: {plan.get('minutes')} minutes\n\n"
        "Write the scene as a sequence of SHOTS, 4-12 seconds each. Every "
        "shot: framing + what happens + who is visible (canon names), the "
        "shot's one diegetic sound, and optionally ONE line of dialogue "
        "with its speaker.\n\n"
        "THE CAMERA CANNOT LIP-SYNC. Stage every spoken line so the "
        "speaker's mouth is not the subject: over the listener's shoulder, "
        "speaker turned away or in motion, reaction shots, distance. Never "
        "a held close-up of someone talking.\n"
        "Dialogue is sparse and loaded — film dialogue, not book dialogue.\n\n"
        "Return JSON only:\n"
        '{"shots": [{"k": 1, "seconds": 6, "framing": "...", "action": "...", '
        '"characters": ["Name"], "sound": "...", '
        '"line": {"speaker": "Name", "text": "..."}}]}'
    )
    if handle:
        handle.progress(0.1, "screenplay", f"writing scene {n}")
    set_model_override(writing_model())
    try:
        raw = await complete(
            "You are a screenwriter and shot-lister in one: every scene you "
            "write is already a shooting plan.", prompt, max_tokens=8000)
    finally:
        set_model_override(None)
    data = extract_json(raw) or {}
    shots = []
    for i, sh in enumerate(data.get("shots") or [], 1):
        if not isinstance(sh, dict) or not (sh.get("action") or "").strip():
            continue
        shot = {"k": i, "seconds": max(3, min(12, int(sh.get("seconds") or 6))),
                "framing": str(sh.get("framing") or "")[:80],
                "action": str(sh.get("action") or "").strip(),
                "characters": [str(c) for c in (sh.get("characters") or []) if c],
                "sound": str(sh.get("sound") or "").strip()[:160]}
        ln = sh.get("line")
        if isinstance(ln, dict) and (ln.get("text") or "").strip():
            shot["line"] = {"speaker": str(ln.get("speaker") or "")[:60],
                            "text": str(ln.get("text") or "").strip()[:220]}
        shots.append(shot)
    if not shots:
        raise RuntimeError(f"Scene {n} came back with no shots")
    scene = {**plan, "shots": shots,
             "seconds": sum(s["seconds"] for s in shots)}
    film = _film(get_book_by_catalog(catalog))
    film.setdefault("scenes", {})[str(n)] = scene
    _save_film(catalog, film)
    return {"n": n, "shots": len(shots), "seconds": scene["seconds"]}


async def write_opening(catalog: str, handle=None) -> dict:
    """Write every scene of the film's first {OPENING_MINUTES} minutes.

    The opening is the proving ground: if these minutes make a viewer care,
    the rest of the film has earned its budget. Written scene by scene so a
    weak one can be rewritten alone.
    """
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    treatment = _film(book).get("treatment") or {}
    if not treatment.get("scenes"):
        raise RuntimeError("Adapt the book first — the opening comes from the treatment")
    chosen, minutes = [], 0.0
    for s in treatment["scenes"]:
        if minutes >= OPENING_MINUTES:
            break
        chosen.append(int(s.get("n") or 0))
        minutes += float(s.get("minutes") or 2)
    written = []
    for idx, n in enumerate(chosen):
        if handle:
            handle.progress(0.05 + 0.9 * idx / max(1, len(chosen)),
                            "screenplay", f"scene {n} of the opening")
        written.append(await write_scene(catalog, n))
    return {"opening_scenes": chosen, "minutes": round(minutes, 1),
            "written": written}
