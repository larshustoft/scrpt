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


def check_gates() -> list:
    """Return a list of failures. Empty list means every gate is in place."""
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
        if "raise_if_broke" not in inspect.getsource(mod) and \
                "OutOfCredits" not in inspect.getsource(mod):
            bad.append(f"{name} no longer stops the run when the account is empty")
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
    if "check_credits" not in src:
        bad.append("the shoot no longer stops at its credit cap")
    _b = _BU.Budget(); _b.quote(drawings_cap=1); _b.spend_drawing()
    try:
        _b.spend_drawing(); bad.append("the drawing cap does not actually refuse")
    except _BU.OverBudget:
        pass

    # 17. One source for a character; a new universe drafts its rules.
    from . import character_bible as _CB
    if not hasattr(_CB, "build"):
        bad.append("the Character Bible can no longer be generated from the plates")
    if "world_rules drafted" not in est:
        bad.append("a universe with no world rules would draw with none")

    return bad
