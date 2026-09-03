"""A take is judged on its whole length, not its first frame.

On 2026-09-02 every one of 135 takes opened exactly on its approved picture
and passed the gate — and by second two, some had a human girl painted in,
a yellow bear pulling the vine, a cartoon pony in place of Glitter. The
gate had measured the one frame the video model is forced to honour and
none of the frames it is free to invent.

So a take is now read at five points across its length. Frame 0 must be the
still. Every later frame must still be the same picture in structure, and
two of them are put to a reader with the still beside them: same
characters, nobody new, nobody human, no mouth moving as if speaking. A
take that barely moves at all is rejected too — on screen it is a
photograph. Anything that fails is filmed again; anything that keeps
failing stops the line and is named.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

# A CALM TAKE IS NOT A PHOTOGRAPH (2026-09-02). At 0.6% the judge refused the
# gentle takes it had itself asked for on the third try; 75 refusals in one
# pass, each a paid retry. A true still is ~0.0%; breathing and drifting
# light sit around 0.2–0.5%. The floor is where a photograph lives.
MIN_MOTION = 0.2          # % of pixels that must change between frames, on average
DRIFT_FLOOR = 0.55        # a later frame must correlate with frame 0 at least this much

TAKE_QUESTIONS = (
    "Picture A is the approved still this shot was filmed from. Picture B is a "
    "frame from later in the same take. Answer JSON only: "
    '{"same_characters": true/false, "new_creature_or_person": true/false, '
    '"duplicate": true/false, "human": true/false, "mouth_speaking": true/false, '
    '"unicorns_in_A": n, "unicorns_in_B": n, "dragons_in_A": n, "dragons_in_B": n, '
    '"birds_in_A": n, "birds_in_B": n, "note": "..."}. '
    "Count every unicorn, dragon and bird in each picture, including blurry, partial "
    "or background ones. "
    "same_characters is true only if every character in A is still in B, "
    "looking like the same character (same species, colours, size). "
    "new_creature_or_person is true if anyone appears in B who is not in A. "
    "duplicate is true if B shows MORE THAN ONE of any character that appears once in A "
    "— two of the same unicorn, two dragons, two birds — even if they look identical. "
    "human is true if any person, girl, boy or human body part is in B. "
    "mouth_speaking is true only for a mouth open mid-word as if talking, not "
    "a smile."
)


def _ff():
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration(video: Path) -> float:
    r = subprocess.run([_ff(), "-i", str(video)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def frame(video: Path, at: float, dest: Path, w: int = 512) -> bool:
    subprocess.run([_ff(), "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", str(video),
                    "-frames:v", "1", "-vf", f"scale={w}:-1", str(dest)],
                   capture_output=True, timeout=120)
    return dest.exists()


def motion_percent(video: Path) -> float:
    """Average % of pixels that change between consecutive frames."""
    out = subprocess.run([_ff(), "-i", str(video), "-vf",
                          "tblend=all_mode=difference,blackframe=amount=0:threshold=32",
                          "-f", "null", "-"], capture_output=True, text=True, timeout=300).stderr
    vals = [float(m) for m in re.findall(r"pblack:(\d+)", out)]
    return round(100.0 - (sum(vals) / len(vals)), 2) if vals else 0.0


async def check_take(clip: Path, still: Path, ask_vision=True) -> dict:
    """Return {"ok": bool, "reasons": [...], "motion": pct, "opens_on_still": corr}."""
    from .producer import _frame_signature, _sig_match
    reasons = []
    D = duration(clip)
    if D <= 0:
        return {"ok": False, "reasons": ["unreadable take"], "motion": 0, "opens_on_still": None}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        pts = [0.0, D * 0.25, D * 0.5, D * 0.75, max(0.0, D - 0.1)]
        frames = []
        for k, t in enumerate(pts):
            f = td / f"f{k}.png"
            frames.append(f if frame(clip, t, f) else None)
        if not frames[0]:
            return {"ok": False, "reasons": ["could not read frame 0"], "motion": 0, "opens_on_still": None}
        s_still = _frame_signature(still)
        s0 = _frame_signature(frames[0])
        opens = _sig_match(s0, s_still)
        if opens < DRIFT_FLOOR:
            reasons.append(f"does not open on its picture ({opens:.2f})")
        # structure must hold across the take
        for k, f in enumerate(frames[1:], 1):
            if f:
                c = _sig_match(_frame_signature(f), s0)
                if c < DRIFT_FLOOR:
                    reasons.append(f"the picture falls apart by {pts[k]:.1f}s ({c:.2f})")
                    break
        # it must actually move
        mo = motion_percent(clip)
        if mo < MIN_MOTION:
            reasons.append(f"barely moves ({mo:.1f}% of pixels change) — a photograph on screen")
        # and a reader looks at the middle and the end beside the still
        if ask_vision and not reasons:
            from ..writing.client import complete_vision, extract_json
            from PIL import Image
            for k in (2, 4):
                f = frames[k]
                if not f:
                    continue
                a = Image.open(still).convert("RGB"); b = Image.open(f).convert("RGB")
                h = 360; a = a.resize((int(a.width * h / a.height), h)); b = b.resize((int(b.width * h / b.height), h))
                pair = Image.new("RGB", (a.width + b.width + 12, h), (0, 0, 0))
                pair.paste(a, (0, 0)); pair.paste(b, (a.width + 12, 0))
                pp = td / f"pair{k}.png"; pair.save(pp)
                try:
                    raw = await complete_vision("You check animation takes against their approved still. JSON only.",
                                                "Picture A is on the left, picture B on the right. " + TAKE_QUESTIONS,
                                                pp.read_bytes())
                    d = extract_json(raw) or {}
                except Exception as e:
                    reasons.append(f"could not be checked: {str(e)[:60]}"); break
                if d.get("human"):
                    reasons.append(f"a human appears by {pts[k]:.1f}s"); break
                # STRANGERS BY COUNT (Lars, 2026-09-03: "made up extra
                # characters" — a pink pony behind Princess, a lion cub on
                # the path — passed the yes/no questions). Numbers do not
                # argue: more of a species in B than in A is a stranger.
                _more = [sp for sp in ("unicorns", "dragons", "birds")
                         if int(d.get(f"{sp}_in_B") or 0) > int(d.get(f"{sp}_in_A") or 0)]
                if _more:
                    reasons.append(f"more {', '.join(_more)} than the picture by {pts[k]:.1f}s: {str(d.get('note'))[:60]}"); break
                if d.get("duplicate"):
                    reasons.append(f"a character is doubled by {pts[k]:.1f}s: {str(d.get('note'))[:60]}"); break
                if d.get("new_creature_or_person"):
                    reasons.append(f"someone not in the picture appears by {pts[k]:.1f}s: {str(d.get('note'))[:60]}"); break
                if d.get("same_characters") is False:
                    reasons.append(f"a character changes by {pts[k]:.1f}s: {str(d.get('note'))[:60]}"); break
                if d.get("mouth_speaking"):
                    reasons.append(f"a mouth moves as if speaking by {pts[k]:.1f}s"); break
    return {"ok": not reasons, "reasons": reasons, "motion": mo, "opens_on_still": round(opens, 2)}


# NAMES SUMMON STRANGERS. "Princess turns her head" put a human princess into
# a take; "Pip pulls the vine" summoned a bear to do the pulling. The video
# model does not know the cast; it knows words. Motion lines are sent with
# every name replaced by what the picture already shows.
def de_name(motion: str, profile: dict) -> str:
    subs = ((profile.get("world") or {}).get("motion_names") or {
        "Princess": "the small unicorn foal", "Glitter": "the tall mother unicorn",
        "Moss": "the little teal dragon", "Pip": "the small blue bird"})
    out = motion
    for name, desc in subs.items():
        out = re.sub(rf"\b{re.escape(name)}'s\b", desc + "'s", out)
        out = re.sub(rf"\b{re.escape(name)}\b", desc, out)
    return out


def frozen_tail(clip: Path, min_seconds: float = 0.5) -> float:
    """Seconds of frozen picture at the END of a finished segment (0.0 = none).
    Law 53 (2026-09-03): a cut is scanned for freeze-frames, not watched for them."""
    import subprocess, re
    try:
        out = subprocess.run([_ff(), "-i", str(clip), "-vf", f"freezedetect=n=-50dB:d={min_seconds}",
                              "-an", "-f", "null", "-"], capture_output=True, text=True, timeout=120).stderr
    except Exception:
        return 0.0
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", out)]
    if not starts:
        return 0.0
    if len(ends) < len(starts):          # still frozen when the segment ended
        return round(max(0.0, duration(clip) - starts[-1]), 2)
    return 0.0


async def check_take_refs(clip: Path, plates: dict, cast: list, species: dict, ask_vision=True) -> dict:
    """Judge a REFERENCE-DRIVEN take (Seedance with the plates attached). Such
    a take composes its own frame, so 'opens on the still' does not apply;
    what must hold is identity — every character is the one on its plate,
    nobody else is in the shot, nothing is a human, and it moves."""
    reasons = []
    D = duration(clip)
    if D <= 0:
        return {"ok": False, "reasons": ["unreadable take"], "motion": 0}
    mo = motion_percent(clip)
    if mo < MIN_MOTION:
        reasons.append(f"barely moves ({mo:.1f}% of pixels change)")
    if reasons or not ask_vision:
        return {"ok": not reasons, "reasons": reasons, "motion": mo}
    from ..writing.client import complete_vision, extract_json
    from PIL import Image
    expected = {}
    for name in cast:
        sp = species.get(name) or species.get(str(name).lower()) or "creature"
        expected[sp] = expected.get(sp, 0) + 1
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        strip = []
        for name, pp in plates.items():
            try:
                im = Image.open(pp).convert("RGB"); im = im.resize((int(im.width * 300 / im.height), 300)); strip.append((name, im))
            except Exception:
                continue
        for t in (D * 0.5, max(0.0, D - 0.15)):
            f = td / f"f{int(t*10)}.png"
            if not frame(clip, t, f):
                continue
            fr = Image.open(f).convert("RGB"); fr = fr.resize((int(fr.width * 300 / fr.height), 300))
            W = sum(im.width for _, im in strip) + 24 * len(strip) + fr.width
            pair = Image.new("RGB", (W, 300), (255, 255, 255)); x = 0
            for _, im in strip:
                pair.paste(im, (x, 0)); x += im.width + 24
            pair.paste(fr, (x, 0)); pp2 = td / f"pair{int(t*10)}.png"; pair.save(pp2)
            names = ", ".join(n for n, _ in strip)
            try:
                raw = await complete_vision("You check an animation frame against approved character plates. JSON only.",
                    f"The pictures on the LEFT are the approved plates of: {names}. The picture on the RIGHT is a frame from a take that "
                    f"should show exactly these characters and nobody else: {', '.join(cast) or 'nobody'}. Answer: "
                    '{"each_matches_plate": true/false, "unicorns": n, "dragons": n, "birds": n, "humans": n, '
                    '"stranger": true/false, "note": "..."}. Count every creature in the RIGHT picture including blurry or partial ones; '
                    'each_matches_plate is false if any character on the right differs from its plate in species, colours, mane, horn, wings or markings.',
                    pp2.read_bytes())
                d = extract_json(raw) or {}
            except Exception as e:
                reasons.append(f"could not be checked: {str(e)[:60]}"); break
            if int(d.get("humans") or 0):
                reasons.append(f"a human appears by {t:.1f}s"); break
            if d.get("stranger"):
                reasons.append(f"someone not in the cast appears by {t:.1f}s: {str(d.get('note'))[:60]}"); break
            more = [sp for sp in ("unicorn", "dragon", "bird") if int(d.get(sp + "s") or 0) > expected.get(sp, 0)]
            if more:
                reasons.append(f"more {', '.join(more)}s than the cast by {t:.1f}s: {str(d.get('note'))[:60]}"); break
            if d.get("each_matches_plate") is False:
                reasons.append(f"a character is not its plate by {t:.1f}s: {str(d.get('note'))[:60]}"); break
    return {"ok": not reasons, "reasons": reasons, "motion": mo}
