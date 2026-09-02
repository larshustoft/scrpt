"""The animatic: the whole film, cut and watchable, before anything is shot.

Nobody in animation animates before the edit is locked, because animation
is the expensive step and re-timing afterwards is how budgets die. Episode
1 was shot at fifteen minutes and only then discovered to be too long.

An animatic is the approved stills, held for exactly as long as their
lines take, with the real acted voices and the real score over them. It
costs no video credits at all. If the animatic is too long, or a shot
repeats, or a beat is confusing, it is found here — where fixing it is
free.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg

from ..config import OUTPUT_DIR


def _ff() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args, what):
    r = subprocess.run([_ff(), *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{what}: {r.stderr[-400:]}")


def build_animatic(catalog: str, board: dict, durations: list = None,
                   out_name: str = "animatic.mp4") -> Path:
    """Stills, each held for its own length, cut together silently.

    The voices and score are laid over it by the normal mix, so what you
    watch is the real edit — only the motion is missing.
    """
    tdir = Path(OUTPUT_DIR) / catalog / "trailer"
    work = tdir / "animatic"
    work.mkdir(parents=True, exist_ok=True)
    panels = board.get("panels") or []
    segs = []
    for i, pn in enumerate(panels):
        n = str(pn.get("n") or i + 1)
        img = tdir / str(pn.get("still") or pn.get("frame") or "")
        if not img.exists():
            continue
        secs = float((durations[i] if durations and i < len(durations)
                      else pn.get("dur") or 4))
        seg = work / f"a-{i:03d}.mp4"
        frames = max(12, int(round(secs * 24)))
        # a slow push keeps a still from reading as a freeze — the classic
        # animatic move, and it makes timing honest to watch
        vf = ("scale=2560:1440:force_original_aspect_ratio=increase,crop=2560:1440,"
              f"zoompan=z='min(1+0.06*on/{frames},1.06)':d={frames}:"
              "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps=24,"
              "format=yuv420p")
        _run(["-y", "-v", "error", "-loop", "1", "-i", str(img),
              "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
              "-vf", vf, "-frames:v", str(frames), "-t", f"{secs:.2f}", "-shortest",
              "-c:v", "h264_videotoolbox", "-b:v", "9M", "-allow_sw", "1",
              "-c:a", "aac", "-b:a", "96k", str(seg)], f"animatic {n}")
        segs.append(seg)
    if not segs:
        raise RuntimeError("No stills to build an animatic from")
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs))
    out = tdir / out_name
    _run(["-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c", "copy", str(out)], "animatic concat")
    return out
