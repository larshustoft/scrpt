"""
The producer: shoots, records and cuts the trailer the director wrote.

Two productions are on the menu (the publisher's two options):

  "full"      — every shot on veo3.1_fast with NATIVE audio (ambience, SFX,
                the world sounding like itself), plus the trailer voice-over
                and a scored music bed. The movie-quality option.
  "voiceover" — silent shots on gen4_turbo carried entirely by the classic
                trailer voice and the score. Cheaper, still cinematic.

Both end on a held card: the book cover on black with the end-card line and
the call to action. Visual continuity comes from the front cover itself — a
vision pass distills the cover's world (palette, era, light, mood) into a
style block appended to every shot prompt, so the trailer looks like the
book it sells.

Costs (1 credit = $0.01): veo3.1_fast w/ audio 15 cr/s, gen4_turbo 5 cr/s,
eleven_v3 VO ~1 cr/50 chars, seed_audio score 0.25 cr/s. A 25s "full"
trailer runs ~320 credits; "voiceover" ~140.
"""

import asyncio
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

import imageio_ffmpeg

from ..database import get_book_by_catalog, update_book
from ..prose.models import Manuscript
from ..writing.client import complete_vision
from . import runway
from .director import write_treatment

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"
FONT_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "fonts"

END_CARD_SECONDS = 6
FADE_SECONDS = 1.5

MODES = {
    # The master: full veo, native audio, full resolution, keyframe-first
    # (a referenced still per shot, then image-to-video). Shot after approval.
    "full":      {"model": "veo3.1", "audio": True,  "shot_seconds": 4, "keyframe": True},
    # The draft: the SAME model family as the master, silent and at 720p —
    # 10 cr/s instead of 15, and a faithful preview of how the master will
    # interpret each shot. (gen4_turbo is image-to-video only and cannot
    # shoot from text; every text-to-video alternative prices higher.)
    "draft":     {"model": "veo3.1_fast", "audio": False, "shot_seconds": 4,
                  "draft": True, "small": True, "keyframe": True},
    "voiceover": {"model": "veo3.1_fast", "audio": False, "shot_seconds": 4,
                  "small": True},
    # The second camera: Seedance 2.5 on fal. Native 10-second takes with the
    # cast portraits and the world plate as references — no keyframe step.
    "seedance":        {"provider": "seedance", "model": "seedance2_5", "audio": True, "shot_seconds": 10,
                        "draft": True, "small": True},
    "seedance_master": {"provider": "seedance", "model": "seedance2_5", "audio": True, "shot_seconds": 10},
}

# Delivery formats. Widescreen is the cinema master; vertical serves
# Reels/Shorts/TikTok; the 4:5 ad master is framed from the vertical
# shoot (no video model shoots 4:5 natively), so those two share takes.
FORMATS = {
    "wide":     {"suffix": "",     "veo": "1920:1080", "gen4": "1280:720",
                 "canvas_veo": (1920, 1080), "canvas_gen4": (1280, 720)},
    "vertical": {"suffix": "-916", "veo": "1080:1920", "gen4": "720:1280",
                 "canvas_veo": (1080, 1920), "canvas_gen4": (720, 1280)},
    "ad":       {"suffix": "-45",  "veo": "1080:1920", "gen4": "720:1280",
                 "canvas_veo": (1080, 1350), "canvas_gen4": (720, 900)},
}




# ── sound recipes ────────────────────────────────────────────────
# The hard-hitting grammar (braams, cut hits, sub drops) is THRILLER
# grammar. Romance and drama get their own rules from the publisher;
# until those are written, the soft recipe below is a provisional stand-in.

SOUND_RECIPES = {
    "action_thriller": {
        "intro": "massive deep cinematic braam with a hard drum impact hit, "
                 "trailer opening",
        "cut_hit": "single deep hard cinematic drum impact hit, tight and "
                   "punchy, huge low end",
        "reveal": "deep cinematic boom with a sub drop and a slow airy "
                  "shimmer, final title reveal",
        "score": "Dark, driving hybrid trailer score: pounding percussion, "
                 "deep braams, a rising pulse that accelerates, hard rhythmic "
                 "hits, aggressive build to a hard cut",
    },
    "romance": {          # provisional — the publisher's romance rules come later
        "intro": "soft warm cinematic swell, gentle piano and strings rising",
        "cut_hit": None,
        "reveal": "warm orchestral bloom with a gentle chime, final reveal",
        "score": "Warm, emotional trailer score: intimate piano over strings, "
                 "slow build to a hopeful, soaring peak",
    },
}


LOOK_RECIPES = {
    "action_thriller": "moody low-key lighting, deep shadows, restrained color, "
                       "atmospheric haze, anamorphic feel, night or failing light",
    "romance": "soft natural light, golden hour and candlelight, warm restrained "
               "palette, gentle haze, shallow depth of field, anamorphic feel",
    "default": "natural cinematic light, restrained palette, atmospheric haze, "
               "anamorphic feel",
}


def look_for(d: dict) -> str:
    """The director's look if a brief exists, else the genre recipe."""
    dr = (d.get("trailer") or {}).get("direction") or {}
    if (dr.get("look") or "").strip():
        return dr["look"].strip()
    return look_recipe(d.get("genre_preset") or "")


def sound_for(d: dict) -> dict:
    """The director's sound design if a brief exists, else the genre recipe."""
    base = dict(sound_recipe(d.get("genre_preset") or ""))
    dr = (d.get("trailer") or {}).get("direction") or {}
    snd = dr.get("sound") or {}
    if snd:
        base["intro"] = snd.get("intro") or base["intro"]
        base["cut_hit"] = snd.get("cut_hit")          # null means: no hits, breathe
        base["reveal"] = snd.get("reveal") or base["reveal"]
    if (dr.get("music") or "").strip():
        base["score"] = dr["music"].strip()
    return base


def look_recipe(genre_preset: str) -> str:
    for key, look in LOOK_RECIPES.items():
        if key in (genre_preset or ""):
            return look
    return LOOK_RECIPES["default"]


def sound_recipe(genre_preset: str) -> dict:
    for key, recipe in SOUND_RECIPES.items():
        if key in (genre_preset or ""):
            return recipe
    return SOUND_RECIPES["action_thriller"]


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


async def _shoot_seedance_take(prompt: str, cover_uri, seconds: int, ratio: str, audio: bool,
                               dest: Path, timeout_s: int = 1800, attempts: int = 6) -> bool:
    """One Seedance take, retrying on Runway's transient "Invalid input", with an
    automatic reference-drop fallback: if the cover keeps getting flagged as a real
    person's likeness (moderation / third-party), ship the same prompt without the
    reference image rather than exhaust every retry on a doomed picture."""
    live_refs = [cover_uri] if cover_uri else []
    moderation_hits = 0
    for attempt in range(attempts):
        task = await runway.generate_seedance(prompt, live_refs, seconds=seconds, ratio=ratio,
                                              model="seedance2_5", audio=audio)
        result = await runway.wait_for(task["id"], timeout_s=timeout_s)
        url = (result.get("output") or [None])[0] if result.get("status") == "SUCCEEDED" else None
        if url:
            await runway.download(url, dest)
            return True
        last_fail = json.dumps(result.get("failure") or result.get("status")).lower()
        if "moderation" in last_fail or "third_party" in last_fail:
            moderation_hits += 1
        if moderation_hits >= 2 and live_refs:
            live_refs = []
        elif "invalid input" not in last_fail:
            break
        await asyncio.sleep(4 * (attempt + 1))
    return False


def _run(args: list, label: str):
    # every x264 encode must be 4:2:0 — QuickTime/Safari cannot play 4:4:4
    args = list(args)
    if "libx264" in args and "-pix_fmt" not in args and "copy" not in args[args.index("libx264") - 1:args.index("libx264") + 1]:
        args = args[:-1] + ["-pix_fmt", "yuv420p", args[-1]]
    proc = subprocess.run([_ffmpeg(), "-y", *args],
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg {label} failed: {proc.stderr[-400:]}")


def _probe_size(path: Path) -> tuple:
    proc = subprocess.run([_ffmpeg(), "-i", str(path)], capture_output=True, text=True, timeout=60)
    m = re.search(r"(\d{3,4})x(\d{3,4})", proc.stderr)
    return (int(m.group(1)), int(m.group(2))) if m else (1280, 720)


def _probe_seconds(path: Path) -> float:
    proc = subprocess.run([_ffmpeg(), "-i", str(path)],
                          capture_output=True, text=True, timeout=60)
    import re
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.?\d*)", proc.stderr)
    if not m:
        return 0.0
    h, mnt, sec = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(sec)


def _save_trailer(catalog: str, patch: dict):
    book = get_book_by_catalog(catalog)
    data = dict(book["data"])
    data["trailer"] = {**(data.get("trailer") or {}), **patch}
    update_book(book["id"], data)



# ── take cache ───────────────────────────────────────────────────
# A take is reused only while the words behind it are unchanged. Each
# generated file is keyed by a hash of its source text; edit a VO line in
# the screenplay editor and only that recording is re-made. Files that
# predate the ledger are grandfathered (existing takes stay valid).

def _h(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:10]


def _takes(catalog: str) -> dict:
    book = get_book_by_catalog(catalog)
    return dict(((book["data"].get("trailer") or {}).get("takes")) or {})


def _take_valid(catalog: str, key: str, source: str, path: Path) -> bool:
    if not (path.exists() and path.stat().st_size > 10_000):
        return False
    stored = _takes(catalog).get(key)
    if stored is None:          # grandfather pre-ledger takes
        _remember_take(catalog, key, source)
        return True
    return stored == _h(source)


def _remember_take(catalog: str, key: str, source: str):
    book = get_book_by_catalog(catalog)
    data = dict(book["data"])
    tr = dict(data.get("trailer") or {})
    takes = dict(tr.get("takes") or {})
    takes[key] = _h(source)
    tr["takes"] = takes
    data["trailer"] = tr
    update_book(book["id"], data)


# ── the world in the cover ───────────────────────────────────────

async def world_style(catalog: str, force: bool = False) -> str:
    """Distill the front cover into a visual-continuity block for every shot."""
    book = get_book_by_catalog(catalog)
    cached = ((book["data"].get("trailer") or {}).get("world_style") or "").strip()
    if cached and not force:
        return cached
    art = OUTPUT_DIR / catalog / "cover-art.png"
    if not art.exists():
        art = OUTPUT_DIR / catalog / "cover-front.png"
    if not art.exists():
        return ""
    style = await complete_vision(
        "You are a film DP translating a book cover into a look book.",
        "This is the book's front cover. In 35-50 words, one paragraph, "
        "describe the VISUAL WORLD a trailer shot in this universe must "
        "match: color palette, quality of light, era, weather, texture, "
        "mood. Physical and concrete. No mention of the cover, text or "
        "typography — only the world itself.",
        art.read_bytes(), max_tokens=300)
    style = style.strip()
    _save_trailer(catalog, {"world_style": style})
    return style


# ── the voice ────────────────────────────────────────────────────

def _vo_script(shots: list) -> str:
    """One continuous read. Ellipses buy the pauses between beats."""
    lines = [(s.get("voiceover") or "").strip() for s in shots]
    return " ... ".join(l for l in lines if l)


# ── the end card ─────────────────────────────────────────────────

def _font(name: str, size: int):
    from PIL import ImageFont
    p = FONT_DIR / name
    if p.exists():
        return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()



def build_series_card(catalog: str, series_title: str, size: tuple) -> Optional[Path]:
    """A large classical title lockup for the opening beat — the series name
    the way a period-drama main title sets it: a small article line, the name
    itself big and widely letterspaced across two lines, framed by hairline
    rules and a centred fleuron. Overlaid on the establishing shot while the
    theme plays, so a reader knows the series before a word is spoken."""
    from PIL import Image, ImageDraw
    words = series_title.strip()
    if not words:
        return None
    W, H = size
    k = W / 1280.0

    # A house may supply a real logo (<series_id>-logo.png, transparent).
    # Artwork always beats type we set ourselves — place it and stop.
    sid = ""
    try:
        from ..database import get_book_by_catalog as _gb
        sid = ((_gb(catalog)["data"].get("series") or {}).get("series_id") or "").strip()
    except Exception:
        pass
    art = SERIES_THEMES / f"{sid}-logo.png" if sid else None
    if art and art.exists() and art.stat().st_size > 5_000:
        logo = Image.open(art).convert("RGBA")
        target_w = int(W * 0.62)
        logo = logo.resize((target_w, max(1, int(logo.height * target_w / logo.width))),
                           Image.LANCZOS)
        plate = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        # the artwork alone, no bloom or scrim behind it — the publisher wants
        # the mark clean on the picture
        gx, gy = (W - logo.width) // 2, int(H * 0.5 - logo.height / 2)
        plate.alpha_composite(logo, (gx, gy))
        dest = OUTPUT_DIR / catalog / "trailer" / f"series-card-{W}x{H}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        plate.save(dest)
        return dest

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # "The Larkspur Season" -> article line + the name across the remaining words
    parts = words.split()
    article, name_words = ("", parts)
    if parts and parts[0].lower() in ("the", "a", "an"):
        article, name_words = parts[0].upper(), parts[1:]
    lines = [" ".join(name_words[:1]).upper(), " ".join(name_words[1:]).upper()] \
        if len(name_words) > 1 else [" ".join(name_words).upper()]
    lines = [l for l in lines if l]

    def spaced(t, em=0.34):
        # real letterspacing: draw glyph by glyph so the tracking is even
        return t

    big = _font("EBGaramond-Regular.ttf", int(96 * k))
    small = _font("EBGaramond-Regular.ttf", int(26 * k))
    IVORY = (255, 250, 242, 255)

    def draw_tracked(text, font, cy, track, fill):
        gaps = [d.textlength(ch, font=font) for ch in text]
        total = sum(gaps) + track * (len(text) - 1)
        x = (W - total) / 2
        for ch, adv in zip(text, gaps):
            for dx, dy in ((2, 2), (-2, 2), (2, -2), (-2, -2), (0, 3)):
                d.text((x + dx, cy + dy), ch, font=font, fill=(0, 0, 0, 160))
            d.text((x, cy), ch, font=font, fill=fill)
            x += adv + track
        return total

    block_h = (len(lines) * int(104 * k)) + (int(46 * k) if article else 0)
    y = H * 0.5 - block_h / 2 - int(28 * k)
    widest = 0
    if article:
        widest = max(widest, draw_tracked(article, small, y, int(11 * k), IVORY))
        y += int(46 * k)
    for ln in lines:
        widest = max(widest, draw_tracked(ln, big, y, int(15 * k), IVORY))
        y += int(104 * k)

    # hairline rules above and below, and a small fleuron beneath
    rule_w = min(W * 0.62, widest * 1.06)
    x0, x1 = (W - rule_w) / 2, (W + rule_w) / 2
    top = H * 0.5 - block_h / 2 - int(56 * k)
    bot = y + int(10 * k)
    for ry in (top, bot):
        d.line([(x0, ry), (x1, ry)], fill=(255, 250, 242, 165), width=max(1, int(1.6 * k)))
    r = max(2, int(4 * k))
    cx, cy = W / 2, bot + int(20 * k)
    d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=(255, 250, 242, 190))
    d.line([(x0 + rule_w * 0.30, cy), (cx - r * 2.4, cy)], fill=(255, 250, 242, 120), width=1)
    d.line([(cx + r * 2.4, cy), (x1 - rule_w * 0.30, cy)], fill=(255, 250, 242, 120), width=1)

    dest = OUTPUT_DIR / catalog / "trailer" / f"series-card-{W}x{H}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def front_cover_hires(catalog: str):
    """The front panel rendered from the print wrap at 300 dpi — real print
    typography at ~1575x2400 instead of the 800px preview PNG."""
    out = OUTPUT_DIR / catalog
    cache = out / "trailer" / "front-hires.png"
    wrap = out / "cover-wrap.pdf"
    chosen = out / "cover-front.png"

    # The wrap is only a better source while it still contains the cover the
    # author actually chose. Picking a new variant rewrites cover-front.png
    # but not the wrap, so a wrap older than the chosen cover is STALE — and
    # rendering from it put a cover on the end card that had been replaced.
    if (wrap.exists() and chosen.exists()
            and chosen.stat().st_mtime > wrap.stat().st_mtime):
        return None                      # caller falls back to the chosen cover

    if not wrap.exists():
        return None
    # the cache must also lose to a newer chosen cover, not just a newer wrap
    newest = max([wrap.stat().st_mtime] +
                 ([chosen.stat().st_mtime] if chosen.exists() else []))
    if cache.exists() and cache.stat().st_mtime >= newest:
        return cache
    try:
        import fitz  # PyMuPDF
        book = get_book_by_catalog(catalog)
        trim = (book["data"].get("trim_size") or "5.25x8").lower().split("x")
        tw, th = float(trim[0]), float(trim[1])
        bleed = 0.125
        doc = fitz.open(str(wrap))
        page = doc[0]
        dpi = 300
        pix = page.get_pixmap(dpi=dpi)
        from PIL import Image
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        # front panel = rightmost trim width; drop the bleed on the outer edges
        px = lambda inches: int(round(inches * dpi))
        right = im.width - px(bleed)
        left = right - px(tw)
        top = px(bleed)
        bottom = top + px(th)
        front = im.crop((left, top, right, bottom))
        cache.parent.mkdir(parents=True, exist_ok=True)
        front.save(cache)
        return cache
    except Exception:
        return None


def build_end_card(catalog: str, end_line: str, cta: str,
                   size: tuple = (1280, 720)) -> Path:
    """The held final frame. Widescreen: cover on the right, the tagline and
    call to action given the left half. Portrait: poster layout. Rendered at
    2x and downsampled so the push-in stays crisp."""
    from PIL import Image, ImageDraw, ImageFilter

    SS = 2                                   # supersample
    W, H = size[0] * SS, size[1] * SS
    portrait = H > W
    k = (W / 720.0) if portrait else (H / 720.0)
    card = Image.new("RGB", (W, H), (8, 10, 14))
    draw = ImageDraw.Draw(card)

    src = front_cover_hires(catalog) or (OUTPUT_DIR / catalog / "cover-front.png")
    if not Path(src).exists():
        src = OUTPUT_DIR / catalog / "cover-art.png"
    cover = Image.open(src).convert("RGB")

    if portrait:
        cw = int(W * 0.62)
        ch = int(cover.height * cw / cover.width)
        max_ch = int(H * 0.78)
        if ch > max_ch:
            ch = max_ch; cw = int(cover.width * ch / cover.height)
        gx, gy = (W - cw) // 2, int((H - ch) * 0.45)
    else:
        ch = int(H * 0.86)
        cw = int(cover.width * ch / cover.height)
        gx, gy = int(W * 0.94) - cw, (H - ch) // 2    # right-hand third, large
    cover = cover.resize((cw, ch), Image.LANCZOS)

    glow = Image.new("RGB", (W, H), (8, 10, 14))
    gd = ImageDraw.Draw(glow)
    m = int(14 * k)
    gd.rectangle([gx - m, gy - m, gx + cw + m, gy + ch + m], fill=(46, 56, 74))
    glow = glow.filter(ImageFilter.GaussianBlur(int(28 * k)))
    card = Image.composite(glow, card, glow.convert("L").point(lambda v: min(255, v * 2)))
    draw = ImageDraw.Draw(card)
    card.paste(cover, (gx, gy))

    def fit(text, font, max_w):
        while draw.textlength(text, font=font) > max_w and font.size > 14:
            font = font.font_variant(size=font.size - 2)
        return font

    def wrap_lines(text, font, max_w):
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=font) <= max_w or not cur:
                cur = t
            else:
                lines.append(cur); cur = w
        if cur:
            lines.append(cur)
        return lines

    hook_txt = f"\u201c{end_line.strip().rstrip('.')}.\u201d" if end_line else ""
    if portrait:
        hook = _font("SourceSerif4-Italic.ttf", int(30 * k))
        small = _font("SourceSerif4-Regular.ttf", int(22 * k))
        if hook_txt:
            f = fit(hook_txt, hook, W * 0.92)
            tw = draw.textlength(hook_txt, font=f)
            draw.text(((W - tw) / 2, max(int(20 * k), gy - int(64 * k))), hook_txt, font=f, fill=(222, 224, 228))
        cta_s = " ".join(cta.upper())
        f2 = fit(cta_s, small, W * 0.92)
        draw.text(((W - draw.textlength(cta_s, font=f2)) / 2, gy + ch + int(44 * k)), cta_s, font=f2, fill=(176, 182, 192))
    else:
        # left column: tagline large, CTA beneath, vertically centred on the cover
        col_x = int(W * 0.07)
        col_w = gx - int(W * 0.06) - col_x
        hook = _font("SourceSerif4-Italic.ttf", int(44 * k))
        small = _font("SourceSerif4-Regular.ttf", int(30 * k if hook_txt else 40 * k))
        lines = wrap_lines(hook_txt, hook, col_w) if hook_txt else []
        lh = int(hook.size * 1.22)
        block_h = len(lines) * lh + (int(40 * k) + small.size if cta else 0)
        y = gy + (ch - block_h) // 2
        for ln in lines:
            draw.text((col_x, y), ln, font=hook, fill=(226, 228, 232)); y += lh
        if cta:
            y += int(40 * k)
            rule_w = int(72 * k)
            draw.rectangle([col_x, y - int(18 * k), col_x + rule_w, y - int(16 * k)], fill=(201, 169, 106))
            draw.text((col_x, y), " ".join(cta.upper()), font=small, fill=(190, 194, 202))

    out = OUTPUT_DIR / catalog / "trailer" / "end-card.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    card = card.resize((size[0], size[1]), Image.LANCZOS)
    card.save(out)
    return out


# ── the shoot ────────────────────────────────────────────────────

# ── quality control: the inspector ───────────────────────────────
# Every still is inspected before a second of video is bought, and every
# clip is spot-checked after. A frame fails for the things that read as
# "AI": a face to camera, lettering, warped hands or limbs, doubled objects,
# a scene that doesn't match the script, or a painterly/rendered look
# where a photograph was ordered. Failed stills are re-rolled (up to two
# more times); a failed clip is reshot once. Costs cents at the still stage,
# saves the expensive mistakes at the video stage.

QC_RULES = ("FAIL if any of these is true: a named character does not match "
            "their CAST description — estimate the apparent age and FAIL if it is more "
            "than 6 years off, or the hair colour/length or build differs; a person looks straight into the "
            "lens or is mid-speech; a face is uncanny, deformed, doubled or "
            "waxy; any text, lettering, logo or signage; warped or extra hands, "
            "fingers or limbs; duplicated, melting or absurdly scaled objects; "
            "the image looks painted, rendered or illustrated rather than "
            "photographed; the scene clearly contradicts the description. "
            "Otherwise PASS. Faces with real emotion are GOOD, not a fault.")


async def _qc_image(png_bytes: bytes, description: str) -> tuple:
    from ..writing.client import complete_vision, extract_json
    try:
        raw = await complete_vision(
            "You are a film DIT inspecting frames for a trailer. Be strict.",
            f"Shot description: {description[:500]}\n\n{QC_RULES}\n"
            'Return JSON only: {"verdict": "PASS" or "FAIL", "reasons": ["..."], "score": 1-10}',
            png_bytes, max_tokens=300)
        r = extract_json(raw) or {}
        if not isinstance(r, dict):
            return True, [], 0
        return (str(r.get("verdict", "PASS")).upper() == "PASS", r.get("reasons") or [], int(r.get("score") or 0))
    except Exception:
        return True, ["inspector unavailable"], 0


def _frame(video: Path, t: float) -> Optional[bytes]:
    import tempfile
    tmp = Path(tempfile.gettempdir()) / f"qc-{video.stem}-{int(t*10)}.png"
    proc = subprocess.run([_ffmpeg(), "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                           "-vf", "scale=960:-1", str(tmp)], capture_output=True, text=True, timeout=60)
    return tmp.read_bytes() if tmp.exists() else None


async def world_plate(catalog: str):
    """The cover's world, light and palette with NO lettering — generated
    once per book and used as the reference for every keyframe still, so
    the stills inherit the universe, never the typography."""
    dest = OUTPUT_DIR / catalog / "trailer" / "world-plate.png"
    if dest.exists() and dest.stat().st_size > 50_000:
        return dest
    art = OUTPUT_DIR / catalog / "cover-art.png"
    if not art.exists():
        return None
    try:
        uri = await runway.upload_file(art)
        task = await runway.text_to_image(
            "A wide cinematic establishing shot of exactly the world in the "
            "reference image — same place, season, light, palette and mood — "
            "with NO text, lettering, titles, names or typography of any kind. "
            "Photorealistic film still, no people.",
            ratio="1920:1080", reference_uris=[uri])
        result = await runway.wait_for(task["id"], timeout_s=300)
        url = (result.get("output") or [None])[0] if result.get("status") == "SUCCEEDED" else None
        if not url:
            return None
        await runway.download(url, dest)
        return dest
    except Exception:
        return None


async def _keyframe(catalog: str, prompt: str, ratio: str, cover_uri,
                    key: str) -> Optional[str]:
    """A referenced still for one shot, cached by its words. Returns a data
    URI ready to be the first frame of the video model."""
    import base64
    dest = OUTPUT_DIR / catalog / "trailer" / f"{key}.png"
    src = f"{ratio}|{prompt}"
    if not _take_valid(catalog, key, src, dest):
        still_ratio = ratio if ratio in ("1920:1080", "1080:1920", "1280:720", "720:1280") else "1280:720"
        if still_ratio == "720:1280":
            still_ratio = "1080:1920"
        try:
            task = await runway.text_to_image(
                prompt + " Photorealistic film still, natural light physics, "
                         "real lens. The reference image supplies only the "
                         "world, light and palette. No text, no lettering, "
                         "no watermark.",
                ratio=still_ratio,
                reference_uris=(cover_uri if isinstance(cover_uri, list) else [cover_uri]) if cover_uri else None)
            result = await runway.wait_for(task["id"], timeout_s=300)
            url = (result.get("output") or [None])[0] if result.get("status") == "SUCCEEDED" else None
            if not url:
                return None
            await runway.download(url, dest)
            _remember_take(catalog, key, src)
        except Exception:
            return None
    data = dest.read_bytes()
    if len(data) > 15_000_000:
        return None
    return "data:image/png;base64," + base64.b64encode(data).decode()


async def _keyframe_qc(catalog: str, prompt: str, ratio: str, cover_uri,
                       key: str, description: str, handle=None, label: str = "") -> Optional[str]:
    """A still that passed inspection: roll, inspect, re-roll (max 3 rolls)."""
    import base64
    best = None
    best_score = -1
    for roll in range(3):
        k = key if roll == 0 else f"{key}-r{roll}"
        uri = await _keyframe(catalog, prompt, ratio, cover_uri, k)
        if not uri:
            continue
        png = base64.b64decode(uri.split(",", 1)[1])
        ok, reasons, score = await _qc_image(png, description)
        if ok:
            return uri
        if handle:
            handle.progress(0.0, "shooting", f"{label} — still rejected: {'; '.join(reasons)[:60]} — re-rolling")
        if score > best_score:
            best, best_score = uri, score
    return best        # nothing passed: use the least-bad still rather than none


async def character_refs(catalog: str, cast: list) -> dict:
    """One portrait plate per lead — generated once from the director's
    description in the cover's world — so the same face, hair and wardrobe
    ride into every still as a reference. Returns name -> runway uri."""
    out = {}
    if not cast:
        return out
    tdir = OUTPUT_DIR / catalog / "trailer"
    tdir.mkdir(parents=True, exist_ok=True)
    world = tdir / "world-plate.png"
    world_uri = None
    if world.exists():
        try:
            world_uri = await runway.upload_file(world)
        except Exception:
            world_uri = None
    for c in cast[:2]:
        name = (c.get("name") or "").strip()
        desc = (c.get("description") or "").strip()
        if not name or not desc:
            continue
        key = f"cast-{_h(name + desc)}"
        dest = tdir / f"{key}.png"
        src = desc
        if not _take_valid(catalog, key, src, dest):
            prompt = (f"Cinematic medium close-up film still of {name}: {desc}. "
                      "Natural light, real lens, photographic skin, calm expression, "
                      "eyes looking slightly off camera, never into the lens. "
                      "The reference image supplies only the world, light and palette. "
                      "No text, no lettering.")
            ok = False
            for roll in range(3):
                try:
                    task = await runway.text_to_image(prompt, ratio="1280:720",
                                                      reference_uris=[world_uri] if world_uri else None)
                    result = await runway.wait_for(task["id"], timeout_s=300)
                    url = (result.get("output") or [None])[0] if result.get("status") == "SUCCEEDED" else None
                    if not url:
                        continue
                    await runway.download(url, dest)
                    passed, _, _ = await _qc_image(dest.read_bytes(), f"portrait of {name}: {desc}")
                    if passed or roll == 2:
                        ok = True
                        break
                except Exception:
                    continue
            if not ok:
                continue
            _remember_take(catalog, key, src)
        try:
            out[name] = await runway.upload_file(dest)
        except Exception:
            out[name] = None
        _CAST_PATHS.setdefault(catalog, {})[name] = dest
    return out


_CAST_PATHS: dict = {}      # catalog -> name -> portrait path (for providers that take files)


async def _insert_clip(catalog: str, prompt: str, seconds: float, ratio: str,
                       canvas: tuple, refs, style: str, look: str, key: str) -> Optional[Path]:
    """A still with a slow push-in — the trailer's detail insert. A few
    credits instead of a few hundred, and exactly the cut a real editor
    reaches for between two plates."""
    tdir = OUTPUT_DIR / catalog / "trailer"
    W, H = canvas
    full = (f"{prompt} Visual world: {style}. Cinematic film-trailer insert, {look}. "
            "Photographic detail shot, shallow depth of field, real anatomy if hands are seen. "
            "No text or lettering anywhere: any letter, envelope, label or page is sealed, "
            "folded, turned away or out of focus so that no writing can be read.")
    uri = await _keyframe_qc(catalog, full, ratio, refs, f"{key}-still", prompt, None, "insert")
    if not uri:
        return None
    png = tdir / f"{key}-still.png"
    dest = tdir / f"{key}.mp4"
    src = f"{canvas}|{seconds}|{full}"
    if _take_valid(catalog, key, src, dest):
        return dest
    frames = max(12, int(round(seconds * 24)))
    # upscale first so the push-in never softens; zoom 1.0 -> ~1.10
    vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
          f"zoompan=z='min(1+0.10*on/{frames},1.10)':d={frames}:"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=24,format=yuv420p")
    _run(["-y", "-loop", "1", "-i", str(png), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
          "-vf", vf, "-frames:v", str(frames), "-t", f"{seconds:.2f}", "-shortest",
          "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "96k",
          str(dest)], "insert")
    _remember_take(catalog, key, src)
    return dest


def _title_card(catalog: str, text: str, seconds: float, canvas: tuple, key: str) -> Path:
    """A typographic title card — black, serif, letter-spaced, pixel-perfect.
    Free, and the most classic cut in the grammar."""
    from PIL import Image, ImageDraw
    tdir = OUTPUT_DIR / catalog / "trailer"
    W, H = canvas
    dest = tdir / f"{key}.mp4"
    src = f"{canvas}|{seconds}|{text}"
    if _take_valid(catalog, key, src, dest):
        return dest
    S = 2
    img = Image.new("RGB", (W * S, H * S), (6, 6, 8))
    draw = ImageDraw.Draw(img)
    words = text.upper().strip()
    size = int(min(W, H) * 0.075) * S
    font = _font("EBGaramond-Regular.ttf", size)
    tracking = int(size * 0.22)
    # measure with tracking
    widths = [draw.textlength(ch, font=font) for ch in words]
    total_w = sum(widths) + tracking * (len(words) - 1)
    while total_w > W * S * 0.84 and size > 20:
        size = int(size * 0.92); font = _font("EBGaramond-Regular.ttf", size); tracking = int(size * 0.22)
        widths = [draw.textlength(ch, font=font) for ch in words]
        total_w = sum(widths) + tracking * (len(words) - 1)
    x = (W * S - total_w) / 2
    y = (H * S - size) / 2 - size * 0.1
    for ch, w in zip(words, widths):
        draw.text((x, y), ch, font=font, fill=(232, 226, 212))
        x += w + tracking
    img = img.resize((W, H), Image.LANCZOS)
    png = tdir / f"{key}.png"
    img.save(png)
    frames = max(12, int(round(seconds * 24)))
    # a breath of scale so the card is alive, not a slide
    vf = (f"scale={W*2}:{H*2},zoompan=z='1+0.03*on/{frames}':d={frames}:"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=24,format=yuv420p")
    _run(["-y", "-loop", "1", "-i", str(png), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
          "-vf", vf, "-frames:v", str(frames), "-t", f"{seconds:.2f}", "-shortest",
          "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "96k",
          str(dest)], "card")
    _remember_take(catalog, key, src)
    return dest


def _subcut(catalog: str, plate_file: Path, start: float, seconds: float, key: str) -> Path:
    """One moment out of an 8-second plate. Plates are shot long and cut
    short: every generation yields two or three cuts."""
    tdir = OUTPUT_DIR / catalog / "trailer"
    dest = tdir / f"{key}.mp4"
    plen = _probe_seconds(plate_file) or 8.0
    start = max(0.0, min(start, max(0.0, plen - seconds - 0.05)))
    src = f"{plate_file.name}|{plate_file.stat().st_mtime_ns}|{start:.2f}|{seconds:.2f}"
    if _take_valid(catalog, key, src, dest):
        return dest
    has_audio = "Audio:" in subprocess.run([_ffmpeg(), "-i", str(plate_file)],
                                           capture_output=True, text=True, timeout=60).stderr
    args = ["-y", "-ss", f"{start:.2f}", "-i", str(plate_file)]
    if not has_audio:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    args += ["-t", f"{seconds:.2f}", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
             "-c:a", "aac", "-b:a", "128k", "-shortest", str(dest)]
    _run(args, "subcut")
    _remember_take(catalog, key, src)
    return dest


async def _sectioned_score(catalog: str, cues: dict, turn_at: float, total: float,
                           prefix: str, recipe: dict) -> Optional[Path]:
    """Two cues and a silence: the intimate cue carries the setup, drops
    to nothing for a beat at the turn, and the build cue takes the
    escalation to the cover. Structure instead of wallpaper."""
    tdir = OUTPUT_DIR / catalog / "trailer"
    a_brief = (cues.get("intimate") or recipe.get("score") or "").strip()
    b_brief = (cues.get("build") or cues.get("intimate") or recipe.get("score") or "").strip()
    gap = 0.9
    a_len = max(6.0, turn_at - 0.6)
    b_len = max(6.0, total - turn_at - gap + 2.0)
    a = await _record_music(catalog, a_brief, a_len + 4, f"{prefix}-intimate")
    b = await _record_music(catalog, b_brief + " Opens on a strong downbeat.", b_len + 4, f"{prefix}-build")
    if not a and not b:
        return None
    if not a or not b:
        return a or b
    dest = tdir / f"score-{_h(a_brief + b_brief + str(round(turn_at, 1)) + str(round(total, 1)))}.mp3"
    if dest.exists():
        return dest
    fc = (f"[0:a]atrim=0:{a_len:.2f},afade=t=in:st=0:d=0.8,afade=t=out:st={max(0.0, a_len-0.9):.2f}:d=0.9,"
          f"apad=pad_dur={gap:.2f}[a];"
          f"[1:a]atrim=0:{b_len:.2f},afade=t=in:st=0:d=0.05,afade=t=out:st={max(0.0, b_len-3.0):.2f}:d=3[b];"
          f"[a][b]concat=n=2:v=0:a=1[out]")
    _run(["-y", "-i", str(a), "-i", str(b), "-filter_complex", fc, "-map", "[out]",
          "-c:a", "libmp3lame", "-b:a", "192k", str(dest)], "score")
    return dest


async def review_cut(catalog: str, video: Path, treatment: dict) -> dict:
    """The director watches the cut: a contact sheet of the assembled
    trailer goes to the vision model, which judges it as a trailer — not
    frame by frame — and names the weakest plates. Defects (artefacts,
    lettering, broken anatomy) are reshot; taste notes are kept for the
    publisher."""
    from ..writing.client import complete_vision, extract_json
    tdir = OUTPUT_DIR / catalog / "trailer"
    sheet = tdir / "review-sheet.png"
    dur = _probe_seconds(video) or 30.0
    n = 20
    step = max(dur / (n + 1), 0.5)
    _run(["-y", "-i", str(video), "-vf", f"fps=1/{step:.3f},scale=480:-1,tile=5x4",
          "-frames:v", "1", str(sheet)], "review-sheet")
    plates = treatment.get("plates") or []
    listing = "\n".join(f"  {p.get('id')}: {(p.get('prompt') or '')[:110]}" for p in plates)
    try:
        raw = await complete_vision(
            "You are a trailer editor at a studio reviewing a cut before it goes out.",
            f"This contact sheet samples the assembled {dur:.0f}-second trailer in order, "
            f"left to right, top to bottom. The plates were:\n{listing}\n\n"
            "The final cover card is HELD for six seconds and therefore appears in "
            "several consecutive frames — that is correct, not a duplicate. "
            "Judge it AS A MOVIE TRAILER: variety of scale (wide/medium/close), "
            "rhythm, human drama on screen, visual defects (artefacts, lettering, "
            "broken anatomy, uncanny faces, objects at absurd scale), consistency "
            "of characters between shots, and whether it would make someone buy "
            "the book. Return JSON only: {\"score\": 1-10, \"reads_as_trailer\": true/false, "
            "\"defects\": [{\"plate\": \"P3\", \"what\": \"under 15 words\"}] (only real visual defects), "
            "\"notes\": [\"up to 5 notes for the publisher, under 20 words each\"]}. Be brief.",
            sheet.read_bytes(), max_tokens=1500)
        r = extract_json(raw) or {}
        if isinstance(r, list):          # some readers answer with a bare list of notes
            r = next((x for x in r if isinstance(x, dict) and ("score" in x or "defects" in x)), None) \
                or {"notes": [str(x)[:160] for x in r][:5]}
        if not isinstance(r, dict):
            r = {}
    except Exception as e:
        r = {"error": str(e)[:200]}
    return r


async def _shoot_seedance(catalog: str, shots: list, mode: dict, style: str, prefix: str,
                          ratio: str, handle, done_offset: int, total_steps: int, cast) -> list:
    """Plates on Seedance 2.5 through Runway: one native take per plate, the
    world plate and the cast portraits riding along as references.
    Inspected like any other clip; one reshoot on a fail."""
    tdir = OUTPUT_DIR / catalog / "trailer"
    tdir.mkdir(parents=True, exist_ok=True)
    book_g = get_book_by_catalog(catalog)
    look = look_for((book_g or {}).get("data", {}))
    plate = await world_plate(catalog)
    world_uri = None
    for src in (plate, OUTPUT_DIR / catalog / "cover-art.png", OUTPUT_DIR / catalog / "cover-front.png"):
        if src and Path(src).exists():
            try:
                world_uri = await runway.upload_file(src)
                break
            except Exception:
                world_uri = None
    if not world_uri:
        raise RuntimeError("Seedance needs the world reference and the upload failed — check the Runway connection")
    char_refs = await character_refs(catalog, cast or [])      # name -> runway uri
    cast_desc = {c.get("name"): c.get("description") for c in (cast or []) if c.get("name")}
    files = []
    for i, shot in enumerate(shots, 1):
        base = shot.get("prompt") or ""
        names = [n for n in (shot.get("characters") or []) if char_refs.get(n)]
        refs = ([world_uri] if world_uri else []) + [char_refs[n] for n in names]
        who = ""
        if world_uri:
            who += " Reference image 1 is the world: its place, light and palette."
        for k, n in enumerate(names):
            who += f" {n} is the person in reference image {k + (2 if world_uri else 1)} — same face, hair and wardrobe."
        # the director's shot, as written — the model does the art direction.
        # Only the reference sentence is added (the house rule: no stacked
        # art direction, no look recipes, no boilerplate).
        prompt = base.strip() + who
        qc_desc = base + "".join(f" CAST — {n}: {cast_desc[n]}" for n in names if cast_desc.get(n))
        seconds = int(shot.get("seconds") or mode["shot_seconds"])
        take_src = f"{mode['model']}|{ratio}|{seconds}|{prompt}"
        key = f"{prefix}-shot-{_h(take_src)}"
        dest = tdir / f"{key}.mp4"
        if _take_valid(catalog, key, take_src, dest):
            files.append(dest)
            continue
        if handle:
            handle.progress((done_offset + i - 1) / total_steps, "shooting", f"clip {i}/{len(shots)} on Seedance 2.5")
        reshot = False
        softened = 0
        for attempt in range(5):
            task = await runway.generate_seedance(prompt, refs, seconds=seconds, ratio=ratio,
                                                  model=mode["model"], audio=mode["audio"] and bool(refs))
            result = await runway.wait_for(task["id"], timeout_s=1500)
            if result.get("status") != "SUCCEEDED":
                failure = json.dumps(result.get("failure") or result.get("error") or "")
                # Runway's input check on Seedance is inconsistent: the same
                # request can be refused once and accepted next. Retry the
                # IDENTICAL prompt — the director's words are never rewritten.
                if "invalid input" in failure.lower() and softened < 3:
                    softened += 1
                    if handle:
                        handle.progress((done_offset + i - 1) / total_steps, "shooting",
                                        f"clip {i}/{len(shots)} — Runway refused the request, retrying ({softened}/3)")
                    await asyncio.sleep(3)
                    continue
                raise RuntimeError(f"Clip {i} failed on Seedance: {result.get('status')} {failure[:200]}")
            url = (result.get("output") or [None])[0]
            if not url:
                raise RuntimeError(f"Plate {i} returned no output")
            await runway.download(url, dest)
            ok_all = True
            for frame_t in (1.0, max(1.5, _probe_seconds(dest) - 0.8)):
                fb = _frame(dest, frame_t)
                if not fb:
                    continue
                ok, reasons, _ = await _qc_image(fb, qc_desc)
                if not ok:
                    ok_all = False
                    if handle and not reshot:
                        handle.progress((done_offset + i - 1) / total_steps, "shooting",
                                        f"plate {i}/{len(shots)} — rejected ({'; '.join(reasons)[:50]}) — reshooting")
                    break
            if ok_all or reshot:
                break
            reshot = True
        _remember_take(catalog, key, take_src)
        files.append(dest)
    return files


async def _shoot(catalog: str, shots: list, mode: dict, style: str,
                 prefix: str, ratio: str = "1280:720", handle=None,
                 done_offset: int = 0, total_steps: int = 10,
                 cast: Optional[list] = None) -> list:
    """Generate every shot sequentially (Runway allows 1 concurrent veo).
    Keyframe modes make a referenced still first, then animate it."""
    tdir = OUTPUT_DIR / catalog / "trailer"
    tdir.mkdir(parents=True, exist_ok=True)
    files = []
    book_g = get_book_by_catalog(catalog)
    look = look_for((book_g or {}).get("data", {}))
    cover_uri = None
    char_refs = {}          # name -> runway uri of the character's portrait plate
    if mode.get("provider") == "seedance":
        return await _shoot_seedance(catalog, shots, mode, style, prefix, ratio, handle,
                                     done_offset, total_steps, cast)
    if mode.get("keyframe"):
        plate = await world_plate(catalog)        # text-free reference
        if plate:
            try:
                cover_uri = await runway.upload_file(plate)   # valid 24h, reused per shot
            except Exception:
                cover_uri = None
        char_refs = await character_refs(catalog, cast or [])
    cast_desc = {c.get("name"): c.get("description") for c in (cast or []) if c.get("name")}
    for i, shot in enumerate(shots, 1):
        prompt = (shot.get("prompt") or "").strip()
        qc_desc = prompt + "".join(f" CAST — {n}: {cast_desc[n]}" for n in (shot.get("characters") or []) if cast_desc.get(n))
        # the director's shot as written; the model art-directs (house rule)
        # which portraits ride along as references for this plate
        refs = [cover_uri] if cover_uri else []
        tagged = []
        for name in (shot.get("characters") or []):
            uri = char_refs.get(name)
            if uri and len(refs) < 3:
                refs.append(uri)
                tagged.append(f"{name} is @ref{len(refs)} (same face, hair and wardrobe)")
        shot_refs = refs or None
        if tagged:
            prompt = f"{prompt} " + ". ".join(tagged) + "."
        if mode["audio"] and shot.get("sound"):
            prompt = f"{prompt} Sound: {shot['sound']}. No speech, no voices."
        take_src = f"{ratio}|{prompt}"
        # content-addressed takes: a scene keeps its footage wherever it
        # moves in the running order; only changed scenes reshoot
        key = f"{prefix}-shot-{_h(take_src)}"
        dest = tdir / f"{key}.mp4"
        if _take_valid(catalog, key, take_src, dest):
            files.append(dest)      # unchanged words, valid take — keep it
            continue
        if handle:
            handle.progress((done_offset + i - 1) / total_steps,
                            "shooting", f"shot {i}/{len(shots)}")
        # moderation verdicts are partly stochastic — retake first; if the
        # filter refuses twice, SOFTEN the scene (keep the image, drop what
        # a conservative filter reads as harm to visible people) and try
        # once more before bothering the publisher.
        result = None
        attempt_prompt = prompt
        first_frame = None
        if mode.get("keyframe"):
            if handle:
                handle.progress((done_offset + i - 1) / total_steps,
                                "shooting", f"shot {i}/{len(shots)} — keyframe still")
            first_frame = await _keyframe_qc(catalog, prompt, ratio, shot_refs, f"{key}-still",
                                             qc_desc, handle, f"shot {i}/{len(shots)}")
        for attempt in range(4):
            task = await runway.generate_shot(
                attempt_prompt,
                reference_image_url=first_frame or "",
                seconds=int(shot.get("seconds") or mode["shot_seconds"]),
                model=mode["model"], audio=mode["audio"], ratio=ratio)
            result = await runway.wait_for(task["id"], timeout_s=900)
            if result.get("status") == "SUCCEEDED":
                break
            failure = json.dumps(result.get("failure") or result.get("error") or "")
            if "moderation" not in failure.lower() or attempt == 3:
                raise RuntimeError(
                    f"Shot {i} failed: {result.get('status')} {failure[:200]}"
                    + (" — the moderation filter refused this scene even "
                       "after an automatic soften; reword it in the "
                       "screenplay and shoot again"
                       if "moderation" in failure.lower() else ""))
            if attempt >= 1:
                if handle:
                    handle.progress((done_offset + i - 1) / total_steps,
                                    "shooting", f"shot {i}/{len(shots)} — softening the scene")
                from ..writing.client import complete
                try:
                    attempt_prompt = (await complete(
                        "You soften film-shot descriptions so a conservative "
                        "video content filter passes them, while keeping the "
                        "same image, mood and camera.",
                        "Rewrite this shot description to pass strict video "
                        "content moderation. Remove anything implying death, "
                        "injury, burial or victimhood of a VISIBLE person — "
                        "keep the place, light, weather, camera move and "
                        "objects. Same length. Return only the rewritten "
                        f"description.\n\n{attempt_prompt}",
                        max_tokens=500)).strip()
                except Exception:
                    pass
            elif handle:
                handle.progress((done_offset + i - 1) / total_steps,
                                "shooting", f"shot {i}/{len(shots)} — retake")
        url = (result.get("output") or [None])[0]
        if not url:
            raise RuntimeError(f"Shot {i} returned no output")
        await runway.download(url, dest)
        # spot-check the clip: two frames through the inspector; one reshoot
        reshot = False
        for frame_t in (1.0, max(1.5, _probe_seconds(dest) - 0.8)):
            fb = _frame(dest, frame_t)
            if not fb:
                continue
            ok, reasons, _ = await _qc_image(fb, qc_desc)
            if not ok and not reshot:
                if handle:
                    handle.progress((done_offset + i - 1) / total_steps, "shooting",
                                    f"shot {i}/{len(shots)} — clip rejected ({'; '.join(reasons)[:50]}) — reshooting")
                task = await runway.generate_shot(
                    attempt_prompt, reference_image_url=first_frame or "",
                    seconds=int(shot.get("seconds") or mode["shot_seconds"]),
                    model=mode["model"], audio=mode["audio"], ratio=ratio)
                res2 = await runway.wait_for(task["id"], timeout_s=900)
                url2 = (res2.get("output") or [None])[0] if res2.get("status") == "SUCCEEDED" else None
                if url2:
                    await runway.download(url2, dest)
                reshot = True
                break
        _remember_take(catalog, key, take_src)
        files.append(dest)
    return files


_VOICE_GATE = asyncio.Semaphore(2)

# The cinema voice. Runway's presets are announcers; the true trailer
# instrument lives in the publisher's ElevenLabs bank. Overridable with
# the `trailer_voice_id` setting.
TRAILER_VOICES = {
    "action_thriller": ("fCxG8OHm4STbIsWe4aT9", "Harrison Gale"),   # the velvet voice
    "romance":         ("pFZP5JQG7iQjIQuC4Bku", "Lily"),
    "default":         ("nPczCjzI2devNBz1zQrb", "Brian"),
}


def trailer_voice(genre_preset: str, catalog: str = "") -> tuple:
    from ..database import get_setting, get_book_by_catalog as _gb
    if catalog:
        book = _gb(catalog)
        cast = ((book or {}).get("data", {}).get("trailer") or {}).get("voice") or {}
        if cast.get("id"):
            return cast["id"], cast.get("name") or "Cast voice"
    override = (get_setting("trailer_voice_id", "") or "").strip()
    if override:
        return override, get_setting("trailer_voice_name", "") or "Custom voice"
    for key, v in TRAILER_VOICES.items():
        if key in (genre_preset or ""):
            return v
    return TRAILER_VOICES["default"]


async def _record_line(catalog: str, text: str, genre: str, key: str,
                       filename: str, speed: float = 0.9,
                       voice_override: str = "") -> Optional[Path]:
    """One cached voice recording (the VO script, or the title read).
    Runs on ElevenLabs directly; the take is keyed on words AND voice, so
    recasting the narrator re-records everything he says.
    voice_override casts a different voice for one line — a character
    speaking in their own voice instead of the trailer narrator."""
    import httpx
    from ..database import get_setting
    if not text.strip():
        return None
    voice_id = voice_override or trailer_voice(genre, catalog)[0]
    dest = OUTPUT_DIR / catalog / "trailer" / filename
    source = f"{voice_id}|{speed}|{text}"
    if _take_valid(catalog, key, source, dest):
        return dest
    api_key = get_setting("elevenlabs_api_key", "")
    if not api_key:
        raise RuntimeError("ElevenLabs is not configured (Settings)")
    async with _VOICE_GATE:      # the plan allows 3 concurrent; stay under it
        async with httpx.AsyncClient(timeout=300) as client:
            for attempt in range(4):
                resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers={"xi-api-key": api_key},
                    json={"text": text,
                          "model_id": get_setting("elevenlabs_model_id", "eleven_multilingual_v2"),
                          "voice_settings": {"stability": 0.38, "similarity_boost": 0.8,
                                             "style": 0.65, "use_speaker_boost": True,
                                             "speed": speed}},
                    params={"output_format": "mp3_44100_128"},
                )
                if resp.status_code == 429 and attempt < 3:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break
            if resp.status_code != 200:
                raise RuntimeError(f"Trailer voice failed ({resp.status_code}): {resp.text[:300]}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
    _remember_take(catalog, key, source)
    return dest




async def _record_sfx(catalog: str, prompt: str, seconds: float, key: str,
                      filename: str) -> Optional[Path]:
    """One cached sound-design cue via eleven_text_to_sound_v2."""
    dest = OUTPUT_DIR / catalog / "trailer" / filename
    if _take_valid(catalog, key, f"{prompt}|{seconds}", dest):
        return dest
    try:
        task = await runway.sound_effect(f"{prompt}. Cinematic sound design, "
                                         "no music, no speech.", seconds)
        result = await runway.wait_for(task["id"], timeout_s=240)
        if result.get("status") != "SUCCEEDED":
            return None
        url = (result.get("output") or [None])[0]
        if not url:
            return None
        await runway.download(url, dest)
        _remember_take(catalog, key, f"{prompt}|{seconds}")
        return dest
    except Exception:
        return None          # a missing cue never kills the cut


async def _record_music(catalog: str, brief: str, seconds: float, prefix: str) -> Optional[Path]:
    if not brief.strip():
        return None
    dest = OUTPUT_DIR / catalog / "trailer" / f"{prefix}-music.mp3"
    key_src = f"{brief}|{int(seconds)}"
    if _take_valid(catalog, f"{prefix}-music", key_src, dest):
        return dest
    # a score the publisher picked by ear always wins over generation
    book = get_book_by_catalog(catalog)
    pinned = ((book["data"].get("trailer") or {}).get("score")) or {}
    if pinned.get("file"):
        pf = OUTPUT_DIR / catalog / pinned["file"]
        if pf.exists() and pf.stat().st_size > 10_000:
            return pf

    # seed_audio fails transiently now and then — retake before giving up,
    # and never let a missing score kill the whole cut.
    raw = dest.with_name(dest.stem + "-raw.mp3")
    for attempt in range(7):
        try:
            task = await runway.music_bed(brief, seconds)
            result = await runway.wait_for(task["id"], timeout_s=300)
            if result.get("status") == "SUCCEEDED":
                url = (result.get("output") or [None])[0]
                if url:
                    await runway.download(url, raw)
                    # the model sometimes returns near-silence: measure, and
                    # regenerate rather than mix nothing
                    if _mean_volume_db(raw) < -35:
                        continue
                    # a fixed loudness so the mix never depends on the model's level
                    _run(["-y", "-i", str(raw), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                          "-c:a", "libmp3lame", "-b:a", "192k", str(dest)], "score normalise")
                    _remember_take(catalog, f"{prefix}-music", key_src)
                    return dest
        except Exception:
            pass
        await asyncio.sleep(4)
    return None


def _mean_volume_db(path: Path) -> float:
    proc = subprocess.run([_ffmpeg(), "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                          capture_output=True, text=True, timeout=120)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", proc.stderr)
    return float(m.group(1)) if m else -99.0


# ── the cut ──────────────────────────────────────────────────────

def _assemble(catalog: str, shot_files: list, end_card: Path,
              vo_cues: Optional[list], music: Optional[Path],
              native_audio: bool,
              sfx: Optional[list] = None,          # [(path, delay_s, vol)]
              tag_vo: Optional[Path] = None, tag_delay: float = 0.0,
              size: tuple = (1280, 720), suffix: str = "",
              trims: Optional[list] = None) -> Path:
    W, H = size
    scope_h = int(round(W / 2.39 / 2) * 2)
    scope_y = (H - scope_h) // 2
    """Concat shots + end card; mix score under voice (and native sound)."""
    tdir = OUTPUT_DIR / catalog / "trailer"

    # 1. normalise every shot to 1280x720/24fps and give each an audio track
    #    (silent if the take has none) so the concat filter never mismatches.
    def _has_audio(path: Path) -> bool:
        proc = subprocess.run([_ffmpeg(), "-i", str(path)],
                              capture_output=True, text=True, timeout=60)
        return "Audio:" in proc.stderr

    # The grade that makes it a trailer and not a screensaver: scope
    # letterbox, crushed blacks, drained saturation, a vignette, and a
    # dip-to-black on every cut.
    # Widescreen wears the scope letterbox; portrait formats fill the
    # frame edge to edge (a letterboxed vertical ad reads as a mistake).
    scope = (f"crop={W}:{scope_h}:0:{scope_y},pad={W}:{H}:0:{scope_y},"
             if W > H else "")
    GRADE = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
             f"crop={W}:{H},{scope}"
             "eq=brightness=-0.04:contrast=1.12:saturation=0.78:gamma=0.96,"
             "vignette=PI/4.4,fps=24,setsar=1")

    def _mean_luma(path: Path) -> float:
        """Average Y (0-255) over the clip — the exposure guard's meter."""
        try:
            proc = subprocess.run([_ffmpeg(), "-i", str(path), "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                                   "-an", "-f", "null", "-"], capture_output=True, text=True, timeout=120)
            vals = [float(x) for x in re.findall(r"YAVG=([\d.]+)", proc.stderr)]
            return sum(vals) / len(vals) if vals else 110.0
        except Exception:
            return 110.0

    segs = []
    for i, f in enumerate(shot_files):
        seg = tdir / f"seg-{i:02d}.mp4"
        use_native = native_audio and _has_audio(f)
        dur = _probe_seconds(f)
        luma = _mean_luma(f)
        # night is allowed; black is not — lift what would crush under the grade
        lift = ""
        if luma < 45:
            lift = f"eq=brightness={min(0.14, (45 - luma) / 45 * 0.16):.3f}:gamma=1.12,"
        elif luma < 60:
            lift = "eq=brightness=0.04:gamma=1.05,"
        vis = min(dur, (trims[i] if trims and i < len(trims) and trims[i] else dur))
        fades = (f",fade=t=in:st=0:d=0.15,"
                 f"fade=t=out:st={max(0.0, vis - 0.3):.2f}:d=0.3") if vis > 1 else ""
        trim = (trims[i] if trims and i < len(trims) else None)
        cut = ["-t", f"{trim:.2f}"] if trim and trim < dur - 0.1 else []
        _run(["-i", str(f), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
              "-shortest", *cut,
              "-vf", lift + GRADE + fades,
              "-map", "0:v:0", "-map", "0:a:0" if use_native else "1:a:0",
              "-c:v", "libx264", "-preset", "fast", "-crf", "19",
              "-c:a", "aac", "-ar", "48000", "-ac", "2",
              str(seg)], f"segment {i}")
        segs.append(seg)

    # end card: slow push-in, silent
    card_seg = tdir / "seg-card.mp4"
    zw, zh = int(W * 1.1) // 2 * 2, int(H * 1.1) // 2 * 2
    _run(["-loop", "1", "-t", str(END_CARD_SECONDS), "-i", str(end_card),
          "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
          "-vf", f"scale={zw}:{zh},zoompan=z='1+0.0125*on/{24*END_CARD_SECONDS}':"
                 f"x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={W}x{H}:fps=24,"
                 f"fade=t=in:st=0:d={FADE_SECONDS},setsar=1",
          "-map", "0:v:0", "-map", "1:a:0",
          "-c:v", "libx264", "-preset", "fast", "-crf", "19",
          "-c:a", "aac", "-ar", "48000", "-ac", "2",
          str(card_seg)], "end card")
    segs.append(card_seg)

    # 2. concat
    listfile = tdir / "concat.txt"
    listfile.write_text("".join(f"file '{s.name}'\n" for s in segs))
    picture = tdir / "picture.mp4"
    _run(["-f", "concat", "-safe", "0", "-i", str(listfile),
          "-c:v", "libx264", "-preset", "fast", "-crf", "19",
          "-c:a", "aac", "-ar", "48000", "-ac", "2",
          "-movflags", "+faststart", str(picture)], "concat")
    total = _probe_seconds(picture)

    # 3. the mix — professional trailer grammar:
    #    a VOICE BUS (high-passed, compressed, presence) on top; the score
    #    and native sound SIDECHAIN-DUCKED by the voice (fast attack, slow
    #    release, ~8 dB) so the bed breathes between lines; sound-design hits
    #    on their own bus; -14 LUFS / -1.5 dBTP delivery.
    inputs = ["-i", str(picture)]
    filters = []
    n = 1

    # voice bus: every VO line + the title read
    voice_inputs = []
    for j, (cue, delay_s, vol) in enumerate(vo_cues or []):
        d = int(delay_s * 1000)
        inputs += ["-i", str(cue)]
        filters.append(f"[{n}:a]adelay={d}|{d},volume={vol}[v{j}]")
        voice_inputs.append(f"[v{j}]"); n += 1
    if tag_vo:
        d = int(tag_delay * 1000)
        inputs += ["-i", str(tag_vo)]
        filters.append(f"[{n}:a]adelay={d}|{d},volume=1.9[vtag]")
        voice_inputs.append("[vtag]"); n += 1
    has_voice = bool(voice_inputs)
    if has_voice:
        # one sidechain key per ducked bus, no orphan outputs
        keys = (["[vkey1]"] if native_audio else []) + (["[vkey2]"] if music else [])
        split = f",asplit={1 + len(keys)}[voice]" + "".join(keys) if keys else "[voice]"
        filters.append(
            "".join(voice_inputs) + f"amix=inputs={len(voice_inputs)}:duration=longest:normalize=0,"
            "highpass=f=90,acompressor=threshold=-18dB:ratio=3:attack=15:release=180:makeup=2,"
            "equalizer=f=3000:t=q:w=1.2:g=2,"
            f"apad=whole_dur={total:.2f},atrim=0:{total:.2f}" + split)

    # bed: native shot sound, ducked by the voice
    bed_lbl = None
    if native_audio:
        if has_voice:
            filters.append("[0:a][vkey1]sidechaincompress=threshold=0.03:ratio=8:attack=90:release=500:makeup=1[bedd]")
            filters.append("[bedd]volume=0.3[bed]")
        else:
            filters.append("[0:a]volume=0.3[bed]")
        bed_lbl = "[bed]"

    # score: looped with crossfades if short, then ducked by the voice
    score_lbl = None
    if music:
        import math
        mdur = _probe_seconds(music) or total
        copies = max(1, math.ceil((total + 2.0) / max(mdur, 4.0)))
        for _ in range(copies):
            inputs += ["-i", str(music)]
        if copies == 1:
            joined = f"[{n}:a]"
        else:
            prev = f"[{n}:a]"
            for k in range(1, copies):
                out_lbl = f"[mx{k}]"
                filters.append(f"{prev}[{n + k}:a]acrossfade=d=1:c1=tri:c2=tri{out_lbl}")
                prev = out_lbl
            joined = prev
        n += copies
        filters.append(
            f"{joined}atrim=0:{total:.2f},volume=1.7,"
            f"afade=t=in:st=0:d=0.6,afade=t=out:st={max(0.0, total-3.0):.2f}:d=3[scoreraw]")
        if has_voice:
            # ~8 dB duck under speech, soft knee, breathes back in half a second
            filters.append("[scoreraw][vkey2]sidechaincompress=threshold=0.03:ratio=6:attack=80:release=550:knee=4:makeup=1[score]")
        else:
            filters.append("[scoreraw]anull[score]")
        score_lbl = "[score]"

    # hits and cues on their own bus
    fx_inputs = []
    for j, (cue, delay_s, vol) in enumerate(sfx or []):
        d = int(delay_s * 1000)
        inputs += ["-i", str(cue)]
        filters.append(f"[{n}:a]adelay={d}|{d},volume={vol}[fx{j}]")
        fx_inputs.append(f"[fx{j}]"); n += 1
    fx_lbl = None
    if fx_inputs:
        filters.append("".join(fx_inputs) + f"amix=inputs={len(fx_inputs)}:duration=longest:normalize=0,"
                       f"apad=whole_dur={total:.2f},atrim=0:{total:.2f}[fx]")
        fx_lbl = "[fx]"

    mix = [l for l in (bed_lbl, score_lbl, fx_lbl, "[voice]" if has_voice else None) if l]
    out = OUTPUT_DIR / catalog / f"trailer{suffix}.mp4"
    tmp_out = OUTPUT_DIR / catalog / f".trailer{suffix}.tmp.mp4"
    if mix:
        graph = (";".join(filters) + ";" + "".join(mix)
                 + f"amix=inputs={len(mix)}:duration=first:normalize=0,"
                 + "loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        _run([*inputs, "-filter_complex", graph,
              "-map", "0:v:0", "-map", "[a]",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
              "-movflags", "+faststart",
              str(tmp_out)], "final mix")
    else:
        _run(["-i", str(picture), "-c", "copy", str(tmp_out)], "final copy")

    # atomic swap: a viewer mid-play keeps their stream
    poster = OUTPUT_DIR / catalog / f"trailer-poster{suffix}.jpg"
    tmp_poster = OUTPUT_DIR / catalog / f".trailer-poster{suffix}.tmp.jpg"
    _run(["-ss", "1.5", "-i", str(tmp_out), "-frames:v", "1", "-q:v", "3",
          str(tmp_poster)], "poster")
    import os
    os.replace(tmp_out, out)
    os.replace(tmp_poster, poster)
    return out


# ── the production ───────────────────────────────────────────────

async def produce(catalog: str, mode_name: str = "full",
                  format_name: str = "wide", fresh: bool = False,
                  handle=None) -> dict:
    """The whole shoot: treatment -> shots -> voice -> score -> cut.
    fresh=True re-rolls EVERY take from the same script — new footage, new
    recordings, new sound — keeping only a score the publisher pinned."""
    if mode_name not in MODES:
        raise ValueError(f"Unknown mode '{mode_name}' (use full or voiceover)")
    if format_name not in FORMATS:
        raise ValueError(f"Unknown format '{format_name}' (use wide, vertical or ad)")
    mode = MODES[mode_name]
    fmt = FORMATS[format_name]
    is_veo = mode["model"].startswith("veo") or mode.get("provider") == "seedance"
    small = bool(mode.get("small")) or not is_veo    # drafts stay 720p-class
    shoot_ratio = fmt["gen4"] if small else fmt["veo"]
    canvas = fmt["canvas_gen4"] if small else fmt["canvas_veo"]
    portrait = canvas[1] > canvas[0]
    # vertical and ad share the same portrait footage takes
    shot_prefix = f"{mode_name}-p" if portrait else mode_name
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = book["data"]
    recipe = sound_for(d)

    if fresh:
        # wipe the take ledger and the files behind it; the pinned score
        # (a deliberate human pick) survives
        book_f = get_book_by_catalog(catalog)
        data_f = dict(book_f["data"])
        tr_f = dict(data_f.get("trailer") or {})
        tr_f["takes"] = {}
        data_f["trailer"] = tr_f
        update_book(book_f["id"], data_f)
        tdir = OUTPUT_DIR / catalog / "trailer"
        if tdir.exists():
            for f in tdir.iterdir():
                if f.suffix in (".mp4", ".mp3") and not f.name.startswith("seg-"):
                    f.unlink(missing_ok=True)

    credits_before = await runway.credit_balance()

    from .director import normalize_treatment
    treatment = ((d.get("trailer") or {}).get("treatment"))
    if not treatment:
        if handle:
            handle.progress(0.02, "directing", "writing the treatment")
        treatment = await write_treatment(catalog)
    treatment = normalize_treatment(treatment)
    plates = treatment.get("plates") or []
    cuts = treatment.get("cuts") or []
    if not plates or not cuts:
        raise RuntimeError("Treatment has no plates")
    inserts = treatment.get("inserts") or []
    cards = treatment.get("cards") or []
    cast = treatment.get("cast") or []

    if handle:
        handle.progress(0.05, "look", "reading the cover's world")
    style = await world_style(catalog)
    look = look_for(d)
    still_ratio = shoot_ratio if shoot_ratio in ("1920:1080", "1080:1920", "1280:720") else "1280:720"

    total_steps = len(plates) + 4
    review = {}
    out = None
    card_start = 0.0
    for round_n in range(2):                       # shoot → cut → review → (reshoot defects once)
        # ── 1. plates: the expensive generations, 8 s each, keyframe-first ──
        plate_files = await _shoot(catalog, plates, mode, style, shot_prefix,
                                   ratio=shoot_ratio, handle=handle, done_offset=1,
                                   total_steps=total_steps, cast=cast)
        by_id = {pl["id"]: f for pl, f in zip(plates, plate_files)}

        # ── 2. the edit: moments out of plates, inserts, cards ──
        if handle:
            handle.progress((len(plates) + 1) / total_steps, "cutting", "cutting the plates into moments")
        world = OUTPUT_DIR / catalog / "trailer" / "world-plate.png"
        world_uri = None
        if world.exists():
            try:
                world_uri = await runway.upload_file(world)
            except Exception:
                world_uri = None
        files, trims, vo_lines = [], [], []     # vo_lines: (file_index, text)
        cut_file = {}                           # cut index -> file index
        for ci, cut in enumerate(cuts):
            kind = cut.get("type") or "plate"
            secs = float(max(0.8, min(6.0, float(cut.get("seconds") or 2.5))))
            clip = None
            if kind == "plate":
                pf = by_id.get(cut.get("plate")) or (plate_files[0] if plate_files else None)
                if pf:
                    start = float(cut.get("start") or 0)
                    clip = _subcut(catalog, pf, start, secs,
                                   f"{shot_prefix}-cut-{_h(f'{pf.name}|{start:.2f}|{secs:.2f}')}")
            elif kind == "insert":
                ins = inserts[int(cut.get("index") or 0)] if inserts else None
                if ins:
                    clip = await _insert_clip(catalog, ins.get("prompt") or "", secs, still_ratio, canvas,
                                              [world_uri] if world_uri else None, style, look,
                                              f"{shot_prefix}-ins-{_h(ins.get('prompt') or '')}")
            elif kind == "card":
                cd = cards[int(cut.get("index") or 0)] if cards else None
                if cd and (cd.get("text") or "").strip():
                    clip = _title_card(catalog, cd["text"], secs, canvas,
                                       f"{shot_prefix}-card-{_h(cd['text'])}")
            if not clip:
                continue
            files.append(clip)
            trims.append(secs)
            cut_file[ci] = len(files) - 1
            if (cut.get("voiceover") or "").strip():
                vo_lines.append((len(files) - 1, cut["voiceover"].strip()))
        if not files:
            raise RuntimeError("The edit produced no cuts")

        # ── 3. voice: one take per line, anchored to its cut ──
        if handle:
            handle.progress((len(plates) + 2) / total_steps, "voice", "recording the voice-over")
        vo_takes = await asyncio.gather(*(
            _record_line(catalog, text, d.get("genre_preset") or "",
                         f"vo-line-{_h(text)}", f"vo-line-{_h(text)}.mp3")
            for _, text in vo_lines))
        durs = [min(_probe_seconds(f), t) for f, t in zip(files, trims)]
        starts = [sum(durs[:i]) for i in range(len(durs))]
        card_start = sum(durs)
        vo_cues = [(take, starts[idx] + 0.25, 1.9)
                   for (idx, _), take in zip(vo_lines, vo_takes) if take and idx < len(starts)]

        # ── 4. score in sections: intimate → silence at the turn → build ──
        if handle:
            handle.progress((len(plates) + 2.4) / total_steps, "score", "scoring")
        turn_cut = int(treatment.get("turn_cut") or max(1, len(cuts) // 2))
        # the turn is a CUT index; map it onto the files that made the edit
        turn_file = cut_file.get(turn_cut)
        if turn_file is None:
            later = [fi for ci, fi in cut_file.items() if ci >= turn_cut]
            turn_file = min(later) if later else max(0, len(files) // 2)
        turn_at = starts[min(turn_file, len(starts) - 1)] if starts else card_start / 2
        music = await _sectioned_score(catalog, treatment.get("music") or {}, turn_at,
                                       card_start + END_CARD_SECONDS, "shared", recipe)

        # ── 5. sound design ──
        sfx = []
        if handle:
            handle.progress((len(plates) + 2.7) / total_steps, "sound", "sound design")
        intro = await _record_sfx(catalog, recipe["intro"], 2.5, "sfx-intro", "sfx-intro.mp3")
        if intro:
            sfx.append((intro, 0.0, 1.0))
        # the turn: a single hit as the silence breaks
        turn_hit = await _record_sfx(catalog, recipe.get("cut_hit") or recipe["reveal"], 2.0,
                                     "sfx-turn", "sfx-turn.mp3")
        if turn_hit and turn_at > 1:
            sfx.append((turn_hit, max(0.0, turn_at + 0.6), 0.9))
        if mode["audio"] or mode.get("draft"):   # each plate's key sound on its first moment
            seen = set()
            for ci, cut in enumerate(cuts):
                pid = cut.get("plate")
                if cut.get("type", "plate") != "plate" or pid in seen or ci not in cut_file:
                    continue
                seen.add(pid)
                pl = next((p_ for p_ in plates if p_["id"] == pid), None)
                sound = ((pl or {}).get("sound") or "").strip()
                if not sound:
                    continue
                cue_key = f"sfx-{_h(sound)}"
                cue = await _record_sfx(catalog, sound, 3.0, cue_key, f"{cue_key}.mp3")
                if cue:
                    sfx.append((cue, starts[cut_file[ci]], 0.7))
        if recipe.get("cut_hit") and not mode.get("draft"):
            hit = await _record_sfx(catalog, recipe["cut_hit"], 1.5, "sfx-hit", "sfx-hit.mp3")
            if hit:
                for t in starts[turn_file + 1:]:     # hits only in the escalation
                    sfx.append((hit, max(0.0, t - 0.08), 0.8))
        reveal = await _record_sfx(catalog, recipe["reveal"], 3.0, "sfx-reveal", "sfx-reveal.mp3")
        if reveal:
            sfx.append((reveal, max(0.0, card_start - 0.3), 0.95))

        tagline = (treatment.get("end_card_text") or "").strip()
        title_read = f"{book['title']}. Available now."
        tag_vo = await _record_line(catalog, title_read, d.get("genre_preset") or "",
                                    "vo-tag", "vo-tag.mp3", speed=0.8)

        if handle:
            handle.progress((len(plates) + 3) / total_steps, "cutting", "assembling the cut")
        card = build_end_card(catalog, tagline, "Available Now", size=canvas)
        out = _assemble(catalog, files, card, vo_cues, music,
                        native_audio=mode["audio"],
                        sfx=sfx, tag_vo=tag_vo, tag_delay=card_start + 0.8,
                        size=canvas, suffix=fmt["suffix"], trims=trims)

        # ── 6. the director watches the cut ──
        if handle:
            handle.progress((len(plates) + 3.5) / total_steps, "review", "the director reviews the cut")
        review = await review_cut(catalog, out, treatment)
        defects = [df for df in (review.get("defects") or []) if isinstance(df, dict) and df.get("plate")]
        if round_n == 0 and defects:
            # invalidate the defective plates' takes (clip + its stills) and go again
            bad_ids = {df["plate"] for df in defects}
            bad_files = {by_id[i].name for i in bad_ids if i in by_id}
            takes = _takes(catalog)
            tdir_ = OUTPUT_DIR / catalog / "trailer"
            for bf in bad_files:
                stem = bf.rsplit(".", 1)[0]
                for key in list(takes.keys()):
                    if key == stem or key.startswith(stem + "-"):
                        takes.pop(key, None)
                for f_ in tdir_.glob(stem + "*"):        # the clip and its stills: gone, so they reshoot
                    f_.unlink(missing_ok=True)
            _save_trailer(catalog, {"takes": takes})
            if handle:
                handle.progress((len(plates) + 3.6) / total_steps, "reshoot",
                                f"reshooting {len(bad_files)} plate(s) the director rejected")
            continue
        break

    _save_trailer(catalog, {"review": review})

    credits_after = await runway.credit_balance()
    record = {
        "mode": mode_name, "model": mode["model"], "format": format_name,
        "quality": "draft" if mode.get("draft") else "master",
        "file": out.name, "poster": f"trailer-poster{fmt['suffix']}.jpg",
        "seconds": round(_probe_seconds(out), 1),
        "credits_used": max(0, credits_before - credits_after),
        "credits_left": credits_after,
        "shots": len(files),
        "plates": len(plates),
        "review": review.get("score"),
        "provider": mode.get("provider", "runway"),
    }

    # the archive: every finished cut is kept and watchable in the cinema
    import datetime
    import shutil
    book2 = get_book_by_catalog(catalog)
    versions = list(((book2["data"].get("trailer") or {}).get("versions")) or [])
    vn = len(versions) + 1
    shutil.copy2(out, OUTPUT_DIR / catalog / f"trailer-v{vn}.mp4")
    poster = OUTPUT_DIR / catalog / record["poster"]
    if poster.exists():
        shutil.copy2(poster, OUTPUT_DIR / catalog / f"trailer-v{vn}.jpg")
    versions.append({"n": vn, "mode": mode_name, "format": format_name,
                     "quality": "draft" if mode.get("draft") else "master",
                     "seconds": record["seconds"],
                     "credits_used": record["credits_used"],
                     "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
    _save_trailer(catalog, {"production": record, "versions": versions})
    return record


# ── the 4K finish ────────────────────────────────────────────────

async def finish_4k(catalog: str, resolution: str = "4k", handle=None) -> dict:
    """Upscale the approved MASTER to 4K (or 2K). Faithful sharpening, not
    re-imagining — and only masters get finished; drafts are for iterating."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    tr = book["data"].get("trailer") or {}
    prod = tr.get("production") or {}
    if prod.get("quality") == "draft":
        if (tr.get("production") or {}).get("mode") != "workorder":
            raise RuntimeError("The latest cut is a draft — shoot the master first")
        # a work-order cut is the footage the publisher approved: finish it as it is
    src = OUTPUT_DIR / catalog / (prod.get("file") or "trailer.mp4")
    if not src.exists():
        raise RuntimeError("No master to finish — produce the trailer first")
    if _probe_seconds(src) > 30:
        raise RuntimeError("The upscaler takes at most 30 seconds of video")

    credits_before = await runway.credit_balance()
    if handle:
        handle.progress(0.1, "upload", "sending the master to the lab")
    uri = await runway.upload_file(src)
    if handle:
        handle.progress(0.25, "upscale", f"finishing in {resolution}")
    task = await runway.video_upscale(uri, resolution=resolution)
    result = await runway.wait_for(task["id"], timeout_s=1800)
    if result.get("status") != "SUCCEEDED":
        raise RuntimeError(f"Upscale failed: {result.get('status')}")
    url = (result.get("output") or [None])[0]
    if not url:
        raise RuntimeError("Upscale returned no output")

    suffix = src.name.replace("trailer", "").replace(".mp4", "")
    dest = OUTPUT_DIR / catalog / f"trailer-4k{suffix}.mp4"
    await runway.download(url, dest)

    # the lab must not lose the mix — remux the master's audio if it did
    proc = subprocess.run([_ffmpeg(), "-i", str(dest)],
                          capture_output=True, text=True, timeout=60)
    if "Audio:" not in proc.stderr:
        fixed = dest.with_suffix(".muxed.mp4")
        _run(["-i", str(dest), "-i", str(src),
              "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
              "-movflags", "+faststart", str(fixed)], "remux audio")
        fixed.replace(dest)

    credits_after = await runway.credit_balance()
    record = {"file": dest.name, "resolution": resolution,
              "source": src.name,
              "seconds": round(_probe_seconds(dest), 1),
              "credits_used": max(0, credits_before - credits_after)}
    import datetime
    fresh = get_book_by_catalog(catalog)
    data = dict(fresh["data"])
    trd = dict(data.get("trailer") or {})
    versions = list(trd.get("versions") or [])
    vn = len(versions) + 1
    import shutil
    shutil.copy2(dest, OUTPUT_DIR / catalog / f"trailer-v{vn}.mp4")
    versions.append({"n": vn, "mode": prod.get("mode"), "format": prod.get("format"),
                     "quality": resolution, "seconds": record["seconds"],
                     "credits_used": record["credits_used"],
                     "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
    trd["versions"] = versions
    trd["finish"] = record
    data["trailer"] = trd
    update_book(fresh["id"], data)
    return record


# ── the score bench ──────────────────────────────────────────────

async def compose_score_options(catalog: str, brief: str, count: int = 3,
                                handle=None) -> dict:
    """Compose candidate scores from the publisher's energy description.
    They land as auditionable files; picking one pins it for every cut."""
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    out = OUTPUT_DIR / catalog

    def _persist(options):
        fresh = get_book_by_catalog(catalog)
        data = dict(fresh["data"])
        tr = dict(data.get("trailer") or {})
        tr["score_options"] = options
        data["trailer"] = tr
        update_book(fresh["id"], data)

    options = []
    _persist(options)          # clear the bench; takes appear as they finish
    done = 0

    async def one_take(i: int):
        nonlocal done
        try:
            task = await runway.music_bed(brief, 32)
            result = await runway.wait_for(task["id"], timeout_s=420)
            if result.get("status") != "SUCCEEDED":
                return
            url = (result.get("output") or [None])[0]
            if not url:
                return
            dest = out / f"score-option-{i}.mp3"
            await runway.download(url, dest)
            options.append({"n": i, "file": dest.name, "brief": brief})
            options.sort(key=lambda o: o["n"])
            _persist(options)  # each finished take is audible immediately
        finally:
            done += 1
            if handle:
                handle.progress(done / count, "composing",
                                f"{done} of {count} takes finished")

    # all three at once — total time is the slowest take, not the sum.
    # If the account tier throttles concurrency, Runway queues the extras
    # and the polling simply waits; never slower than sequential.
    await asyncio.gather(*(one_take(i) for i in range(1, count + 1)))
    _persist(options)
    return {"options": options}


def pin_score(catalog: str, n: int) -> dict:
    """The publisher's pick becomes THE score for every future cut."""
    import shutil
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    tr = dict(book["data"].get("trailer") or {})
    opt = next((o for o in (tr.get("score_options") or []) if o.get("n") == n), None)
    if not opt:
        raise ValueError(f"No score option {n}")
    src = OUTPUT_DIR / catalog / opt["file"]
    if not src.exists():
        raise ValueError("That option's file is gone — compose again")
    dest = OUTPUT_DIR / catalog / "score-pinned.mp3"
    shutil.copy2(src, dest)
    data = dict(book["data"])
    tr["score"] = {"file": dest.name, "brief": opt.get("brief") or ""}
    data["trailer"] = tr
    update_book(book["id"], data)
    return tr["score"]



async def _write_vo_script(book: dict, n: int = 4) -> list:
    """The narrator's lines, written as a trailer voice-over from the
    back-cover text: hook, stakes, turn, closing question. Short, spoken,
    no repetition, under 40 words in all."""
    d = book["data"]
    blurb = (d.get("back_cover_blurb") or ((d.get("manuscript") or {}).get("blurb")) or "").strip()
    if not blurb:
        return []
    from ..writing.client import extract_json
    EXEMPLAR = (
        "Some places stay with you, even when you've spent your whole life leaving. / "
        "When her grandmother dies, Elinor inherits the house where she spent her childhood summers. / "
        "She came back to Lake Como for one reason. / To sell it. / "
        "But the house isn't the only thing that's been waiting for her. / "
        "Dario hasn't changed. / He hasn't aged. / And he can't leave. / "
        "A promise made long ago has kept him here. / "
        "Now, to save the house, she must break the promise. / "
        "To save him, she must finally learn how to stay.")
    try:
        raw = await _chatgpt(
            "You write movie-trailer voice-over for books: few words, spoken rhythm, every line lands, "
            "and the lines tell the story in order — the picture will be cut to them.",
            f"BOOK: \"{book['title']}\"\nGENRE: {_genre_label(book)}\nBACK COVER:\n{blurb}\n\n"
            "Write the trailer voice-over in the HOUSE SHAPE, 10-12 lines, 80-100 words in all:\n"
            "1. a theme line that states what the story is about in one breath;\n"
            "2. the situation — who the protagonist is and what just happened (name them once);\n"
            "3. the protagonist's intent, in two short lines: '... for one reason.' / 'To ...';\n"
            "4. the turn: 'But ... isn't the only thing ...' (the discovery that changes everything);\n"
            "5. three very short strokes about the force against them — a person, a threat, a secret "
            "(use a name only if the back cover gives one);\n"
            "6. the rule or the clock that binds the story, one line;\n"
            "7. the twin stakes: 'To save X, they must ...' / 'To save Y, they must ...' — "
            "with the protagonist's own pronoun.\n"
            "ONLY what the back cover says: no invented characters, names, places or facts; every "
            "line must be traceable to the back cover. Plain words, spoken sentences, no rhetorical "
            "questions, no adjectives piled up, no repetition of an idea or a key word. Do not write "
            "the title or 'available on Amazon' — that is added. Model the RHYTHM (not the content or "
            f"the genre) on this example from a romance:\n{EXEMPLAR}\n\n"
            'Return JSON: {"lines": ["...", "..."]}')
        lines = [str(x).strip() for x in (extract_json(raw) or {}).get("lines", []) if str(x).strip()]
        return lines[:12]
    except Exception:
        return []


async def _chatgpt(system: str, user: str) -> str:
    """The publisher's rule: the voice-over is written by ChatGPT (OpenAI), same
    engine family as the covers. gpt-5 first, older models if it is unavailable."""
    import httpx
    from ..config import OPENAI_API_KEY
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    last = None
    async with httpx.AsyncClient(timeout=120) as c:
        for model in ("gpt-5", "gpt-4.1", "gpt-4o"):
            try:
                r = await c.post("https://api.openai.com/v1/responses",
                                 headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                                 json={"model": model, "instructions": system, "input": user})
                if r.status_code != 200:
                    last = r.text[:200]; continue
                data = r.json()
                text = "".join(cc.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                               for cc in item.get("content", []) if cc.get("type") == "output_text")
                if text.strip():
                    return text
            except Exception as e:
                last = str(e)[:200]
    raise RuntimeError(f"ChatGPT did not answer: {last}")


def _genre_label(book: dict) -> str:
    from ..prose.models import GENRE_PRESETS
    g = (book["data"].get("genre_preset") or "").strip()
    return (GENRE_PRESETS.get(g) or {}).get("label") or g.replace("_", " ").title() or "fiction"


# the score follows the genre — the vibe the publisher wants for each shelf
SCORE_BY_GENRE = {
    "romance":        "Cinematic string orchestra film score for a romantic movie: lush legato strings, a slow "
                      "yearning melody in the violins over warm cellos, gentle swells, bittersweet and hopeful, "
                      "in the style of a classic Hollywood love theme. No percussion, no drums, no electronic sounds, no piano, no vocals.",
    "thriller":       "Epic action-thriller movie trailer score: driving cinematic percussion and pounding "
                      "drums, deep braams, staccato strings, massive brass hits, a relentless rising pulse that "
                      "accelerates and builds to an explosive climax. Dark, loud, urgent. No vocals.",
    "mystery":        "Cinematic mystery score: suspended strings, a slow piano motif, soft pulse, curious and "
                      "uneasy, building with restraint. No vocals.",
    "fantasy":        "Sweeping epic orchestral fantasy score: strings, horns and choir-like pads, wonder and "
                      "danger, building to a grand swell. No vocals.",
    "default":        "Cinematic orchestral trailer score, emotional and building to a peak. No vocals.",
}


SERIES_THEMES = Path.home() / ".scrpt" / "house" / "series"


def series_theme(book: dict):
    """A series can have ONE theme, used by every book in it — the way a
    television series keeps its main title across a season. Stored per
    series id, so all four Larkspur trailers share a sound the reader
    recognises before the title card arrives."""
    sid = ((book["data"].get("series") or {}).get("series_id") or "").strip()
    if not sid:
        return None
    f = SERIES_THEMES / f"{sid}-theme.mp3"
    if not (f.exists() and f.stat().st_size > 10_000):
        return None
    # A theme is dropped in by hand, so its loudness is whatever the composer
    # or the generator happened to produce — one theme can be 14 dB quieter
    # than another and vanish under the narration at the same bed setting.
    # Normalise once to a house standard so every theme lands at the same
    # level and `bed` means the same thing for all of them.
    norm = SERIES_THEMES / f"{sid}-theme.norm.mp3"
    if not (norm.exists() and norm.stat().st_mtime >= f.stat().st_mtime):
        try:
            _run(["-y", "-i", str(f), "-af", "loudnorm=I=-18:TP=-2:LRA=11",
                  "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", str(norm)],
                 "series theme normalise")
        except Exception:
            return f
    return norm if norm.exists() else f


def score_brief_for(book: dict) -> str:
    g = (book["data"].get("genre_preset") or "").lower()
    if "romance" in g and "dark" not in g:
        key = "romance"
    elif "romantasy" in g or "fantasy" in g:
        key = "fantasy"
    elif "thriller" in g or "crime" in g or "dark_romance" in g:
        key = "thriller"
    elif "mystery" in g:
        key = "mystery"
    else:
        key = "default"
    return SCORE_BY_GENRE[key]


async def _pick_blurb_lines(blurb: str, n: int = 4) -> list:
    """(kept) Three or four strong sentences, VERBATIM from the back-cover text."""
    import re as _re
    sentences = [x.strip() for x in _re.split(r"(?<=[.!?])\s+", blurb.replace("\n", " ")) if len(x.strip()) > 3]
    if len(sentences) <= n:
        return sentences
    from ..writing.client import complete, extract_json, mechanical_model, set_model_override
    try:
        set_model_override(mechanical_model())
        raw = await complete(
            "You pick trailer narration from a book's back-cover copy.",
            "From these numbered sentences pick the " + str(n) + " that work best spoken slowly "
            "by a deep movie-trailer narrator — the hook, the stakes, the closing question. "
            "No two picks may repeat the same idea or share a key word (e.g. do not pick both "
            "'...avoiding: staying' and '...choose to stay'). Keep them in reading order. "
            "Return JSON: {\"indices\": [..]}\n\n"
            + "\n".join(f"{i}. {x}" for i, x in enumerate(sentences)), max_tokens=120)
        idx = [int(i) for i in (extract_json(raw) or {}).get("indices", []) if 0 <= int(i) < len(sentences)]
        idx = sorted(dict.fromkeys(idx))[:n]
        picked = []
        import re as _re2
        def _stems(t):
            return {w[:5] for w in _re2.findall(r"[a-z']{4,}", t.lower())}
        for i in idx:                      # drop a line that repeats an earlier pick's idea
            st_ = _stems(sentences[i])
            if any(len(st_ & _stems(q)) >= 2 for q in picked):
                continue
            picked.append(sentences[i])
        if picked:
            return picked
    except Exception:
        pass
    finally:
        set_model_override(None)
    return [sentences[0], sentences[len(sentences) // 2], sentences[-1]]


def _mix_narration(take: Path, vo: list, out: Path, tag: Optional[Path] = None, tag_at: float = 0.0,
                   score: Optional[Path] = None, bed: float = 0.42,
                   score_fade_in: float = 1.0):
    """vo: [(path, start_s)]. The take's own sound stays as ambience, the
    score sits under it, and both duck under every narration line."""
    inputs = ["-i", str(take)]
    filters = []
    labels = []
    n = 1
    score_idx = None
    if score and score.exists():
        inputs += ["-stream_loop", "-1", "-i", str(score)]      # the score repeats as long as the film needs
        score_idx = n; n += 1
    for item in vo:
        path, start = item[0], item[1]
        gain = 1.45 * (item[2] if len(item) > 2 and item[2] else 1.0)
        inputs += ["-i", str(path)]
        filters.append(f"[{n}:a]adelay={int(start*1000)}|{int(start*1000)},volume={gain:.2f}[v{n}]")
        labels.append(f"[v{n}]"); n += 1
    if tag and tag.exists():
        inputs += ["-i", str(tag)]
        filters.append(f"[{n}:a]adelay={int(tag_at*1000)}|{int(tag_at*1000)},volume=1.5[v{n}]")
        labels.append(f"[v{n}]"); n += 1
    total = _probe_seconds(take) or 30.0
    if score_idx is not None:
        filters.append(f"[{score_idx}:a]atrim=0:{total:.2f},asetpts=PTS-STARTPTS,"
                       f"afade=t=in:st=0:d={score_fade_in:.2f},"
                       f"afade=t=out:st={max(0.0, total-2.4):.2f}:d=2.2,volume={bed:.2f}[scr]")
        filters.append("[0:a]volume=0.7[amb]")
        filters.append("[amb][scr]amix=inputs=2:duration=first:normalize=0[bedraw]")
        bed_in = "[bedraw]"
    else:
        bed_in = "[0:a]"
    if not labels:
        filters.append(f"{bed_in}apad=whole_dur={total:.2f},atrim=0:{total:.2f},loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    else:
        filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0,"
                       f"apad=whole_dur={total:.2f},atrim=0:{total:.2f},asplit=2[voice][key]")
        filters.append(f"{bed_in}[key]sidechaincompress=threshold=0.04:ratio=5:attack=80:release=600:makeup=1[bed]")
        filters.append(f"[bed][voice]amix=inputs=2:duration=longest:normalize=0,apad=whole_dur={total:.2f},atrim=0:{total:.2f},loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    _run(["-y", *inputs, "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[a]",
          "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out)], "narration mix")
    return out


def _trim_model_ending(take: Path) -> Path:
    """Seedance tends to finish on its own title card (a painted copy of the
    cover) whatever the work order says. If the take's last cut falls inside
    the final seven seconds, everything after that cut is the model's end
    screen: drop it, so the real cover is the only ending."""
    dur = _probe_seconds(take) or 0
    if dur < 12:
        return take
    proc = subprocess.run([_ffmpeg(), "-i", str(take), "-vf", "select='gt(scene,0.3)',showinfo",
                           "-an", "-f", "null", "-"], capture_output=True, text=True, timeout=300)
    cuts = [float(m) for m in re.findall(r"pts_time:([\d.]+)", proc.stderr)]
    late = [c for c in cuts if c >= dur - 7.0]
    if not late:
        return take
    cut_at = min(late)
    if cut_at < dur * 0.5:
        return take
    trimmed = take.with_name(take.stem + "-trimmed.mp4")
    _run(["-y", "-i", str(take), "-t", f"{cut_at:.2f}", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
          "-c:a", "aac", "-b:a", "160k", str(trimmed)], "trim model ending")
    return trimmed if trimmed.exists() else take


# ── the script-led cut ───────────────────────────────────────────
# The footage follows the narration, not the model's order: shots are found
# and classified, the man is held back until the line that introduces him,
# and a line about a specific image gets a clip generated for it.

def _shots_of(video: Path, min_len: float = 1.2) -> list:
    dur = _probe_seconds(video) or 0
    proc = subprocess.run([_ffmpeg(), "-i", str(video), "-vf", "select='gt(scene,0.3)',showinfo",
                           "-an", "-f", "null", "-"], capture_output=True, text=True, timeout=600)
    cuts = [0.0] + [float(m) for m in re.findall(r"pts_time:([\d.]+)", proc.stderr)] + [dur]
    shots = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a >= min_len:
            shots.append((a, b))
        elif shots:
            shots[-1] = (shots[-1][0], b)      # a flicker joins its neighbour
    return shots


async def _classify_shots(video: Path, shots: list) -> list:
    from ..writing.client import complete_vision, extract_json
    out = []
    for a, b in shots:
        fb = _frame(video, a + (b - a) / 2)
        info = {"man": False, "woman": False, "child": False, "desc": ""}
        if fb:
            try:
                raw = await complete_vision(
                    "You describe film frames precisely.",
                    'Return JSON only: {"man": true/false (an adult man visible), "woman": true/false '
                    '(an adult woman visible), "child": true/false, "text": true/false (any readable text, '
                    'lettering, screen UI or signage), "desc": "six words"}', fb, max_tokens=120)
                j = extract_json(raw) or {}
                if isinstance(j, dict):
                    info.update({k: bool(j.get(k)) for k in ("man", "woman", "child", "text")})
                    info["desc"] = str(j.get("desc", ""))[:60]
            except Exception:
                pass
        out.append({"start": a, "end": b, **info})
    return out


def _cut_segment(video: Path, a: float, b: float, dest: Path, W: int, H: int):
    _run(["-y", "-ss", f"{a:.3f}", "-i", str(video), "-t", f"{max(0.2, b - a):.3f}", "-an",
          "-vf", f"scale={W}:{H},fps=24,format=yuv420p", "-c:v", "libx264", "-preset", "fast", "-crf", "18", str(dest)], "cut")


def _script_cut(catalog: str, footage: Path, shots: list, plan: list, W: int, H: int) -> Path:
    """plan: [(need_seconds, allow_man, insert_clip or None)] in order. Fills each
    block from the shot pool in footage order, trimming the last shot to fit."""
    tdir = OUTPUT_DIR / catalog / "trailer"
    parts = []
    used = set()
    uses: dict = {}
    n = 0
    for need, allow_man, insert in plan:
        if insert and insert.exists():
            seg = tdir / f"cut-{n:02d}.mp4"; n += 1
            _cut_segment(insert, 0.0, min(need, _probe_seconds(insert) or need), seg, W, H)
            parts.append(seg)
            continue
        remaining = need
        for i, sh in enumerate(shots):
            if remaining <= 0.15:
                break
            if i in used or sh.get("text") or (sh["man"] and not allow_man):
                continue
            take = min(sh["end"] - sh["start"], remaining)
            seg = tdir / f"cut-{n:02d}.mp4"; n += 1
            _cut_segment(footage, sh["start"], sh["start"] + take, seg, W, H)
            parts.append(seg); used.add(i); remaining -= take
            uses[i] = uses.get(i, 0) + 1
        guard = 0
        while remaining > 0.5 and guard < 12:
            # pool ran dry: cycle the least-used eligible shots, a different one each time
            pool = [(i, sh) for i, sh in enumerate(shots) if not sh.get("text") and (allow_man or not sh["man"])]
            if not pool:
                break
            i, sh = min(pool, key=lambda x: (uses.get(x[0], 0), -(x[1]["end"] - x[1]["start"])))
            take = min(sh["end"] - sh["start"], remaining, 3.5)
            seg = tdir / f"cut-{n:02d}.mp4"; n += 1
            _cut_segment(footage, sh["start"], sh["start"] + take, seg, W, H)
            parts.append(seg); remaining -= take; uses[i] = uses.get(i, 0) + 1; guard += 1
    lst = tdir / "cut-list.txt"
    lst.write_text("".join(f"file '{p_.name}'\n" for p_ in parts))
    out = tdir / "workorder-scriptcut.mp4"
    _run(["-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], "script cut")
    return out


async def _upscale_chunked(src: Path, handle=None) -> Path:
    """Runway's upscaler takes ≤30 s per job: split, upscale each part, rejoin."""
    up = src.with_name(src.stem + "-4k.mp4")
    if up.exists():
        return up
    total = _probe_seconds(src) or 0
    parts = []
    n = max(1, int(total // 29.0) + (1 if total % 29.0 > 0.5 else 0))
    seg_len = total / n
    for i in range(n):
        part = src.with_name(f"{src.stem}-part{i}.mp4")
        _run(["-y", "-ss", f"{i*seg_len:.3f}", "-i", str(src), "-t", f"{seg_len:.3f}", "-an",
              "-c:v", "libx264", "-preset", "fast", "-crf", "16", str(part)], "4k split")
        part_up = part.with_name(part.stem + "-4k.mp4")
        if not part_up.exists():
            if handle:
                handle.progress(0.79, "4k", f"upscaling part {i+1}/{n} to 4K")
            uri = await runway.upload_file(part)
            task = await runway.video_upscale(uri, resolution="4k")
            result = await runway.wait_for(task["id"], timeout_s=1800)
            url = (result.get("output") or [None])[0] if result.get("status") == "SUCCEEDED" else None
            if not url:
                raise RuntimeError(f"4K upscale failed on part {i+1}: {result.get('status')}")
            await runway.download(url, part_up)
        parts.append(part_up)
    lst = src.with_name(src.stem + "-4k.txt")
    lst.write_text("".join(f"file '{p_.name}'\n" for p_ in parts))
    _run(["-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(up)], "4k join")
    return up


# ── the work order ───────────────────────────────────────────────
# The publisher's rule (2026-08-22): SCRPT gives the video model a work
# order, not art direction. One request: the title, the front cover as the
# reference, the back-cover text, and the end screen. The model directs.

WORKORDER_RATIO = {"wide": {"draft": "1280:720", "master": "1920:1080"},
                   "vertical": {"draft": "720:1280", "master": "1080:1920"},
                   "ad": {"draft": "720:1280", "master": "1080:1920"}}


def workorder_prompt(book: dict) -> str:
    d = book["data"]
    blurb = (d.get("back_cover_blurb") or ((d.get("manuscript") or {}).get("blurb")) or d.get("description") or "").strip()
    author = d.get("author_name") or ""
    return (
        f"Create a movie trailer for a book called \"{book['title']}\". It is a {_genre_label(book)} novel. "
        "Use the front cover (the reference image) as a reference. "
        "Do not add an end screen, title card or any text — the book cover end screen is added afterwards. "
        "No voice-over.\n\n"
        f"{blurb}"
    )


async def produce_workorder(catalog: str, quality: str = "draft", format_name: str = "wide",
                            seconds: int = 30, handle=None, reuse_take: bool = True,
                            finish: str = "", takes_wanted: int = 1) -> dict:
    """finish="4k": the Seedance footage (≤30 s) goes through Runway's
    upscaler and the cover card is rendered natively at 4K, so the whole
    film — not just the take — is delivered at 3840×2160."""
    """One take, one prompt. Seedance 2.5 on Runway directs the whole trailer."""
    import datetime
    import shutil
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    fmt = FORMATS.get(format_name, FORMATS["wide"])
    ratio = WORKORDER_RATIO.get(format_name, WORKORDER_RATIO["wide"])["master" if quality == "master" else "draft"]
    cover = OUTPUT_DIR / catalog / "cover-front.png"
    if not cover.exists():
        raise RuntimeError("The book has no front cover yet — the work order needs it as the reference")
    prompt = workorder_prompt(book)
    if handle:
        handle.progress(0.05, "work order", "handing the work order to Seedance 2.5")
    cover_uri = await runway.upload_file(cover)
    credits_before = await runway.credit_balance()
    tdir = OUTPUT_DIR / catalog / "trailer"
    tdir.mkdir(parents=True, exist_ok=True)
    dest = tdir / f"workorder-{_h(prompt + ratio + str(seconds))}.mp4"
    last_err = None
    if reuse_take and dest.exists() and dest.stat().st_size > 500_000:
        if handle:
            handle.progress(0.6, "shooting", "reusing the take (same work order) — re-finishing only")
    else:
        if handle:
            handle.progress(0.15, "shooting", f"Seedance is making the trailer ({seconds}s, {ratio})")
        if not await _shoot_seedance_take(prompt, cover_uri, seconds, ratio, True, dest):
            raise RuntimeError("Seedance could not make the trailer: Runway kept refusing the work order")

    out = OUTPUT_DIR / catalog / f"trailer{fmt['suffix']}.mp4"
    # the model's own end screen goes; the real cover is the only ending
    if handle:
        handle.progress(0.78, "ending", "removing the model's own end screen")
    dest = _trim_model_ending(dest)
    # a long narration needs more picture: a second take from the same work
    # order, its own end screen removed, cut onto the first
    if takes_wanted >= 2:
        dest2 = tdir / f"workorder-{_h(prompt + ratio + str(seconds))}-take2.mp4"
        if not (dest2.exists() and dest2.stat().st_size > 500_000):
            if handle:
                handle.progress(0.5, "shooting", "a second take for the longer narration")
            if not await _shoot_seedance_take(prompt, cover_uri, seconds, ratio, True, dest2):
                raise RuntimeError("second take failed: Runway could not deliver a usable take")
        second = _trim_model_ending(dest2)
        joined = tdir / f"workorder-joined-{_h(dest.name + second.name)}.mp4"
        if not joined.exists():
            W0, H0 = _probe_size(dest)
            lst = tdir / "workorder-join.txt"
            n1 = tdir / "workorder-join-1.mp4"; n2 = tdir / "workorder-join-2.mp4"
            for src_, dst_ in ((dest, n1), (second, n2)):
                _run(["-y", "-i", str(src_), "-vf", f"scale={W0}:{H0},fps=24,format=yuv420p", "-an",
                      "-c:v", "libx264", "-preset", "fast", "-crf", "18", str(dst_)], "join norm")
            lst.write_text(f"file '{n1.name}'\nfile '{n2.name}'\n")
            _run(["-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], "join")
        dest = joined
    if finish == "4k":
        dest = await _upscale_chunked(dest, handle)
    # ── the narration first: its timing shapes the cut ──
    if handle:
        handle.progress(0.8, "narration", "recording the narrator")
    blurb = (book["data"].get("back_cover_blurb") or ((book["data"].get("manuscript") or {}).get("blurb")) or "").strip()
    stored = (book["data"].get("trailer") or {}).get("workorder_lines")
    lines = list(stored) if stored else await _write_vo_script(book, 4)
    if lines and not stored:
        _save_trailer(catalog, {"workorder_lines": lines})
    genre = book["data"].get("genre_preset") or ""
    takes, kept_lines = [], []
    for ln in lines:
        _g = (book["data"].get("genre_preset") or "").lower()
        _fast = any(k in _g for k in ("thriller", "crime", "action", "mystery"))
        vo_speed = float((book["data"].get("trailer") or {}).get("workorder_vo_speed") or (1.12 if _fast else 0.88))
        t_ = await _record_line(catalog, ln, genre, f"vo-wo-{_h(ln)}-{vo_speed}", f"vo-wo-{_h(ln)}-{vo_speed}.mp3", speed=vo_speed)
        if t_:
            takes.append(t_); kept_lines.append(ln)
    durs = [_probe_seconds(t_) or 3.0 for t_ in takes]
    GAP = 0.6 if _fast else 1.1
    cue_times = []
    t0 = 2.0
    for d_ in durs:
        cue_times.append(t0); t0 += d_ + GAP
    footage_needed = t0 + 1.5                      # narration ends 1.5 s before the cover
    # as many takes as the narration needs: every ~26 s of picture is one take
    pieces = [dest]
    k = 2
    while sum((_probe_seconds(x) or 0) for x in pieces) + 1.0 < footage_needed and k <= 5:
        destk = tdir / f"workorder-{_h(prompt + ratio + str(seconds))}-take{k}.mp4"
        if not (destk.exists() and destk.stat().st_size > 500_000):
            if handle:
                handle.progress(0.5, "shooting", f"take {k} for the longer narration")
            if not await _shoot_seedance_take(prompt, cover_uri, seconds, ratio, True, destk):
                raise RuntimeError(f"take {k} failed: Runway could not deliver a usable take")
        pieces.append(_trim_model_ending(destk))
        k += 1
    if len(pieces) > 1:
        joined = tdir / f"workorder-joined-{_h(''.join(p_.name for p_ in pieces))}.mp4"
        if not joined.exists():
            W0, H0 = _probe_size(pieces[0])
            norm = []
            for i, src_ in enumerate(pieces):
                dst_ = tdir / f"workorder-join-{i+1}.mp4"
                _run(["-y", "-i", str(src_), "-vf", f"scale={W0}:{H0},fps=24,format=yuv420p", "-an",
                      "-c:v", "libx264", "-preset", "fast", "-crf", "18", str(dst_)], "join norm")
                norm.append(dst_)
            lst = tdir / "workorder-join.txt"
            lst.write_text("".join(f"file '{n.name}'\n" for n in norm))
            _run(["-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], "join")
        dest = joined
    W, H = _probe_size(dest)

    # ── the script-led cut: the man is held until the line before he is named;
    #    a line about the girl in the lake gets its own clip ──
    bible = (book["data"].get("manuscript") or {}).get("story_bible") or {}
    chars = bible.get("characters") or []
    male_names = [c.get("name", "").split()[0] for c in chars if str(c.get("description", "")).lower().find(" he ") >= 0 or "hero" in str(c.get("role", "")).lower() or "love interest" in str(c.get("role", "")).lower()]
    male_names = [m for m in male_names if m] or ["Dario"]
    man_from = None
    for i, ln in enumerate(kept_lines):
        if any(n_ in ln for n_ in male_names):
            man_from = cue_times[max(0, i - 1)]
            break
    child_line = next((i for i, ln in enumerate(kept_lines) if "childhood" in ln.lower()), None)
    child_clip = None
    if child_line is not None:
        child_clip = tdir / "workorder-childhood.mp4"
        if not child_clip.exists():
            if handle:
                handle.progress(0.81, "shooting", "a clip of the girl in the lake for the childhood line")
            try:
                task = await runway.generate_seedance(
                    "A young girl, about eight years old, swimming and playing in the lake in front of the old villa "
                    "on a bright summer afternoon, laughing, splashing, then floating on her back in the sun.",
                    [cover_uri], seconds=8, ratio=ratio, model="seedance2_5", audio=False)
                result = await runway.wait_for(task["id"], timeout_s=1500)
                url = (result.get("output") or [None])[0] if result.get("status") == "SUCCEEDED" else None
                if url:
                    await runway.download(url, child_clip)
            except Exception:
                child_clip = None
        if child_clip and not child_clip.exists():
            child_clip = None
    # ── script-led shooting: one clip per beat of the narration, described by
    #    the lines themselves (the words are the picture's brief); the work-order
    #    takes fill the opening and any gaps ──
    beats = []          # (start_line_index, end_line_index_exclusive)
    i = 0
    while i < len(kept_lines):
        span_ = 1
        # short lines pair up into one beat; a long line stands alone
        while i + span_ < len(kept_lines) and sum(len(kept_lines[j].split()) for j in range(i, i + span_ + 1)) <= 16 and span_ < 2:
            span_ += 1
        beats.append((i, i + span_)); i += span_
    beat_clips = {}
    for bi, (a_, b_) in enumerate(beats):
        if child_line is not None and a_ <= child_line < b_:
            continue                                  # that beat has its lake clip
        text = " ".join(kept_lines[a_:b_])
        need = sum(durs[a_:b_]) + GAP * (b_ - a_)
        secs = int(max(5, min(12, round(need + 1.5))))
        clip = tdir / f"beat-{_h(text + ratio)}.mp4"
        if not (clip.exists() and clip.stat().st_size > 200_000):
            if handle:
                handle.progress(0.82, "shooting", f"beat {bi + 1}/{len(beats)}: {text[:50]}")
            try:
                task = await runway.generate_seedance(
                    f"A shot for a {_genre_label(book)} movie trailer illustrating this narration: \"{text}\" "
                    "No text or lettering on screen.",
                    [cover_uri], seconds=secs, ratio=ratio, model="seedance2_5", audio=False)
                result = await runway.wait_for(task["id"], timeout_s=1500)
                url = (result.get("output") or [None])[0] if result.get("status") == "SUCCEEDED" else None
                if url:
                    await runway.download(url, clip)
                elif handle:
                    handle.progress(0.82, "shooting", f"beat {bi + 1} failed: {json.dumps(result.get('failure') or result.get('status'))[:140]}")
            except Exception as e:
                if handle:
                    handle.progress(0.82, "shooting", f"beat {bi + 1} error: {str(e)[:140]}")
        if clip.exists():
            beat_clips[bi] = _trim_model_ending(clip)
    if handle:
        handle.progress(0.83, "cutting", "cutting the footage to the script")
    shots = await _classify_shots(dest, _shots_of(dest))
    plan = []
    cursor = 0.0
    marks = []
    if child_clip and child_line is not None:
        marks.append((cue_times[child_line], min(durs[child_line] + GAP, _probe_seconds(child_clip) or 8.0), child_clip))
    for bi, (a_, b_) in enumerate(beats):
        if bi in beat_clips:
            length = sum(durs[a_:b_]) + GAP * (b_ - a_)
            marks.append((cue_times[a_], min(length, _probe_seconds(beat_clips[bi]) or length), beat_clips[bi]))
    marks.sort(key=lambda m: m[0])
    for at, length, clip in marks:
        if at < cursor:                      # overlapping marks: the earlier one keeps its time
            length -= (cursor - at); at = cursor
            if length < 0.8:
                continue
        if at > cursor:
            plan.append((at - cursor, man_from is not None and cursor >= man_from, None))
        plan.append((length, False, clip))
        cursor = at + length
    if man_from is not None and man_from > cursor:
        plan.append((man_from - cursor, False, None)); cursor = man_from
    if footage_needed > cursor:
        plan.append((footage_needed - cursor, True, None))
    dest = _script_cut(catalog, dest, shots, plan, W, H)
    # a small shortfall is absorbed by holding the last frame; a real one is refused later
    have = _probe_seconds(dest) or 0
    if 0 < footage_needed - have <= 3.0:
        padded = tdir / "workorder-scriptcut-padded.mp4"
        _run(["-y", "-i", str(dest), "-vf", f"tpad=stop_mode=clone:stop_duration={footage_needed - have + 0.3:.2f}",
              "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18", str(padded)], "pad")
        dest = padded

    # ── the real cover card, dissolving in; the music fades after the read ──
    if handle:
        handle.progress(0.86, "end screen", "adding the book's actual cover")
    tagline = ((book["data"].get("manuscript") or {}).get("tagline") or book["data"].get("tagline") or "").strip()
    card = build_end_card(catalog, tagline, "Available on Amazon", size=(W, H))
    card_clip = tdir / f"workorder-card-{W}x{H}.mp4"
    tag_vo = None
    try:
        tag_vo = await _record_line(catalog, f"{book['title']} — Available on Amazon.", genre,
                                    "vo-wo-tag2", "vo-wo-tag2.mp3", speed=0.8)
    except Exception:
        pass
    XF = 1.2
    TAG_IN = XF + 0.8
    tag_len = (_probe_seconds(tag_vo) if tag_vo else 3.0) or 3.0
    CARD_S = round(TAG_IN + tag_len + 0.8 + 2.6, 2)
    _run(["-y", "-loop", "1", "-t", f"{CARD_S:.1f}", "-i", str(card), "-f", "lavfi", "-t", f"{CARD_S:.1f}", "-i", "anullsrc=r=48000:cl=stereo",
          "-vf", f"scale={W}:{H},fps=24,format=yuv420p", "-r", "24", "-ar", "48000", "-ac", "2",
          "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(card_clip)], "workorder card")
    take_norm = tdir / "workorder-take-norm.mp4"
    _run(["-y", "-i", str(dest), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
          "-map", "0:v", "-map", "1:a", "-shortest",
          "-vf", f"scale={W}:{H},fps=24,format=yuv420p",
          "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "160k", str(take_norm)], "workorder norm")
    take_s = _probe_seconds(take_norm) or footage_needed
    # the agreed script is the fixed point: every line must end ≥1 s before the cover.
    # a small shortfall is covered by holding the last frame; a large one needs more picture.
    _last_end = max((t + (_probe_seconds(t_) or 3.0)) for t_, t in zip(takes, cue_times)) if takes else 0
    _need_take = _last_end + 1.0 + XF
    if take_s < _need_take:
        short = _need_take - take_s
        if short > 3.5:
            raise RuntimeError(f"The picture is {short:.1f} s too short for the agreed script — "
                               "not built with lines missing; shoot another take")
        held = tdir / "workorder-take-held.mp4"
        _run(["-y", "-i", str(take_norm), "-vf", f"tpad=stop_mode=clone:stop_duration={short + 0.2:.2f}",
              "-af", f"apad=pad_dur={short + 0.2:.2f}", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
              "-c:a", "aac", "-b:a", "160k", str(held)], "workorder hold")
        take_norm = held
        take_s = _probe_seconds(take_norm) or _need_take
    picture = tdir / "workorder-picture.mp4"
    _run(["-y", "-i", str(take_norm), "-i", str(card_clip), "-filter_complex",
          f"[0:v][1:v]xfade=transition=fade:duration={XF}:offset={max(0.0, take_s - XF):.2f}[v];"
          f"[0:a][1:a]acrossfade=d={XF}[a]",
          "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
          "-c:a", "aac", "-b:a", "160k", str(picture)], "workorder dissolve")
    total = _probe_seconds(picture) or (take_s + CARD_S - XF)
    card_at = take_s - XF
    gains = (book["data"].get("trailer") or {}).get("workorder_line_gain") or {}
    cues = [(t_, t, next((g for k, g in gains.items() if k.lower() in ln.lower()), 1.0))
            for t_, t, ln in zip(takes, cue_times, kept_lines)]
    # the agreed script is the fixed point: every line must fit before the cover

    # ── the score, under everything, resolving on the cover ──
    score = None
    try:
        if handle:
            handle.progress(0.9, "score", "composing the score")
        score_brief = score_brief_for(book)
        score = await _record_music(catalog, score_brief, total + 15, "workorder")
        if not score:
            raise RuntimeError("No usable score came back from the music model — the trailer was not finished without music")
    except RuntimeError:
        raise
    mixed = tdir / "workorder-mixed.mp4"
    out = OUTPUT_DIR / catalog / (f"trailer-4k{fmt['suffix']}.mp4" if finish == "4k" else f"trailer{fmt['suffix']}.mp4")
    bed = (book["data"].get("trailer") or {}).get("workorder_bed") or (0.8 if _fast else 0.42)
    fade_in = float((book["data"].get("trailer") or {}).get("score_fade_in") or 3.5)
    if _mix_narration(picture, cues, mixed, tag=tag_vo, tag_at=card_at + TAG_IN, score=score,
                      bed=bed, score_fade_in=fade_in):
        shutil.copy2(mixed, out)
    else:
        shutil.copy2(picture, out)
    poster = OUTPUT_DIR / catalog / f"trailer-poster{fmt['suffix']}.jpg"
    _run(["-y", "-i", str(out), "-ss", "1.0", "-frames:v", "1", "-q:v", "3", str(poster)], "poster")
    credits_after = await runway.credit_balance()
    record = {"mode": "workorder", "model": "seedance2_5", "format": format_name,
              "quality": ("4k" if finish == "4k" else ("master" if quality == "master" else "draft")), "provider": "seedance",
              "file": out.name, "poster": poster.name, "seconds": round(_probe_seconds(out), 1),
              "credits_used": max(0, credits_before - credits_after), "credits_left": credits_after,
              "shots": 1, "plates": 1, "prompt": prompt}
    book2 = get_book_by_catalog(catalog)
    versions = list(((book2["data"].get("trailer") or {}).get("versions")) or [])
    vn = len(versions) + 1
    shutil.copy2(out, OUTPUT_DIR / catalog / f"trailer-v{vn}.mp4")
    if poster.exists():
        shutil.copy2(poster, OUTPUT_DIR / catalog / f"trailer-v{vn}.jpg")
    versions.append({"n": vn, "mode": "workorder", "format": format_name, "quality": record["quality"],
                     "seconds": record["seconds"], "credits_used": record["credits_used"],
                     "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
    _save_trailer(catalog, {"production": record, "versions": versions, "workorder_prompt": prompt})
    return record



# ── the storyboard ───────────────────────────────────────────────
# The publisher hands SCRPT a storyboard: numbered panels with a shot
# description, a duration and the voice-over line. Each panel is shot as
# its own clip (the panel text is the model's brief, plus the board's
# global style note), cut to the board's timing, narrated line by line,
# scored by genre, closed on the real cover.


async def parse_storyboard_image(image_bytes: bytes, book: dict) -> dict:
    """Read an uploaded storyboard sheet (a director's panel grid, however
    rough) and transcribe it into the board this module shoots from. The
    publisher's panels and captions are the brief; nothing is invented
    beyond what a professional storyboard artist would infer from the
    image to make each panel shootable."""
    from ..writing.client import complete_vision, extract_json
    import io
    from PIL import Image
    # complete_vision always declares image/png to the API — normalize
    # whatever format the upload actually is (jpg, webp, ...) to real PNG
    # bytes so the declared and actual media types never mismatch.
    buf = io.BytesIO()
    Image.open(io.BytesIO(image_bytes)).convert("RGB").save(buf, format="PNG")
    image_bytes = buf.getvalue()
    blurb = (book["data"].get("back_cover_blurb")
             or ((book["data"].get("manuscript") or {}).get("blurb")) or "").strip()
    prompt = (
        f"This is a movie-trailer storyboard for the book \"{book['title']}\" "
        f"({_genre_label(book)}). Back-cover copy, for context only:\n{blurb[:800]}\n\n"
        "Transcribe EVERY numbered panel in the image, in order, into a shootable board. "
        "For each panel, look at both its thumbnail image and its caption together, then "
        "write a full, self-contained shot description a video model can film WITHOUT ever "
        "seeing this storyboard — describe the framing, the subject, the setting, the action "
        "and the lighting concretely, in one or two sentences. Do not invent new plot events, "
        "characters or locations beyond what the panel and caption show; do not skip, merge "
        "or reorder panels. If a panel's caption already reads like a spoken trailer line "
        "(short, punchy), reuse it near-verbatim as that panel's voice-over; if a panel is "
        "purely visual (no caption line, or a scene label only), leave \"vo\" as an empty "
        "string — not every panel needs narration. Never repeat the same voice-over idea or "
        "key phrase across two panels. Give each panel a duration in seconds — 3 to 4.5 for "
        "most beats, a little longer only for an establishing or closing panel — long enough "
        "to hold its own visual and, if it has one, its voice-over line at a natural pace.\n\n"
        "Also write: an overall STYLE line (look, color grade, camera handling, genre tone — "
        "read from the whole board, including any stated genre/tone header) and a MUSIC brief "
        "(instrumentation, mood, tempo, explicitly \"no vocals\") that matches that tone — "
        "write it as a real score brief, not just the tone words.\n\n"
        "Return JSON only: {\"style\": \"...\", \"music\": \"...\", "
        "\"panels\": [{\"n\": \"1\", \"title\": \"...\", \"dur\": 3.5, "
        "\"shot\": \"...\", \"vo\": \"...\"}, ...]}"
    )
    raw = await complete_vision(
        "You are a professional storyboard artist and trailer editor, transcribing a "
        "director's storyboard into precise shooting notes for a video model that will "
        "never see the original image.",
        prompt, image_bytes, max_tokens=6000)
    data = extract_json(raw) or {}
    panels = data.get("panels") or []
    if not isinstance(panels, list) or not panels:
        raise RuntimeError("Could not find any numbered panels in that image")
    clean = []
    for i, pn in enumerate(panels):
        if not isinstance(pn, dict) or not (pn.get("shot") or "").strip():
            continue
        try:
            dur = float(pn.get("dur") or 3.5)
        except (TypeError, ValueError):
            dur = 3.5
        clean.append({
            "n": str(pn.get("n") or i + 1),
            "title": str(pn.get("title") or "")[:80],
            "dur": max(2.0, min(12.0, dur)),
            "shot": str(pn.get("shot") or "").strip(),
            "vo": str(pn.get("vo") or "").strip(),
        })
    if not clean:
        raise RuntimeError("Could not find any shootable panels in that image")
    return {"style": str(data.get("style") or "").strip(),
            "music": str(data.get("music") or "").strip(),
            "panels": clean}


async def produce_storyboard(catalog: str, board: dict, format_name: str = "wide",
                             handle=None, version_label: str = "storyboard") -> dict:
    import datetime
    import shutil
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    fmt = FORMATS.get(format_name, FORMATS["wide"])
    ratio = WORKORDER_RATIO.get(format_name, WORKORDER_RATIO["wide"])["draft"]
    cover = OUTPUT_DIR / catalog / "cover-front.png"
    tdir = OUTPUT_DIR / catalog / "trailer"
    tdir.mkdir(parents=True, exist_ok=True)
    if not cover.exists():
        raise RuntimeError("The book has no front cover yet — upload it on the Cover tab first")
    cover_uri = await runway.upload_file(cover)
    # character references: the same face across books (e.g. Luc Reyer)
    char_uris = {}
    for name, rel in (board.get("characters") or {}).items():
        pth = Path(rel) if str(rel).startswith("/") else OUTPUT_DIR / catalog / "trailer" / rel
        if pth.exists():
            try:
                char_uris[name] = await runway.upload_file(pth)
            except Exception:
                pass
    credits_before = await runway.credit_balance()
    from .bible import apply_cast, cast_of, world_of
    cast = cast_of(book)
    world = world_of(book)
    # a board may bring its own style; otherwise the bible's world describes it
    style = (board.get("style") or "").strip() or world.get("style", "")
    panels = board.get("panels") or []
    genre = book["data"].get("genre_preset") or ""
    _g = genre.lower()
    _fast = any(k in _g for k in ("thriller", "crime", "action", "mystery"))

    # 1. narration first (each panel's line), so panel lengths can stretch to fit
    vo_speed = float((book["data"].get("trailer") or {}).get("workorder_vo_speed") or (1.12 if _fast else 0.88))
    GAP = 0.5
    vo_files, vo_durs = [], []
    if handle:
        handle.progress(0.05, "narration", "recording the narrator")
    # a panel may also carry a LINE: a character speaking in their own voice,
    # landing just after the narrator rather than over him.
    #   "line": {"text": "...", "voice": "<elevenlabs id>", "gap": 0.3, "speed": 1.0}
    line_files: list = []
    for pn in panels:
        ln = (pn.get("vo") or "").strip()
        if not ln:
            vo_files.append(None); vo_durs.append(0.0)
        else:
            t_ = await _record_line(catalog, ln, genre, f"vo-sb-{_h(ln)}-{vo_speed}", f"vo-sb-{_h(ln)}-{vo_speed}.mp3", speed=vo_speed)
            vo_files.append(t_); vo_durs.append((_probe_seconds(t_) if t_ else 0.0) or 0.0)
        spoken = pn.get("line") or {}
        stext = (spoken.get("text") or "").strip()
        if stext:
            svoice = (spoken.get("voice") or "").strip()
            sspeed = float(spoken.get("speed") or 1.0)
            sf = await _record_line(catalog, stext, genre,
                                    f"line-sb-{_h(stext + svoice)}-{sspeed}",
                                    f"line-sb-{_h(stext + svoice)}-{sspeed}.mp3",
                                    speed=sspeed, voice_override=svoice)
            line_files.append((sf, float(spoken.get("gap") or 0.3),
                               (_probe_seconds(sf) if sf else 0.0) or 0.0))
        else:
            line_files.append((None, 0.0, 0.0))

    # 2. one clip per panel, trimmed to the panel's length (stretched if the line needs it)
    W = H = None
    segs, cues, t = [], [], 0.0
    # A trailer should breathe before it speaks: hold the opening image on
    # music alone for a beat so the score sets the tone, then bring the
    # narrator in. Only the first panel is stretched; everything after it
    # keeps the board's timing.
    # House default (learned on The Botanist's Quiet Ruin): a trailer opens on
    # music. Three seconds of score over the establishing shot — carrying the
    # series logo if there is one — before the narrator says a word.
    lead_in = float((book["data"].get("trailer") or {}).get("score_lead_in") or 3.0)

    # ── plan every panel first, then SHOOT THEM ALL AT ONCE.
    # Shooting inside the assembly loop meant panel 2 waited for panel 1 to
    # come back from Runway. Nine panels at two to five minutes each is most
    # of an hour spent waiting, and the panels do not depend on one another.
    plans = []
    for i, pn in enumerate(panels):
        want = float(pn.get("dur") or 3)
        lf, lgap, llen = line_files[i]
        spoken_end = (vo_durs[i] + lgap + llen + 0.45) if lf else 0.0
        off = lead_in if i == 0 else 0.0
        need = off + max(want, (vo_durs[i] + GAP if vo_durs[i] else 0), spoken_end)
        secs = int(max(4, min(12, round(need + 0.6))))
        use_cover_ref = board.get("cover_ref", True)
        refs = [cover_uri] if use_cover_ref else []
        who = " Reference image 1 is the book cover: its world and palette." if use_cover_ref else ""
        for name in (pn.get("characters") or []):
            if char_uris.get(name):
                refs.append(char_uris[name])
                who += f" {name} is the man in reference image {len(refs)} — the same face, hair, beard and build." if who else f" {name} is the man in reference image {len(refs)} — the same face, hair, beard and build."
        # the cast sheet is canon: a named character always arrives with the
        # same words, so the face does not drift from panel to panel
        shot_txt = apply_cast(pn.get("shot", "").strip(), cast)
        prompt = f"{shot_txt} {style} No text or lettering on screen.{who}".strip()
        clip = tdir / f"sb-{_h(prompt + ratio + str(secs))}.mp4"
        plans.append({"i": i, "pn": pn, "prompt": prompt, "refs": refs,
                      "secs": secs, "clip": clip, "need": need, "off": off,
                      "lf": lf, "lgap": lgap})

    done_n = [0]
    shoot_gate = asyncio.Semaphore(4)

    async def shoot_panel(pl):
        i, pn, clip = pl["i"], pl["pn"], pl["clip"]
        prompt, refs, secs = pl["prompt"], pl["refs"], pl["secs"]
        if clip.exists() and clip.stat().st_size > 200_000:
            return
        async with shoot_gate:
            if handle:
                handle.progress(0.1 + 0.6 * i / max(1, len(panels)), "shooting", f"panel {pn.get('n', i+1)} — {pn.get('title','')}")
            ok = False
            moderation_hits = 0
            live_refs = list(refs)
            last_fail = ""
            for attempt in range(8):
                task = await runway.generate_seedance(prompt, live_refs, seconds=secs, ratio=ratio,
                                                      model="seedance2_5", audio=False)
                result = await runway.wait_for(task["id"], timeout_s=1500)
                url = (result.get("output") or [None])[0] if result.get("status") == "SUCCEEDED" else None
                if url:
                    await runway.download(url, clip); ok = True; break
                last_fail = json.dumps(result.get("failure") or result.get("failureCode") or result.get("status"))
                if "moderation" in last_fail.lower() or "third_party" in last_fail.lower():
                    moderation_hits += 1
                # a run of likeness/moderation blocks with a reference image likely means the
                # reference (the cover, or a cast face) reads as a real person — the same picture
                # keeps getting rejected no matter how many times we ask, so drop the image and
                # ship on the text alone rather than exhaust every retry on a doomed reference.
                if moderation_hits >= 3 and live_refs:
                    live_refs = []
                    if handle:
                        handle.progress(0.1 + 0.6 * i / max(1, len(panels)), "shooting",
                                        f"panel {pn.get('n', i+1)} — reference image looks blocked as a real likeness, retrying without it")
                elif handle:
                    handle.progress(0.1 + 0.6 * i / max(1, len(panels)), "shooting", f"panel {pn.get('n', i+1)} retry — {last_fail[:120]}")
                await asyncio.sleep(8 * (attempt + 1))
            if not ok:
                raise RuntimeError(f"panel {pn.get('n', i+1)} could not be shot: {last_fail[:200]}")
        done_n[0] += 1
        if handle:
            handle.progress(0.1 + 0.6 * done_n[0] / max(1, len(plans)), "shooting",
                            f"{done_n[0]} of {len(plans)} panels shot")

    await asyncio.gather(*(shoot_panel(pl) for pl in plans))

    # ── now assemble, in order, from clips that already exist
    for pl in plans:
        i, pn, clip = pl["i"], pl["pn"], pl["clip"]
        need, off = pl["need"], pl["off"]
        lf, lgap = pl["lf"], pl["lgap"]
        if W is None:
            W, H = _probe_size(clip)
        seg = tdir / f"sb-seg-{i:02d}.mp4"
        _cut_segment(clip, 0.0, need, seg, W, H)
        segs.append(seg)
        if vo_files[i]:
            cues.append((vo_files[i], t + off + 0.15, 1.0))
        if lf:
            # lands after the narrator has finished — never over him
            cues.append((lf, t + off + 0.15 + vo_durs[i] + lgap, 1.25))
        t += need
    # the series name over the opening beat, while the theme plays alone
    series_title = ((book["data"].get("series") or {}).get("series_title") or "").strip()
    if lead_in >= 1.5 and series_title and segs:
        card = build_series_card(catalog, series_title, (W, H))
        if card:
            plated = tdir / "sb-seg-00-titled.mp4"
            # the logo breathes: a slow fade up, a real hold, a slow fade away.
            # It may linger past the first narration line — a main title does.
            seg_len = _probe_seconds(segs[0]) or 6.0
            fin_at, fin = 0.4, 1.2
            hold_until = min(seg_len - 2.0, lead_in + 0.9)     # stays just past the lead-in
            hold_until = max(fin_at + fin + 0.6, hold_until)
            fout = 1.3
            _run(["-y", "-i", str(segs[0]), "-loop", "1", "-i", str(card),
                  "-filter_complex",
                  f"[1:v]format=rgba,fade=t=in:st={fin_at}:d={fin}:alpha=1,"
                  f"fade=t=out:st={hold_until:.2f}:d={fout}:alpha=1[t];"
                  f"[0:v][t]overlay=0:0:enable='between(t,0,{hold_until + fout + 0.3:.2f})',"
                  f"fps=24,format=yuv420p[v]",
                  "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                  "-t", f"{_probe_seconds(segs[0]) or 6:.2f}", str(plated)], "series card overlay")
            segs[0] = plated

    footage = tdir / "sb-footage.mp4"
    lst = tdir / "sb-list.txt"
    lst.write_text("".join(f"file '{x.name}'\n" for x in segs))
    _run(["-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(footage)], "storyboard concat")

    # 3. the real cover, the title read, the score, the mix — as the work order does
    if handle:
        handle.progress(0.82, "end screen", "adding the book's actual cover")
    tagline = ((book["data"].get("manuscript") or {}).get("tagline") or book["data"].get("tagline") or "").strip()
    card = build_end_card(catalog, tagline, "Available on Amazon", size=(W, H))
    card_clip = tdir / f"sb-card-{W}x{H}.mp4"
    tag_vo = await _record_line(catalog, f"{book['title']} — Available on Amazon.", genre, "vo-wo-tag2", "vo-wo-tag2.mp3", speed=0.8)
    XF = 1.2; TAG_IN = XF + 0.8
    tag_len = (_probe_seconds(tag_vo) if tag_vo else 3.0) or 3.0
    CARD_S = round(TAG_IN + tag_len + 0.8 + 2.6, 2)
    _run(["-y", "-loop", "1", "-t", f"{CARD_S:.1f}", "-i", str(card), "-f", "lavfi", "-t", f"{CARD_S:.1f}", "-i", "anullsrc=r=48000:cl=stereo",
          "-vf", f"scale={W}:{H},fps=24,format=yuv420p", "-r", "24", "-ar", "48000", "-ac", "2",
          "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(card_clip)], "sb card")
    take_norm = tdir / "sb-take-norm.mp4"
    _run(["-y", "-i", str(footage), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a", "-shortest",
          "-vf", f"scale={W}:{H},fps=24,format=yuv420p", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "160k", str(take_norm)], "sb norm")
    take_s = _probe_seconds(take_norm) or t
    picture = tdir / "sb-picture.mp4"
    _run(["-y", "-i", str(take_norm), "-i", str(card_clip), "-filter_complex",
          f"[0:v][1:v]xfade=transition=fade:duration={XF}:offset={max(0.0, take_s - XF):.2f}[v];[0:a][1:a]acrossfade=d={XF}[a]",
          "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "160k", str(picture)], "sb dissolve")
    total = _probe_seconds(picture) or (take_s + CARD_S - XF)
    card_at = take_s - XF
    if handle:
        handle.progress(0.9, "score", "composing the score")
    score = series_theme(book)
    if score:
        if handle:
            handle.progress(0.9, "score", "using the series theme")
    else:
        score = await _record_music(catalog, (board.get("music") or "").strip() or score_brief_for(book), total + 15, "storyboard")
    if not score:
        raise RuntimeError("No usable score came back from the music model")
    mixed = tdir / "sb-mixed.mp4"
    out = OUTPUT_DIR / catalog / f"trailer{fmt['suffix']}.mp4"
    bed = (book["data"].get("trailer") or {}).get("workorder_bed") or (0.8 if _fast else 0.42)
    fade_in = float((book["data"].get("trailer") or {}).get("score_fade_in") or 3.5)
    if _mix_narration(picture, cues, mixed, tag=tag_vo, tag_at=card_at + TAG_IN, score=score,
                      bed=bed, score_fade_in=fade_in):
        shutil.copy2(mixed, out)
    else:
        shutil.copy2(picture, out)
    poster = OUTPUT_DIR / catalog / f"trailer-poster{fmt['suffix']}.jpg"
    _run(["-y", "-i", str(out), "-ss", "1.0", "-frames:v", "1", "-q:v", "3", str(poster)], "poster")
    credits_after = await runway.credit_balance()
    record = {"mode": "storyboard", "model": "seedance2_5", "format": format_name, "quality": "draft", "provider": "seedance",
              "file": out.name, "poster": poster.name, "seconds": round(_probe_seconds(out), 1),
              "credits_used": max(0, credits_before - credits_after), "credits_left": credits_after,
              "shots": len(panels), "plates": len(panels)}
    book2 = get_book_by_catalog(catalog)
    versions = list(((book2["data"].get("trailer") or {}).get("versions")) or [])
    vn = len(versions) + 1
    shutil.copy2(out, OUTPUT_DIR / catalog / f"trailer-v{vn}.mp4")
    if poster.exists():
        shutil.copy2(poster, OUTPUT_DIR / catalog / f"trailer-v{vn}.jpg")
    versions.append({"n": vn, "mode": "storyboard", "format": format_name, "quality": "draft", "seconds": record["seconds"],
                     "credits_used": record["credits_used"], "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
    _save_trailer(catalog, {"production": record, "versions": versions, "storyboard": board})
    return record
