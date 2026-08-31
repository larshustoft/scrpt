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
    # Lars's reference frame (2026-08-30): thin geometric sans, wide
    # tracking — Futura is the closest system face to the mockup
    for fp, idx in (("/System/Library/Fonts/Supplemental/Futura.ttc", 0),
                    ("/System/Library/Fonts/Avenir Next.ttc", 0),
                    ("/System/Library/Fonts/HelveticaNeue.ttc", 0)):
        try:
            return ImageFont.truetype(fp, size, index=idx)
        except OSError:
            continue
    return ImageFont.load_default()


def build(out=HERE / "endcard-tigerworks.mp4"):
    img = Image.new("RGB", (W, H), (0, 0, 0))
    dr = ImageDraw.Draw(img)
    f = _font(64)
    text, gap = "TigerWorks", 40         # wide airy tracking, per the mockup
    tw = sum(dr.textlength(c, font=f) + gap for c in text) - gap
    bb = dr.textbbox((0, 0), text, font=f)
    x, y = (W - tw) / 2, (H - (bb[3] - bb[1])) / 2 - bb[1] - 26
    for c in text:
        dr.text((x, y), c, font=f, fill=(255, 255, 255))
        x += dr.textlength(c, font=f) + gap

    # the studio line: where the work is made (Lars, 2026-08-30)
    f2 = _font(30)
    sub, gap2 = "France 2026", 10
    tw2 = sum(dr.textlength(ch, font=f2) + gap2 for ch in sub) - gap2
    x2 = (W - tw2) / 2
    y2 = y + (bb[3] - bb[1]) + 46
    for ch in sub:
        dr.text((x2, y2), ch, font=f2, fill=(168, 168, 168))
        x2 += dr.textlength(ch, font=f2) + gap2

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
