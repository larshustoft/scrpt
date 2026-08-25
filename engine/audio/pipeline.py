"""
SCRPT Audiobook Pipeline
=========================
manuscript -> narration script -> ElevenLabs TTS (chapter by chapter)
-> ffmpeg mastering to retail audiobook spec -> opening/closing credits
-> retail sample.

Target spec (ACX/industry): RMS between -23 and -18 dB, true peak <= -3 dB,
noise floor <= -60 dB RMS, 192+ kbps CBR MP3, 44.1 kHz. Each chapter is one
file; a <5 min retail sample is cut from chapter one.

ElevenLabs is accepted by Spotify/Findaway, Google Play, Kobo et al. — not by
ACX itself (Audible-side goes through KDP Virtual Voice instead). Disclosure
of AI narration is required on most platforms.
"""

import asyncio
import json
import shutil
import re
from pathlib import Path

import httpx

from ..config import OUTPUT_DIR
from ..database import get_book_by_catalog, get_setting, update_book
from ..jobs import JobHandle
from ..prose.models import AudioChapter, AudioState, Manuscript
from ..writing.parsing import blocks_to_text

ELEVEN_BASE = "https://api.elevenlabs.io/v1"
_RNNOISE = str(Path(__file__).resolve().parent / "models" / "std.rnnn")
MAX_CHUNK_CHARS = 4200          # per TTS request, split at paragraph boundaries
TARGET_LUFS = -19.0             # lands RMS comfortably inside -23..-18
TRUE_PEAK = -3.5
SAMPLE_MAX_S = 280              # retail sample < 5 minutes


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"  # PATH fallback


# ── narration script ─────────────────────────────────────────────

_ITALIC = re.compile(r"\*(.+?)\*")


def _clean_for_narration(text: str, pronunciation: dict[str, str]) -> str:
    t = _ITALIC.sub(r"\1", text)
    t = t.replace("***", "").replace("## ", "").replace("### ", "").replace("> ", "")
    for word, hint in pronunciation.items():
        t = re.sub(rf"\b{re.escape(word)}\b", hint, t)
    return t.strip()


def build_narration_script(book: dict, ms: Manuscript, voice_name: str) -> list[dict]:
    """Returns [{index, title, text}] — index 0 = opening credits, -1 = closing."""
    author = book["data"].get("author_name", "") or "the author"
    title = book["title"]
    pron = (book["data"].get("audio") or {}).get("pronunciation", {})

    # track 001 is the TigerWorks ident (copied in, not narrated); the book's
    # own opening credits are 002 and every chapter shifts up by two.
    segments = [{
        "index": 2,
        "title": "Opening credits",
        "text": f"{title}. Written by {author}.",
    }]
    written = 0
    for ch in ms.chapters:
        # an outlined-but-unwritten chapter has no text: narrating it would
        # produce a track that announces a chapter title and then stops
        if not ch.blocks:
            continue
        written += 1
        body = _clean_for_narration(blocks_to_text(ch.blocks), pron)
        announce = f"Chapter {ch.index}."
        if ch.title and ch.title.lower() != f"chapter {ch.index}":
            announce = f"Chapter {ch.index}. {ch.title}."
        segments.append({"index": ch.index + 2, "title": ch.title,
                         "text": f"{announce}\n\n{body}",
                         "first_chapter": written == 1})
    segments.append({
        "index": (segments[-1]["index"] if len(segments) > 1 else 1) + 1,
        "title": "Closing credits",
        "text": (f"This has been {title}, written by {author}. "
                 f"Narrated by {voice_name}. Thank you for listening."),
    })
    return segments


# ── TTS ──────────────────────────────────────────────────────────

def _split_chunks(text: str) -> list[str]:
    paras = text.split("\n\n")
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 > MAX_CHUNK_CHARS and cur:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


# best output format the account's tier allows — learned on first 403 and
# remembered for the session. SCRPT's ffmpeg mastering re-encodes to the
# retail 192kbps CBR spec regardless, so a lower source rate still ships.
_TTS_FORMATS = ["mp3_44100_192", "mp3_44100_128"]
_tts_format_index = 0


async def _tts_chunk(client: httpx.AsyncClient, api_key: str, voice_id: str,
                     model_id: str, text: str, out_path: Path,
                     prev_text: str = "", next_text: str = ""):
    global _tts_format_index
    while True:
        resp = await client.post(
            f"{ELEVEN_BASE}/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key},
            json={
                "text": text,
                "model_id": model_id,
                # request continuity context so chunk seams are inaudible
                "previous_text": prev_text[-600:] if prev_text else None,
                "next_text": next_text[:600] if next_text else None,
                "voice_settings": {"stability": 0.55, "similarity_boost": 0.75,
                                   "style": 0.25, "use_speaker_boost": True},
            },
            params={"output_format": _TTS_FORMATS[_tts_format_index]},
            timeout=300,
        )
        if (resp.status_code == 403 and "subscription_required" in resp.text
                and _tts_format_index < len(_TTS_FORMATS) - 1):
            _tts_format_index += 1  # drop to the tier's best format and retry
            continue
        if resp.status_code != 200:
            raise RuntimeError(f"ElevenLabs TTS failed ({resp.status_code}): {resp.text[:300]}")
        out_path.write_bytes(resp.content)
        return


async def _run_ffmpeg(*args: str):
    proc = await asyncio.create_subprocess_exec(
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.decode()[:400]}")


async def _concat_and_master(chunk_paths: list[Path], out_path: Path, tmp_dir: Path):
    """Concat chunks, then two-pass-style loudnorm to spec, 192k CBR 44.1k."""
    listfile = tmp_dir / "concat.txt"
    listfile.write_text("\n".join(f"file '{p.as_posix()}'" for p in chunk_paths))
    raw = tmp_dir / "raw.mp3"
    await _run_ffmpeg("-f", "concat", "-safe", "0", "-i", str(listfile),
                      "-c", "copy", str(raw))
    await _run_ffmpeg(
        "-i", str(raw),
        "-af", (f"highpass=f=70,arnndn=m={_RNNOISE}:mix=0.8,"
                f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11"),
        "-ar", "44100", "-b:a", "192k", "-codec:a", "libmp3lame",
        str(out_path),
    )
    raw.unlink(missing_ok=True)
    listfile.unlink(missing_ok=True)


async def _duration_s(path: Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        _ffmpeg(), "-i", str(path), "-f", "null", "-",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    m = re.search(r"time=(\d+):(\d+):(\d+\.?\d*)", stderr.decode())
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


# ── orchestrated job ─────────────────────────────────────────────

async def audition_sample(catalog: str, voice_id: str, voice_name: str = "") -> dict:
    """Narrate the book's actual opening (~2 paragraphs) in a candidate voice
    so the publisher casts on real material, not a stock preview."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError(f"Book {catalog} not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    ch1 = next((c for c in ms.chapters if c.blocks), None)
    if not ch1:
        raise ValueError("Nothing drafted yet to audition with")

    from ..routers.assistant import elevenlabs_key
    api_key = elevenlabs_key()
    if not api_key:
        raise ValueError("ElevenLabs API key is not configured")
    model_id = get_setting("elevenlabs_model_id", "eleven_multilingual_v2")

    paras = []
    for b in ch1.blocks:
        if getattr(b, "text", ""):
            paras.append(b.text)
        if sum(len(p) for p in paras) > 700:
            break
    text = _clean_for_narration("\n\n".join(paras)[:900], {})

    audio_dir = Path(OUTPUT_DIR) / catalog / "audiobook"
    audio_dir.mkdir(parents=True, exist_ok=True)
    out = audio_dir / f"audition-{_slug(voice_id)}.mp3"
    async with httpx.AsyncClient() as client:
        await _tts_chunk(client, api_key, voice_id, model_id, text, out)
    return {"file": out.name, "voice_id": voice_id, "voice_name": voice_name}


async def audiobook_job(handle: JobHandle, catalog: str) -> dict:
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError(f"Book {catalog} not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    if not ms.chapters or not any(c.blocks for c in ms.chapters):
        raise ValueError("Manuscript has no drafted chapters")

    from ..routers.assistant import elevenlabs_key
    api_key = elevenlabs_key()
    # the voice cast on the BOOK wins; the Settings voice is the house default
    cast = book["data"].get("audio") or {}
    voice_id = cast.get("voice_id") or get_setting("elevenlabs_voice_id", "")
    voice_name = (cast.get("voice_name")
                  or get_setting("elevenlabs_voice_name", "an AI voice"))
    model_id = get_setting("elevenlabs_model_id", "eleven_multilingual_v2")
    if not api_key or not voice_id:
        raise ValueError(
            "No narrator cast. Pick a voice in the book's Audiobook tab "
            "(or set a house default in Settings)."
        )

    audio_dir = Path(OUTPUT_DIR) / catalog / "audiobook"
    tmp_dir = audio_dir / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    state = AudioState.model_validate(book["data"].get("audio", {}))
    state.status = "scripting"
    state.voice_id, state.voice_name, state.model_id = voice_id, voice_name, model_id
    _persist(book, state)

    segments = build_narration_script(book, ms, voice_name)
    (audio_dir / "narration_script.json").write_text(
        json.dumps(segments, indent=2, ensure_ascii=False))

    state.status = "rendering"
    state.chapters = []
    _persist(book, state)

    # ── the house ident ──────────────────────────────────────────
    # Every TigerWorks audiobook opens on the same short audio logo. It is a
    # brand asset, not narration: rendered once, in the house voice, and
    # copied in front of every book so the sound is identical every time.
    done_files: list[AudioChapter] = []
    from .ident import ensure_ident
    ident_src = await ensure_ident() or Path.home() / ".scrpt" / "house" / "audiobook-intro.mp3"
    if ident_src and ident_src.exists() and ident_src.stat().st_size > 10_000:
        ident = audio_dir / "001_tigerworks.mp3"
        shutil.copy2(ident_src, ident)
        done_files.append(AudioChapter(
            index=1, title="TigerWorks", audio_path=str(ident),
            duration_s=await _duration_s(ident), chars=0))
        state.chapters = list(done_files)
        _persist(book, state)

    async with httpx.AsyncClient() as client:
        for n, seg in enumerate(segments):
            if handle.cancelled():
                return {}
            handle.progress(0.03 + 0.85 * n / len(segments), "tts",
                            f"Narrating: {seg['title'] or f'segment {n}'}")
            chunks = _split_chunks(seg["text"])
            chunk_paths = []
            for ci, chunk in enumerate(chunks):
                cp = tmp_dir / f"seg{seg['index']:03d}_c{ci:03d}.mp3"
                await _tts_chunk(
                    client, api_key, voice_id, model_id, chunk, cp,
                    prev_text=chunks[ci - 1] if ci > 0 else "",
                    next_text=chunks[ci + 1] if ci + 1 < len(chunks) else "",
                )
                chunk_paths.append(cp)

            out = audio_dir / f"{seg['index']:03d}_{_slug(seg['title'])}.mp3"
            await _concat_and_master(chunk_paths, out, tmp_dir)
            for cp in chunk_paths:
                cp.unlink(missing_ok=True)
            dur = await _duration_s(out)
            done_files.append(AudioChapter(
                index=seg["index"], title=seg["title"],
                audio_path=str(out), duration_s=dur, chars=len(seg["text"]),
            ))
            state.chapters = done_files
            state.total_duration_s = sum(c.duration_s for c in done_files)
            _persist(book, state)

    # retail sample: first chapters file (index 1), capped under 5 minutes
    handle.progress(0.92, "sample", "Cutting retail sample")
    first_idx = next((sg["index"] for sg in segments if sg.get("first_chapter")), None)
    first = next((c for c in done_files if c.index == first_idx), None)
    if first:
        sample = audio_dir / "retail_sample.mp3"
        await _run_ffmpeg("-i", first.audio_path, "-t", str(SAMPLE_MAX_S),
                          "-ar", "44100", "-b:a", "192k", "-codec:a", "libmp3lame",
                          str(sample))
        state.sample_path = str(sample)

    state.status = "mastered"
    state.mastered_dir = str(audio_dir)
    _persist(book, state)
    return {"chapters": len(done_files),
            "total_minutes": round(state.total_duration_s / 60, 1)}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "audio").lower()).strip("-")[:40] or "audio"


def _persist(book: dict, state: AudioState):
    data = dict(get_book_by_catalog(book["catalog_number"])["data"])
    data["audio"] = state.model_dump(mode="json")
    update_book(book["id"], data)
