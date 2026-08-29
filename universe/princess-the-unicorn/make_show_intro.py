"""THE show intro: a quick travel through the Rainbow Forest — Princess
dancing, running, jumping — and at the end she leaps into place in the
logo and BLINKS just as the music ends.
Usage: python3 make_show_intro.py theme.mp3 out.mp4 shot1 shot2 shot3 shot4
"""
import subprocess, sys, re
from pathlib import Path
import imageio_ffmpeg
from PIL import Image, ImageChops

HERE = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
X = 0.4
SHOT = 3.3


def _wordmark() -> Path:
    """The real wordmark (variant 3), trimmed and made TRANSPARENT — the
    white paper becomes alpha so only the lettering overlays the film."""
    wm = Image.open(HERE / "logo-3.png").convert("RGB")
    bg = Image.new("RGB", wm.size, (255, 255, 255))
    bbox = ImageChops.difference(wm, bg).getbbox()
    if bbox:
        wm = wm.crop(bbox)
    tw = 900
    th = int(wm.height * tw / wm.width)
    wm = wm.resize((tw, th), Image.LANCZOS)
    import numpy as np
    arr = np.asarray(wm, dtype=np.int16)
    whiteness = arr.min(axis=2)          # near-white where all channels high
    alpha = np.clip((235 - whiteness) * 4, 0, 255).astype("uint8")
    rgba = np.dstack([arr.astype("uint8"), alpha])
    p = HERE / "_wordmark.png"
    Image.fromarray(rgba, "RGBA").save(p)
    return p, th


def make(theme: str, out: str, shots: list) -> str:
    wm, wm_h = _wordmark()
    # ── the ending: her white-background leap with the wordmark beneath
    leap = HERE / "leap-white.mp4"
    end_seg = HERE / "_end_seg.mp4"
    wm_y = 1080 - wm_h - 56
    subprocess.run([FF, "-y", "-v", "error", "-i", str(leap), "-i", str(wm),
                    "-filter_complex",
                    ("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                     "crop=1920:1080,fps=24,setpts=PTS-STARTPTS,"
                     "colorlevels=rimax=0.86:gimax=0.86:bimax=0.86[bg];"
                     f"[bg][1:v]overlay=x=(W-w)/2:y={wm_y}[v]"),
                    "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "fast",
                    "-crf", "16", str(end_seg)], check=True)
    r = subprocess.run([FF, "-i", str(end_seg)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    end_s = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))

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
    total = n * SHOT + end_s
    args = ["-y", "-v", "error"]
    for seg in segs:
        args += ["-i", str(seg)]
    args += ["-i", str(end_seg), "-i", str(theme)]
    f, off = [], 0.0
    prev = "0:v"
    for i in range(1, n + 1):
        off += SHOT
        f.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={X}:offset={off - X:.2f}[x{i}]")
        prev = f"x{i}"
    f.append(f"[{prev}]fade=t=in:st=0:d=0.5,format=yuv420p[v]")
    # the music ends exactly at the blink: trim to the video, quick fade
    f.append(f"[{n + 1}:a]atrim=0:{total:.2f},afade=t=out:st={total - 0.35:.2f}:d=0.35[a]")
    args += ["-filter_complex", ";".join(f), "-map", "[v]", "-map", "[a]",
             "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "fast",
             "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(out)]
    subprocess.run([FF, *args], check=True)
    for seg in segs + [end_seg, wm]:
        Path(seg).unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    print(make(sys.argv[1], sys.argv[2], sys.argv[3:]))
