"""The Princess the Unicorn film intro: the logo blooms on soft white and
the FULL theme plays. No episode title — titling gets its own card after
the intro, like real shows. Usage:
    python3 make_intro.py [theme.mp3] [out.mp4]
"""
import subprocess, sys
from pathlib import Path
import imageio_ffmpeg
from PIL import Image

HERE = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()


def _theme_seconds(theme: str) -> float:
    import re
    r = subprocess.run([FF, "-i", theme], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        return 20.0
    h, mi, se = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(se)


def make_intro(theme: str = "", out: str = "intro.mp4") -> str:
    from PIL import ImageChops
    logo = Image.open(HERE / "logo.png").convert("RGB")
    # trim the artwork's uneven whitespace so it centres BY EYE, not by file
    bg = Image.new("RGB", logo.size, (255, 255, 255))
    bbox = ImageChops.difference(logo, bg).getbbox()
    if bbox:
        logo = logo.crop(bbox)
    # supersampled 4K card: zoompan's integer rounding is what wobbles at
    # 1080p — at double resolution the drift halves below visibility
    W, H = 3840, 2160
    card = Image.new("RGB", (W, H), (253, 251, 249))
    lw = int(W * 0.5); lh = int(logo.height * lw / logo.width)
    if lh > int(H * 0.72):
        lh = int(H * 0.72); lw = int(logo.width * lh / logo.height)
    card.paste(logo.resize((lw, lh), Image.LANCZOS),
               ((W - lw) // 2, (H - lh) // 2))
    still = HERE / "_intro_card.png"
    card.save(still)
    seconds = max(6.0, min(30.0, _theme_seconds(theme) if theme else 20.0))
    frames = int(seconds * 24)
    vf = (f"zoompan=z='min(1.05,1+0.05*on/{frames})':d={frames}:"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=24,"
          f"fade=t=in:st=0:d=0.8,fade=t=out:st={seconds-0.8:.2f}:d=0.8,"
          f"format=yuv420p")
    cmd = [FF, "-y", "-v", "error", "-loop", "1", "-i", str(still)]
    if theme and Path(theme).exists():
        cmd += ["-i", str(theme),
                "-af", f"atrim=0:{seconds:.2f},afade=t=out:st={seconds-0.6:.2f}:d=0.6"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-vf", vf, "-t", f"{seconds:.2f}", "-c:v", "libx264",
            "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out)]
    subprocess.run(cmd, check=True)
    still.unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 else str(HERE / "theme/theme-instrumental.mp3")
    out = sys.argv[2] if len(sys.argv) > 2 else str(HERE / "intro-full.mp4")
    print(make_intro(theme, out))
