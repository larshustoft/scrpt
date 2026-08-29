"""The episode outro: the logo rests small at the top, credits breathe in
below over the instrumental theme, closing with the site. ~12 seconds.
Usage: python3 make_outro.py [out.mp4]
"""
import subprocess, sys
from pathlib import Path
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, ImageChops

HERE = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 24
W, H = 1920, 1080
SECONDS = 12.0

CREDITS = [
    ("Created by", 40),
    ("TIGERWORKS", 66),
    ("", 24),
    ("Story by Lily Tiger", 40),
    ("", 24),
    ("www.princesstheunicorn.com", 36),
]


def _font(size, bold=False):
    for fp in ("/System/Library/Fonts/Supplemental/Didot.ttc",
               "/System/Library/Fonts/Supplemental/Georgia.ttf"):
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def build(out: str) -> str:
    logo = Image.open(HERE / "logo.png").convert("RGB")
    bg = Image.new("RGB", logo.size, (255, 255, 255))
    bbox = ImageChops.difference(logo, bg).getbbox()
    if bbox:
        logo = logo.crop(bbox)
    card = Image.new("RGB", (W, H), (253, 251, 249))
    lw = int(W * 0.24); lh = int(logo.height * lw / logo.width)
    card.paste(logo.resize((lw, lh), Image.LANCZOS), ((W - lw) // 2, int(H * 0.08)))
    dr = ImageDraw.Draw(card)
    y = int(H * 0.08) + lh + int(H * 0.07)
    gold, ink = (201, 169, 106), (90, 78, 84)
    for text, size in CREDITS:
        if not text:
            y += size
            continue
        f = _font(size)
        tw = dr.textlength(text, font=f)
        colour = gold if text == "TIGERWORKS" else ink
        dr.text(((W - tw) / 2, y), text, font=f, fill=colour)
        y += int(size * 1.5)
    still = HERE / "_outro_card.png"
    card.save(still)
    theme = HERE / "theme/theme-instrumental.mp3"
    frames = int(SECONDS * FPS)
    vf = (f"zoompan=z='min(1.03,1+0.03*on/{frames})':d={frames}:"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=24,"
          f"fade=t=in:st=0:d=0.7,fade=t=out:st={SECONDS-1.0:.2f}:d=1.0,"
          f"format=yuv420p")
    subprocess.run([FF, "-y", "-v", "error", "-framerate", "24", "-loop", "1",
                    "-t", f"{SECONDS:.2f}", "-i", str(still),
                    "-i", str(theme),
                    "-af", (f"atrim=0:{SECONDS:.2f},"
                            f"afade=t=in:st=0:d=0.5,"
                            f"afade=t=out:st={SECONDS-1.4:.2f}:d=1.4"),
                    "-vf", vf, "-t", f"{SECONDS:.2f}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                    "-c:a", "aac", "-b:a", "192k", str(out)], check=True)
    still.unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else str(HERE / "outro.mp4")
    print(build(out))
