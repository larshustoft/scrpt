#!/usr/bin/env python3
"""Shoot and cut the two ends of a Princess the Unicorn episode.

  opening — the film's first minute: show intro, then the first four
            storyboard shots of SC-039 scored with the theme
            continuation. Takes are shot with the producer's EXACT
            prompt/hash convention so the full film build later reuses
            every one of them for free.
  outro   — the universe-standard ending: Glitter tucks Princess in
            and sings The Unicorn Lullaby; Princess falls asleep just
            before the song ends; 2s TigerWorks card, done.

Run from the repo root with the engine PYTHONPATH. Reads the DB
read-only; take files are written with canonical names and no ledger
writes (the producer grandfathers pre-ledger takes).
"""
import asyncio
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        import os
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from engine.trailer import runway                     # noqa: E402
from engine.trailer.producer import _h, trailer_voice  # noqa: E402
from engine.trailer.bible import apply_cast, cast_of   # noqa: E402

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = ROOT / "universe/princess-the-unicorn"
CATALOG = "SC-039"
TDIR = ROOT / "output" / CATALOG / "trailer"
RATIO = "1280:720"
VO_SPEED = 0.88
GAP = 0.5
LEAD_IN = 3.0


def _book():
    db = sqlite3.connect(f"file:{ROOT}/data/scrpt.db?mode=ro", uri=True)
    row = db.execute("SELECT id, data FROM books WHERE catalog_number=?",
                     (CATALOG,)).fetchone()
    return {"id": row[0], "data": json.loads(row[1])}


def _probe_seconds(p: Path) -> float:
    r = subprocess.run([FF, "-i", str(p)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def _run(args):
    subprocess.run([FF, "-y", *args], check=True, capture_output=True)


async def _say(book, text: str, filename: str, speed: float,
               voice_override: str = "") -> Path:
    """One cached voice line — the producer's TTS verbatim, minus the
    DB ledger write (files with canonical names get grandfathered)."""
    dest = TDIR / filename
    if dest.exists() and dest.stat().st_size > 10_000:
        return dest
    from engine.database import get_setting
    voice_id = voice_override or trailer_voice(
        book["data"].get("genre_preset") or "", CATALOG)[0]
    api_key = get_setting("elevenlabs_api_key", "")
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key},
            json={"text": text,
                  "model_id": get_setting("elevenlabs_model_id",
                                          "eleven_multilingual_v2"),
                  "voice_settings": {"stability": 0.38,
                                     "similarity_boost": 0.8,
                                     "style": 0.65, "use_speaker_boost": True,
                                     "speed": speed}},
            params={"output_format": "mp3_44100_128"})
    if resp.status_code != 200:
        raise RuntimeError(f"voice failed ({resp.status_code}): {resp.text[:200]}")
    dest.write_bytes(resp.content)
    return dest


async def _shoot(prompt: str, refs: list, secs: int, clip: Path) -> Path:
    if clip.exists() and clip.stat().st_size > 10_000:
        print(f"  cached  {clip.name}")
        return clip
    r = await runway.generate_seedance(prompt, refs, seconds=secs, ratio=RATIO)
    t = await runway.wait_for(r["id"], timeout_s=1800)
    if t.get("status") != "SUCCEEDED" or not (t.get("output") or [None])[0]:
        raise RuntimeError(f"take failed: {t.get('failure')}")
    await runway.download(t["output"][0], clip)
    print(f"  shot    {clip.name}")
    return clip


async def _plate_uris(names):
    uris = {}
    for n in names:
        p = TDIR / "bible" / f"{n.lower()}.png"
        if p.exists():
            uris[n] = await runway.upload_file(p)
    return uris


# ── the opening ──────────────────────────────────────────────────

async def opening():
    book = _book()
    movie = book["data"]["movie"]
    sb = movie["storyboard"]
    style = sb["style"].strip()
    cast = cast_of(book)
    vc = movie.get("voice_cast") or {}
    panels = sb["panels"][:4]

    # voices first — panel lengths stretch to fit them
    vo_files, vo_durs, line_files = [], [], []
    for pn in panels:
        vo = (pn.get("vo") or "").strip()
        if vo:
            f = await _say(book, vo, f"vo-sb-{_h(vo)}-{VO_SPEED}.mp3", VO_SPEED)
            vo_files.append(f)
            vo_durs.append(_probe_seconds(f))
        else:
            vo_files.append(None)
            vo_durs.append(0.0)
        ln = pn.get("line") or {}
        text = (ln.get("text") or "").strip()
        if text:
            voice = (vc.get(ln.get("speaker")) or {}).get("id", "")
            sspeed = 1.0
            f = await _say(book, text, f"line-sb-{_h(text + voice)}-{sspeed}.mp3",
                           sspeed, voice_override=voice)
            line_files.append((f, 0.3, _probe_seconds(f)))
        else:
            line_files.append((None, 0.0, 0.0))

    # shoot — prompt built EXACTLY as produce_storyboard builds it
    char_uris = await _plate_uris({c for pn in panels
                                   for c in (pn.get("characters") or [])})
    plans = []
    for i, pn in enumerate(panels):
        want = float(pn.get("dur") or 3)
        lf, lgap, llen = line_files[i]
        spoken_end = (vo_durs[i] + lgap + llen + 0.45) if lf else 0.0
        off = LEAD_IN if i == 0 else 0.0
        need = off + max(want, (vo_durs[i] + GAP if vo_durs[i] else 0), spoken_end)
        secs = int(max(4, min(12, round(need + 0.6))))

        refs, who = [], ""
        for name in (pn.get("characters") or []):
            if char_uris.get(name):
                refs.append(char_uris[name])
                who += (f" {name} is the person in reference image {len(refs)} — "
                        f"exactly the same face, hair and build, in this scene.")
        frame = TDIR / (pn.get("frame") or "")
        if frame.exists():
            refs.append(await runway.upload_file(frame))
            who += (f" Reference image {len(refs)} is the storyboard frame for "
                    f"this exact shot: match its composition, framing, light "
                    f"and blocking — but every face comes from the earlier "
                    f"reference images, not from this frame.")
        shot_txt = apply_cast(pn.get("shot", "").strip(), cast)
        snd = (pn.get("sound") or "").strip()
        snd_txt = f" Sound: {snd}. No music, no speech, no voices." if snd else ""
        prompt = f"{shot_txt} {style} No text or lettering on screen.{snd_txt}{who}".strip()
        clip = TDIR / f"sb-{_h(prompt + RATIO + str(secs))}.mp4"
        plans.append({"i": i, "need": need, "off": off, "secs": secs,
                      "clip": clip, "prompt": prompt, "refs": refs,
                      "lf": lf, "lgap": lgap})

    b0 = await runway.credit_balance()
    await asyncio.gather(*[_shoot(p["prompt"], p["refs"], p["secs"], p["clip"])
                           for p in plans])
    b1 = await runway.credit_balance()
    print(f"opening takes cost {b0 - b1}, balance {b1}")

    # cut: each panel runs its need, hard film cuts, voices placed on time
    work = HERE / "work-opening"
    work.mkdir(exist_ok=True)
    segs = []
    for p, vf, vd in zip(plans, vo_files, vo_durs):
        i, need = p["i"], p["need"]
        seg = work / f"seg-{i}.mp4"
        af = ["-i", str(p["clip"])]
        # native take audio quiet under everything
        amix = f"[0:a]atrim=0:{need:.3f},asetpts=PTS-STARTPTS,volume=0.5[na]"
        chains, mixes = [amix], "[na]"
        n_in = 1
        if vf:
            af += ["-i", str(vf)]
            chains.append(f"[{n_in}:a]adelay={int(p['off']*1000)}|{int(p['off']*1000)}[vo]")
            mixes += "[vo]"
            n_in += 1
        if p["lf"]:
            at = (p["off"] + vd + p["lgap"]) if vf else (p["off"] + p["lgap"])
            af += ["-i", str(p["lf"])]
            chains.append(f"[{n_in}:a]adelay={int(at*1000)}|{int(at*1000)}[ln]")
            mixes += "[ln]"
            n_in += 1
        chains.append(f"{mixes}amix=inputs={n_in}:normalize=0,"
                      f"apad=whole_dur={need:.3f},atrim=0:{need:.3f}[aout]")
        _run([*af,
              "-filter_complex",
              f"[0:v]trim=0:{need:.3f},setpts=PTS-STARTPTS,"
              f"scale=1920:1080,fps=24,format=yuv420p[vout];" + ";".join(chains),
              "-map", "[vout]", "-map", "[aout]",
              "-c:v", "libx264", "-preset", "medium", "-crf", "18",
              "-c:a", "aac", "-ar", "48000", "-ac", "2", str(seg)])
        segs.append(seg)

    # concat the episode body plain — the score is laid over the FINAL cut so
    # it can start inside the intro's white fade (no dead air at the seam)
    ins, fc = [], ""
    for i, s in enumerate(segs):
        ins += ["-i", str(s)]
        fc += f"[{i}:v][{i}:a]"
    n = len(segs)
    fc += f"concat=n={n}:v=1:a=1[bv][ba]"
    body = work / "episode-open.mp4"
    _run([*ins, "-filter_complex", fc,
          "-map", "[bv]", "-map", "[ba]",
          "-c:v", "libx264", "-preset", "medium", "-crf", "18",
          "-c:a", "aac", "-ar", "48000", "-ac", "2", str(body)])

    # intro in front, then the theme continuation enters 1.8s BEFORE the
    # episode starts — inside the intro's fade-to-white — at natural tempo,
    # setting the scene under the narration and bowing out as dialogue lands
    intro = HERE / "show-intro-v8.mp4"
    theme = HERE / "theme/theme-continuation.mp3"
    ilen = _probe_seconds(intro)
    tlen = _probe_seconds(theme)
    t_at = max(0.0, ilen - 1.8)
    out = HERE / "film-opening-preview.mp4"
    _run(["-i", str(intro), "-i", str(body), "-i", str(theme),
          "-filter_complex",
          "[0:v]scale=1920:1080,fps=24,format=yuv420p[v0];"
          "[0:a]aresample=48000,aformat=channel_layouts=stereo[a0];"
          "[1:v]scale=1920:1080,fps=24,format=yuv420p[v1];"
          "[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];"
          "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][cat];"
          f"[2:a]aresample=48000,aformat=channel_layouts=stereo,"
          f"volume=0.45,afade=t=in:st=0:d=0.6,"
          f"afade=t=out:st={tlen-2.5:.3f}:d=2.5,"
          f"adelay={int(t_at*1000)}|{int(t_at*1000)}[sc];"
          "[cat][sc]amix=inputs=2:normalize=0[a]",
          "-map", "[v]", "-map", "[a]",
          "-c:v", "libx264", "-preset", "medium", "-crf", "18",
          "-c:a", "aac", "-b:a", "192k", str(out)])
    print("opening ->", out, f"({_probe_seconds(out):.1f}s)")


# ── the outro ────────────────────────────────────────────────────

OUTRO_SHOTS = [
    (9, "Wide shot of a cozy woodland bedroom at night, deep velvety blues, "
        "moonlight through a round window. Glitter gently pulls a soft leaf "
        "blanket over Princess, who is lying in a little moss bed, both "
        "facing the camera, warm and tender.",
     "hushed night-time room, the soft rustle of a blanket, faint crickets outside"),
    (9, "Medium shot beside the moss bed: Glitter lowers her head close to "
        "Princess and sings softly to her, mouth barely moving, eyes warm "
        "and loving. Princess blinks slowly, heavy-eyed, snuggled under the "
        "leaf blanket, both faces visible to the camera.",
     "hushed room tone, faint crickets, the tiniest chime of a silver bell"),
    (10, "Slow close-up of Princess's face on the pillow of moss: her "
         "sparkling violet eyes flutter, close gently, and she drifts to "
         "sleep with a tiny contented smile. Glitter's head lowers softly "
         "into frame beside her, watching over her sleeping foal.",
     "hushed night-time room, soft slow breathing, faint crickets"),
]


async def outro():
    book = _book()
    sb = book["data"]["movie"]["storyboard"]
    style = sb["style"].strip()
    cast = cast_of(book)
    takes_dir = HERE / "outro-takes"
    takes_dir.mkdir(exist_ok=True)

    char_uris = await _plate_uris(["Princess", "Glitter"])
    b0 = await runway.credit_balance()
    clips = []
    for secs, shot, snd in OUTRO_SHOTS:
        refs, who = [], ""
        for name in ("Princess", "Glitter"):
            if char_uris.get(name):
                refs.append(char_uris[name])
                who += (f" {name} is the person in reference image {len(refs)} — "
                        f"exactly the same face, hair and build, in this scene.")
        shot_txt = apply_cast(shot, cast)
        prompt = (f"{shot_txt} {style} No text or lettering on screen. "
                  f"Sound: {snd}. No music, no speech, no voices.{who}").strip()
        clip = takes_dir / f"ot-{_h(prompt + RATIO + str(secs))}.mp4"
        clips.append((clip, secs))
        await _shoot(prompt, refs, secs, clip)
    b1 = await runway.credit_balance()
    print(f"outro takes cost {b0 - b1}, balance {b1}")

    lullaby = HERE / "theme/lullaby-short-harp.mp3"
    llen = _probe_seconds(lullaby)          # ~26.1s
    X = 0.7                                  # dreamy crossfades
    raw = sum(s for _, s in clips)
    avail = [min(s, _probe_seconds(c)) - 0.25 for c, s in clips]
    net = sum(avail) - X * (len(clips) - 1)
    stretch = max(1.0, min(1.2, llen / net)) if net < llen else 1.0

    # uniform CFR segments first, then xfade on direct inputs
    work = HERE / "work-outro"
    work.mkdir(exist_ok=True)
    segs = []
    for i, ((c, _), av) in enumerate(zip(clips, avail)):
        seg = work / f"ot-seg-{i}.mp4"
        _run(["-i", str(c), "-filter_complex",
              f"[0:v]trim=0:{av:.3f},setpts=(PTS-STARTPTS)*{stretch:.4f},"
              f"scale=1920:1080,fps=24,format=yuv420p[v]",
              "-map", "[v]", "-an",
              "-c:v", "libx264", "-preset", "medium", "-crf", "18",
              "-r", "24", str(seg)])
        segs.append(seg)

    durs = [_probe_seconds(s) for s in segs]
    ins, fc = [], ""
    for i, s in enumerate(segs):
        ins += ["-i", str(s)]
    off1 = durs[0] - X
    off2 = off1 + durs[1] - X
    scene_len = off2 + durs[2]
    fade_at = max(llen - 1.2, scene_len - 1.2)
    fc = (f"[0:v][1:v]xfade=transition=fade:duration={X}:offset={off1:.3f}[x1];"
          f"[x1][2:v]xfade=transition=fade:duration={X}:offset={off2:.3f}[x2];"
          f"[x2]tpad=stop_mode=clone:stop_duration=6,trim=0:{llen:.3f},"
          f"setpts=PTS-STARTPTS,fade=t=out:st={llen-1.2:.3f}:d=1.2[vout];"
          f"[3:a]apad=whole_dur={llen:.3f},atrim=0:{llen:.3f}[aout]")
    scene = work / "outro-scene.mp4"
    _run([*ins, "-i", str(lullaby), "-filter_complex", fc,
          "-map", "[vout]", "-map", "[aout]",
          "-c:v", "libx264", "-preset", "medium", "-crf", "18",
          "-c:a", "aac", "-ar", "48000", "-ac", "2", "-r", "24", str(scene)])

    # 2s TigerWorks card, silent, then done
    card = HERE / "endcard-tigerworks.mp4"
    out = HERE / "episode-outro.mp4"
    _run(["-i", str(scene), "-i", str(card), "-filter_complex",
          "[0:v]scale=1920:1080,fps=24,format=yuv420p[v0];"
          "[0:a]aresample=48000,aformat=channel_layouts=stereo[a0];"
          "[1:v]scale=1920:1080,fps=24,format=yuv420p[v1];"
          "[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];"
          "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]",
          "-map", "[v]", "-map", "[a]",
          "-c:v", "libx264", "-preset", "medium", "-crf", "18",
          "-c:a", "aac", "-b:a", "192k", str(out)])
    print("outro ->", out, f"({_probe_seconds(out):.1f}s)")


if __name__ == "__main__":
    asyncio.run({"opening": opening, "outro": outro}[sys.argv[1]]())
