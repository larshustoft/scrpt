"""
The house ident — the short audio logo that opens every audiobook.

Every publishing house gets its own, automatically: the name comes from the
Copyright holder in Settings, the line is written from it, and the whole
thing is rendered once and reused by every book. A new SCRPT install never
has to think about it — the first audiobook builds the ident on the way past.

The asset is deliberately OUTSIDE the book output tree (~/.scrpt/house), because
it belongs to the house, not to any one title.
"""

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Optional

import httpx
import imageio_ffmpeg

from ..database import get_setting, set_setting

HOUSE_DIR = Path.home() / ".scrpt" / "house"
IDENT = HOUSE_DIR / "audiobook-intro.mp3"
STING = HOUSE_DIR / "logo-music.mp3"

# Lily — velvety, warm, authoritative without being stiff. The house default;
# any voice in the account can be used instead.
DEFAULT_IDENT_VOICE = "pFZP5JQG7iQjIQuC4Bku"
DEFAULT_IDENT_VOICE_NAME = "Lily - Velvety Actress"

# The house shape, chosen by the publisher: a plain presentation line, then
# the promise. No article needed — the name follows "presented by".
LINE_TEMPLATE = "This audiobook is presented by {name}. Stories that travel with you."


def _article(name: str) -> str:
    """"An Olive Tree audiobook", not "A Olive Tree audiobook". Judged on the
    SOUND of the first word, not just the letter: a name opening on a long-U
    ("Universal", "Union") or a sounded-out "one" takes "A"."""
    w = re.sub(r"[^A-Za-z]", "", name.split()[0] if name.split() else "")
    if not w:
        return "A"
    low = w.lower()
    if low.startswith(("uni", "use", "user", "euro", "eu", "one", "once")):
        return "A"
    return "An" if low[0] in "aeiou" else "A"

# The bench for an ident: warm, composed, brand-carrying voices. Any voice in
# the account can be used instead — these are just the ones offered by default.
IDENT_VOICES = [
    {"id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily", "blurb": "Velvety British — the house default"},
    {"id": "Xb7hH8MSUJpSbSDYk0k2", "name": "Alice", "blurb": "Clear, engaging British"},
    {"id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda", "blurb": "Knowledgable, professional American"},
    {"id": "hpp4J3VqNfWAUOO0d1Us", "name": "Bella", "blurb": "Professional, bright, warm American"},
    {"id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel", "blurb": "Steady British broadcaster"},
    {"id": "nPczCjzI2devNBz1zQrb", "name": "Brian", "blurb": "Deep, resonant American"},
]

MUSIC_BRIEF = (
    "A short cinematic audio logo for a publishing house: one warm rising piano "
    "and string swell that blooms and resolves on a single sustained chord, "
    "intimate and confident, like the opening ident of a film studio. Five "
    "seconds. No drums, no vocals."
)

LEAD_IN = 0.9      # music alone before the voice lands
TAIL = 1.6         # the chord resolving after the last word


def house_name() -> str:
    """Whose house this is — the Copyright holder, and ONLY that.

    There is deliberately no fallback to the imprint name: silently branding
    the ident with a different name is worse than refusing to build one. That
    fallback once turned a TigerWorks ident into an "Olive Tree Publishing"
    ident the moment the Copyright holder was momentarily blank."""
    return (get_setting("copyright_holder", "") or "").strip()


def ident_line() -> str:
    """The words. A house that has written its own keeps them; otherwise the
    line is built from the house name."""
    custom = (get_setting("audiobook_ident_line", "") or "").strip()
    if custom:
        return custom
    name = house_name()
    return LINE_TEMPLATE.format(name=name) if name else ""


def ident_voice() -> tuple:
    return ((get_setting("audiobook_ident_voice_id", "") or DEFAULT_IDENT_VOICE),
            (get_setting("audiobook_ident_voice_name", "") or DEFAULT_IDENT_VOICE_NAME))


def _seconds(path: Path) -> float:
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def signature() -> str:
    """What the current ident should be made of. If this changes, the asset
    on disk is stale and gets rebuilt."""
    vid, _ = ident_voice()
    return f"{ident_line()}|{vid}"


def is_current() -> bool:
    return (IDENT.exists() and IDENT.stat().st_size > 10_000
            and get_setting("audiobook_ident_signature", "") == signature())


async def _record_voice(line: str, voice_id: str, dest: Path) -> None:
    from ..routers.assistant import elevenlabs_key
    key = elevenlabs_key()
    if not key:
        raise RuntimeError("ElevenLabs is not configured (Settings)")
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": key},
            json={"text": line,
                  "model_id": get_setting("elevenlabs_model_id", "") or "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.55, "similarity_boost": 0.8,
                                     "style": 0.25, "use_speaker_boost": True,
                                     "speed": 0.95}},
            params={"output_format": "mp3_44100_128"})
    if r.status_code != 200:
        raise RuntimeError(f"Ident voice failed ({r.status_code}): {r.text[:200]}")
    dest.write_bytes(r.content)


async def _make_sting() -> Optional[Path]:
    """The music bed. Generated once and kept forever — every rebuild of the
    words reuses it, so the house keeps one sound."""
    if STING.exists() and STING.stat().st_size > 10_000:
        return STING
    try:
        from ..trailer import runway
        if not runway.configured():
            return None
        task = await runway.music_bed(MUSIC_BRIEF, 8)
        res = await runway.wait_for(task["id"], timeout_s=300)
        url = (res.get("output") or [None])[0] if res.get("status") == "SUCCEEDED" else None
        if not url:
            return None
        await runway.download(url, STING)
        return STING if STING.exists() else None
    except Exception:
        return None      # a missing sting must never block the ident


async def build_ident(force: bool = False) -> dict:
    """Render the house ident. Returns a record describing what was made."""
    line = ident_line()
    if not line:
        raise RuntimeError(
            "Set the Copyright holder in Settings — the ident is named after it.")
    if not force and is_current():
        return {"built": False, "line": line, "file": str(IDENT),
                "seconds": round(_seconds(IDENT), 2), "reason": "already current"}

    HOUSE_DIR.mkdir(parents=True, exist_ok=True)
    voice_id, voice_name = ident_voice()
    # keep the outgoing take: a bad rebuild is then one copy away from undone
    if IDENT.exists() and IDENT.stat().st_size > 10_000:
        try:
            import shutil as _sh
            _sh.copy2(IDENT, HOUSE_DIR / "audiobook-intro.previous.mp3")
        except OSError:
            pass
    vo = HOUSE_DIR / "logo-vo.mp3"
    await _record_voice(line, voice_id, vo)
    sting = await _make_sting()

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    vlen = _seconds(vo) or 4.0
    total = round(LEAD_IN + vlen + TAIL, 2)
    tmp = HOUSE_DIR / ".ident.tmp.mp3"

    if sting:
        # music opens alone, the voice lands over it, both resolve together
        args = [ff, "-y", "-i", str(sting), "-i", str(vo), "-filter_complex",
                # The generated sting is written as a RISING swell, which peaks
                # exactly where the read ends — so the bed appeared to surge the
                # moment the voice stopped. Compressing it flat (measured: +6 dB
                # of swell -> 0.0) means the bed sits still under the voice and
                # can only ever fall away afterwards. The fade starts on the
                # last word, not at a fixed offset from the end.
                f"[0:a]atrim=0:{total},"
                f"acompressor=threshold=0.03:ratio=6:attack=200:release=800,"
                f"volume=1.15,afade=t=in:st=0:d=0.5,"
                f"afade=t=out:st={max(0.0, LEAD_IN + vlen):.2f}:d={TAIL:.2f}[m];"
                f"[1:a]adelay={int(LEAD_IN * 1000)}|{int(LEAD_IN * 1000)},volume=1.35[v];"
                # normalize=0 is the point: amix otherwise re-normalises the
                # remaining input when the voice track ends, so the music
                # jumped ~14 dB the instant the read finished. With it off the
                # bed simply keeps its own level and fades out.
                f"[m][v]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,"
                f"loudnorm=I=-16:TP=-1.5:LRA=11[a]",
                "-map", "[a]", "-t", f"{total}"]
    else:
        # no music engine: the words alone, still mastered to spec
        args = [ff, "-y", "-i", str(vo), "-af",
                f"adelay=300|300,apad=pad_dur=0.8,loudnorm=I=-16:TP=-1.5:LRA=11"]
    args += ["-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", str(tmp)]
    r = subprocess.run(args, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"Ident mix failed: {r.stderr[-300:]}")
    tmp.replace(IDENT)

    set_setting("audiobook_ident_signature", signature())
    set_setting("audiobook_ident_line", line)
    set_setting("audiobook_ident_voice_id", voice_id)
    set_setting("audiobook_ident_voice_name", voice_name)
    return {"built": True, "line": line, "voice": voice_name, "music": bool(sting),
            "file": str(IDENT), "seconds": round(_seconds(IDENT), 2)}


async def ensure_ident() -> Optional[Path]:
    """Called on the way into every audiobook. Builds the ident if the house
    has never made one (or the name/voice changed). Never raises: a book must
    still be narrated even if the ident cannot be made."""
    try:
        if is_current():
            return IDENT
        await build_ident()
        return IDENT if IDENT.exists() else None
    except Exception:
        return IDENT if (IDENT.exists() and IDENT.stat().st_size > 10_000) else None
