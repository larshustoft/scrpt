"""The logo-entrance ending: the DRAWN unicorn from the logo itself hops in
from the right of the screen, lands in her exact place over the lettering,
winks one eye — and the full song plays out, uncut. Her sprite is lifted
from logo.png, so her form and size never change at all."""
import subprocess, sys, json
from pathlib import Path
import imageio_ffmpeg
from PIL import Image, ImageFilter
import numpy as np

HERE = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 24
W, H = 1920, 1080


def _card(img_name):
    logo = Image.open(HERE / img_name).convert("RGB")
    s = min(W * 0.86 / logo.width, H * 0.92 / logo.height)
    lw, lh = int(logo.width * s), int(logo.height * s)
    ox, oy = (W - lw) // 2, (H - lh) // 2
    card = Image.new("RGB", (W, H), (255, 255, 255))
    card.paste(logo.resize((lw, lh), Image.LANCZOS), (ox, oy))
    return card, s, ox, oy


def _isolate():
    """Her pixels straight from logo.png — component analysis, no AI twins.
    Returns (sprite RGBA, sprite origin, base card = logo minus her).
    Aligned by construction: the base + sprite == the logo, pixel-exact."""
    from collections import deque
    logo = Image.open(HERE / "logo.png").convert("RGB")
    arr = np.asarray(logo)
    small = arr[::4, ::4]
    nonwhite = small.min(axis=2) < 232
    lab = np.zeros(nonwhite.shape, dtype=np.int32)
    cur = 0
    Hs, Ws = nonwhite.shape
    comps = {}
    for yy in range(Hs):
        for xx in range(Ws):
            if nonwhite[yy, xx] and not lab[yy, xx]:
                cur += 1
                q = deque([(yy, xx)]); lab[yy, xx] = cur
                px = []
                while q:
                    cy, cx = q.popleft()
                    px.append((cy, cx))
                    for dy, dx in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                        ny, nx = cy+dy, cx+dx
                        if 0 <= ny < Hs and 0 <= nx < Ws and nonwhite[ny, nx] and not lab[ny, nx]:
                            lab[ny, nx] = cur; q.append((ny, nx))
                comps[cur] = px
    # she is the biggest component whose centroid sits in the UPPER half
    best, best_n = None, 0
    for cid, px in comps.items():
        cy = sum(p[0] for p in px) / len(px)
        if cy < Hs * 0.52 and len(px) > best_n:
            best, best_n = cid, len(px)
    mask_small = (lab == best)
    mask = np.kron(mask_small, np.ones((4, 4), dtype=bool))[:arr.shape[0], :arr.shape[1]]
    m = Image.fromarray((mask * 255).astype(np.uint8)).filter(
        ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(1.5))
    malpha = np.asarray(m)
    ys, xs = np.nonzero(malpha > 40)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
    rgba = np.dstack([arr, malpha])
    sprite = Image.fromarray(rgba).crop((x0, y0, x1 + 1, y1 + 1))
    base = arr.copy()
    a3 = (malpha.astype(np.float32) / 255.0)[..., None]
    base = (base * (1 - a3) + 255 * a3).astype(np.uint8)
    return sprite, (int(x0), int(y0)), Image.fromarray(base)


def _wink_patch():
    """ONLY the eye area from the wink twin — the lettering never flickers."""
    a = np.asarray(Image.open(HERE / "logo.png").convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(HERE / "logo-wink.png").convert("RGB").resize(
        (a.shape[1], a.shape[0])), dtype=np.int16)
    mag = np.abs(a - b).sum(axis=2)
    # search only the upper-central region (her head lives there)
    mag[int(a.shape[0]*0.55):, :] = 0
    ys, xs = np.nonzero(mag > 90)
    if len(xs) == 0:
        return None, (0, 0)
    x0, y0, x1, y1 = xs.min()-6, ys.min()-6, xs.max()+6, ys.max()+6
    patch = Image.open(HERE / "logo-wink.png").convert("RGB").resize(
        (a.shape[1], a.shape[0])).crop((x0, y0, x1, y1))
    return patch, (int(x0), int(y0))


def build(seconds: float, out_path: Path) -> float:
    """Render the ending at an exact length. Timeline inside:
    enter (1.3s) -> settle -> hold -> WINK -> hold to the end."""
    card_open, s, ox, oy = _card("logo.png")
    sprite, (sx, sy), base_logo = _isolate()
    # base card = the logo with her erased, fitted identically to card_open
    lw, lh = int(base_logo.width * s), int(base_logo.height * s)
    card_text = Image.new("RGB", (W, H), (255, 255, 255))
    card_text.paste(base_logo.resize((lw, lh), Image.LANCZOS), (ox, oy))
    # wink card = the real logo with only the eye patch swapped
    patch, (px_, py_) = _wink_patch()
    card_wink = card_open.copy()
    if patch is not None:
        pw, ph = int(patch.width * s), int(patch.height * s)
        card_wink.paste(patch.resize((pw, ph), Image.LANCZOS),
                        (ox + int(px_ * s), oy + int(py_ * s)))
    sw, sh = int(sprite.width * s), int(sprite.height * s)
    sp = sprite.resize((sw, sh), Image.LANCZOS)
    tx, ty = ox + int(sx * s), oy + int(sy * s)      # her true place

    frames_dir = HERE / "_endframes2"
    frames_dir.mkdir(exist_ok=True)
    for f in frames_dir.glob("*.png"):
        f.unlink()
    n_total = int(seconds * FPS)
    n_enter = int(1.3 * FPS)
    n_settle = int(0.35 * FPS)
    n_wink = 8
    n_after_wink = FPS               # the wink, hold ONE second, episode
    n_hold = max(6, n_total - n_enter - n_settle - n_wink - n_after_wink)
    idx = 0

    def emit(im, times=1):
        nonlocal idx
        for _ in range(times):
            im.save(frames_dir / f"f{idx:04d}.png")
            idx += 1

    start_x = W + 40
    arc_h = 260.0
    for i in range(n_enter):
        t = (i + 1) / n_enter
        e = t * t * (3 - 2 * t)
        x = int(start_x + (tx - start_x) * e)
        y = int(ty - arc_h * 4 * t * (1 - t))        # parabolic hop
        fr = card_text.copy()
        fr.paste(sp, (x, y), sp)
        emit(fr)
    for i in range(n_settle):                        # soft landing bounce
        dy = int(6 * (1 - (i + 1) / n_settle))
        fr = card_text.copy()
        fr.paste(sp, (tx, ty + dy), sp)
        emit(fr)
    emit(card_open, n_hold)                          # in place — the logo
    emit(card_wink, n_wink)                          # the one-eye wink
    emit(card_open, n_after_wink)                    # hold 1s — then the episode
    seg = out_path
    subprocess.run([FF, "-y", "-v", "error", "-framerate", str(FPS),
                    "-i", str(frames_dir / "f%04d.png"),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                    "-pix_fmt", "yuv420p", str(seg)], check=True)
    return idx / FPS


if __name__ == "__main__":
    print(build(float(sys.argv[1]) if len(sys.argv) > 1 else 6.5,
                HERE / "_logoending2.mp4"))
