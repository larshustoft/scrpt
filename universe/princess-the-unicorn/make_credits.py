#!/usr/bin/env python3
"""The credits ending: two screens over the theme instrumental.

Screen 1 — "Created and Written by The Tiger Family / Music by Lars
Tiger", with Princess sitting and breathing in the corner and Pip
flying the outer margin, never over the words.
Screen 2 — the TigerWorks mark, Pip flying out of frame.

Frame-by-frame compositing: nothing generated, nothing random.
"""
import math, shutil, subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = Path(__file__).parent
W, H, FPS = 1920, 1080, 24
S1, S2 = 9.0, 8.0                      # seconds per screen
BRAND = Path("/Users/tiger/.scrpt/house/brand/tigerworks-white.png")


def _font(size):
    for fp in ("/System/Library/Fonts/Supplemental/Futura.ttc",
               "/System/Library/Fonts/Avenir Next.ttc",
               "/System/Library/Fonts/HelveticaNeue.ttc"):
        try:
            return ImageFont.truetype(fp, size, index=0)
        except OSError:
            continue
    return ImageFont.load_default()


def _tracked(dr, text, font, cx, y, gap, fill, shadow=True):
    """Letterspaced, with a soft dark shadow so white type stays readable
    over a bright painted backdrop."""
    w = sum(dr.textlength(c, font=font) + gap for c in text) - gap
    if shadow:
        sh = tuple(int(v * 0.10) for v in (255, 255, 255))
        for dx, dy in ((2, 2), (2, 3), (3, 2), (-1, 2), (1, 3)):
            x = cx - w / 2
            for c in text:
                dr.text((x + dx, y + dy), c, font=font, fill=sh)
                x += dr.textlength(c, font=font) + gap
    x = cx - w / 2
    for c in text:
        dr.text((x, y), c, font=font, fill=fill)
        x += dr.textlength(c, font=font) + gap


def _fit(img, h_px):
    return img.resize((int(img.width * h_px / img.height), h_px), Image.LANCZOS)


def _pip_pose(pip, t):
    """A flap: the wings read as motion if the bird lifts and tilts."""
    lift = math.sin(t * 7.0) * 6
    tilt = math.sin(t * 7.0) * 5
    return pip.rotate(tilt, resample=Image.BICUBIC, expand=True), lift


def build_over_clip(clip: Path, out=HERE / "credits-ending.mp4"):
    """Credits over a LIVE scene (Lars, 2026-08-31: full-screen animation,
    not a sprite on a still). The clip carries the world and Princess
    walking in; we only lay the type and the mark on top."""
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    # 1. the type, as a transparent overlay with its scrim
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(over)
    for y in range(H):                      # top-down scrim for legibility
        a = int(205 * max(0.0, 1 - (y / H) / 0.86))
        dr.line([(0, y), (W, y)], fill=(12, 16, 34, a))
    f_small, f_big = _font(26), _font(54)
    _tracked(dr, "CREATED AND WRITTEN BY", f_small, W / 2, H * 0.34, 5, (222, 222, 226, 255))
    _tracked(dr, "The Tiger Family", f_big, W / 2, H * 0.40, 3, (255, 255, 255, 255))
    _tracked(dr, "MUSIC BY", f_small, W / 2, H * 0.56, 5, (222, 222, 226, 255))
    _tracked(dr, "Lars Tiger", f_big, W / 2, H * 0.62, 3, (255, 255, 255, 255))
    over.save(tmp / "type.png")

    # 2. the mark screen, as before
    mark = Image.open(BRAND).convert("RGBA")
    mark = mark.crop(mark.split()[3].getbbox())
    mark = mark.resize((int(W * 0.145), int(mark.height * (W * 0.145) / mark.width)),
                       Image.LANCZOS)
    # the mark rides the SAME living scene, over a dim so it reads
    over2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(over2)
    d2.rectangle([0, 0, W, H], fill=(6, 9, 22, 165))
    over2.paste(mark, ((W - mark.width) // 2, (H - mark.height) // 2), mark)
    over2.save(tmp / "mark.png")

    scene = tmp / "scene.mp4"
    subprocess.run([FF, "-y", "-i", str(clip),
                    "-loop", "1", "-framerate", str(FPS), "-t", str(S1),
                    "-i", str(tmp / "type.png"),
                    "-filter_complex",
                    f"[0:v]scale={W}:{H},fps={FPS},format=yuv420p,"
                    f"fade=t=in:st=0:d=0.8[bg];"
                    f"[1:v]format=rgba,fade=t=in:st=0.6:d=1.0:alpha=1,"
                    f"fade=t=out:st={S1-1.0:.1f}:d=1.0:alpha=1[tx];"
                    f"[bg][tx]overlay=0:0,trim=0:{S1},setpts=PTS-STARTPTS[v]",
                    "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium",
                    "-crf", "17", str(scene)], check=True, capture_output=True)

    markclip = tmp / "mark.mp4"
    subprocess.run([FF, "-y", "-ss", str(S1), "-i", str(clip),
                    "-loop", "1", "-framerate", str(FPS), "-t", str(S2),
                    "-i", str(tmp / "mark.png"), "-filter_complex",
                    f"[0:v]scale={W}:{H},fps={FPS},format=yuv420p,"
                    f"trim=0:{S2},setpts=PTS-STARTPTS[bg];"
                    f"[1:v]format=rgba,fade=t=in:st=0:d=1.0:alpha=1,"
                    f"fade=t=out:st={S2-1.2:.1f}:d=1.2:alpha=1[mk];"
                    f"[bg][mk]overlay=0:0,fade=t=out:st={S2-1.0:.1f}:d=1.0[v]",
                    "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium",
                    "-crf", "17", "-r", str(FPS), str(markclip)],
                   check=True, capture_output=True)

    total = S1 + S2
    subprocess.run([FF, "-y", "-i", str(scene), "-i", str(markclip),
                    "-i", str(HERE / "theme/theme-instrumental.mp3"),
                    "-filter_complex",
                    f"[0:v][1:v]concat=n=2:v=1:a=0[v];"
                    f"[2:a]atrim=0:{total},aresample=48000,"
                    f"aformat=channel_layouts=stereo,afade=t=in:st=0:d=0.8,"
                    f"afade=t=out:st={total-2.5:.1f}:d=2.5,"
                    f"loudnorm=I=-14:TP=-1.5:LRA=11[a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "17", "-c:a", "aac",
                    "-b:a", "192k", "-r", str(FPS), str(out)],
                   check=True, capture_output=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print("credits (live scene) ->", out)


def build():
    """Real animation, not moved stills (Lars, 2026-08-31): Princess walks
    in on a four-frame cycle, settles, breathes and blinks; Pip flies on a
    four-frame wing-flap. Screen two is the mark alone — no characters."""
    S = HERE / "sprites"
    walk = [Image.open(S / f"princess-{i}.png").convert("RGBA") for i in (0, 1, 2, 3)]
    stand = Image.open(S / "princess-4.png").convert("RGBA")
    blink = Image.open(S / "princess-5.png").convert("RGBA")
    flap = [Image.open(S / f"pip-{i}.png").convert("RGBA") for i in range(4)]
    PH = 430                                  # Princess height on screen
    walk = [_fit(w, PH) for w in walk]
    stand, blink = _fit(stand, PH), _fit(blink, PH)
    flap = [_fit(f, 165) for f in flap]

    mark = Image.open(BRAND).convert("RGBA")
    mark = mark.crop(mark.split()[3].getbbox())
    mark = mark.resize((int(W * 0.145), int(mark.height * (W * 0.145) / mark.width)),
                       Image.LANCZOS)

    # THE KINGDOM AS BACKDROP (Lars, 2026-08-31) — the same world the
    # website opens with, painted empty so she can walk into her place.
    bg = Image.open(HERE / "credits-backdrop.png").convert("RGB")
    sc = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * sc + 1), int(bg.height * sc + 1)), Image.LANCZOS)
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2,
                  (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    # a gentle top-down scrim so white credits read on a bright painting
    scrim = Image.new("L", (1, H))
    for y in range(H):
        f = max(0.0, 1 - (y / H) / 0.86)
        scrim.putpixel((0, y), int(205 * f))
    scrim = scrim.resize((W, H))
    plate = Image.composite(Image.new("RGB", (W, H), (12, 16, 34)), bg, scrim)

    frames = HERE / "work-credits"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir()
    f_small, f_big = _font(26), _font(54)
    GREY, WHITE = (222, 222, 226), (255, 255, 255)

    glide = _fit(Image.open(S / "pip-glide.png").convert("RGBA"), 165)
    flare = _fit(Image.open(S / "pip-flare.png").convert("RGBA"), 175)
    perch = _fit(Image.open(S / "pip-perch.png").convert("RGBA"), 140)

    def _bez(p0, p1, p2, p3, u):
        """Cubic bezier — the shape of a real flight path, not a line."""
        m = 1 - u
        return (m*m*m*p0[0] + 3*m*m*u*p1[0] + 3*m*u*u*p2[0] + u*u*u*p3[0],
                m*m*m*p0[1] + 3*m*m*u*p1[1] + 3*m*u*u*p2[1] + u*u*u*p3[1])

    # in at the top right, a dipping swoop across, landing bottom left
    # the words own the middle of the frame: he sweeps ABOVE them, then
    # dives down the empty left edge to land (Lars: never in the way)
    P0 = (W * 1.06, H * 0.12)
    P1 = (W * 0.74, H * 0.02)      # rises over the top right
    P2 = (W * 0.05, H * 0.10)      # crosses high, above the credits
    P3 = (W * 0.12, H * 0.80)      # drops down the left to land
    FLY_T, LAND_T = 5.2, 6.4       # flying until 5.2s, feet down by 6.4s

    def pip_frame(t):
        """Returns (sprite, x, y). Eased flight, banking with the velocity,
        wings that flap on the climb and glide on the dive, a flare before
        touchdown, then perched and settling."""
        if t >= LAND_T:
            settle = max(0.0, 1 - (t - LAND_T) / 0.5)
            hop = -abs(math.sin((t - LAND_T) * 9)) * 10 * settle
            return perch, P3[0], P3[1] + hop
        if t >= FLY_T:                       # the flare: braking, feet down
            u = (t - FLY_T) / (LAND_T - FLY_T)
            x, y = _bez(P0, P1, P2, P3, 1.0)
            x_prev, y_prev = _bez(P0, P1, P2, P3, 0.93)
            x = x_prev + (x - x_prev) * u
            y = y_prev + (y - y_prev) * u
            return flare, x, y
        # ease-in-out along the curve so he accelerates and slows naturally
        raw = t / FLY_T
        u = raw * raw * (3 - 2 * raw)
        x, y = _bez(P0, P1, P2, P3, u)
        x2, y2 = _bez(P0, P1, P2, P3, min(1.0, u + 0.02))
        dy = y2 - y
        if dy > 6:                            # diving — hold the wings out
            spr = glide
        else:                                 # climbing/level — flap harder
            rate = 11 if dy < -2 else 8
            spr = flap[int(t * rate) % 4]
        bank = max(-28, min(28, -(y2 - y) * 1.6 + (x2 - x) * 0.10))
        return spr.rotate(bank, resample=Image.BICUBIC, expand=True), x, y

    n1 = int(S1 * FPS)
    WALK_END = 3.6                            # she walks in, then settles
    x_start, x_home = int(-W * 0.16), int(W * 0.17)
    for i in range(n1):
        t = i / FPS
        img = plate.copy()
        if fade_bg := min(1.0, t / 0.8):
            pass
        dr = ImageDraw.Draw(img)
        fade = min(1.0, t / 0.8, max(0.0, (S1 - t) / 0.8))
        if fade < 1:                       # fade the whole picture in/out
            img = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), img, fade)
            dr = ImageDraw.Draw(img)
        g = tuple(int(v * fade) for v in GREY)
        w_ = tuple(int(v * fade) for v in WHITE)
        _tracked(dr, "CREATED AND WRITTEN BY", f_small, W / 2, H * 0.34, 5, g)
        _tracked(dr, "The Tiger Family", f_big, W / 2, H * 0.40, 3, w_)
        _tracked(dr, "MUSIC BY", f_small, W / 2, H * 0.56, 5, g)
        _tracked(dr, "Lars Tiger", f_big, W / 2, H * 0.62, 3, w_)

        if t < WALK_END:                      # WALKING: 8 fps cycle, moving left
            k = int(t * 8) % 4
            sp = walk[k]                                    # facing right, entering
            _e = t / WALK_END
            _e = 1 - (1 - _e) ** 2            # she slows as she arrives
            px = int(x_start + (x_home - x_start) * _e)
            bob = math.sin(t * 8 * math.pi / 2) * 3
        else:                                 # SETTLED: breathing, blinking
            u = t - WALK_END
            eyes_shut = (u % 3.4) > 3.15      # a real blink, twice a screen
            sp = blink if eyes_shut else stand              # turns to the viewer
            px = x_home
            bob = math.sin(u * 1.7) * 4
        py = int(H - sp.height - H * 0.06 + bob)
        if fade < 1:
            sp = sp.copy(); sp.putalpha(sp.split()[3].point(lambda a: int(a * fade)))
        img.paste(sp, (px, py), sp)

        # (Pip retired from the credits — Lars, 2026-08-31)
        img.save(frames / f"a{i:04d}.png")

    n2 = int(S2 * FPS)
    for i in range(n2):                       # the mark, alone
        t = i / FPS
        img = Image.new("RGB", (W, H), (0, 0, 0))
        fade = min(1.0, t / 0.9, max(0.0, (S2 - t) / 1.2))
        m = mark.copy()
        m.putalpha(m.split()[3].point(lambda a: int(a * fade)))
        img.paste(m, ((W - m.width) // 2, (H - m.height) // 2), m)
        img.save(frames / f"b{i:04d}.png")

    total = S1 + S2
    subprocess.run([FF, "-y", "-framerate", str(FPS), "-i", str(frames / "a%04d.png"),
                    "-framerate", str(FPS), "-i", str(frames / "b%04d.png"),
                    "-i", str(HERE / "theme/theme-instrumental.mp3"),
                    "-filter_complex",
                    f"[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v];"
                    f"[2:a]atrim=0:{total},aresample=48000,"
                    f"aformat=channel_layouts=stereo,afade=t=in:st=0:d=0.8,"
                    f"afade=t=out:st={total-2.5:.1f}:d=2.5,"
                    f"loudnorm=I=-14:TP=-1.5:LRA=11[a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "17", "-c:a", "aac",
                    "-b:a", "192k", "-r", str(FPS),
                    str(HERE / "credits-ending.mp4")], check=True, capture_output=True)
    shutil.rmtree(frames)
    print("credits ->", HERE / "credits-ending.mp4", f"({total:.0f}s)")


if __name__ == "__main__":
    build()
