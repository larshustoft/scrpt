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
    """The end screen is the MARK, nothing else (Lars, 2026-08-31): the
    white TigerWorks logo centred on black. No typeset name, no place,
    no year — the logo carries all of it."""
    logo = Path("/Users/tiger/.scrpt/house/brand/tigerworks-white.png")
    img = Image.new("RGB", (W, H), (0, 0, 0))
    lg = Image.open(logo).convert("RGBA")
    bbox = lg.split()[3].getbbox() or (0, 0, lg.width, lg.height)
    lg = lg.crop(bbox)
    target_w = int(W * 0.20)
    lg = lg.resize((target_w, int(lg.height * target_w / lg.width)), Image.LANCZOS)
    img.paste(lg, ((W - lg.width) // 2, (H - lg.height) // 2), lg)

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
