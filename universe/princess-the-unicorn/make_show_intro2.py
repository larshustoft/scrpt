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

HERE = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
X = 0.4

SHOTS = [("intro-s1.mp4", 2.6), ("test-gallop.mp4", 3.2),
         ("intro-s3.mp4", 3.2), ("intro-s4.mp4", 3.0)]
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
    wm, wm_h = _wordmark()
    sky_len = min(_dur(HERE / SKY), 5.4)
    # the wordmark fades in under her during the sky shot's second half
    wm_y = 1080 - wm_h - 64
    end_seg = HERE / "_end.mp4"
    subprocess.run([FF, "-y", "-v", "error", "-i", str(HERE / SKY),
                    "-framerate", "24", "-loop", "1", "-t", f"{sky_len:.2f}",
                    "-i", str(wm),
                    "-filter_complex",
                    ("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                     "crop=1920:1080,fps=24,setpts=PTS-STARTPTS[bg];"
                     "[1:v]format=rgba,fade=t=in:st=1.6:d=0.8:alpha=1[wmf];"
                     f"[bg][wmf]overlay=x=(W-w)/2:y={wm_y}[v]"),
                    "-map", "[v]", "-an", "-t", f"{sky_len:.2f}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                    str(end_seg)], check=True)
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
    f.append(f"[{n + 1}:a]atrim=0:{total:.2f},afade=t=out:st={total - 0.3:.2f}:d=0.3[a]")
    args += ["-filter_complex", ";".join(f), "-map", "[v]", "-map", "[a]",
             "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "fast",
             "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(out)]
    subprocess.run([FF, *args], check=True)
    for seg, _ in segs:
        seg.unlink(missing_ok=True)
    end_seg.unlink(missing_ok=True)
    wm.unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    print(make(sys.argv[1], sys.argv[2]))
