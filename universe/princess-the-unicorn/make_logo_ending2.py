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
    s = min(W * 0.86 / logo.width, H * 0.92 / logo.height) * 0.9
    lw, lh = int(logo.width * s), int(logo.height * s)
    ox, oy = (W - lw) // 2, (H - lh) // 2 - int(H * 0.025)
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
    n_enter = int(1.05 * FPS)
    n_hop2 = int(0.45 * FPS)
    n_settle = int(0.3 * FPS)
    n_wink = 8
    n_after_wink = FPS               # the wink, hold ONE second, episode
    n_hold = max(4, n_total - n_enter - n_hop2 - n_settle - n_wink
                 - n_after_wink - int(0.8 * FPS))
    idx = 0

    def emit(im, times=1):
        nonlocal idx
        for _ in range(times):
            im.save(frames_dir / f"f{idx:04d}.png")
            idx += 1

    import math as _m
    white_bg = Image.new("RGB", (W, H), (255, 255, 255))
    start_x = W + 40
    arc_h = 300.0
    for i in range(n_enter):
        t = (i + 1) / n_enter
        e = t * t * (3 - 2 * t)
        x = start_x + (tx - start_x) * e
        arc = 4 * t * (1 - t)
        y = ty - arc_h * arc
        # ALIVE: she pitches with the arc (nose up rising, level at the top,
        # nose down landing) and squash-stretches like a real jump
        vel = 1 - 2 * t                          # +1 rising … -1 falling
        angle = 22.0 * vel                       # a real leap, not a glide
        stretch = 1.0 + 0.16 * arc               # long at the apex
        squash = 1.0 - 0.12 * (1 - arc) * (1 if t > 0.5 else 0.4)
        fw = max(2, int(sp.width * (2 - stretch) * (1 / squash) * squash))
        fw = max(2, int(sp.width / stretch ** 0.5))
        fh = max(2, int(sp.height * stretch * squash))
        frame_sp = sp.resize((fw, fh), Image.BILINEAR).rotate(
            angle, expand=True, resample=Image.BILINEAR)
        cx = x + sp.width / 2
        cy = y + sp.height / 2
        # the lettering appears only as she is almost in place (Lars)
        ta = 0.0 if t < 0.72 else ((t - 0.72) / 0.28) ** 1.2
        fr = Image.blend(white_bg, card_text, min(1.0, ta))
        fr.paste(frame_sp, (int(cx - frame_sp.width / 2),
                            int(cy - frame_sp.height / 2)), frame_sp)
        emit(fr)
    # a happy second bounce before she settles — she is ALIVE
    hop2_x0 = tx - int(sp.width * 0.06)
    for i in range(n_hop2):
        t2 = (i + 1) / n_hop2
        arc2 = 4 * t2 * (1 - t2)
        x = int(hop2_x0 + (tx - hop2_x0) * t2)
        y = int(ty - 90 * arc2)
        angle2 = 10.0 * (1 - 2 * t2)
        st2 = 1.0 + 0.08 * arc2
        fw = max(2, int(sp.width / st2 ** 0.5))
        fh = max(2, int(sp.height * st2))
        fsp = sp.resize((fw, fh), Image.BILINEAR).rotate(
            angle2, expand=True, resample=Image.BILINEAR)
        ta2 = min(1.0, 0.85 + 0.15 * t2)
        fr = Image.blend(white_bg, card_text, ta2)
        fr.paste(fsp, (int(x + sp.width / 2 - fsp.width / 2),
                       int(y + sp.height / 2 - fsp.height / 2)), fsp)
        emit(fr)
    for i in range(n_settle):                    # landing: squash then rise
        k = (i + 1) / n_settle
        sq = 1.0 - 0.10 * _m.sin(_m.pi * min(1.0, k * 1.4))
        fh = max(2, int(sp.height * sq))
        fw = max(2, int(sp.width * (2 - sq) ** 0.5))
        frame_sp = sp.resize((fw, fh), Image.BILINEAR)
        fr = card_text.copy()
        fr.paste(frame_sp, (int(tx + (sp.width - fw) / 2),
                            int(ty + (sp.height - fh))), frame_sp)
        emit(fr)
    emit(card_open, n_hold)                          # in place — the logo
    emit(card_wink, n_wink)                          # the one-eye wink
    emit(card_open, n_after_wink)                    # hold 1s
    white = Image.new("RGB", (W, H), (255, 255, 255))
    n_fade = int(0.8 * FPS)                          # …then a soft white-out
    for i in range(n_fade):
        emit(Image.blend(card_open, white, (i + 1) / n_fade))
    seg = out_path
    subprocess.run([FF, "-y", "-v", "error", "-framerate", str(FPS),
                    "-i", str(frames_dir / "f%04d.png"),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                    "-pix_fmt", "yuv420p", str(seg)], check=True)
    return idx / FPS


if __name__ == "__main__":
    print(build(float(sys.argv[1]) if len(sys.argv) > 1 else 6.5,
                HERE / "_logoending2.mp4"))
