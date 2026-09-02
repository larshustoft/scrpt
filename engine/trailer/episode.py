"""The bookends: the piece of the line that turns a cut into an EPISODE.

Every episode of every universe ends up here — intro in front, outro
behind, one level for the whole thing. It lives on its own so the shoot
path and a re-cut can both use it; it was inline in the router until
2026-08-31, which meant a re-cut could not reach it.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

from ..config import OUTPUT_DIR
from .. import database as db


def _ff() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _video_seconds(path: Path) -> float:
    """The PICTURE length, not the container's — a part whose audio runs
    long drags every part after it out of sync."""
    pr = subprocess.run([_ff(), "-i", str(path), "-map", "0:v", "-c", "copy",
                         "-f", "null", "-"], capture_output=True, text=True)
    ts = re.findall(r"time=(\d+):(\d+):([\d.]+)", pr.stderr)
    if not ts:
        return 0.0
    h, m, s = ts[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


def universe_bookends(catalog: str):
    """(intro, outro) for the universe this book belongs to."""
    root = Path(__file__).resolve().parents[2]
    v = db.get_setting("universes", "")
    reg = v if isinstance(v, dict) else json.loads(v or "{}")
    for u in reg.values():
        prof = json.loads((root / u["profile"]).read_text())
        if catalog not in (prof.get("members") or []):
            continue
        cr = prof.get("creatives") or {}
        ip, op = cr.get("show_intro"), cr.get("show_outro")
        intro = (root / ip) if ip and (root / ip).exists() else None
        outro = (root / op) if op and (root / op).exists() else None
        return intro, outro
    return None, None


def master_in_place(video: Path) -> bool:
    """ONE LEVEL FOR THE WHOLE EPISODE (Lars, 2026-08-31: the lullaby was
    15 dB under the story and vanished). Measured first, then applied
    exactly, so quiet scenes stay quiet in FEEL without disappearing."""
    FF = _ff()
    an = subprocess.run([FF, "-i", str(video), "-af",
                         "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
                         "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", an.stderr, re.S)
    if not m:
        return False
    d = json.loads(m.group(0))
    af = ("loudnorm=I=-14:TP=-1.5:LRA=11:"
          f"measured_I={d['input_i']}:measured_TP={d['input_tp']}:"
          f"measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}:"
          f"offset={d['target_offset']}:linear=true")
    tmp = video.with_name(video.stem + "-mastered.mp4")
    subprocess.run([FF, "-y", "-v", "error", "-i", str(video), "-af", af,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-ar", "48000", str(tmp)], check=True, timeout=1800)
    tmp.replace(video)
    return True


def attach_bookends(catalog: str, film: Path, handle=None) -> dict:
    """Intro in front, outro behind, then master. Free ffmpeg work."""
    out = {"intro_attached": False, "outro_attached": False, "mastered": False}
    intro, outro = universe_bookends(catalog)
    if not (intro or outro) or not film.exists():
        return out
    if handle:
        handle.progress(0.98, "premiere", "attaching intro and outro")
    FF = _ff()
    parts = [p for p in (intro, film, outro) if p]
    merged = film.with_name("film-with-bookends.mp4")
    ins, fc, labels = [], [], ""
    for i, p in enumerate(parts):
        ins += ["-i", str(p)]
        vl = _video_seconds(p)
        fc.append(f"[{i}:v]scale=1920:1080,fps=24,format=yuv420p[v{i}]")
        fc.append(f"[{i}:a]aresample=48000,apad,atrim=0:{vl:.3f}[a{i}]"
                  if vl > 0 else f"[{i}:a]aresample=48000[a{i}]")
        labels += f"[v{i}][a{i}]"
    fc.append(f"{labels}concat=n={len(parts)}:v=1:a=1[v][a]")
    subprocess.run([FF, "-y", "-v", "error", *ins,
                    "-filter_complex", ";".join(fc),
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
                    "-preset", "fast", "-crf", "18", "-c:a", "aac",
                    "-b:a", "192k", str(merged)], check=True, timeout=2400)
    if handle:
        handle.progress(0.99, "premiere", "mastering the sound")
    out["mastered"] = master_in_place(merged)
    merged.replace(film)
    out["intro_attached"] = bool(intro)
    out["outro_attached"] = bool(outro)
    return out


def archive_film_version(catalog: str, film: Path, label: str = "",
                         notes: str = "") -> dict:
    """Keep every finished cut. A film is re-cut many times — new score,
    new voices, a new script — and the only way to judge a change is to
    put the two versions side by side (Lars, 2026-08-31). The live file
    stays `film.mp4`; each finished cut is also copied to `film-vN.mp4`
    with its poster, and listed in the screening room forever."""
    import shutil
    from datetime import datetime
    from ..database import get_book_by_catalog, update_book
    book = get_book_by_catalog(catalog)
    if not book or not film.exists():
        return {}
    data = dict(book["data"])
    mv = dict(data.get("movie") or {})
    versions = list(mv.get("versions") or [])
    n = max([int(v.get("n") or 0) for v in versions] + [0]) + 1
    out = film.parent
    shutil.copy2(film, out / f"film-v{n}.mp4")
    poster = out / "film-poster.jpg"
    if poster.exists():
        shutil.copy2(poster, out / f"film-v{n}.jpg")
    rec = {"n": n, "label": label or f"cut {n}",
           "seconds": round(_video_seconds(film)),
           "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "notes": notes}
    versions.append(rec)
    mv["versions"] = versions
    data["movie"] = mv
    update_book(book["id"], data)
    return rec


def export_audiobook(catalog: str, film: Path) -> Path:
    """The audiobook edition of an episode IS the film's soundtrack.

    Lars, 2026-08-31: the acted multi-voice read with the theme, the score
    and the lullaby is a better listen than any flat narration — and it is
    already paid for by the time the film is mixed. Re-mastered a little
    quieter than the film, because audio-only listening has no picture to
    carry the loud moments."""
    if not film.exists():
        return None
    out = film.parent / "audiobook-episode.mp3"
    subprocess.run([_ff(), "-y", "-v", "error", "-i", str(film), "-vn",
                    "-af", "loudnorm=I=-18:TP=-2:LRA=11",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(out)],
                   check=True, timeout=1800)
    return out if out.exists() else None
