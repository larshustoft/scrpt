"""The Princess the Unicorn film intro: the logo blooms on soft white,
the episode name appears beneath, the theme plays. Usage:
    python3 make_intro.py "The Hidden Spring" [theme.mp3] [out.mp4]
"""
import subprocess, sys
from pathlib import Path
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()

def make_intro(episode: str, theme: str = "", out: str = "intro.mp4",
               seconds: float = 6.0) -> str:
    logo = Image.open(HERE / "logo.png").convert("RGB")
    W, H = 1920, 1080
    card = Image.new("RGB", (W, H), (253, 251, 249))
    lw = int(W * 0.46); lh = int(logo.height * lw / logo.width)
    card.paste(logo.resize((lw, lh), Image.LANCZOS), ((W - lw) // 2, int(H * 0.16)))
    dr = ImageDraw.Draw(card)
    for fp in ("/System/Library/Fonts/Supplemental/Didot.ttc",
               "/System/Library/Fonts/Supplemental/Georgia.ttf"):
        try:
            font = ImageFont.truetype(fp, 74); break
        except Exception:
            continue
    tw = dr.textlength(episode, font=font)
    while tw > W * 0.7 and font.size > 30:
        font = font.font_variant(size=font.size - 4)
        tw = dr.textlength(episode, font=font)
    dr.text(((W - tw) / 2, int(H * 0.16) + lh + int(H * 0.05)), episode,
            font=font, fill=(214, 130, 160))
    still = HERE / "_intro_card.png"
    card.save(still)
    frames = int(seconds * 24)
    vf = (f"zoompan=z=\'min(1.06,1+0.06*on/{frames})\':d={frames}:"
          f"x=\'iw/2-(iw/zoom/2)\':y=\'ih/2-(ih/zoom/2)\':s={W}x{H}:fps=24,"
          f"fade=t=in:st=0:d=0.6,fade=t=out:st={seconds-0.7:.2f}:d=0.7,format=yuv420p")
    cmd = [FF, "-y", "-v", "error", "-loop", "1", "-i", str(still)]
    if theme and Path(theme).exists():
        cmd += ["-i", str(theme),
                "-af", f"atrim=0:{seconds:.2f},afade=t=out:st={seconds-1.2:.2f}:d=1.2"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-vf", vf, "-t", f"{seconds:.2f}", "-c:v", "libx264", "-preset", "fast",
            "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)]
    subprocess.run(cmd, check=True)
    still.unlink(missing_ok=True)
    return out

if __name__ == "__main__":
    ep = sys.argv[1] if len(sys.argv) > 1 else "The Hidden Spring"
    theme = sys.argv[2] if len(sys.argv) > 2 else str(HERE / "theme/theme-instrumental.mp3")
    out = sys.argv[3] if len(sys.argv) > 3 else str(HERE / f"intro-sample.mp4")
    print(make_intro(ep, theme, out))
