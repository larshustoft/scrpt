"""
The director: turns a finished book into a shootable trailer.

A trailer is not a summary. It is a promise: a hook, an escalation, a turn,
and a title card. This module writes that treatment from the book's own bible
and back-cover copy, then breaks it into SHOTS a video model can actually
render — each with its own camera, subject, lighting and duration — plus the
voice-over and the music brief.

Nothing here calls a video API. The treatment is reviewable (and cheap) on its
own, which is the point: you approve the film before you pay to shoot it.
"""

import json
from typing import Optional

from ..database import get_book_by_catalog, update_book
from ..prose.models import Manuscript
from ..writing.client import complete, extract_json

# A 25-second trailer: six shots plus a held cover card.
DEFAULT_SECONDS = 25
SHOT_SECONDS = 4


def _character_sheet(ms: Manuscript, limit: int = 3) -> str:
    if not ms.story_bible or not ms.story_bible.characters:
        return ""
    out = []
    for ch in ms.story_bible.characters[:limit]:
        out.append(f"- {ch.name} ({ch.role}): {ch.description}")
    return "\n".join(out)


async def write_treatment(catalog: str, seconds: int = DEFAULT_SECONDS,
                          brief: str = "") -> dict:
    """Write the trailer: beats, shots, voice-over, music brief."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = book["data"]
    ms = Manuscript.model_validate(d.get("manuscript") or {})
    b = ms.story_bible
    n_shots = max(4, (seconds - 5) // SHOT_SECONDS)   # last ~5s is the cover card
    # a reference trailer sets the rhythm: faster cuts → more, shorter shots
    ref = (d.get("trailer") or {}).get("reference") or {}
    if ref.get("avg_shot_seconds"):
        target = max(2.0, min(5.0, float(ref["avg_shot_seconds"]) * 1.6))   # AI clips can't cut as fast as live footage
        n_shots = int(max(4, min(12, round((seconds - 5) / target))))

    plot = "\n".join(
        f"  Ch{c.index}: {c.outline_summary}"
        for c in ms.chapters if c.outline_summary)[:3200]
    brief = (
        f"BOOK: \"{book['title']}\" by {d.get('author_name','')}\n"
        f"GENRE: {d.get('genre_preset','')}\n"
        f"LOGLINE: {getattr(b, 'logline', '')}\n"
        f"SETTING: {getattr(b, 'setting', '')} ({getattr(b, 'time_period', '')})\n"
        f"TONE: {getattr(b, 'tone', '')}\n"
        f"CHARACTERS:\n{_character_sheet(ms)}\n"
        f"BACK COVER COPY:\n{d.get('back_cover_blurb') or ms.blurb or ''}\n"
        f"TAGLINE: {ms.tagline}\n"
        f"THE PLOT — the trailer is built from THIS story:\n{plot}\n"
    )
    from .reference import reference_block
    from .direction import direction_block
    ref_block = reference_block(d) + direction_block(d)
    direction = (d.get("trailer") or {}).get("direction") or {}
    if direction.get("shots") and not ref.get("avg_shot_seconds"):
        n_shots = int(max(4, min(12, int(direction["shots"]))))
        seconds = int(max(20, min(60, int(direction.get("seconds") or seconds))))
    if brief.strip():
        brief_block = (
            "\nPUBLISHER'S BRIEF — this is the trailer the publisher wants; "
            f"follow it over everything below:\n\"\"\"\n{brief.strip()}\n\"\"\"\n"
        )
    else:
        brief_block = ""

    n_plates = int(max(5, min(8, round(n_shots * 1.0))))
    prompt = (
        f"{brief_block}{ref_block}{brief}\n"
        f"Direct a {seconds}-second book trailer that CUTS like a real movie "
        "trailer. It ends on a held card of the book's cover, which is "
        "supplied — you do NOT describe that card.\n\n"
        "HOW A TRAILER IS BUILT HERE — three layers:\n"
        f"1. PLATES: exactly {n_plates} generated video clips, 8-10 seconds each, "
        "described the way a person would say it to a filmmaker — PLAIN WORDS, "
        "30-50 words: who is there, where, what happens (two or three beats in "
        "order: an action, a reaction, a reveal), the light and time of day, and "
        "at most one simple camera movement ('the camera drifts closer', 'we follow "
        "her'). NO technical vocabulary: no lens names, no film stock, no "
        "'anamorphic', 'halation', 'grain', 'rack focus', no 'cut to' — the video "
        "model does the cinematography. Lead characters MAY be seen, faces included, "
        "with real emotion — but never speaking and never looking into the "
        "lens. Put two people in the same frame, touching or almost touching, "
        "in at least two plates: that is the drama. Vary the scale: at least "
        "one close plate (hands, eyes, an object) and one wide.\n"
        "2. INSERTS: 4-8 still images with a slow push-in — details that carry "
        "story (a letter, a lock, a photograph, a ring, a doorway). 15-30 plain "
        "words each, no technical vocabulary, no text or lettering in the image.\n"
        "3. CARDS: 3-5 typographic title cards, 1-4 words each, in classic "
        "trailer grammar (THIS SUMMER / ONE HOUSE / EVERY DEBT COMES DUE). "
        "They carry the sales promise so the voice-over can do less.\n\n"
        f"THE CUT: 18-26 cuts in {seconds - 5} seconds, in three movements — "
        "SETUP (longer cuts, 2.5-4 s, the world and the longing), the TURN "
        "(one held beat, then a hard silence), ESCALATION (cuts of 1-2 s "
        "accelerating to the cover). A cut is one of: a PLATE moment (plate id, "
        "start offset 0-6 s, 1-4 s long), an INSERT (index), or a CARD (index). "
        "Use every plate at least twice from different offsets; use every "
        "insert and card once.\n\n"
        "GROUNDING (house rule, non-negotiable): every plate, insert, line and "
        "card is built on the book's actual plot — its places, characters, "
        "events. A publisher's brief steers emphasis and tone but never "
        "replaces the story. Never invent scenes, characters or imagery "
        "foreign to the book. Keep continuity: the same character is described "
        "the same way every time (age, hair, wardrobe).\n\n"
        "CAST: the one or two lead characters who appear on screen, each with "
        "a 25-40 word physical description (age, face, hair, build, wardrobe "
        "for this story) — the reference portrait is generated from it.\n"
        "VOICE-OVER: at most 6 short lines across the whole cut, attached to "
        "cuts, total under 45 words. Classic trailer grammar: short "
        "declaratives, a promise, a turn. Silence is allowed and good.\n"
        "MUSIC: two cues — 'intimate' for the setup and 'build' for the "
        "escalation — each a 25-40 word brief (instrumentation, tempo, how it "
        "moves). Name the emotion, not a band.\n\n"
        'Return JSON only: {"concept": "one line on the angle", '
        '"cast": [{"name": "...", "description": "..."}], '
        '"plates": [{"id": "P1", "prompt": "...", "sound": "key diegetic sound", "characters": ["name"]}], '
        '"inserts": [{"prompt": "..."}], '
        '"cards": [{"text": "THIS SUMMER"}], '
        '"cuts": [{"type": "plate", "plate": "P1", "start": 0, "seconds": 3.0, "voiceover": ""}, '
        '{"type": "insert", "index": 0, "seconds": 2.0, "voiceover": ""}, '
        '{"type": "card", "index": 0, "seconds": 1.6}], '
        '"turn_cut": 9, '
        '"music": {"intimate": "...", "build": "..."}, '
        '"end_card_text": "the SALES tagline read over the final cover card: clear, hard, ownable, max 8 words"}'
    )

    raw = await complete(
        "You are a trailer director for a publishing house. You cut trailers "
        "that make people buy books: image first, promise second, never a plot "
        "summary.", prompt, max_tokens=4000)
    treatment = extract_json(raw) or {}
    treatment = normalize_treatment(treatment)

    fresh = get_book_by_catalog(catalog)
    data = dict(fresh["data"])
    data["trailer"] = {**(data.get("trailer") or {}), "treatment": treatment,
                       "seconds": seconds}
    update_book(fresh["id"], data)
    return treatment


def normalize_treatment(t: dict) -> dict:
    """One shape for every script, old or new. Plates double as `shots`
    (the desk's editor and the take ledger read them); an old-style script
    with only `shots` gets a plain one-cut-per-shot edit."""
    t = dict(t or {})
    plates = t.get("plates") or []
    if not plates and t.get("shots"):
        plates = []
        for i, sh in enumerate(t["shots"], 1):
            plates.append({"id": f"P{i}", "prompt": sh.get("prompt") or "",
                           "sound": sh.get("sound") or "", "characters": [],
                           "voiceover": sh.get("voiceover") or "",
                           "seconds": sh.get("seconds") or 4})
        t["plates"] = plates
    for i, pl in enumerate(plates, 1):
        pl.setdefault("id", f"P{i}")
        pl["n"] = i
        pl["seconds"] = int(pl.get("seconds") or 10) if 8 <= int(pl.get("seconds") or 10) <= 12 else 10
    if not t.get("cuts"):
        t["cuts"] = [{"type": "plate", "plate": pl["id"], "start": 0,
                      "seconds": float(min(6, max(2, int(pl.get("_len") or 4)))),
                      "voiceover": pl.get("voiceover") or ""} for pl in plates]
    # the desk's editor shows one VO line per plate: mirror the first cut's
    # line onto its plate for display, and a line typed on a plate whose
    # cuts are silent rides onto that plate's first cut
    first_cut = {}
    for c in t.get("cuts") or []:
        if c.get("type", "plate") == "plate" and c.get("plate") not in first_cut:
            first_cut[c.get("plate")] = c
    for pl in plates:
        fc = first_cut.get(pl["id"])
        plate_vo = (pl.get("voiceover") or "").strip()
        cut_vo = next(((c.get("voiceover") or "").strip() for c in (t.get("cuts") or [])
                       if c.get("type", "plate") == "plate" and c.get("plate") == pl["id"]
                       and (c.get("voiceover") or "").strip()), "")
        if cut_vo and not plate_vo:
            pl["voiceover"] = cut_vo
        elif plate_vo and not cut_vo and fc is not None:
            fc["voiceover"] = plate_vo
        elif plate_vo and cut_vo and plate_vo != cut_vo:
            # the publisher edited the plate's line: it replaces the cut's
            for c in t.get("cuts") or []:
                if c.get("type", "plate") == "plate" and c.get("plate") == pl["id"] and (c.get("voiceover") or "").strip() == cut_vo:
                    c["voiceover"] = plate_vo
                    break
    t["shots"] = plates
    t.setdefault("inserts", [])
    t.setdefault("cards", [])
    t.setdefault("cast", [])
    if isinstance(t.get("music"), str):
        t["music"] = {"intimate": t["music"], "build": t["music"]}
    t.setdefault("music", {})
    return t


def shot_list(catalog: str) -> list[dict]:
    book = get_book_by_catalog(catalog)
    t = ((book or {}).get("data", {}).get("trailer") or {}).get("treatment") or {}
    return t.get("shots") or []


async def rewrite_line(catalog: str, shot_n: int = 0,
                       tagline: bool = False, field: str = "voiceover") -> list[str]:
    """Alternative takes for ONE element of the script — the punch-up desk.
    field: "voiceover", "scene" (what the camera sees), "sound", or the
    tagline via tagline=True. Returns four options; the publisher picks."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = book["data"]
    ms = Manuscript.model_validate(d.get("manuscript") or {})
    b = ms.story_bible
    treatment = ((d.get("trailer") or {}).get("treatment")) or {}
    shots = treatment.get("shots") or []

    script = "\n".join(
        f"  Shot {s.get('n')}: [{(s.get('prompt') or '')[:90]}] "
        f"VO: {s.get('voiceover') or '(silent)'}"
        for s in shots)
    if tagline:
        target = (f"the TAGLINE shown as text over the final cover card. "
                  f"Current: \"{treatment.get('end_card_text') or ''}\"")
        rules = ("Max 8 words. Clear, hard, ownable — a line a movie poster "
                 "would carry. It sells the hook of THIS plot.")
    else:
        shot = next((s for s in shots if s.get("n") == shot_n), None)
        if not shot:
            raise ValueError(f"No shot {shot_n} in the treatment")
        if field == "scene":
            target = (f"the SCENE for shot {shot_n} — what the camera sees "
                      f"and what happens in the clip. "
                      f"Current: \"{(shot.get('prompt') or '')[:300]}\"")
            rules = ("40-70 words each, written for an AI video model: ONE "
                     "continuous camera move, concrete nouns — subject, "
                     "action, setting, light, weather, lens feel. No "
                     "dialogue, no on-screen text. Faces allowed, with real "
                     "emotion — never speaking, never looking into the lens. "
                     "Keep character "
                     "continuity: the same character keeps the same look "
                     "as in the other shots. Each option shows a genuinely "
                     "DIFFERENT scene or moment from the book that could "
                     "serve this beat of the trailer.")
        elif field == "sound":
            target = (f"the KEY DIEGETIC SOUND for shot {shot_n} "
                      f"[{(shot.get('prompt') or '')[:120]}]. "
                      f"Current: \"{shot.get('sound') or ''}\"")
            rules = ("A short sound-design cue, max 15 words: the world's "
                     "own sound for this image. Physical and concrete, no "
                     "music, no speech.")
        else:
            target = (f"the VOICE-OVER for shot {shot_n} "
                      f"[{(shot.get('prompt') or '')[:120]}]. "
                      f"Current: \"{shot.get('voiceover') or '(silent)'}\"")
            rules = ("Max 12 words. Classic Hollywood trailer grammar: short "
                     "declaratives, escalation. It must flow from the previous "
                     "line and into the next. An empty string is a valid option "
                     "if silence would hit harder.")

    prompt = (
        f"BOOK: \"{book['title']}\" — {getattr(b, 'logline', '')}\n"
        f"TRAILER CONCEPT: {treatment.get('concept') or ''}\n"
        f"THE SCRIPT AS IT STANDS:\n{script}\n"
        f"TAGLINE: {treatment.get('end_card_text') or ''}\n\n"
        f"Write FOUR alternative versions of {target}\n{rules}\n"
        "GROUNDING (house rule): every line is built on the book's actual "
        "plot — never invent facts foreign to the story.\n"
        'Return JSON only: ["option one", "option two", "option three", "option four"]'
    )
    raw = await complete(
        "You are a Hollywood trailer copywriter. Lines that sell, never "
        "lines that narrate.", prompt, max_tokens=600)
    options = extract_json(raw)
    return [str(o).strip() for o in options if isinstance(o, str)][:4]


async def write_shot(catalog: str, after_n: int = 0) -> dict:
    """Write ONE new shot to insert after shot `after_n` (0 = a new opening).
    The new scene bridges its neighbours and comes from the book's plot."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = book["data"]
    ms = Manuscript.model_validate(d.get("manuscript") or {})
    b = ms.story_bible
    treatment = ((d.get("trailer") or {}).get("treatment")) or {}
    shots = treatment.get("shots") or []
    if not shots:
        raise ValueError("No treatment to insert into")

    script = "\n".join(
        f"  Shot {s.get('n')}: [{(s.get('prompt') or '')[:110]}] "
        f"VO: {s.get('voiceover') or '(silent)'}"
        for s in shots)
    if after_n <= 0:
        place = "as the NEW OPENING, before shot 1"
    elif after_n >= len(shots):
        place = f"after shot {after_n}, as the new final shot before the cover card"
    else:
        place = f"between shot {after_n} and shot {after_n + 1}"

    prompt = (
        f"BOOK: \"{book['title']}\" — {getattr(b, 'logline', '')}\n"
        f"TRAILER CONCEPT: {treatment.get('concept') or ''}\n"
        f"THE SCRIPT AS IT STANDS:\n{script}\n\n"
        f"Write ONE new shot to insert {place}. It must bridge its "
        "neighbours — continuing the escalation, never repeating an image.\n"
        "RULES: one continuous camera move; what the camera sees, physically "
        "— subject, action, setting, light, weather, lens feel, 40-70 words; "
        "no dialogue, no on-screen text; faces allowed with real emotion, "
        "never speaking, never looking into the lens; keep character "
        "continuity with the other shots.\n"
        "GROUNDING (house rule): the scene comes from the book's actual "
        "plot — its places, characters, events.\n"
        'Return JSON only: {"camera": "the move", '
        '"prompt": "what the camera sees, 40-70 words", '
        '"voiceover": "a selling line under 12 words, or empty", '
        '"sound": "key diegetic sound", "seconds": 4}'
    )
    raw = await complete(
        "You are a trailer director for a publishing house. Image first, "
        "promise second, never a plot summary.", prompt, max_tokens=800)
    shot = extract_json(raw)

    new_shots = []
    inserted = False
    if after_n <= 0:
        new_shots.append(shot)
        inserted = True
    for s2 in shots:
        new_shots.append(s2)
        if not inserted and s2.get("n") == after_n:
            new_shots.append(shot)
            inserted = True
    if not inserted:
        new_shots.append(shot)
    for i, s2 in enumerate(new_shots, 1):
        s2["n"] = i

    fresh = get_book_by_catalog(catalog)
    data = dict(fresh["data"])
    tr = dict(data.get("trailer") or {})
    treatment = dict(tr.get("treatment") or {})
    treatment["shots"] = new_shots
    tr["treatment"] = treatment
    tr["approved"] = False          # a new scene needs a new okay
    data["trailer"] = tr
    update_book(fresh["id"], data)
    return {"shot": shot, "count": len(new_shots)}
