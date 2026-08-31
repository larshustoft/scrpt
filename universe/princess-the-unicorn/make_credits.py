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


def _tracked(dr, text, font, cx, y, gap, fill):
    w = sum(dr.textlength(c, font=font) + gap for c in text) - gap
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


def build():
    """Real animation, not moved stills (Lars, 2026-08-31): Princess walks
    in on a four-frame cycle, settles, breathes and blinks; Pip flies on a
    four-frame wing-flap. Screen two is the mark alone — no characters."""
    S = HERE / "sprites"
    walk = [Image.open(S / f"princess-{i}.png").convert("RGBA") for i in (0, 1, 2, 3)]
    stand = Image.open(S / "princess-4.png").convert("RGBA")
    blink = Image.open(S / "princess-5.png").convert("RGBA")
    flap = [Image.open(S / f"pip-{i}.png").convert("RGBA") for i in range(4)]
    PH = 380                                  # Princess height on screen
    walk = [_fit(w, PH) for w in walk]
    stand, blink = _fit(stand, PH), _fit(blink, PH)
    flap = [_fit(f, 165) for f in flap]

    mark = Image.open(BRAND).convert("RGBA")
    mark = mark.crop(mark.split()[3].getbbox())
    mark = mark.resize((int(W * 0.20), int(mark.height * (W * 0.20) / mark.width)),
                       Image.LANCZOS)

    frames = HERE / "work-credits"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir()
    f_small, f_big = _font(26), _font(54)
    GREY, WHITE = (150, 150, 150), (255, 255, 255)

    def pip_xy(u):
        """The outer margin, clockwise — never across the words."""
        mx, my = int(W * 0.07), int(H * 0.12)
        if u < 0.40:
            return mx, int(H * 0.82 - (H * 0.64) * (u / 0.40))
        if u < 0.70:
            return int(mx + (W - 2 * mx) * ((u - 0.40) / 0.30)), my
        return W - mx, int(my + (H * 0.55) * ((u - 0.70) / 0.30))

    n1 = int(S1 * FPS)
    WALK_END = 3.6                            # she walks in, then settles
    x_start, x_home = int(W * 1.02), int(W * 0.78)
    for i in range(n1):
        t = i / FPS
        img = Image.new("RGB", (W, H), (0, 0, 0))
        dr = ImageDraw.Draw(img)
        fade = min(1.0, t / 0.8, max(0.0, (S1 - t) / 0.8))
        g = tuple(int(v * fade) for v in GREY)
        w_ = tuple(int(v * fade) for v in WHITE)
        _tracked(dr, "CREATED AND WRITTEN BY", f_small, W / 2, H * 0.34, 5, g)
        _tracked(dr, "The Tiger Family", f_big, W / 2, H * 0.40, 3, w_)
        _tracked(dr, "MUSIC BY", f_small, W / 2, H * 0.56, 5, g)
        _tracked(dr, "Lars Tiger", f_big, W / 2, H * 0.62, 3, w_)

        if t < WALK_END:                      # WALKING: 8 fps cycle, moving left
            k = int(t * 8) % 4
            sp = walk[k].transpose(Image.FLIP_LEFT_RIGHT)   # facing left, entering
            px = int(x_start + (x_home - x_start) * (t / WALK_END))
            bob = math.sin(t * 8 * math.pi / 2) * 3
        else:                                 # SETTLED: breathing, blinking
            u = t - WALK_END
            eyes_shut = (u % 3.4) > 3.15      # a real blink, twice a screen
            sp = (blink if eyes_shut else stand).transpose(Image.FLIP_LEFT_RIGHT)
            px = x_home
            bob = math.sin(u * 1.7) * 4
        py = int(H - sp.height - H * 0.06 + bob)
        if fade < 1:
            sp = sp.copy(); sp.putalpha(sp.split()[3].point(lambda a: int(a * fade)))
        img.paste(sp, (px, py), sp)

        # Pip: a real flap cycle at 10 fps, riding the margin
        u = (t / 7.0) % 1.0
        bx, by = pip_xy(u)
        b = flap[int(t * 10) % 4]
        if u >= 0.70:
            b = b.transpose(Image.FLIP_LEFT_RIGHT)
        if fade < 1:
            b = b.copy(); b.putalpha(b.split()[3].point(lambda a: int(a * fade)))
        img.paste(b, (int(bx - b.width / 2), int(by - b.height / 2)), b)
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
