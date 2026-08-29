"""The FULL-FOOTAGE intro: the friends in motion, cut to the theme, closing
on the logo — a real show opening. Shots are passed as file paths so the
cut upgrades whenever better takes exist.
Usage: python3 make_intro_footage.py theme.mp3 out.mp4 shot1.mp4 shot2.mp4 ...
"""
import subprocess, sys, re
from pathlib import Path
import imageio_ffmpeg
from PIL import Image, ImageChops

HERE = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
X = 0.45          # dissolve
SHOT = 3.8        # seconds per shot
LOGO_S = 5.2      # the logo closes the intro


def _logo_card() -> Path:
    logo = Image.open(HERE / "logo.png").convert("RGB")
    bg = Image.new("RGB", logo.size, (255, 255, 255))
    bbox = ImageChops.difference(logo, bg).getbbox()
    if bbox:
        logo = logo.crop(bbox)
    W, H = 3840, 2160
    card = Image.new("RGB", (W, H), (253, 251, 249))
    lw = int(W * 0.5); lh = int(logo.height * lw / logo.width)
    if lh > int(H * 0.72):
        lh = int(H * 0.72); lw = int(logo.width * lh / logo.height)
    card.paste(logo.resize((lw, lh), Image.LANCZOS), ((W - lw) // 2, (H - lh) // 2))
    p = HERE / "_logo_card.png"
    card.save(p)
    return p


def make(theme: str, out: str, shots: list) -> str:
    card = _logo_card()
    # the logo becomes a real video segment first — xfade trusts files,
    # not still-image branches (the film assembler's own lesson)
    frames = int(LOGO_S * 24)
    logo_seg = HERE / "_logo_seg.mp4"
    subprocess.run([FF, "-y", "-v", "error", "-framerate", "24", "-loop", "1",
                    "-t", f"{LOGO_S:.2f}", "-i", str(card),
                    "-vf", (f"zoompan=z='min(1.05,1+0.05*on/{frames})':d={frames}:"
                            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                            f"s=1920x1080:fps=24,format=yuv420p"),
                    "-t", f"{LOGO_S:.2f}", "-c:v", "libx264", "-preset", "fast",
                    "-crf", "16", str(logo_seg)], check=True)
    # normalize every shot to its own CFR segment first — xfade trusts
    # uniform files only (Seedance takes are VFR; the assembler's lesson)
    segs = []
    for i, sh in enumerate(shots):
        seg = HERE / f"_seg_{i}.mp4"
        subprocess.run([FF, "-y", "-v", "error", "-ss", "0.3",
                        "-t", f"{SHOT + X:.2f}", "-i", str(sh),
                        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,"
                               "crop=1920:1080,fps=24,setpts=PTS-STARTPTS",
                        "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                        str(seg)], check=True)
        segs.append(seg)
    n = len(segs)
    args = ["-y", "-v", "error"]
    for seg in segs:
        args += ["-i", str(seg)]
    args += ["-i", str(logo_seg)]
    if theme and Path(theme).exists():
        args += ["-i", str(theme)]
    total = n * SHOT + LOGO_S
    f, prev, off = [], None, 0.0
    for i in range(n):
        f.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")
    f.append(f"[{n}:v]fps=24,setpts=PTS-STARTPTS[vL]")
    prev = "v0"
    for i in range(1, n):
        off += SHOT
        f.append(f"[{prev}][v{i}]xfade=transition=fade:duration={X}:offset={off - X:.2f}[x{i}]")
        prev = f"x{i}"
    off += SHOT
    f.append(f"[{prev}][vL]xfade=transition=fade:duration={X}:offset={off - X:.2f}[xf]")
    f.append(f"[xf]fade=t=in:st=0:d=0.6,fade=t=out:st={total - 0.8:.2f}:d=0.8,format=yuv420p[v]")
    if theme and Path(theme).exists():
        f.append(f"[{n + 1}:a]atrim=0:{total:.2f},"
                 f"afade=t=out:st={total - 0.8:.2f}:d=0.8[a]")
        maps = ["-map", "[v]", "-map", "[a]"]
    else:
        maps = ["-map", "[v]"]
    args += ["-filter_complex", ";".join(f), *maps,
             "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "fast",
             "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(out)]
    subprocess.run([FF, *args], check=True)
    card.unlink(missing_ok=True)
    logo_seg.unlink(missing_ok=True)
    for seg in segs:
        seg.unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    theme, out = sys.argv[1], sys.argv[2]
    print(make(theme, out, sys.argv[3:]))
