"""The plate is the law — so the plate has to be checked against the law.

Episode 1 was drawn for weeks from a Glitter plate with a floor-length
mane, while her written bible said mid-neck. Nobody had ever compared the
picture with the text, so the picture quietly became the truth and every
still in the film inherited it (Lars, 2026-09-01: "why does Glitter
suddenly have super long hair").

A universe may not be drawn until its plates have been read back against
the bible that describes them. This runs once per universe, costs a few
cents, and is the difference between a mistake that happens once and a
mistake that ships in twenty-six episodes.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from ..config import OUTPUT_DIR
from ..credits import OutOfCredits

SPEC_KEYS = ["build", "body shape)", "face", "nose", "eyes", "hair", "length",
             "skin_or_fur", "notable features)", "with colours and hex)",
             "clothing", "palette"]


async def verify_plates(catalog: str, handle=None) -> dict:
    """Read every character plate back against its written specification."""
    from ..writing.client import complete_vision, extract_json
    from ..database import get_book_by_catalog

    book = get_book_by_catalog(catalog)
    ch = (book["data"].get("childrens") or {}).get("bible") or {}
    chars = [c for c in (ch.get("characters") or []) if c.get("name")]
    bdir = Path(OUTPUT_DIR) / catalog / "trailer" / "bible"
    out = {}

    async def one(c):
        name = c["name"]
        f = bdir / f"{name.lower()}.png"
        if not f.exists():
            return name, ["no plate drawn"]
        spec = "\n".join(f"- {k.rstrip(')')}: {c[k]}" for k in SPEC_KEYS if c.get(k))
        try:
            raw = await complete_vision(
                "You are a character designer checking a reference plate against its "
                "written specification. You answer in JSON and you are strict but fair.",
                f"This picture is meant to be {name}.\n\nTHE WRITTEN SPECIFICATION:\n{spec}\n\n"
                "Answer JSON only: {\"matches\": true/false, \"mismatches\": [\"...\"]}\n"
                # WHAT A PLATE IS FOR (2026-09-01). A plate is the character,
                # drawn once, timeless. Judged loosely it blocked a film over a
                # third shade missing from a cutie mark and over a story rule
                # about which page a bell first appears on — neither of which
                # a reference sheet can be wrong about.
                "List ONLY contradictions that would make this look like a "
                "DIFFERENT CHARACTER: the wrong species or age, clearly wrong "
                "body proportions, wrong main colours, a mane or tail much "
                "longer or shorter than described, a major marking or prop "
                "that is missing or added, the wrong number of limbs.\n"
                "IGNORE: background, pose, lighting, artistic style; small "
                "differences of shade or gradient; fine detail inside a small "
                "marking; and ANY rule about when something appears in the "
                "story — a plate shows the character complete, not a moment "
                "in the plot.",
                f.read_bytes())
            d = extract_json(raw) or {}
            return name, [str(m) for m in (d.get("mismatches") or [])][:6]
        except OutOfCredits:
            raise
        except Exception as e:
            return name, [f"could not be checked: {str(e)[:80]}"]

    for name, problems in await asyncio.gather(*[one(c) for c in chars]):
        out[name] = problems
        if handle:
            handle.progress(0.5, "plates", f"checked {name}")
    ok = all(not v for v in out.values())
    return {"passes": ok, "by_character": out}


# THE RULES A PICTURE IS CHECKED AGAINST (Lars, 2026-09-01: "we do not
# want all these caves and rocks", "there are probably 140 different
# looking images of the same rock"). A rule written into a prompt is a
# request. A rule checked afterwards, with the picture in hand, is a rule.
WORLD_QUESTIONS = [
    "Is there a boulder, egg-shaped stone, standing rock, door or any other object "
    "sitting inside or directly in front of a cave, den, hollow or tunnel opening?",
    "Is there a human being of any kind in the picture — a person, girl, boy, princess "
    "or human hand or face?",
    "Is there any text, lettering or numbers in the picture?",
    # A SMILE IS NOT SPEECH (2026-09-02). Moss's approved plate smiles with his
    # mouth open, and the checker was failing every shot he smiled in. The rule
    # exists because lip-sync was removed — a mouth mid-word flaps in video. A
    # smile does not.
    "Is any character's mouth open AS IF TALKING — jaw dropped mid-word, as in "
    "a conversation? A closed-lip smile or a gently open happy smile is NOT "
    "talking and must be answered false.",
    "Is there a cave, den, tunnel, burrow, hollow or any dark opening in rock or "
    "earth anywhere in this picture, including small ones far in the background?",
    "Is there a large pale rounded boulder or standing stone anywhere in this "
    "picture — one big enough to be noticed rather than ordinary small ground stones?",
    # ANATOMY (Lars, 2026-09-02: "this unicorn has 5 legs"). A picture with the
    # wrong number of legs, heads, horns or wings passed every check we had.
    "Does any character have the WRONG NUMBER of legs, hooves, heads, horns, "
    "wings, eyes or tails — count them carefully — or a limb that joins the "
    "body in an impossible place?",
    "Is any ribbon, rope, string or vine strung BETWEEN two characters, joining "
    "one to the other, when nothing in the scene should connect them?",
    # THE BRANCH LIVES ONLY IN ITS OWN SHOTS (Lars, 2026-09-03: "the branch
    # keeps showing up in the clips after it's been lifted away"). 12 of 102
    # later stills carried a log or branch nobody asked for.
    "Is there a fallen tree branch, log, or large stick lying on the ground, "
    "across a path or in the water anywhere in this picture?",
]

# Questions 5 and 6 only apply where the story did not ask for the thing.
# The one round white stone IS the plot of episode one, and the spring
# really does come out of an opening in the cliff; flagging those is the
# check being literal instead of useful.
# PLURALS COUNT (2026-09-02). These matched only the singular, so a shot
# whose whole subject was "a row of huge white stones" was never exempted —
# it was flagged for containing a stone, redrawn, flagged again, forever.
# A rule that can never be satisfied is worse than no rule: it spends money
# in a loop and never converges.
CONDITIONAL = {4: r"\b(caves?|openings?|holes?|cracks?|tunnels?|hollows?|dens?|mouth of)\b",
               8: r"\b(branch(es)?|logs?|sticks?|twigs?)\b",
               # a vine/rope the shot itself puts in their hands is not a stray ribbon
               7: r"\b(vines?|ropes?|ribbons?|strings?|pull(s|ing)?|taut)\b",
               5: r"\b(stones?|boulders?|rocks?)\b"}


SCENERY_QUESTIONS = {4, 5, 8}      # cave, big boulder, fallen branch — things a place has, not a character
_MASTER_CACHE: dict = {}


async def _master_has(board: dict, tdir, pn: dict, qidx: list) -> list:
    """Which of the scenery questions `qidx` are ALSO true for the approved
    still this shot continues. Read once per master picture, then cached."""
    srcs = [x.strip() for x in str(pn.get("continues") or "").split(",") if x.strip()]
    byn = {str(p.get("n")): p for p in (board.get("panels") or [])}
    waived = set()
    for src in srcs:
        m = byn.get(src)
        if not m:
            continue
        f = tdir / str(m.get("still") or "")
        if not f.exists():
            continue
        key = (str(f), tuple(sorted(qidx)))
        if key not in _MASTER_CACHE:
            try:
                qs = "\n".join(f"{k+1}. {WORLD_QUESTIONS[i]}" for k, i in enumerate(qidx))
                raw = await complete_vision("You check pictures against a set of rules. JSON only.",
                                            f"Answer these questions about this picture:\n{qs}\n\n"
                                            'Return {"answers": [true/false … one per question …]} where true means YES, the thing IS there.',
                                            f.read_bytes())
                a = (extract_json(raw) or {}).get("answers") or []
                _MASTER_CACHE[key] = {i for k, i in enumerate(qidx) if k < len(a) and a[k] is True}
            except OutOfCredits:
                raise
            except Exception:
                _MASTER_CACHE[key] = set()
        waived |= _MASTER_CACHE[key]
    return [i for i in qidx if i in waived]


async def verify_stills(catalog: str, board: dict, handle=None, limit: int = 0,
                        only: set = None) -> dict:
    """Read every still back against the world's standing rules.

    A rule written into a prompt is a request; a rule checked afterwards is
    a rule. This is what catches the thing nobody thought to forbid — a
    stone in a cave mouth that quietly steals the story's key image
    (Lars, 2026-09-01)."""
    from ..writing.client import complete_vision, extract_json
    from ..database import get_book_by_catalog
    # WHO THE CHECKER IS LOOKING AT (2026-09-01). Without the cast it read a
    # correct picture of Princess and reported "this shows a unicorn, not a
    # Princess" — 92 shots flagged, most of them fine. A check that cries
    # wolf is worse than no check: it buries the real failures and it spends
    # money redrawing pictures that were right all along.
    _bk = get_book_by_catalog(catalog) or {}
    _cast = [c for c in ((((_bk.get("data") or {}).get("childrens") or {})
                          .get("bible") or {}).get("characters") or []) if c.get("name")]
    who = "\n".join(
        ("- {}: {} {}".format(c["name"],
                              str(c.get("build (body shape)") or c.get("build") or ""),
                              str(c.get("skin_or_fur") or "")).strip())[:200]
        for c in _cast)
    who = ("THE CAST OF THIS FILM — judge the picture by these descriptions, "
           "not by the names alone:\n" + who + "\n\n") if who else ""
    tdir = Path(OUTPUT_DIR) / catalog / "trailer"
    panels = (board.get("panels") or [])[: limit or None]
    # ONLY WHAT CHANGED GETS READ AGAIN (2026-09-02). Every repair round
    # re-read all 146 pictures when only the redrawn ones could have
    # changed — three minutes and hundreds of vision calls a round.
    if only is not None:
        panels = [p for p in panels if str(p.get("n")) in only]
    gate = asyncio.Semaphore(int(__import__("os").environ.get("SCRPT_VISION_LANES", "6")))
    qs = "\n".join(f"{i+1}. {q}" for i, q in enumerate(WORLD_QUESTIONS))

    async def one(pn):
        f = tdir / str(pn.get("still") or "")
        if not f.exists():
            return None
        # A RULE CANNOT FIRE WHERE THE STORY ITSELF PUT THE THING THERE.
        # The stone blocking an opening IS the plot in a handful of shots;
        # flagging those as continuity errors is the check being literal
        # rather than useful (2026-09-01).
        _text = " ".join([str(pn.get("shot") or ""), str(pn.get("place") or ""),
                          " ".join(pn.get("props") or [])])
        allowed = set()
        if "white-stone" in (pn.get("props") or []) or \
                re.search(r"\b(stones?|boulders?|rocks?)\b", _text, re.I):
            allowed.add(0)
        for qi, pat in CONDITIONAL.items():
            if re.search(pat, _text, re.I):
                allowed.add(qi)
        # THE PICTURE MUST ALSO BE THE SHOT (Lars, 2026-09-01: a close-up
        # of a dewdrop on a leaf came back as a wide valley landscape, and
        # nothing noticed until it was in the film). Asked in the same call
        # as the rules, so checking a whole episode is one pass, not two.
        line = str(pn.get("shot") or "").strip()
        async with gate:
            try:
                raw = await complete_vision(
                    "You check pictures against a set of rules. JSON only, and you only "
                    "report what you can actually see.",
                    f"Answer these questions about this picture:\n{qs}\n\n"
                    + who +
                    f"This picture is meant to be this shot —\n\"{line}\"\n"
                    # WHAT COUNTS AS A WRONG PICTURE (Lars, 2026-09-01). Left
                    # broad, this question failed a perfectly good close-up of
                    # Princess for "not a determined expression, no sense of
                    # pride" — a drawing cannot act, and chasing that never
                    # converges. It now judges only the four things that
                    # actually went wrong in the delivered film.
                    "Answer NO only if one of these four things is wrong:\n"
                    "  1. THE CAMERA IS AT THE WRONG DISTANCE — a close-up or a "
                    "detail drawn as a wide landscape, or a wide shot drawn as "
                    "a close-up.\n"
                    "  2. A CHARACTER NAMED IN THE LINE IS MISSING, or there is "
                    "a character in the picture the line does not mention.\n"
                    "  3. THE SUBJECT IS WRONG — the picture is of something "
                    "else than the line describes.\n"
                    "  4. THERE IS AN OBJECT THE LINE DOES NOT ASK FOR that "
                    "would confuse a child — a spare bell lying on the ground, "
                    "a second copy of something that exists once.\n"
                    "Answer YES for everything else. A DRAWING CANNOT ACT: never "
                    "judge expression, mood, emotion, pride or determination. "
                    "Never judge exact pose or blocking (beside instead of "
                    "behind), style, palette, lighting, or whether distant "
                    "scenery mentioned in passing is visible.\n\n"
                    'Return {"answers": [true/false … one per numbered question …], '
                    '"shows_the_shot": true/false, "why_not": "…"} where true in '
                    '"answers" means YES, the thing IS there.',
                    f.read_bytes())
                d = extract_json(raw) or {}
                a = d.get("answers") or []
                fired = [i for i, v in enumerate(a)
                         if v is True and i not in allowed and i < len(WORLD_QUESTIONS)]
                # SCENERY IS INHERITED FROM THE MASTER (2026-09-03). Shot 28
                # continues shot 17; shot 17 (approved, in the film) has a pale
                # rock cutting; shot 28 was refused four times for "a large
                # pale boulder" that continuity itself put there. A scenery
                # rule (cave, boulder, branch) that also holds for the
                # approved picture this shot continues is waived, and said so.
                _inherit = [i for i in fired if i in SCENERY_QUESTIONS]
                if _inherit and (pn.get("continues") or ""):
                    _waived = await _master_has(board, tdir, pn, _inherit)
                    for i in _waived:
                        fired.remove(i)
                        print(f"[stills] shot {pn.get('n')}: '{WORLD_QUESTIONS[i][:40]}…' inherited from shot {pn.get('continues')}", flush=True)
                flags = [WORLD_QUESTIONS[i][:60] for i in fired]
                if line and d.get("shows_the_shot") is False:
                    flags.append("not the shot on the board: "
                                 + str(d.get("why_not") or "")[:90])
                return (str(pn.get("n")), flags) if flags else None
            except OutOfCredits:
                raise      # the account is empty: stop the run, spend nothing
            except Exception as e:
                # NEVER SILENT. A check that cannot run is a check that
                # failed, not a check that passed.
                return (str(pn.get("n")), [f"could not be checked: {str(e)[:70]}"])

    out = {}
    for r in await asyncio.gather(*[one(p) for p in panels], return_exceptions=True):
        # THE STOP SIGNAL SURVIVES A GATHER (2026-09-01). return_exceptions
        # turns every failure into a value, including the one failure that
        # must halt the run.
        if isinstance(r, OutOfCredits):
            raise r
        if isinstance(r, tuple):
            out[r[0]] = r[1]
        if handle:
            handle.progress(0.5, "stills", f"checked {len(out)} flagged")
    return {"flagged": out, "checked": len(panels)}


async def verify_story(catalog: str, board: dict, handle=None, limit: int = 0) -> dict:
    """Does each picture actually show its own beat?

    The world rules catch what must never be there. This catches the other
    half: a picture that contradicts the words heard over it, the wrong
    characters, the wrong moment of the story, or a place that has changed
    since the last time we saw it (Lars, 2026-09-01)."""
    from ..writing.client import complete_vision, extract_json
    tdir = Path(OUTPUT_DIR) / catalog / "trailer"
    panels = (board.get("panels") or [])[: limit or None]
    gate = asyncio.Semaphore(int(__import__("os").environ.get("SCRPT_VISION_LANES", "6")))

    async def one(pn):
        f = tdir / str(pn.get("still") or "")
        if not f.exists():
            return None
        heard = " ".join(x for x in [(pn.get("vo") or ""),
                                     ((pn.get("line") or {}).get("text") or "")] if x)
        state = state_for(board, pn.get("scene"))
        async with gate:
            try:
                raw = await complete_vision(
                    "You are the continuity supervisor on a children's animated film. "
                    "JSON only. You report only what you can actually see.",
                    f"THE SHOT IS MEANT TO SHOW: {pn.get('shot')}\n"
                    f"THE WORDS HEARD OVER IT: {heard or '(none)'}\n"
                    f"CHARACTERS ALLOWED: {', '.join(pn.get('present') or []) or 'none'}\n"
                    f"THE STATE OF THE WORLD: {state or 'nothing special'}\n\n"
                    'Return {"matches": true/false, "problems": ["..."]}\n'
                    "Report ONLY: the picture showing something different from what is "
                    "described; a character present who is not allowed, or a described "
                    "character missing; the picture contradicting the words heard over it; "
                    "the state of the world contradicted. Ignore style, beauty and framing.",
                    f.read_bytes())
                d = extract_json(raw) or {}
                probs = [str(x) for x in (d.get("problems") or [])][:3]
                return (str(pn.get("n")), probs) if probs else None
            except Exception:
                return None

    out = {}
    for r in await asyncio.gather(*[one(p) for p in panels], return_exceptions=True):
        # THE STOP SIGNAL SURVIVES A GATHER (2026-09-01). return_exceptions
        # turns every failure into a value, including the one failure that
        # must halt the run.
        if isinstance(r, OutOfCredits):
            raise r
        if isinstance(r, tuple):
            out[r[0]] = r[1]
    return {"flagged": out, "checked": len(panels)}


LOCATION_QUESTIONS = [
    "Is there a cave, den, tunnel, burrow, hollow or any dark opening in rock "
    "or earth anywhere in this picture?",
    "Is there a large pale rounded boulder or standing stone anywhere in this "
    "picture — one big enough to be noticed rather than ordinary ground stones?",
    "Is there any character, animal or person in this picture?",
]
_LOC_KEY = ["cave", "stone", "character"]


async def verify_locations(universe_dir, profile: dict) -> dict:
    """Read the places the whole season is drawn from, back against the rules.

    A plate is drawn once and every shot set there inherits it. So a cave in
    a location plate is a cave in forty shots, and no amount of redrawing
    those shots can remove it — which is exactly what happened: the spring
    plate carried a big pale boulder, and every picture of the spring came
    back with one no matter what the shot said (Lars, 2026-09-01: "why is
    that rock appearing all over the place").

    Places the story genuinely needs an opening or the stone in are listed
    in the universe's `place_exemptions`.
    """
    from ..writing.client import complete_vision, extract_json
    from pathlib import Path as _P
    cre = profile.get("creatives") or {}
    exempt = cre.get("place_exemptions") or {}
    qs = "\n".join(f"{i+1}. {q}" for i, q in enumerate(LOCATION_QUESTIONS))
    out = {}

    async def one(key, f):
        try:
            raw = await complete_vision(
                "You check pictures against rules. JSON only.",
                f"Answer these questions about this picture:\n{qs}\n\n"
                'Return {"answers": [true/false, true/false, true/false]}',
                _P(f).read_bytes())
            a = (extract_json(raw) or {}).get("answers") or []
            allowed = set(exempt.get(key) or [])
            return key, [_LOC_KEY[i] for i, v in enumerate(a)
                         if v is True and i < len(_LOC_KEY)
                         and _LOC_KEY[i] not in allowed]
        except OutOfCredits:
            raise
        except Exception as e:
            return key, [f"could not be checked: {str(e)[:60]}"]

    places = cre.get("locations") or {}
    jobs = []
    for key, rel in places.items():
        f = _P(universe_dir) / rel
        if f.exists():
            jobs.append(one(key, f))
    for key, bad in await asyncio.gather(*jobs):
        if bad:
            out[key] = bad
    return {"flagged": out, "checked": len(jobs)}
