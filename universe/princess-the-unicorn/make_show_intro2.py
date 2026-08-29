"""Show intro v2 — the boarded cut: sunrise → gallop → stream leap → glade
dance → HIGH SKY LEAP where she holds the logo pose against bright sky, the
wordmark rises beneath her, and she blinks as the music ends. Quick start:
0.2s fade, music from the first frame.
Usage: python3 make_show_intro2.py theme.mp3 out.mp4
"""
import subprocess, sys, re
from pathlib import Path
import imageio_ffmpeg
from PIL import Image, ImageChops
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))

HERE = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
X = 0.4

ENDING_AT = 17.0        # the logo animation begins ON "Unicoooorn"
SHOT_NAMES = ["intro-s1.mp4", "test-gallop.mp4", "intro-s3.mp4",
              "intro-rainbow.mp4", "intro-friends.mp4"]


def _wordmark():
    wm = Image.open(HERE / "logo-3.png").convert("RGB")
    bg = Image.new("RGB", wm.size, (255, 255, 255))
    bbox = ImageChops.difference(wm, bg).getbbox()
    if bbox:
        wm = wm.crop(bbox)
    tw = 860
    th = int(wm.height * tw / wm.width)
    wm = wm.resize((tw, th), Image.LANCZOS)
    arr = np.asarray(wm, dtype=np.int16)
    alpha = np.clip((235 - arr.min(axis=2)) * 4, 0, 255).astype("uint8")
    p = HERE / "_wm.png"
    Image.fromarray(np.dstack([arr.astype("uint8"), alpha])).save(p)
    return p, th


def _dur(path):
    r = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    h, mi, se = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(se)


def make(theme: str, out: str) -> str:
    # the body carries five shots to EXACTLY 17.0s, and the logo animation
    # begins on the word "Unicoooorn"; the whole song plays untouched
    theme_len = _dur(theme)

    # each shot contributes what it truly HAS; a gentle stretch (max 15%
    # slow-motion, invisible in this register) lands the body on exactly
    # ENDING_AT so the logo begins on the word
    avails = []
    for name in SHOT_NAMES:
        a = max(1.5, _dur(HERE / name) - 0.35)
        if name == "intro-s1.mp4":
            a = min(a, 1.4)     # a quick glimpse of the world, then ACTION
        avails.append(a)
    nsh = len(SHOT_NAMES)
    raw_net = sum(avails) - (nsh - 1) * X
    stretch = min(1.2, max(1.0, ENDING_AT / raw_net))
    segs = []
    for i, (name, avail) in enumerate(zip(SHOT_NAMES, avails)):
        seg = HERE / f"_s{i}.mp4"
        out_len = avail * stretch
        subprocess.run([FF, "-y", "-v", "error", "-ss", "0.15",
                        "-t", f"{avail:.2f}", "-i", str(HERE / name),
                        "-vf", ("scale=1920:1080:force_original_aspect_ratio=increase,"
                                f"crop=1920:1080,setpts={stretch:.4f}*PTS,fps=24"),
                        "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                        str(seg)], check=True)
        segs.append((seg, out_len - X))     # net contribution per shot
    body_net = sum(sec for _, sec in segs) + X   # last shot keeps its tail
    need_ending = max(4.2, theme_len + 2.1 - body_net)
    end_seg = HERE / "_logoending2.mp4"
    from make_logo_ending2 import build as _build_le
    ending_s = _build_le(need_ending, end_seg)
    sky_len = ending_s

    total = sum(s for _, s in segs) + X + sky_len - X   # body_net + ending
    args = ["-y", "-v", "error"]
    for seg, _ in segs:
        args += ["-i", str(seg)]
    args += ["-i", str(end_seg), "-i", str(theme)]
    n = len(segs)
    f, off, prev = [], 0.0, "0:v"
    for i in range(1, n + 1):
        off += segs[i - 1][1]
        f.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={X}:offset={off - X:.2f}[x{i}]")
        prev = f"x{i}"
    f.append(f"[{prev}]fade=t=in:st=0:d=0.2,format=yuv420p[v]")
    # the FULL song, untouched — it ends naturally, then the wink and the
    # one-second hold close the intro (Lars: no cutting)
    f.append(f"[{n + 1}:a]apad=whole_dur={total:.2f}[a]")
    args += ["-filter_complex", ";".join(f), "-map", "[v]", "-map", "[a]",
             "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "fast",
             "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(out)]
    subprocess.run([FF, *args], check=True)
    for seg, _ in segs:
        seg.unlink(missing_ok=True)
    end_seg.unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    print(make(sys.argv[1], sys.argv[2]))
