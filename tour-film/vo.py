import asyncio, os, sys, httpx
from pathlib import Path
BOOKR = Path("/Users/tiger/Desktop/CATALOG ENGINE/bookr")
for line in (BOOKR / ".env").read_text().splitlines():
    if line.strip() and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
sys.path.insert(0, str(BOOKR)); sys.path.insert(0, str(Path(__file__).parent))
from engine.database import get_setting
from board import PANELS, END_VO

# HER voice — Jessica, the guide/assistant voice, with the commercial's tuned
# delivery (the raw-default rendering is what sounded wrong). Brian says only
# the end line, as always.
JESSICA = "cgSgspJ2msm6clMCkdW9"
BRIAN = "nPczCjzI2devNBz1zQrb"
KEY = get_setting("elevenlabs_api_key", "")
OUT = Path(__file__).parent

async def say(client, text, dest, voice, speed=0.95):
    if dest.exists():
        return
    text = text.replace("SCRPT", "Script")
    for a in range(4):
        r = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            headers={"xi-api-key": KEY},
            json={"text": text, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.45, "similarity_boost": 0.8,
                                     "style": 0.35, "use_speaker_boost": True,
                                     "speed": speed}},
            params={"output_format": "mp3_44100_128"})
        if r.status_code == 200:
            dest.write_bytes(r.content); print("vo", dest.name, flush=True); return
        if r.status_code == 429:
            await asyncio.sleep(2 * (a + 1)); continue
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")

async def main():
    async with httpx.AsyncClient(timeout=300) as c:
        for p in PANELS:
            if p.get("vo") and p.get("voz") != "native":
                await say(c, p["vo"], OUT / f"vo_{p['n']:02d}.mp3", JESSICA)
        await say(c, END_VO, OUT / "vo_end.mp3", BRIAN, speed=0.88)
    print("vo done", flush=True)

asyncio.run(main())
