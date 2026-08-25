"""
Reference trailers: learn the craft of a trailer the publisher admires.

Given a YouTube link, SCRPT measures what makes that trailer work — its cut
rhythm, its voice-over register, its music shape, its visual grammar and
structure — and hands the director a REFERENCE block: "match this rhythm
and feel". Never its footage, never its words: craft, not content.

Pipeline: yt_dlp (small download) → ffmpeg scene-cut detection (pacing) →
Whisper transcription (VO register) → a contact sheet of frames read by the
vision model (look, camera, structure, end card).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

from ..config import OPENAI_API_KEY, OUTPUT_DIR
from ..database import get_book_by_catalog, update_book
from ..writing.client import complete_vision


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _download(url: str, dest_dir: Path) -> dict:
    import yt_dlp
    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480]/b",
        "outtmpl": str(dest_dir / "reference.%(ext)s"),
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "merge_output_format": "mp4",
        "ffmpeg_location": str(Path(_ffmpeg()).parent),
    }
    info = None
    last = None
    # YouTube's web client blocks scripted fetches; the app clients don't
    for clients in (["android"], ["ios"], ["tv"], ["mweb"]):
        try:
            with yt_dlp.YoutubeDL({**opts, "extractor_args": {"youtube": {"player_client": clients}}}) as y:
                info = y.extract_info(url, download=True)
            break
        except Exception as e:
            last = e
    if info is None:
        raise RuntimeError(f"YouTube refused every client: {str(last)[:120]}")
    files = sorted(dest_dir.glob("reference.*"), key=lambda p: p.stat().st_mtime)
    video = next((f for f in files if f.suffix in (".mp4", ".mkv", ".webm")), files[-1] if files else None)
    return {"title": info.get("title"), "duration": info.get("duration"),
            "channel": info.get("uploader"), "file": str(video) if video else None}


def _cuts(video: Path) -> list[float]:
    """Scene-change timestamps — the trailer's pulse."""
    proc = subprocess.run(
        [_ffmpeg(), "-i", str(video), "-vf", "select='gt(scene,0.32)',showinfo",
         "-an", "-f", "null", "-"], capture_output=True, text=True, timeout=600)
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", proc.stderr)]


def _contact_sheet(video: Path, out: Path, n: int = 12) -> Path:
    dur = 0.0
    proc = subprocess.run([_ffmpeg(), "-i", str(video)], capture_output=True, text=True, timeout=60)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.?\d*)", proc.stderr)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    step = max(dur / (n + 1), 0.5)
    subprocess.run(
        [_ffmpeg(), "-y", "-i", str(video),
         "-vf", f"fps=1/{step:.3f},scale=480:-1,tile=4x3", "-frames:v", "1", str(out)],
        capture_output=True, text=True, timeout=300)
    return out


def _audio(video: Path, out: Path) -> Path:
    subprocess.run([_ffmpeg(), "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                    "-b:a", "48k", str(out)], capture_output=True, text=True, timeout=300)
    return out


def _transcribe(audio: Path) -> str:
    if not OPENAI_API_KEY:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        with open(audio, "rb") as f:
            r = client.audio.transcriptions.create(model="whisper-1", file=f)
        return (getattr(r, "text", "") or "").strip()
    except Exception:
        return ""


async def analyze_reference(catalog: str, url: str) -> dict:
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    rdir = OUTPUT_DIR / catalog / "trailer" / "reference"
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _download, url, rdir)
    if not info.get("file"):
        raise RuntimeError("Could not download the reference video")
    video = Path(info["file"])
    cuts = await loop.run_in_executor(None, _cuts, video)
    sheet = await loop.run_in_executor(None, _contact_sheet, video, rdir / "sheet.png")
    audio = await loop.run_in_executor(None, _audio, video, rdir / "audio.mp3")
    transcript = await loop.run_in_executor(None, _transcribe, audio)

    dur = float(info.get("duration") or 0) or (cuts[-1] if cuts else 30.0)
    n_shots = len(cuts) + 1
    avg_shot = round(dur / max(n_shots, 1), 2)
    # pacing curve: shots per 10-second window
    buckets = {}
    for c in cuts:
        buckets[int(c // 10)] = buckets.get(int(c // 10), 0) + 1
    curve = [buckets.get(i, 0) for i in range(int(dur // 10) + 1)]

    analysis = {}
    try:
        raw = await complete_vision(
            "You are a trailer editor analysing a reference cut for craft, not content.",
            f"This contact sheet samples a {dur:.0f}-second trailer ('{info.get('title')}') "
            f"in order, left to right, top to bottom. It has about {n_shots} shots "
            f"(avg {avg_shot}s); cuts per 10s: {curve}. Voice-over transcript: "
            f"\"{transcript[:1200]}\".\n\n"
            "Describe the CRAFT so another director can match its rhythm and feel for a "
            "different story. Return JSON only: {"
            "\"structure\": \"acts and turns in 2-3 sentences\", "
            "\"pacing\": \"how shot length evolves, where it accelerates\", "
            "\"visual_grammar\": \"palette, light, camera moves, framing, how people are shown\", "
            "\"voice_register\": \"tone, sentence shape, how much VO vs silence\", "
            "\"music_shape\": \"instrumentation and how it builds\", "
            "\"sound_design\": \"hits, risers, silences\", "
            "\"end_card\": \"how it closes\", "
            "\"lessons\": [\"5 short rules to emulate\"]}",
            sheet.read_bytes(), max_tokens=1200)
        from ..writing.client import extract_json
        analysis = extract_json(raw) or {}
    except Exception as e:
        analysis = {"error": str(e)[:200]}

    record = {
        "url": url, "title": info.get("title"), "channel": info.get("channel"),
        "duration": dur, "shots": n_shots, "avg_shot_seconds": avg_shot,
        "pacing_curve": curve, "transcript": transcript[:2000],
        "analysis": analysis,
    }
    fresh = get_book_by_catalog(catalog)
    data = dict(fresh["data"])
    tr = dict(data.get("trailer") or {})
    tr["reference"] = record
    data["trailer"] = tr
    update_book(fresh["id"], data)
    # the source file is not kept — craft, not content
    try:
        video.unlink(missing_ok=True)
        audio.unlink(missing_ok=True)
    except Exception:
        pass
    return record


def reference_block(d: dict) -> str:
    """What the director reads: the reference's craft, as rules."""
    ref = (d.get("trailer") or {}).get("reference") or {}
    if not ref:
        return ""
    a = ref.get("analysis") or {}
    lessons = "\n".join(f"  - {l}" for l in (a.get("lessons") or []))
    return (
        f"\nREFERENCE TRAILER (match its rhythm and feel — never its content): "
        f"\"{ref.get('title')}\", {ref.get('duration', 0):.0f}s, ~{ref.get('shots')} shots, "
        f"avg {ref.get('avg_shot_seconds')}s per shot.\n"
        f"Structure: {a.get('structure', '')}\nPacing: {a.get('pacing', '')}\n"
        f"Look: {a.get('visual_grammar', '')}\nVoice: {a.get('voice_register', '')}\n"
        f"Music: {a.get('music_shape', '')}\nSound: {a.get('sound_design', '')}\n"
        f"Close: {a.get('end_card', '')}\nRules:\n{lessons}\n"
        "Plan the shot count and durations to land this rhythm inside the house format.\n"
    )
