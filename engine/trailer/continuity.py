"""Continuity: the part of a film the camera cannot know.

Every shot is generated on its own, from its own sentence. The camera has
no idea that a rock fell two scenes ago, that the creek is dry, that the
mother walked away, or how big the dragon is next to the unicorn. So the
state of the world has to be written into every prompt — as a positive
statement AND as a negative one, because a model that is not told a thing
is absent will happily put it in (Lars, 2026-09-01, after a film where
water flowed through a blocked spring and a mother appeared in the shot
where her daughter had just lost her).

Three jobs live here:

1. `state_for` — what is true at a given scene, as prompt text.
2. `presence_for` — who is allowed on screen in a shot, and who is not.
3. `check_board` — the desk check: repeated framings, near-identical
   consecutive shots, an event shown twice, a forbidden thing named in a
   shot's own description. Run before a single credit is spent.
"""
from __future__ import annotations

import difflib
import re

FRAMINGS = ("wide", "medium", "close", "detail")

# A shot never shows a character speaking: the voices are recorded
# separately and no generated mouth has ever matched them (Lars,
# 2026-09-01: "remove lip sync from all scenes").
NO_LIPSYNC = ("No character speaks on camera. Every mouth stays closed. "
              "Characters listen, react, walk and do — nobody talks.")


def state_for(board: dict, scene: int) -> str:
    """The world's state at this scene, as a sentence for the camera.

    board["continuity"] = {"states": [{"key": "water", "from_scene": 4,
    "until_scene": 11, "say": "...", "forbid": ["water", "stream"]}, ...]}
    """
    out = []
    for st in ((board.get("continuity") or {}).get("states") or []):
        a = int(st.get("from_scene") or 0)
        b = st.get("until_scene")
        b = int(b) if b is not None else 10_000
        if a <= int(scene or 0) < b and st.get("say"):
            out.append(str(st["say"]).strip())
    return " ".join(out)


def forbidden_for(board: dict, scene: int) -> list:
    bad = []
    for st in ((board.get("continuity") or {}).get("states") or []):
        a = int(st.get("from_scene") or 0)
        b = st.get("until_scene")
        b = int(b) if b is not None else 10_000
        if a <= int(scene or 0) < b:
            bad += [w.lower() for w in (st.get("forbid") or [])]
    return bad


def presence_for(pn: dict, cast_names: list) -> str:
    """Who is in this shot — and, said out loud, who is not.

    An EMPTY list is a statement, not a gap: a landscape with nobody in
    it. Saying nothing let the reference sheet leak all four characters
    into the opening shot of the film (2026-09-01)."""
    present = [c for c in (pn.get("present") or []) if c]
    if not present:
        return ("NO CHARACTERS APPEAR IN THIS SHOT. It is a place only — "
                "no unicorns, no bird, no dragon, nobody at all.")
    absent = [c for c in cast_names if c not in present]
    line = f"Only {', '.join(present)} appear in this shot."
    if absent:
        line += f" {', '.join(absent)} are NOT in this shot — do not draw them."
    return line


def scale_line(profile: dict) -> str:
    """The size chart. Characters drift because nothing repeats their size."""
    ch = (profile.get("creatives") or {}).get("scale_chart")
    return str(ch).strip() if ch else ""


def shot_prompt_suffix(board: dict, pn: dict, cast_names: list,
                       profile: dict = None) -> str:
    """Everything the camera cannot infer, appended to a shot's own words."""
    bits = [state_for(board, pn.get("scene")),
            presence_for(pn, cast_names),
            scale_line(profile or {}),
            NO_LIPSYNC]
    return " ".join(b for b in bits if b)


def applies(board: dict) -> bool:
    """These laws are for the CHILDREN'S line — picture books and the
    animated films made from them (Lars, 2026-09-01). A grown-up novel's
    trailer has humans in it, speaks on camera, and has no universe bible
    to be consistent with; imposing a children's continuity ledger on it
    would be nonsense. A board qualifies when it belongs to a universe, or
    was built as a children's film."""
    return bool((board or {}).get("continuity")
                or str((board or {}).get("format") or "").lower() == "childrens"
                or str((board or {}).get("kind") or "").lower() in ("film", "episode"))


def own_words(shot: str) -> str:
    """A shot's own description, with the appended rules stripped off.

    Continuity clauses are added to many shots verbatim ("THE STONE HAS NOT
    MOVED…"), and comparing full texts then reports every one of them as a
    duplicate of its neighbour (2026-09-01)."""
    out = []
    for seg in re.split(r"(?<=[.;])\s+", shot or ""):
        if re.search(r"\b(NO |NOT |THE STONE|THE LINE-UP|Every mouth|no cave|no den|"
                     r"no boulder|nobody is|open forest|The forest here)", seg):
            continue
        if seg.strip().isupper():
            continue
        out.append(seg)
    return " ".join(out).strip() or (shot or "")


def check_board(board: dict) -> list:
    """The desk check. Returns a list of problems, worst first."""
    problems = []
    if not applies(board):
        return problems
    panels = board.get("panels") or []
    seen_events = {}
    prev = None
    prev2 = None
    for i, pn in enumerate(panels):
        n = pn.get("n", i + 1)
        shot = " ".join(str(pn.get("shot") or "").split())
        scene = pn.get("scene")
        # a name inside a NEGATIVE sentence is an instruction, not a character
        _positive = " ".join(
            seg for seg in re.split(r"(?<=[.;])\s+", shot)
            if not re.search(r"\b(no|not|never|without)\b", seg, re.I))

        # 1. the same event shown twice
        ev = (pn.get("event") or "").strip()
        if ev:
            if ev in seen_events:
                problems.append(f"shot {n}: event '{ev}' was already shown in "
                                f"shot {seen_events[ev]} — an event happens once")
            else:
                seen_events[ev] = n

        # 1b. a character on screen before the story has met them
        first = (board.get("continuity") or {}).get("first_appearance") or {}
        for who in (pn.get("present") or []):
            fs = first.get(str(who))
            if fs is not None and scene is not None and int(scene) < int(fs):
                problems.append(f"shot {n}: {who} appears in scene {scene}, but is "
                                f"not met until scene {fs}")

        # 1c. a character NAMED IN THE PROSE before the story meets them.
        # The cast list was cleaned but three descriptions still said "as Pip
        # flutters awake nearby", and the camera drew what the sentence said
        # (Lars, 2026-09-01). The check reads the words, not just the list.
        for who, fs in (first or {}).items():
            if scene is not None and int(scene) < int(fs) and \
                    re.search(rf"\b{re.escape(str(who))}\b", _positive):
                problems.append(f"shot {n}: names {who} in scene {scene}, but "
                                f"{who} is not met until scene {fs}")

        # 2. a forbidden thing named in the shot's own description
        for word in forbidden_for(board, scene):
            if re.search(rf"\b{re.escape(word)}\b", shot, re.I):
                problems.append(f"shot {n}: says '{word}', which the story says "
                                f"is not there in scene {scene}")

        # 2b. a human in a world that has none
        if re.search(r"\b(girl|boy|woman|man|child|children|people|person|princess(es)?"
                     r"|prince|human)\b", shot, re.I) and "Princess" not in shot:
            problems.append(f"shot {n}: describes a human — this world has none")

        # 2c. THE PICTURE AND THE CAST LIST MUST AGREE. Shot 10 said "the two
        # unicorns continuing on together" while its cast list said NO
        # CHARACTERS, so the prompt asked for both at once and the drawing
        # made no sense (Lars, 2026-09-01).
        named = [c for c in (board.get("cast_names") or
                             ["Glitter", "Princess", "Pip", "Moss"])
                 if re.search(rf"\b{re.escape(c)}\b", _positive)]  # case-sensitive
        listed = list(pn.get("present") or [])
        if named and not listed:
            problems.append(f"shot {n}: names {', '.join(named)} in the picture but its cast "
                            f"list is empty — the prompt will ask for nobody and for them")
        for c in named:
            if listed and c not in listed:
                problems.append(f"shot {n}: names {c} in the picture but {c} is not in its "
                                f"cast list")
        if re.search(r"\b(the two unicorns|both of them|the three friends|they walk|they "
                     r"stand)\b", shot, re.I) and not listed:
            problems.append(f"shot {n}: describes characters but lists none")

        # 3. a mouth moving
        if re.search(r"\b(speak|speaking|says|talking|mouth open|shouts)\b", _positive, re.I):
            problems.append(f"shot {n}: describes someone speaking — the film has no lip sync")

        # 4. the storybook look outside the summary
        if re.search(r"\b(storybook page|open book|book page|illustrated page)\b", shot, re.I) \
                and (pn.get("look") or "") != "storybook":
            problems.append(f"shot {n}: asks for the storybook look, which belongs "
                            f"only to the closing summary")

        if prev is not None:
            pshot = own_words(" ".join(str(prev.get("shot") or "").split()))
            # 5. two shots in a row framed the same way
            # THREE IN A ROW IS A RUT; TWO IS A CUT (2026-09-01). Firing on
            # two identical framings made ordinary coverage — a wide
            # establishing shot followed by another wide — read as a defect
            # and would have stopped the line over nothing.
            fa, fb = (prev.get("framing") or "").lower(), (pn.get("framing") or "").lower()
            if fa and fa == fb and (prev2 or {}).get("framing", "").lower() == fa:
                problems.append(f"shot {n}: the third {fa} shot in a row")
            # 6. two shots in a row that are near enough to be the same picture
            ratio = difflib.SequenceMatcher(None, pshot.lower(),
                                            own_words(shot).lower()).ratio()
            if ratio > 0.72:
                problems.append(f"shot {n}: reads {int(ratio*100)}% the same as the shot "
                                f"before it — two shots cannot open the same way")
        prev2, prev = prev, pn
    # A BOARD MAY NOT CONTRADICT ITSELF (Lars, 2026-09-01: "this film looks
    # different"). Two fields describe every shot — the words and the
    # structured cast and camera — and the drawing stage obeys the fields
    # while the eye reads the words. Where they disagree, the picture is
    # wrong before anyone draws it: shot 6 said "Princess trotting close
    # behind her mother" with a cast list of one, so one pony was drawn.
    # This is free to check and it runs before any picture is paid for.
    # A NAME IS CAPITALISED; A PLANT IS NOT (2026-09-01). Matching "moss"
    # without case put the dragon into two scenes of damp green ground.
    # The name is matched case-sensitively; only the role phrases are loose.
    ALIAS = {"Glitter": (r"\bGlitter\b", r"\b(her|his|the) mother\b"),
             "Princess": (r"\bPrincess\b", r""),
             "Moss": (r"\bMoss\b", r"\bthe (little )?(green )?dragon\b"),
             "Pip": (r"\bPip\b", r"\bthe bird\b")}
    SAYS = [("detail", r"\bdetail (shot|close-up|of)\b|\bclose detail\b"),
            ("wide", r"\bwide (shot|view)\b|\bfrom a distance\b"),
            ("close", r"\bclose(-| )?(shot|on|up|view)\b"),
            ("medium", r"\bmedium shot\b")]
    for i, pn in enumerate(board.get("panels") or []):
        n = pn.get("n", i + 1)
        shot = " ".join(str(pn.get("shot") or "").split())
        if not shot:
            continue
        framing = str(pn.get("framing") or "").strip().lower()
        for want, pat in SAYS:
            if re.search(pat, shot, re.I):
                if framing and framing != want:
                    problems.append(
                        f"shot {n}: the words say a {want} shot but the camera "
                        f"is set to {framing} — the picture will be drawn "
                        f"{framing}")
                break
        present = [str(x) for x in (pn.get("present") or [])]
        _pos = " ".join(seg for seg in re.split(r"(?<=[.;])\s+", shot)
                        if not re.search(r"\b(no|not|never|without)\b", seg, re.I))
        for name, (npat, rpat) in ALIAS.items():
            hit = re.search(npat, _pos) or (rpat and re.search(rpat, _pos, re.I))
            if hit and name not in present:
                problems.append(
                    f"shot {n}: the words put {name} on screen but the cast "
                    f"list for this shot does not — {name} will not be drawn")

    return problems


# ── the board repairs a person had to make by hand on 2026-09-01 ──────────
FRAMING_SAYS = [("detail", r"\bdetail (shot|close-up|of)\b|\bclose detail\b"),
                ("wide", r"\bwide (shot|view)\b|\bfrom a distance\b"),
                ("close", r"\bclose(-| )?(shot|on|up|view)\b"),
                ("medium", r"\bmedium shot\b")]

# A NAME IS CAPITALISED; A PLANT IS NOT. Matching "moss" loosely once put a
# dragon into two scenes of damp green ground.
CAST_SAYS = {"Glitter": (r"\bGlitter\b", r"\b(her|his|the) mother\b"),
             "Princess": (r"\bPrincess\b", r""),
             "Moss": (r"\bMoss\b", r"\bthe (little )?(green )?dragon\b"),
             "Pip": (r"\bPip\b", r"\bthe bird\b")}


def repair_board(board: dict) -> list:
    """Make the board agree with itself, before anything is drawn from it.

    Every shot is described twice — in words, and in the structured camera
    and cast the drawing stage actually obeys. Where they disagreed, the
    picture was wrong before anyone drew it: shot 6 read "Princess trotting
    close behind her mother" and carried a cast list of one name, so one
    pony was drawn and the checker rejected it, round after round.

    A person reconciled 18 shots by hand to finish episode one. This does
    the same thing, deterministically, in a second, and it is ADDITIVE for
    cast: a character the words put on screen is added, and nobody is ever
    removed — a cast list is also the record of who the story says is there,
    and a model asked to "reconcile" it emptied shots that plainly had
    characters in them.

    Returns a list of what it changed, for the run's record.
    """
    if not applies(board):
        return []
    changed = []
    for i, pn in enumerate(board.get("panels") or []):
        n = pn.get("n", i + 1)
        line = " ".join(str(pn.get("shot") or "").split())
        if not line:
            continue
        for want, pat in FRAMING_SAYS:
            if re.search(pat, line, re.I):
                if (pn.get("framing") or "").lower() != want:
                    changed.append(f"shot {n}: camera set to {want}, as the words say")
                    pn["framing"] = want
                break
        positive = " ".join(seg for seg in re.split(r"(?<=[.;])\s+", line)
                            if not re.search(r"\b(no|not|never|without)\b", seg, re.I))
        present = list(pn.get("present") or [])
        for name, (npat, rpat) in CAST_SAYS.items():
            if name in present:
                continue
            if re.search(npat, positive) or (rpat and re.search(rpat, positive, re.I)):
                present.append(name)
                changed.append(f"shot {n}: {name} added to the cast, as the words say")
        if sorted(present) != sorted(pn.get("present") or []):
            pn["present"] = present
    return changed
