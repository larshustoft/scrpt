"""
The narrator's desk: hear the opening of the book.

A few minutes of the first chapter, read by the house audiobook voice.
Two jobs in one: you hear what the audiobook will sound like, and the
opening — the pages that sell the sample — gets a fast quality check by
ear. Weak sentences hide on the page and stand up immediately when read
aloud.

Uses eleven_v3 through Runway (5000-character ceiling, so the preview is
a single take). ~1 credit per 50 characters: a full preview costs about
55 credits.
"""

from pathlib import Path
from typing import Optional

from .database import get_book_by_catalog, update_book, get_setting
from .prose.models import BlockType, Manuscript

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

TARGET_CHARS = 2700          # ~450 words, ~3 minutes read

# The house preview narrator: "Roy - Deep, Calm, Soothing" from the
# ElevenLabs library (the publisher's pick). A book with a CAST narrator
# is previewed by its own narrator instead, so what you hear is what
# ships; a settings override beats everything.
HOUSE_PREVIEW_VOICE = ("tyTP8F2QWIFGeIBiYTic", "Roy - Deep, Calm, Soothing")


def narrator_voice(book: dict) -> tuple:
    """Returns (voice_id, display_name) for the opening preview."""
    override = (get_setting("audiobook_preview_voice_id", "") or "").strip()
    if override:
        return override, get_setting("audiobook_preview_voice_name", "") or "Custom voice"
    audio = book["data"].get("audio") or {}
    if audio.get("voice_id"):
        return audio["voice_id"], audio.get("voice_name") or "Cast narrator"
    return HOUSE_PREVIEW_VOICE


def opening_text(catalog: str, max_chars: int = TARGET_CHARS) -> dict:
    """The start of chapter one, cut at a sentence boundary."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript") or {})
    first = next((c for c in ms.chapters if c.blocks), None)
    if not first:
        # a picture book's story lives in spreads, not chapters
        _sp = ((book["data"].get("childrens") or {}).get("spreads")) or []
        paras = [(s.get("text") or "").strip() for s in _sp
                 if (s.get("text") or "").strip()]
        if not paras:
            raise ValueError("The book has no written chapters yet")
    else:
        paras = [b.text for b in first.blocks
                 if b.type == BlockType.PARAGRAPH and (b.text or "").strip()]
    text = ""
    for p in paras:
        if text and len(text) + len(p) + 2 > max_chars:
            break
        text = f"{text}\n\n{p}".strip()
    # last resort: one giant opening paragraph — cut at a sentence end
    if len(text) > max_chars:
        cut = max(text.rfind(". ", 0, max_chars), text.rfind("! ", 0, max_chars),
                  text.rfind("? ", 0, max_chars))
        text = text[:cut + 1] if cut > 200 else text[:max_chars]

    if first is None:
        # a picture book reads straight through — title, then the story
        return {"chapter_title": "The story",
                "text": f"{book['title']}.\n\n{text}",
                "words": len(text.split())}
    intro = f"{book['title']}. Chapter one"
    if first.title:
        intro += f": {first.title}"
    return {"chapter_title": first.title, "text": f"{intro}.\n\n{text}",
            "words": len(text.split())}


async def preview(catalog: str, handle=None) -> dict:
    """Record the opening and park the mp3 next to the book's other files.

    Runs on ElevenLabs directly — the same rail as the narration desk — so
    the preview voice IS an audiobook voice, not a trailer announcer.
    """
    import httpx

    book = get_book_by_catalog(catalog)
    opening = opening_text(catalog)
    voice_id, voice_name = narrator_voice(book)
    api_key = get_setting("elevenlabs_api_key", "")
    if not api_key:
        raise RuntimeError("ElevenLabs is not configured (Settings)")
    model_id = get_setting("elevenlabs_model_id", "eleven_multilingual_v2")

    if handle:
        handle.progress(0.15, "recording", f"{voice_name.split(' - ')[0]} reads the opening")

    dest = OUTPUT_DIR / catalog / "audiobook-preview.mp3"
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key},
            json={"text": opening["text"], "model_id": model_id,
                  "voice_settings": {"stability": 0.55, "similarity_boost": 0.75,
                                     "style": 0.25, "use_speaker_boost": True}},
            params={"output_format": "mp3_44100_128"},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"ElevenLabs TTS failed ({resp.status_code}): {resp.text[:300]}")
        dest.write_bytes(resp.content)
    await studio_master(dest, dest, handle=handle)

    record = {"file": dest.name, "voice": voice_name, "voice_id": voice_id,
              "words": opening["words"],
              "chapter_title": opening["chapter_title"],
              "chars": len(opening["text"])}
    fresh = get_book_by_catalog(catalog)
    data = dict(fresh["data"])
    data["audiobook"] = {**(data.get("audiobook") or {}), "preview": record}
    update_book(fresh["id"], data)
    return record


CHUNK_CHARS = 4500      # per ElevenLabs request, split at paragraph boundaries


def chapter_text(catalog: str) -> dict:
    """All of chapter one, as paragraphs."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript") or {})
    first = next((c for c in ms.chapters if c.blocks), None)
    if not first:
        _sp = ((book["data"].get("childrens") or {}).get("spreads")) or []
        paras = [(s.get("text") or "").strip() for s in _sp
                 if (s.get("text") or "").strip()]
        if not paras:
            raise ValueError("The book has no written chapters yet")
        # a picture book reads straight through — no chapter announcement
        text = f"{book['title']}.\n\n" + "\n\n".join(paras)
        return {"chapter_title": "The story", "text": text,
                "words": len(text.split()), "chars": len(text)}
    paras = [b.text.strip() for b in first.blocks
             if b.type == BlockType.PARAGRAPH and (b.text or "").strip()]
    intro = f"{book['title']}. Chapter one"
    if first.title:
        intro += f": {first.title}"
    text = f"{intro}.\n\n" + "\n\n".join(paras)
    return {"chapter_title": first.title, "text": text, "words": len(text.split()), "chars": len(text)}


def _chunks(text: str, limit: int = CHUNK_CHARS) -> list:
    out, cur = [], ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) + 2 > limit:
            out.append(cur); cur = para
        else:
            cur = f"{cur}\n\n{para}".strip()
    if cur:
        out.append(cur)
    return out


async def record_chapter(catalog: str, handle=None) -> dict:
    """Record the whole of chapter one in the cast voice — chunked, with
    continuity context between chunks so the seams are inaudible — and
    joined into one mp3. Progress is real: one tick per chunk."""
    import httpx, subprocess
    import imageio_ffmpeg

    book = get_book_by_catalog(catalog)
    ch = chapter_text(catalog)
    voice_id, voice_name = narrator_voice(book)
    api_key = get_setting("elevenlabs_api_key", "")
    if not api_key:
        raise RuntimeError("ElevenLabs is not configured (Settings)")
    model_id = get_setting("elevenlabs_model_id", "eleven_multilingual_v2")
    chunks = _chunks(ch["text"])
    tdir = OUTPUT_DIR / catalog / "audio-preview"
    tdir.mkdir(parents=True, exist_ok=True)
    import json as _json
    # the live manifest: parts appear here as they are mastered, so the
    # publisher can start listening while the rest is still being read
    for old in tdir.glob("ready-*.mp3"):
        old.unlink(missing_ok=True)
    live = tdir / "live.json"
    def _publish(ready: list, done: bool):
        names = ([ident_part.name] if ident_part else []) + [r.name for r in ready]
        live.write_text(_json.dumps({"voice": voice_name, "total": len(chunks),
                                     "parts": names, "done": done,
                                     "chapter_title": ch["chapter_title"]}))
    ident_part = None
    ready: list = []
    # the house ident opens the preview exactly as it opens the audiobook, so
    # "Hear the opening" is what a listener actually hears on retail. It is a
    # finished asset: it rides in front of the parts without being mastered
    # with them, and stays out of `ready` so the join logic is unaffected.
    from .audio.ident import ensure_ident
    ident_src = await ensure_ident()
    if ident_src and ident_src.exists() and ident_src.stat().st_size > 10_000:
        import shutil as _shutil
        ident_part = tdir / "tigerworks.mp3"
        _shutil.copy2(ident_src, ident_part)
    _publish(ready, False)
    parts = []
    async with httpx.AsyncClient(timeout=300) as client:
        for i, text in enumerate(chunks):
            if handle:
                handle.progress(0.05 + 0.85 * i / len(chunks), "recording",
                                f"{voice_name.split(' - ')[0]} reads part {i + 1} of {len(chunks)}")
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": api_key},
                json={"text": text, "model_id": model_id,
                      "previous_text": chunks[i - 1][-600:] if i > 0 else None,
                      "next_text": chunks[i + 1][:600] if i + 1 < len(chunks) else None,
                      "voice_settings": {"stability": 0.55, "similarity_boost": 0.75,
                                         "style": 0.25, "use_speaker_boost": True}},
                params={"output_format": "mp3_44100_128"},
            )
            if resp.status_code != 200:
                raise RuntimeError(f"ElevenLabs TTS failed ({resp.status_code}): {resp.text[:300]}")
            part = tdir / f"part-{i:02d}.mp3"
            part.write_bytes(resp.content)
            parts.append(part)
            # master this part now and publish it to the live player
            rdy = tdir / f"ready-{i:02d}.mp3"
            try:
                studio = await studio_master(part, rdy, handle=None)
                ready.append(rdy)
                _publish(ready, False)
            except Exception:
                pass
    if handle:
        handle.progress(0.93, "joining", "joining the parts")
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    # the chapter file is the mastered parts joined (already at spec —
    # one loudness pass per part keeps the seams inaudible at this chain)
    join_src = ready if len(ready) == len(parts) else parts
    lst = tdir / "parts.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in join_src))
    dest = OUTPUT_DIR / catalog / "audiobook-chapter1.mp3"
    tmp = OUTPUT_DIR / catalog / ".audiobook-chapter1.tmp.mp3"
    r = subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", str(tmp)],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("join failed: " + r.stderr[-300:])
    import os
    os.replace(tmp, dest)
    if join_src is parts:
        studio = await studio_master(dest, dest, handle=handle)
    else:
        studio = {"isolated": False, "chain": STUDIO_CHAIN, "per_part": True}
    # the ident goes on AFTER mastering — it is already a finished asset and
    # must never be run through the narration chain
    if ident_part and ident_part.exists():
        lst2 = tdir / "with-ident.txt"
        lst2.write_text(f"file '{ident_part}'\nfile '{dest}'\n")
        tmp2 = OUTPUT_DIR / catalog / ".audiobook-chapter1.ident.mp3"
        r2 = subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst2),
                             "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", str(tmp2)],
                            capture_output=True, text=True, timeout=600)
        if r2.returncode == 0:
            os.replace(tmp2, dest)
    _publish(ready, True)
    import re
    pr = subprocess.run([ff, "-i", str(dest)], capture_output=True, text=True, timeout=60)
    m = re.search(r"Duration: (\d+):(\d+):(\d+)", pr.stderr)
    secs = (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))) if m else 0
    record = {"file": dest.name, "voice": voice_name, "voice_id": voice_id,
              "words": ch["words"], "chars": ch["chars"], "chapter_title": ch["chapter_title"],
              "seconds": secs, "parts": len(parts), "studio": studio}
    fresh = get_book_by_catalog(catalog)
    data = dict(fresh["data"])
    data["audiobook"] = {**(data.get("audiobook") or {}), "chapter1": record}
    update_book(fresh["id"], data)
    return record


# ── the studio chain ─────────────────────────────────────────────
RNNOISE_MODEL = str(Path(__file__).resolve().parent / "audio" / "models" / "std.rnnn")
# A read from a synthetic voice still carries whatever its source carried:
# room tone, hiss, a slightly uneven level. A studio fixes that after the
# read; so do we — with the lightest touch that works. 1) ElevenLabs Audio
# Isolation when the key allows it; 2) a rumble filter, RNNoise (a neural
# denoiser trained on speech: takes the floor under ACX's -60 dB with the
# voice's detail intact — FFT denoisers, gates and compressors all audibly
# squeezed or muffled the read, measured and rejected), then audiobook
# loudness (-19 LUFS, -3 dBTP).

STUDIO_CHAIN = ("highpass=f=70,"
                f"arnndn=m={RNNOISE_MODEL}:mix=0.8,"     # speech-trained denoiser: floor down, timbre intact
                "loudnorm=I=-19:TP=-3:LRA=11")


async def _isolate(src: Path, dest: Path) -> bool:
    """ElevenLabs Audio Isolation: background noise off the read."""
    import httpx
    api_key = get_setting("elevenlabs_api_key", "")
    if not api_key or (get_setting("audiobook_isolate", "1") or "1") != "1":
        return False
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            with open(src, "rb") as f:
                resp = await client.post("https://api.elevenlabs.io/v1/audio-isolation",
                                         headers={"xi-api-key": api_key},
                                         files={"audio": (src.name, f, "audio/mpeg")})
        if resp.status_code != 200 or len(resp.content) < 10_000:
            return False
        dest.write_bytes(resp.content)
        return True
    except Exception:
        return False


async def studio_master(src: Path, dest: Path, handle=None) -> dict:
    import subprocess, os
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    work = src.with_suffix(".isolated.mp3")
    if handle:
        handle.progress(0.94, "studio", "removing room noise")
    isolated = await _isolate(src, work)
    inp = work if isolated else src
    if handle:
        handle.progress(0.97, "studio", "mastering to audiobook spec")
    tmp = dest.with_suffix(".tmp.mp3")
    r = subprocess.run([ff, "-y", "-i", str(inp), "-af", STUDIO_CHAIN,
                        "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", str(tmp)],
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError("studio master failed: " + r.stderr[-300:])
    os.replace(tmp, dest)
    try:
        work.unlink(missing_ok=True)
    except Exception:
        pass
    return {"isolated": isolated, "chain": STUDIO_CHAIN}
