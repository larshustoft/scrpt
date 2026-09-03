"""The gates that protect a film are themselves checked, on every run.

Every rule in this module exists because a film was delivered that did not
match the board it was approved from (2026-09-01). The rules are cheap and
they are load-bearing, so the one thing that must never happen is a later
change quietly removing one — a gate that has been refactored away looks
exactly like a gate that never fires.

`check_gates()` proves, from the running code, that each protection is
present and behaves. It costs nothing, needs no network, and is called
before any film is shot. If it fails, the line stops.
"""
from __future__ import annotations

import inspect
from pathlib import Path


_PASSED_IN_THIS_PROCESS = False


def check_gates() -> list:
    """Return a list of failures. Empty list means every gate is in place.

    Checked once per process. The gates read source text from disk, and a
    file edited while a run is live is read at the running code's old line
    numbers — on 2026-09-02 that stopped a finished picture stage at the
    door of the shoot for a gate that was in fact in place. A process that
    passed at its start has the code it passed with; re-reading the disk
    tells it nothing true about itself.
    """
    global _PASSED_IN_THIS_PROCESS
    if _PASSED_IN_THIS_PROCESS:
        return []
    bad = []
    from . import producer as P
    from . import episode_line as E
    from . import verify as V
    from . import shotstills as S

    # 1. A take's identity must include the picture's BYTES, not its name.
    src = inspect.getsource(P.produce_storyboard)
    if "_still_fingerprint" not in src:
        bad.append("the take key no longer includes the still's contents — "
                   "a redrawn picture would be served as old footage")

    # 2. "Could not compare" must never be expressible as a passing score.
    if P._off_board(None) is not False:
        bad.append("an uncheckable take is being treated as off-board")
    if not P._off_board(-0.9) or not P._off_board(0.1):
        bad.append("a take that is not its still is being accepted")
    if P._off_board(0.99):
        bad.append("a take that IS its still is being rejected")

    # 3. The film must refuse to be cut when it does not match the board.
    if "will not be cut" not in src:
        bad.append("the pre-cut board check is gone — a film could be "
                   "assembled from shots that are not the approved pictures")

    # 4. An unrecorded picture take must not be grandfathered in.
    if "grandfather=False" not in src:
        bad.append("shot takes are being grandfathered into the ledger unproven")

    # 5. Every check that exists must be called by the line.
    line = inspect.getsource(E)
    for fn in ("verify_stills", "verify_plates", "draw_location_plates",
               "draw_prop_plates"):
        if fn not in line:
            bad.append(f"{fn}() is not called by the line — it protects nothing")

    # 6. A refused picture must be able to stop the line.
    if "raise stills" not in line:
        bad.append("a refused picture no longer stops the episode")

    # 7. The picture checker must be given the cast, or it cries wolf.
    if "THE CAST OF THIS FILM" not in inspect.getsource(V.verify_stills):
        bad.append("the picture checker is judging without the cast")

    # 8. A repair must be able to redraw only what failed.
    if "only" not in inspect.signature(S.draw_shot_stills).parameters:
        bad.append("stills can no longer be redrawn selectively — a repair "
                   "would cost a full redraw")

    # 9. A place the board uses must be established before it is drawn,
    #    and a place with no plate must stop the line rather than warn.
    from . import episode_line as _E
    est = inspect.getsource(_E.establish_world)
    if "would look" not in est or "raise RuntimeError" not in est:
        bad.append("a place with no plate no longer stops the line — every "
                   "shot set there would drift")
    if "place_briefs" not in est:
        bad.append("new places are no longer established before they are drawn")

    # 10. An empty account must stop the run everywhere, not look like a
    #     bad picture, a failed check, or an ordinary transient error.
    from . import plates as _P
    from . import runway as _R
    from ..writing import client as _C
    from ..credits import OutOfCredits, looks_broke
    if not looks_broke("Your credit balance is too low to access the Anthropic API"):
        bad.append("an empty Anthropic account is no longer recognised")
    if not looks_broke("credit_balance_exhausted"):
        bad.append("an empty OpenAI account is no longer recognised")
    for mod, name in ((_P, "drawing"), (_R, "shooting"), (_C, "writing")):
        src_ = inspect.getsource(mod)
        if "raise_if_broke" not in src_ and "OutOfCredits" not in src_:
            bad.append(f"{name} no longer stops the run when the account is empty")
        # THE NAME MUST RESOLVE, NOT JUST APPEAR (2026-09-02): runway.py
        # called raise_if_broke without importing it, this gate read the
        # text and passed, and the shoot died on its first take.
        for nm in ("raise_if_broke", "OutOfCredits"):
            if nm in src_ and not hasattr(mod, nm):
                bad.append(f"{name}: {nm} is used but not imported — the first refusal would crash the run")
    if "OutOfCredits" not in inspect.getsource(V):
        bad.append("the picture checker would swallow an empty account")

    # 11. The plates a whole season inherits must themselves be checked.
    if "verify_locations" not in est:
        bad.append("location plates are no longer checked against the world "
                   "rules — a cave in one plate is a cave in forty shots")

    # 12. A dead checker must stop the line, never start a redraw loop.
    dcs = inspect.getsource(_E := __import__("engine.trailer.episode_line",
                                             fromlist=["x"]).draw_and_check_stills)
    if "could not be checked" not in dcs or "unchecked" not in dcs:
        bad.append("a picture the checker could not read would be redrawn as "
                   "if it were a bad picture — an outage becomes a spend loop")

    # 13. The board must be made self-consistent before anything is drawn.
    from . import episode_line as _EL
    if "repair_board" not in inspect.getsource(_EL.run_episode):
        bad.append("the board is no longer repaired before drawing — a shot "
                   "whose words and cast list disagree would be drawn wrong")

    # 14. Rejections must be recorded, and earned rules must reach the prompt.
    if "lessons" not in inspect.getsource(_EL.draw_and_check_stills):
        bad.append("rejections are no longer recorded — the next film would "
                   "repeat this one's mistakes")
    if "standing_rules" not in inspect.getsource(S.still_prompt):
        bad.append("earned rules no longer reach the drawing prompt")

    # 15. The plates must be the Character Bible's pictures, verified by hash.
    if "md5" not in est or "plates" not in est:
        bad.append("episodes no longer verify their character plates against "
                   "the universe's canonical pictures — a redrawn reference "
                   "sheet could silently replace an approved character")

    # 16. A run may not spend past its quote: drawings are counted at the
    #     call, the episode quotes caps, and the shoot checks its balance.
    from . import make_episode as _ME
    from . import budget as _BU
    if "BUDGET.spend_drawing" not in inspect.getsource(_P):
        bad.append("drawings are no longer counted against the cap")
    if "BUDGET.quote" not in inspect.getsource(_ME.make_episode):
        bad.append("an episode no longer quotes its spending caps before it starts")
    if "_BUDGET.launch(" not in src:
        bad.append("takes are launched without reserving their cost against the cap")
    _d = _BU.Budget(); _d.quote(drawings_cap=5, credits_cap=100)
    try:
        for _ in range(5): _d.launch(5)
        bad.append("the credit cap does not refuse a launch past the cap")
    except _BU.OverBudget:
        pass
    _b = _BU.Budget(); _b.quote(drawings_cap=1); _b.spend_drawing()
    _c = _BU.Budget(); _c.quote(drawings_cap=5, credits_cap=100, credits_start=1000)
    try:
        _c.check_credits(0); _c.check_credits(None)
    except _BU.OverBudget:
        bad.append("an empty balance read is treated as a spend — a shoot would stop on a hiccup")
    try:
        _b.spend_drawing(); bad.append("the drawing cap does not actually refuse")
    except _BU.OverBudget:
        pass

    # 17. One source for a character; a new universe drafts its rules.
    from . import character_bible as _CB
    if not hasattr(_CB, "build"):
        bad.append("the Character Bible can no longer be generated from the plates")
    if "world rules drafted" not in est:
        bad.append("a universe with no world rules would draw with none")

    # 18. A board is drawn from its OWN world map, never another episode's.
    if "has no world map" not in inspect.getsource(_ME.make_episode):
        bad.append("a board without a world map would be drawn from episode one's places")
    from . import world as _W
    if "shot_props" not in inspect.getsource(_W.apply_world):
        bad.append("shot-level props are ignored — a fixed object can vanish from a shot")

    # 19. The board repair must exist as a callable, not just be mentioned.
    #     It was sliced out of its file twice by edits that cut at the wrong
    #     `return`; the run would have died at import time, after the quote.
    from . import continuity as _CN
    if not callable(getattr(_CN, "repair_board", None)) or not callable(getattr(_CN, "check_board", None)):
        bad.append("repair_board/check_board are missing from continuity.py")

    # 20. The Show Bible is the source: objects verified by hash like the
    #     characters, the document generated from the same files, and every
    #     run recording the bible it was drawn from.
    from . import show_bible as _SB
    if not (callable(getattr(_SB, "build", None)) and callable(getattr(_SB, "manifest", None))):
        bad.append("the Show Bible can no longer be generated from the universe")
    if "props_plates" not in est:
        bad.append("object plates are no longer verified against the universe by hash")
    if "_bible_manifest" not in inspect.getsource(_ME.make_episode):
        bad.append("an episode no longer records which Show Bible it was drawn from")

    if not bad:
        _PASSED_IN_THIS_PROCESS = True
    # 21. A take is judged on its whole length, and motion lines carry no names.
    if "_check_take" not in src or ("_de_name" not in src and "_motion_for_attempt" not in src):
        bad.append("takes are no longer judged along their length, or motion lines "
                   "carry character names — a human or a bear could walk into a take")
    from . import takecheck as _TC
    if _TC.de_name("Princess looks at Moss.", {}) == "Princess looks at Moss.":
        bad.append("de_name no longer replaces names")

    # 22. A shot with a still is never filmed from a sentence.
    if "still could not be uploaded" not in src:
        bad.append("a failed still upload can again drop a shot into text-to-video")

    # 23. The score is led by the show's music direction, not a free mood.
    if "music_direction" not in inspect.getsource(P._film_score):
        bad.append("the score no longer carries the show's music direction — chapters would drift into cinema")

    # 24. Character lines carry their cast voice on every entry path.
    if "voice cast applied" not in inspect.getsource(_ME.make_episode):
        bad.append("character lines can again be recorded in the narrator's voice")

    # 25. No freeze-frames in the cut (Lars, 2026-09-03: "the clip stops and
    # turns into a still image"). A short take stretches and bounces; it
    # never holds a cloned last frame.
    _cut_src = inspect.getsource(P.produce_storyboard)
    if "tpad=stop_mode=clone" in _cut_src or "tail_bounce" not in _cut_src:
        bad.append("the cut can freeze a shot on its last frame again")

    # 26. Strangers are counted, not argued (a pink pony behind Princess passed
    # the yes/no questions). The take judge compares species counts A vs B.
    from . import takecheck as _TC
    if "unicorns_in_B" not in _TC.TAKE_QUESTIONS or "_in_B" not in inspect.getsource(_TC.check_take):
        bad.append("the take judge no longer counts characters — invented extras would pass")

    # 27. A prop lives only in its own shots: the picture checker asks about a
    # stray branch/log, exempt only where the shot names one.
    from . import verify as _V
    if not any("fallen tree branch" in q for q in _V.WORLD_QUESTIONS) or 8 not in _V.CONDITIONAL:
        bad.append("a fallen branch can again appear in shots that never mention it")

    # 28. The cut scans itself for frozen tails, and a dangling sound cue is
    # replaced before the SFX model can turn it into a voice.
    _ps = inspect.getsource(P.produce_storyboard)
    if "frozen_tails" not in _ps or "_DANGLING_CUE" not in _ps:
        bad.append("the cut no longer scans for freeze-frames / fragment sound cues")

    # 29. THE FILTER CHAIN IS WIRED (Lars, 2026-09-03: "a string of filters
    # that runs in the creation of animation films"). Every filter in
    # filters.CHAIN must be referenced from the function that has to call
    # it — a filter nobody calls is not a filter.
    import importlib
    from . import filters as _F
    for _e in _F.CHAIN:
        _modname, _fn = _e["where"].split(".", 1)
        try:
            _mod = importlib.import_module(f"engine.trailer.{_modname}")
            _obj = _mod
            for _part in _fn.split("."):
                _obj = getattr(_obj, _part)
            _src = inspect.getsource(_obj)
        except Exception as _ex:
            bad.append(f"filter {_e['name']}: {_e['where']} cannot be read ({str(_ex)[:40]})"); continue
        if _e.get("needle", _e["name"]) not in _src:
            bad.append(f"filter {_e['name']} is not wired into {_e['where']}")

    # 30. Scenery is inherited from the approved master a shot continues.
    if "_master_has" not in inspect.getsource(_V.verify_stills):
        bad.append("a continuation can again be refused for scenery its approved master has")

    return bad
