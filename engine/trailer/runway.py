"""
Runway client — SCRPT's camera.

Auth note that costs people money: Runway's developer API (dev.runwayml.com)
has its OWN credit pool, entirely separate from an app.runwayml.com Standard/
Pro/Max subscription. A creative subscription buys you nothing here; the
organisation needs its own API credits.

Key is stored in settings as `runway_api_key`.
"""

import asyncio
from typing import Optional

import httpx

from ..database import get_setting, set_setting

BASE = "https://api.dev.runwayml.com/v1"
API_VERSION = "2024-11-06"          # Runway requires an explicit version header


def api_key() -> str:
    """Key comes from the environment first (RUNWAYML_API_SECRET, the name the
    official SDK expects), falling back to the settings table."""
    import os
    return (os.environ.get("RUNWAYML_API_SECRET")
            or get_setting("runway_api_key", "") or "").strip()


def configured() -> bool:
    return bool(api_key())


def _headers() -> dict:
    return {"Authorization": f"Bearer {api_key()}",
            "X-Runway-Version": API_VERSION,
            "Content-Type": "application/json"}


async def check_connection() -> dict:
    """Is the key valid, and does the organisation have credits?"""
    if not configured():
        return {"connected": False,
                "message": "No Runway API key set. Create one at "
                           "dev.runwayml.com and add credits there — an "
                           "app.runwayml.com subscription does NOT cover API use."}
    async with httpx.AsyncClient(timeout=30) as c:
        try:
            r = await c.get(f"{BASE}/organization", headers=_headers())
        except httpx.HTTPError as e:
            return {"connected": False, "message": str(e)[:200]}
    if r.status_code == 200:
        data = r.json()
        credits = (data.get("creditBalance") if isinstance(data, dict) else None)
        return {"connected": True, "credits": credits, "organization": data}
    return {"connected": False, "status": r.status_code,
            "message": r.text[:300]}


# Legal durations per video model. Anything else is snapped down to the
# nearest legal value so a treatment written in 4-5s beats still shoots.
MODEL_DURATIONS = {
    "gen4_turbo": (5, 10),
    "gen4.5": (5, 10),
    "veo3.1": (4, 6, 8),
    "veo3.1_fast": (4, 6, 8),
}


def snap_duration(model: str, seconds: int) -> int:
    legal = MODEL_DURATIONS.get(model, (5, 10))
    fits = [d for d in legal if d <= seconds]
    return max(fits) if fits else min(legal)


async def generate_shot(prompt: str, reference_image_url: str = "",
                        seconds: int = 5, ratio: str = "1280:720",
                        model: str = "gen4_turbo", audio: bool = False) -> dict:
    """Start one shot. Returns the task id; poll with `wait_for`.

    A reference image is what holds a character's face steady across shots —
    Gen-4 keeps identity from a single still, so SCRPT feeds the same
    character plate to every shot that person appears in.
    """
    if not configured():
        raise ValueError("Runway is not connected")
    duration = snap_duration(model, seconds)
    if model.startswith("veo") and ratio in ("1920:1080", "1080:1920"):
        duration = 8          # veo's 1080p classes only shoot 8-second takes
    body: dict = {"model": model, "promptText": prompt[:1000],
                  "duration": duration, "ratio": ratio}
    if model.startswith("veo"):
        body["audio"] = audio          # native dialogue/SFX/ambience
    endpoint = "/image_to_video" if reference_image_url else "/text_to_video"
    if reference_image_url:
        # the still is the FIRST FRAME; veo wants the array form
        body["promptImage"] = ([{"uri": reference_image_url, "position": "first"}]
                               if model.startswith("veo") else reference_image_url)
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}{endpoint}", headers=_headers(), json=body)
    raise_if_broke("Runway", r.status_code, r.text, "shooting")
    if r.status_code >= 300:
        raise RuntimeError(f"Runway rejected the shot ({r.status_code}): {r.text[:300]}")
    return r.json()


async def generate_seedance(prompt: str, reference_uris: list, seconds: int = 10,
                            ratio: str = "1280:720", model: str = "seedance2_5",
                            audio: bool = True) -> dict:
    """One native Seedance take on Runway: text_to_video with up to 30
    reference images (the world plate and the cast portraits), 4-30 s,
    480p/720p/1080p, audio generated with the picture."""
    if not configured():
        raise ValueError("Runway is not connected")
    body: dict = {"model": model, "promptText": prompt[:15000 if model == "seedance2_5" else 3500],
                  "duration": int(max(4, min(30 if model == "seedance2_5" else 15, seconds))),
                  "ratio": ratio, "audio": bool(audio)}
    refs = [u for u in (reference_uris or []) if u][:30 if model == "seedance2_5" else 9]
    if refs:
        body["references"] = [{"uri": u} for u in refs]
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}/text_to_video", headers=_headers(), json=body)
    raise_if_broke("Runway", r.status_code, r.text, "shooting")
    if r.status_code >= 300:
        raise RuntimeError(f"Runway rejected the Seedance take ({r.status_code}): {r.text[:300]}")
    return r.json()


async def wait_for(task_id: str, timeout_s: int = 600) -> dict:
    """Poll a task to completion. Video generation takes tens of seconds."""
    waited = 0
    misses = 0
    async with httpx.AsyncClient(timeout=30) as c:
        while waited < timeout_s:
            try:
                r = await c.get(f"{BASE}/tasks/{task_id}", headers=_headers())
            except httpx.HTTPError:
                # a dropped poll is not a failed generation — keep waiting
                misses += 1
                if misses > 8:
                    raise
                await asyncio.sleep(6)
                waited += 6
                continue
            misses = 0
            raise_if_broke("Runway", r.status_code, r.text, "shooting")
            if r.status_code >= 300:
                raise RuntimeError(f"Task poll failed ({r.status_code}): {r.text[:200]}")
            data = r.json()
            status = data.get("status")
            if status in ("SUCCEEDED", "FAILED", "CANCELLED"):
                return data
            await asyncio.sleep(6)
            waited += 6
    return {"status": "TIMEOUT", "id": task_id}


def estimate_cost(shots: int, seconds_each: int = 5) -> dict:
    """Runway bills per second of output. Retakes are the real cost driver."""
    per_second = 0.12
    base = shots * seconds_each * per_second
    return {"shots": shots, "seconds": shots * seconds_each,
            "first_pass_usd": round(base, 2),
            "realistic_usd": round(base * 2.5, 2),   # ~2-3 takes per shot
            "note": "Runway API credits are separate from an app subscription."}


# ── audio: the other half of a trailer ──────────────────────────

# ElevenLabs preset voices exposed through Runway. Chosen by genre; a
# `trailer_voice` setting overrides everything.
GENRE_VOICES = {
    "action_thriller": "Clint",      # deep, gravelled — the classic read
    "romance": "Eleanor",            # warm, intimate
    "default": "James",
}


def trailer_voice(genre_preset: str) -> str:
    override = (get_setting("trailer_voice", "") or "").strip()
    if override:
        return override
    for key, voice in GENRE_VOICES.items():
        if key in (genre_preset or ""):
            return voice
    return GENRE_VOICES["default"]


async def text_to_speech(text: str, preset_id: str,
                         stability: float = 0.35, style: float = 0.65,
                         speed: float = 0.9) -> dict:
    """eleven_v3 voice-over. ~1 credit per 50 characters. Supports inline
    audio tags like [whispers]; we mostly lean on punctuation and pacing."""
    body = {"model": "eleven_v3",
            "promptText": text[:2900],
            "voice": {"type": "runway-preset", "presetId": preset_id},
            "stability": stability, "style": style, "speed": speed,
            "useSpeakerBoost": True}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}/text_to_speech", headers=_headers(), json=body)
    raise_if_broke("Runway", r.status_code, r.text, "shooting")
    if r.status_code >= 300:
        raise RuntimeError(f"Runway TTS rejected ({r.status_code}): {r.text[:300]}")
    return r.json()


async def sound_effect(prompt: str, seconds: float = 0,
                       model: str = "eleven_text_to_sound_v2") -> dict:
    """One SFX or ambience cue. 1 credit per second with a duration."""
    body: dict = {"model": model, "promptText": prompt[:2900]}
    if seconds:
        body["duration"] = seconds
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}/sound_effect", headers=_headers(), json=body)
    raise_if_broke("Runway", r.status_code, r.text, "shooting")
    if r.status_code >= 300:
        raise RuntimeError(f"Runway SFX rejected ({r.status_code}): {r.text[:300]}")
    return r.json()


async def music_bed(brief: str, seconds: float) -> dict:
    """Trailer score from the treatment's music brief via seed_audio
    (text-to-audio: understands music description). 0.25 credits/second."""
    body = {"model": "seed_audio",
            "promptText": (f"Instrumental film-trailer score, no vocals, no "
                           f"speech, about {int(seconds)} seconds long with a "
                           f"continuous build. {brief}")[:2000],
            "outputFormat": "mp3"}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}/sound_effect", headers=_headers(), json=body)
    raise_if_broke("Runway", r.status_code, r.text, "shooting")
    if r.status_code >= 300:
        raise RuntimeError(f"Runway music rejected ({r.status_code}): {r.text[:300]}")
    return r.json()


async def download(url: str, dest) -> None:
    """Runway output URLs are ephemeral — pull the file down immediately."""
    from pathlib import Path
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)


async def credit_balance() -> int:
    info = await check_connection()
    return int(info.get("credits") or 0)


# ── uploads + the 4K finish ──────────────────────────────────────

async def upload_file(path) -> str:
    """Push a local file to Runway's ephemeral store; returns a runway://
    URI valid for 24 hours."""
    from pathlib import Path as _P
    path = _P(path)
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(f"{BASE}/uploads", headers=_headers(),
                         json={"filename": path.name, "type": "ephemeral"})
        raise_if_broke("Runway", r.status_code, r.text, "shooting")
        if r.status_code >= 300:
            raise RuntimeError(f"Upload init failed ({r.status_code}): {r.text[:200]}")
        d = r.json()
        files = {"file": (path.name, path.read_bytes())}
        r2 = await c.post(d["uploadUrl"], data=d.get("fields") or {}, files=files)
        if r2.status_code >= 300:
            raise RuntimeError(f"Upload failed ({r2.status_code}): {r2.text[:200]}")
    return d["runwayUri"]


async def video_upscale(video_uri: str, resolution: str = "4k",
                        creativity: int = 12) -> dict:
    """Magnific creative upscaler. Low creativity = faithful sharpening —
    the finish for an approved master, not a re-imagining. Billed per
    output frame: 4k ≈ 29 credits/second at 24fps."""
    body = {"model": "magnific_video_upscaler_creative",
            "videoUri": video_uri, "resolution": resolution,
            "creativity": creativity}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{BASE}/video_upscale", headers=_headers(), json=body)
    raise_if_broke("Runway", r.status_code, r.text, "shooting")
    if r.status_code >= 300:
        raise RuntimeError(f"Upscale rejected ({r.status_code}): {r.text[:300]}")
    return r.json()


async def text_to_image(prompt: str, ratio: str = "1920:1080",
                        reference_uris: Optional[list] = None,
                        model: str = "gen4_image") -> dict:
    """A keyframe still. Reference images (the cover art) hold palette,
    world and wardrobe across every shot. 5 cr at 720p, 8 cr at 1080p."""
    body: dict = {"model": model, "promptText": prompt[:1000], "ratio": ratio}
    if reference_uris:
        body["referenceImages"] = [{"uri": u, "tag": f"ref{i+1}"} for i, u in enumerate(reference_uris[:3])]
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}/text_to_image", headers=_headers(), json=body)
    raise_if_broke("Runway", r.status_code, r.text, "shooting")
    if r.status_code >= 300:
        raise RuntimeError(f"Runway still rejected ({r.status_code}): {r.text[:300]}")
    return r.json()
