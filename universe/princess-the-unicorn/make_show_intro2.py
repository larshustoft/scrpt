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

SHOTS = [("intro-s1.mp4", 2.6), ("test-gallop.mp4", 3.2),
         ("intro-s3.mp4", 3.2), ("intro-rainbow.mp4", 3.0)]
SKY = "intro-sky.mp4"


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
    # the sky flight plays LIVE (trimmed before her in-take blink), then the
    # logo-birth ending takes over: shrink -> stiffen -> song ends -> wink
    sky_live = min(_dur(HERE / SKY) - 1.8, 3.4)
    end_seg_a = HERE / "_end_a.mp4"
    subprocess.run([FF, "-y", "-v", "error", "-i", str(HERE / SKY),
                    "-vf", ("scale=1920:1080:force_original_aspect_ratio=increase,"
                            "crop=1920:1080,fps=24,setpts=PTS-STARTPTS,"
                            "colorlevels=rimax=0.92:gimax=0.92:bimax=0.92"),
                    "-an", "-t", f"{sky_live:.2f}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                    str(end_seg_a)], check=True)
    # the WHOLE song plays — the ending stretches so the song finishes
    # before the wink, and the intro ends 1s after it
    theme_len = _dur(theme)
    body_net = sum(sec for _, sec in SHOTS)
    need_ending = max(4.5, theme_len + 1.45 - body_net - sky_live)
    end_seg_b = HERE / "_logoending2.mp4"
    from make_logo_ending2 import build as _build_le
    ending_s = _build_le(need_ending, end_seg_b)
    sky_len = sky_live + ending_s
    end_seg = HERE / "_end.mp4"
    subprocess.run([FF, "-y", "-v", "error", "-i", str(end_seg_a), "-i", str(end_seg_b),
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]", "-c:v", "libx264", "-preset", "fast",
                    "-crf", "16", str(end_seg)], check=True)
    segs = []
    for i, (name, secs) in enumerate(SHOTS):
        seg = HERE / f"_s{i}.mp4"
        subprocess.run([FF, "-y", "-v", "error", "-ss", "0.2",
                        "-t", f"{secs + X:.2f}", "-i", str(HERE / name),
                        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,"
                               "crop=1920:1080,fps=24,setpts=PTS-STARTPTS",
                        "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                        str(seg)], check=True)
        segs.append((seg, secs))
    total = sum(s for _, s in segs) + sky_len
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
