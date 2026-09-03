"""THE FILTER CHAIN — every gate an animation film passes through, in order,
in one place (Lars, 2026-09-03: "turn these into a string of filters that runs
in the creation of animation films, so that we don't have to filter out these
clips manually" and "avoid spending money on video generations of clips that
are not useable").

Two kinds of filter live here:
  * PRE-FLIGHT filters run BEFORE money is spent and either fix the input or
    refuse to spend: a still that failed its picture check is never filmed; a
    motion line is linted (no names, no arrivals, one action) and a risky
    action is asked for gently on the FIRST take instead of the third.
  * POST filters judge what came back (picture checks, the take judge, the
    cut scan) — most of them already exist in verify.py / takecheck.py /
    producer.py; CHAIN lists them so the whole string is visible and gate 29
    proves each one is wired into the function that must call it.

Every verdict is written on the panel under pn["filters"][name] so the run
record can report what the chain stopped and what it saved.
"""
from __future__ import annotations

import re

# ── the chain, in running order ─────────────────────────────────────────────
# where = "module.function" that MUST reference `name` (gate 29 checks source)
CHAIN = [
    # desk (free, before any drawing)
    {"stage": "desk",     "name": "check_board",     "where": "continuity.check_board",
     "stops": "a board that contradicts itself (framing vs words, cast vs words, instructions in lines)"},
    {"stage": "desk",     "name": "repair_board",    "where": "continuity.repair_board",
     "stops": "the same, by rewriting the board from its own words"},
    {"stage": "desk",     "name": "apply_world",     "where": "world.apply_world",
     "stops": "props/places drifting: only the map may place an object in a shot"},
    # picture (each drawing ≈ $0.19; a refused picture is redrawn, never filmed)
    {"stage": "picture",  "name": "verify_plates",   "where": "verify.verify_plates",
     "stops": "a character plate that is not the approved character"},
    {"stage": "picture",  "name": "verify_locations","where": "verify.verify_locations",
     "stops": "a place plate that breaks the world rules"},
    {"stage": "picture",  "name": "verify_stills",   "where": "verify.verify_stills",
     "stops": "wrong distance, missing/extra character, wrong subject, stray object, anatomy, stray branch"},
    # pre-flight (free; this is where video money is saved)
    {"stage": "preflight","name": "still_cleared",   "where": "producer.produce_storyboard",
     "stops": "filming a picture that never passed its check"},
    {"stage": "preflight","name": "motion_lint",     "where": "producer.produce_storyboard",
     "stops": "names, arrivals, reveals and multi-action lines that make the model invent"},
    {"stage": "preflight","name": "gentle_first",    "where": "producer.produce_storyboard",
     "stops": "paying for a wild first take on an action the model is known to drop"},
    {"stage": "preflight","name": "take_length",     "where": "producer.produce_storyboard",
     "stops": "a 10s take (50 cr) where a 5s take + bounce (25 cr) carries the words"},
    {"stage": "preflight","name": "budget_launch",   "where": "producer.produce_storyboard", "needle": "_BUDGET.launch",
     "stops": "any take past the quoted cap — reserved before the request"},
    # take (25–50 cr each; a refused take is banked as .badN and re-shot)
    {"stage": "take",     "name": "check_take",      "where": "takecheck.check_take",
     "stops": "does not open on its picture, falls apart, barely moves, human, duplicate, stranger by count, mouth mid-word"},
    {"stage": "take",     "name": "take_ledger",     "where": "producer.produce_storyboard", "needle": "_remember_take",
     "stops": "a stale take served for a changed picture"},
    # cut (free)
    {"stage": "cut",      "name": "board_gate",      "where": "producer.produce_storyboard",
     "stops": "cutting any take marked take_problem or off its picture"},
    {"stage": "cut",      "name": "frozen_tails",    "where": "producer.produce_storyboard",
     "stops": "a shot that ends on a still frame (bounce instead of tpad)"},
    {"stage": "cut",      "name": "sfx_words",       "where": "producer.produce_storyboard",
     "stops": "a sound effect that came back as a voice (transcribes to words)"},
    {"stage": "cut",      "name": "_DANGLING_CUE",   "where": "producer.produce_storyboard",
     "stops": "a fragment sound cue before it is rendered"},
    # delivery (free)
    {"stage": "delivery", "name": "check_gates",     "where": "make_episode.make_episode", "needle": "check_gates",
     "stops": "a run on an engine where any law has been edited out"},
]


# ── pre-flight: the motion line ─────────────────────────────────────────────
# Actions gen4_turbo drops or invents on (measured over ep1's refused takes):
# lifting/carrying, running, shaking, turning around, walking toward camera,
# crowds/swarms, anything entering the frame.
RISKY = re.compile(r"\b(lift|lifts|lifting|raise|raises|carr(y|ies|ying)|run|runs|running|gallop|jump|jumps|leap|"
                   r"shake|shakes|shaking|turn(s|ing)? (around|to face|her body|his body)|"
                   r"walk(s|ing)? (toward|towards|to) (the )?camera|swarm|crowd|dozens|many small|"
                   r"splash|skid|tumble|roll(s|ing)? over|flies (up|away|off)|takes off)\b", re.I)
# Things that ask for something NEW to enter the frame: the model obliges with
# a stranger. Only an INDEFINITE newcomer counts ("a bird flies in", "another
# unicorn appears", "a second foal joins") — a cast member arriving, emerging
# or being revealed is her own shot and stays.
ARRIVAL = re.compile(r"\b(a|an|another|some|two|three|several|more|new)\s+(?:\w+\s+){0,3}?"
                     r"(enters?|entering|appears?|appearing|arrives?|arriving|comes? (?:in|into|out|along)|"
                     r"joins?|joining|emerges?|emerging|walks? (?:in|into|up)|flies (?:in|into|down)|lands?)\b"
                     r"|\ba (?:new|second|another) (?:unicorn|foal|dragon|bird|creature|character|animal)\b", re.I)


def motion_lint(motion: str, profile: dict | None = None) -> dict:
    """Return {"motion": cleaned, "risky": bool, "notes": [...]}.
    Cleans: names → species (de_name), arrivals removed, at most three sentences."""
    from .takecheck import de_name
    notes = []
    m = (motion or "").strip()
    if profile:
        m2 = de_name(m, profile)
        if m2 != m:
            notes.append("names replaced"); m = m2
    sents = [s.strip() for s in re.split(r"(?<=[.])\s+", m) if s.strip()]
    kept = []
    for s in sents:
        if ARRIVAL.search(s):
            notes.append(f"arrival dropped: {s[:50]}"); continue
        kept.append(s)
    if len(kept) > 3:
        notes.append(f"{len(kept)} sentences → 3"); kept = kept[:3]
    m = " ".join(kept)
    risky = bool(RISKY.search(m))
    if risky:
        notes.append("risky action → gentle first")
    return {"motion": m, "risky": risky, "notes": notes}


CALM = ("The camera holds completely still. The characters breathe and blink and shift their "
        "weight very slightly; leaves, flowers, light and dust drift gently. Nobody walks, "
        "turns or reaches.")


def motion_for_attempt(motion: str, attempt: int, profile: dict | None = None) -> tuple[str, dict]:
    """The motion line to send on try N (0-based). A risky action is asked for
    slowly and only a little on try 0; the last paid try always asks for
    almost nothing. Returns (line, lint)."""
    lint = motion_lint(motion, profile)
    m = lint["motion"] or CALM
    if lint["risky"]:
        ladder = [m + " Everything happens slowly and only a little; nothing else moves.", CALM, CALM]
    else:
        ladder = [m, m + " Everything happens slowly and only a little; nothing else moves.", CALM]
    return ladder[min(attempt, len(ladder) - 1)], lint


MAX_TAKE_SECONDS = 5      # HOUSE RULE (Lars, 2026-09-03): no clip and no video generation longer than 5 seconds


def take_seconds(need: float) -> int:
    """Always 5. A line that needs more than 5s of picture is a board fault
    (the board splits it into two shots); the cut may stretch ≤1.5× and bounce
    the tail, never buy a longer take."""
    return MAX_TAKE_SECONDS


# ── post: sound effects that came back as voices ────────────────────────────
_WORD = re.compile(r"[A-Za-z]{3,}")


def sfx_has_words(path) -> str:
    """'' if the clip is a sound; otherwise the words heard (a voice, not an
    effect). Uses the local faster-whisper model when present; never spends."""
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return ""
    try:
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(str(path), beam_size=1, vad_filter=True)
        text = " ".join(s.text for s in segs).strip()
    except Exception:
        return ""
    words = _WORD.findall(text)
    return text if len(words) >= 2 else ""


def mark(pn: dict, name: str, verdict) -> None:
    pn.setdefault("filters", {})[name] = verdict


def report(board: dict) -> dict:
    """What the chain did on this film, by filter."""
    out: dict = {}
    for p in board.get("panels") or []:
        for k, v in (p.get("filters") or {}).items():
            d = out.setdefault(k, {"shots": 0, "acted": 0})
            d["shots"] += 1
            if v and v not in ("ok", True):
                d["acted"] += 1
    return out
