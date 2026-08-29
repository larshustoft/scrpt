#!/usr/bin/env python3
"""The end card — the last thing on screen in every episode.

Spec (Lars, 2026-08-29, superseding the gold version): white letters
on black, "TigerWorks" in a minimalistic sans font, centered
vertically and horizontally, 2 seconds, nothing else. The website
gets added later. Carries a silent audio track so concat is trivial.
"""
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = Path(__file__).parent
W, H = 1920, 1080
DUR = 2.0


def _font(size):
    for fp in ("/System/Library/Fonts/HelveticaNeue.ttc",
               "/System/Library/Fonts/Helvetica.ttc",
               "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(fp, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build(out=HERE / "endcard-tigerworks.mp4"):
    img = Image.new("RGB", (W, H), (0, 0, 0))
    dr = ImageDraw.Draw(img)
    f = _font(84)
    text, gap = "TigerWorks", 4          # a whisper of tracking, nothing more
    tw = sum(dr.textlength(c, font=f) + gap for c in text) - gap
    bb = dr.textbbox((0, 0), text, font=f)
    x, y = (W - tw) / 2, (H - (bb[3] - bb[1])) / 2 - bb[1]
    for c in text:
        dr.text((x, y), c, font=f, fill=(255, 255, 255))
        x += dr.textlength(c, font=f) + gap

    still = HERE / "endcard-tigerworks.png"
    img.save(still)
    subprocess.run([
        FF, "-y", "-framerate", "24", "-loop", "1", "-t", str(DUR),
        "-i", str(still),
        "-f", "lavfi", "-t", str(DUR),
        "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "slow",
        "-crf", "17", "-c:a", "aac", "-shortest", "-r", "24", str(out),
    ], check=True, capture_output=True)
    print("end card ->", out)


if __name__ == "__main__":
    build()
