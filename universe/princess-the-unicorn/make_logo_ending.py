"""The logo-birth ending: live Princess shrinks into the drawn unicorn's
exact position and size, TURNS STIFF (becomes the logo), and after the song
ends she winks one eye — the last beat before the episode.
Renders exact frames; the final open-eye frames ARE logo.png."""
import subprocess, sys, json, re
from pathlib import Path
import imageio_ffmpeg
from PIL import Image, ImageFilter
import numpy as np

HERE = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 24
W, H = 1920, 1080


def _card(img_name):
    """A logo image fitted onto the 1920x1080 white card; returns card and
    the transform (scale, ox, oy) from logo coords to card coords."""
    logo = Image.open(HERE / img_name).convert("RGB")
    s = min(W * 0.86 / logo.width, H * 0.92 / logo.height)
    lw, lh = int(logo.width * s), int(logo.height * s)
    ox, oy = (W - lw) // 2, (H - lh) // 2
    card = Image.new("RGB", (W, H), (255, 255, 255))
    card.paste(logo.resize((lw, lh), Image.LANCZOS), (ox, oy))
    return card, s, ox, oy


def _her_still(sky_path, t):
    tmp = HERE / "_her.png"
    subprocess.run([FF, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(sky_path),
                    "-frames:v", "1", str(tmp)], check=True)
    im = Image.open(tmp).convert("RGB").resize((W, H))
    # lift the pale sky to white and feather the edges so the shrinking
    # frame melts into the card instead of showing a rectangle
    arr = np.asarray(im, dtype=np.float32)
    arr = np.clip((arr - 0) * (255.0 / 235.0), 0, 255)
    im = Image.fromarray(arr.astype("uint8"))
    mask = Image.new("L", (W, H), 0)
    from PIL import ImageDraw
    d = ImageDraw.Draw(mask)
    d.ellipse([W*0.16, H*0.04, W*0.84, H*0.99], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(90))
    white = Image.new("RGB", (W, H), (255, 255, 255))
    return Image.composite(im, white, mask), tmp


def build(sky_path: str, out: str, hold_before_wink=0.9,
          shrink_s=1.5, wink_at_end=True):
    geo = json.loads((HERE / "logo-geometry.json").read_text())
    bx0, by0, bx1, by1 = geo["unicorn_bbox"]
    card_open, s, ox, oy = _card("logo.png")
    card_text, _, _, _ = _card("logo-textonly.png")
    card_wink, _, _, _ = _card("logo-wink.png")
    # her target box on the card
    tx0, ty0 = ox + bx0 * s, oy + by0 * s
    tx1, ty1 = ox + bx1 * s, oy + by1 * s
    her, tmp = _her_still(sky_path, max(0.0, _dur(sky_path) - 1.8))

    frames_dir = HERE / "_endframes"
    frames_dir.mkdir(exist_ok=True)
    for f in frames_dir.glob("*.png"):
        f.unlink()
    idx = 0

    def emit(im):
        nonlocal idx
        im.save(frames_dir / f"f{idx:04d}.png")
        idx += 1

    # ── phase B: the shrink-morph (ease-in-out), stiffening at the end
    nB = int(shrink_s * FPS)
    for i in range(nB):
        t = (i + 1) / nB
        e = t * t * (3 - 2 * t)              # smoothstep
        # interpolate her frame from full-screen to the target box
        cw = W + (tx1 - tx0 - W) * e
        ch = H + (ty1 - ty0 - H) * e
        cx = 0 + tx0 * e
        cy = 0 + ty0 * e
        base = card_text.copy()
        scaled = her.resize((max(2, int(cw)), max(2, int(ch))), Image.BILINEAR)
        base.paste(scaled, (int(cx), int(cy)))
        # stiffen: crossfade to the DRAWN logo over the last 35%
        if e > 0.65:
            a = (e - 0.65) / 0.35
            base = Image.blend(base, card_open, a)
        emit(base)
    # ── phase C: stiff hold (song resolves) …
    for _ in range(int(hold_before_wink * FPS)):
        emit(card_open)
    # … then the one-eye WINK — the last thing before the episode
    if wink_at_end:
        for _ in range(7):
            emit(card_wink)
        for _ in range(10):
            emit(card_open)
    seg = HERE / "_logoending.mp4"
    subprocess.run([FF, "-y", "-v", "error", "-framerate", str(FPS),
                    "-i", str(frames_dir / "f%04d.png"),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                    "-pix_fmt", "yuv420p", str(seg)], check=True)
    tmp.unlink(missing_ok=True)
    return seg, idx / FPS


def _dur(path):
    r = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    h, mi, se = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(se)


if __name__ == "__main__":
    seg, secs = build(sys.argv[1] if len(sys.argv) > 1 else str(HERE / "intro-sky.mp4"),
                      "out")
    print(seg, f"{secs:.2f}s")
