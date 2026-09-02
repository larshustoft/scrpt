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

MIN_MOTION = 0.6          # % of pixels that must change between frames, on average
DRIFT_FLOOR = 0.55        # a later frame must correlate with frame 0 at least this much

TAKE_QUESTIONS = (
    "Picture A is the approved still this shot was filmed from. Picture B is a "
    "frame from later in the same take. Answer JSON only: "
    '{"same_characters": true/false, "new_creature_or_person": true/false, '
    '"human": true/false, "mouth_speaking": true/false, "note": "..."}. '
    "same_characters is true only if every character in A is still in B, "
    "looking like the same character (same species, colours, size). "
    "new_creature_or_person is true if anyone appears in B who is not in A. "
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
