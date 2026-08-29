#!/usr/bin/env python3
"""The closing credits card — the last thing on screen in every episode.

Design (Lars, 2026-08-29): short, simple, minimalistic. Just the
TigerWorks wordmark with the year below and the website, then black.
It follows the lullaby tuck-in scene, so it fades IN from black and
back OUT to black; audio is carried by the lullaby's tail, so the
card itself is silent.
"""
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = Path(__file__).parent
W, H = 1920, 1080
DUR = 6.0          # seconds on screen
FADE = 0.9         # fade from/to black at each end
GOLD = (201, 169, 106)
SOFT = (150, 140, 146)


def _font(size):
    for fp in ("/System/Library/Fonts/Supplemental/Didot.ttc",
               "/System/Library/Fonts/Supplemental/Georgia.ttf"):
        try:
            return ImageFont.truetype(fp, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build(out=HERE / "credits-card.mp4"):
    img = Image.new("RGB", (W, H), (8, 7, 10))
    dr = ImageDraw.Draw(img)

    # wordmark, letterspaced by hand so it reads as a mark, not a word
    f_mark = _font(92)
    text, gap = "TIGERWORKS", 14
    tw = sum(dr.textlength(c, font=f_mark) + gap for c in text) - gap
    x = (W - tw) / 2
    y = H * 0.415
    for c in text:
        dr.text((x, y), c, font=f_mark, fill=GOLD)
        x += dr.textlength(c, font=f_mark) + gap

    # a hairline rule, then year and site, quiet and small
    dr.rectangle([W / 2 - 90, H * 0.545, W / 2 + 90, H * 0.545 + 2],
                 fill=(70, 62, 68))
    for txt, size, yy in (("2026", 34, 0.585),
                          ("princesstheunicorn.com", 30, 0.645)):
        f = _font(size)
        dr.text(((W - dr.textlength(txt, font=f)) / 2, H * yy),
                txt, font=f, fill=SOFT)

    still = HERE / "credits-card.png"
    img.save(still)

    subprocess.run([
        FF, "-y", "-framerate", "24", "-loop", "1",
        "-t", str(DUR), "-i", str(still),
        "-vf", (f"fade=t=in:st=0:d={FADE},"
                f"fade=t=out:st={DUR - FADE}:d={FADE},format=yuv420p"),
        "-c:v", "libx264", "-preset", "slow", "-crf", "17",
        "-r", "24", str(out),
    ], check=True, capture_output=True)
    print("credits card ->", out)


if __name__ == "__main__":
    build()
