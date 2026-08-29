"""The print interior for a picture book.

The novel interior flows text through an HTML page and prints it with a
browser. A picture book is the opposite problem: full-bleed artwork with a
few words set on top, and a page count that print binding fixes for you.

So this builds the PDF directly.

Two rules come from the printer, not from us:

  · **The page count must divide by 8.** A picture book is folded from
    sheets, so 24, 32 or 40 pages — never 30. We pad with blanks at the back
    rather than let the printer reject the file.
  · **Full-bleed art needs bleed.** Art that runs to the edge must actually
    run PAST it, or trimming variance leaves a white hairline. The page is
    built at trim + bleed and the artwork fills it.

Text stays inside the safe margin, and away from the gutter, because words
that fall into the fold cannot be read.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

PT = 72.0  # PDF points per inch


def _spec(rec: dict, book: dict) -> dict:
    from ..prose.models import CHILDRENS_PRESETS
    preset = CHILDRENS_PRESETS.get(rec.get("preset") or "") or \
        CHILDRENS_PRESETS["picture_book"]
    d = book.get("data") or {}
    trim = ((d.get("format") or {}).get("trim_size")
            or d.get("trim_size") or preset["trim"])
    try:
        tw, th = (float(x) for x in str(trim).lower().split("x"))
    except Exception:
        tw, th = 8.5, 8.5
    return {
        "trim_w": tw, "trim_h": th,
        "bleed": float(preset.get("bleed") or 0.125),
        "safe": float(preset.get("safe_margin") or 0.25),
        "gutter": float(preset.get("gutter") or 0.375),
        "pages": int(preset.get("pages") or 32),
        "label": preset.get("label", "Picture book"),
    }


def _fit_cover(img, w_px: int, h_px: int):
    """Fill the page, centre-cropping — never letterbox artwork."""
    from PIL import Image
    iw, ih = img.size
    scale = max(w_px / iw, h_px / ih)
    nw, nh = int(iw * scale + 0.5), int(ih * scale + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - w_px) // 2, (nh - h_px) // 2
    return img.crop((x, y, x + w_px, y + h_px))


ZONE_NAMES = [
    ("top", 0), ("upper", 1), ("lower", 2), ("foot", 3),
]
COL_NAMES = [("left", 0), ("right", 1), ("centre", 2)]
WIDTH_NAMES = [("wide", 0), ("column", 1), ("narrow", 2)]


def _subject_mask(img):
    """Characters at 1/8 scale: pixels unlike the border palette, largest
    connected clump, grown through same-colored flesh, dilated for margin.
    Shared by the zone scorer and the paper wash — one definition of
    "someone is standing here"."""
    import numpy as _np
    from collections import deque
    sm = img.resize((max(1, img.width // 8), max(1, img.height // 8)))
    arr = _np.asarray(sm.convert("RGB"), dtype=_np.float32)
    bpx = max(2, sm.height // 14)
    border = _np.concatenate([arr[:bpx].reshape(-1, 3), arr[-bpx:].reshape(-1, 3),
                              arr[:, :bpx].reshape(-1, 3), arr[:, -bpx:].reshape(-1, 3)])
    rs = _np.random.RandomState(7)
    pal = border[rs.choice(len(border), min(48, len(border)), replace=False)]
    dist = _np.sqrt(_np.min(((arr[:, :, None, :] - pal[None, None, :, :]) ** 2)
                            .sum(-1), axis=2))
    hot = dist >= max(float(_np.percentile(dist, 65)), 25.0)
    lab = _np.zeros(hot.shape, dtype=_np.int32)
    cur = 0
    Hs, Ws = hot.shape
    for yy in range(Hs):
        for xx in range(Ws):
            if hot[yy, xx] and not lab[yy, xx]:
                cur += 1
                q = deque([(yy, xx)]); lab[yy, xx] = cur
                while q:
                    cy, cx = q.popleft()
                    for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                        ny, nx = cy+dy, cx+dx
                        if 0 <= ny < Hs and 0 <= nx < Ws and hot[ny, nx] and not lab[ny, nx]:
                            lab[ny, nx] = cur; q.append((ny, nx))
    char_mask = _np.zeros(hot.shape, dtype=bool)
    if cur:
        sizes = _np.bincount(lab.ravel())[1:]
        big = int(sizes.argmax()) + 1
        char_mask = lab == big
        blob_px = arr[char_mask]
        centres = blob_px[rs.choice(len(blob_px), min(24, len(blob_px)), replace=False)]
        near = _np.sqrt(_np.min(((arr[:, :, None, :] - centres[None, None, :, :]) ** 2)
                                .sum(-1), axis=2)) < 30.0
        q = deque(map(tuple, _np.argwhere(char_mask)))
        while q:
            cy, cx = q.popleft()
            for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                ny, nx = cy+dy, cx+dx
                if 0 <= ny < Hs and 0 <= nx < Ws and near[ny, nx] and not char_mask[ny, nx]:
                    char_mask[ny, nx] = True; q.append((ny, nx))
        grown = char_mask.copy()
        for _ in range(2):
            g = grown.copy()
            g[1:, :] |= grown[:-1, :]; g[:-1, :] |= grown[1:, :]
            g[:, 1:] |= grown[:, :-1]; g[:, :-1] |= grown[:, 1:]
            grown = g
        char_mask = grown
    return dist, char_mask


def zone_candidates(img, safe_px: int, n_lines: int, line_px: int,
                    prefs: Optional[dict] = None) -> list:
    """Every sensible place the words could sit on this picture, ranked.

    Scored by how busy the artwork is inside each box and how even its tone
    is — a mottled area swallows letters. `prefs` carries what the house has
    learned from past books: positions the editor kept score better, ones
    they moved away from score worse. Returns dicts the UI can offer as
    alternatives, best first.
    """
    from PIL import ImageFilter, ImageStat
    import numpy as _np
    W, H = img.size
    # a page with real paper takes the WHOLE passage — capping the block at
    # 40% forced half the words onto the facing art (Lars, 2026-08-29)
    block_h = min(int(n_lines * line_px * 1.55) + int(safe_px * 0.5), int(H * 0.62))
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    grey = img.convert("L")
    prefs = prefs or {}

    dist, char_mask = _subject_mask(img)

    avail = W - 2 * safe_px
    widths = {"wide": avail, "column": int(avail * 0.74), "narrow": int(avail * 0.60)}
    bands = {"top": safe_px, "upper": int(H * 0.36),
             "lower": int(H * 0.58), "foot": H - safe_px - block_h}

    out = []
    for wname, bw in widths.items():
        cols = {"left": safe_px, "right": W - safe_px - bw, "centre": (W - bw) // 2}
        for cname, x in cols.items():
            for bname, y0 in bands.items():
                y = max(safe_px, min(y0, H - safe_px - block_h))
                x2 = max(safe_px, min(x, W - safe_px - bw))
                box = (x2, y, x2 + bw, y + block_h)
                e = ImageStat.Stat(edges.crop(box))
                g = ImageStat.Stat(grey.crop(box))
                sx0, sy0 = box[0] // 8, box[1] // 8
                sx1, sy1 = max(sx0 + 1, box[2] // 8), max(sy0 + 1, box[3] // 8)
                subj = float(dist[sy0:sy1, sx0:sx1].mean())   # off-palette art
                on_char = float(char_mask[sy0:sy1, sx0:sx1].mean())  # veto weight
                bcx = (box[0] + box[2]) / 2 / W - 0.5
                bcy = (box[1] + box[3]) / 2 / H - 0.5
                central = max(0.0, 1.0 - 2.2 * (bcx * bcx + bcy * bcy) ** 0.5)
                # busy background is workable UNDER A SCRIM — cap its
                # penalty so a flowery corner beats a character's flank
                will_scrim = e.mean[0] > 14
                busy_pen = e.mean[0] + e.stddev[0] * 0.8
                # panels are banned, so busy or mottled ground can no longer
                # be rescued — it must simply lose to flat paper
                will_scrim = False
                # the words belong on PAPER, full stop — a zone that is not
                # clean bright paper is a last resort, never a preference
                is_paper = (g.mean[0] > 215 and g.stddev[0] < 20
                            and on_char < 0.02)
                score = ((0 if is_paper else 200.0)           # paper or bust
                         + busy_pen                            # busy art
                         + g.stddev[0] * 1.1                  # mottled tone kills bare ink
                         + subj * 0.65                        # off-palette art
                         + on_char * 420.0                    # NEVER on a character
                         + central * 16.0                     # subjects live mid-frame
                         + (bw / avail) * 2.0)                # longer lines are
                                                              # welcome on open paper (Lars)
                key = f"{bname}-{cname}-{wname}"
                score -= float(prefs.get(key, 0.0)) * 3.0     # what we learned
                # painterly art has soft edges even where it is loud — the
                # tonal spread betrays a flower bed at any resolution. White
                # type only on genuinely DARK ground; anything mottled or
                # midtone gets the panel.
                light = g.mean[0] < 100
                contrast_ok = abs(g.mean[0] - (255 if light else 30)) > 120
                out.append({
                    "key": key, "band": bname, "column": cname, "width": wname,
                    "box": list(box), "score": round(score, 2),
                    "light_text": light,
                    "scrim": (not contrast_ok) or e.mean[0] > 14
                             or g.stddev[0] > 26,
                })
    out.sort(key=lambda d: d["score"])
    return out


def _quiet_zone(img, safe_px: int, n_lines: int, line_px: int,
                prefs: Optional[dict] = None, force_key: str = ""):
    """The chosen placement — the house pick, or the editor's override."""
    cands = zone_candidates(img, safe_px, n_lines, line_px, prefs)
    pick = None
    if force_key:
        pick = next((c for c in cands if c["key"] == force_key), None)
    pick = pick or cands[0]
    return (tuple(pick["box"]), pick["light_text"], pick["scrim"], pick["key"],
            pick["score"])


async def build_interior(catalog: str, handle=None) -> dict:
    """Write interior.pdf for a children's book (off the event loop)."""
    import asyncio
    return await asyncio.to_thread(_build_interior, catalog, handle)


def _build_interior(catalog: str, handle=None) -> dict:
    """The actual page-by-page build."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfgen import canvas as rl_canvas

    from ..config import OUTPUT_DIR
    from ..database import get_book_by_catalog, get_setting

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    rec = (book["data"].get("childrens") or {})
    ms_rec = book["data"].get("manuscript") or {}
    spreads = rec.get("spreads") or []
    if not spreads:
        raise RuntimeError("This is not a children's book, or it has not been written")
    art = rec.get("art") or {}
    if not art:
        raise RuntimeError("Draw the illustrations before exporting the interior")

    sp = _spec(rec, book)
    out_dir = Path(OUTPUT_DIR) / catalog
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "interior.pdf"

    # KDP full bleed adds 0.125in to the top, bottom and OUTSIDE edge only —
    # never the gutter. Bleeding into the fold as well meant both pages
    # carried the same strip of picture, so a spread showed 0.25in of art
    # twice and the cat had two faces at the join.
    page_w = (sp["trim_w"] + sp["bleed"]) * PT
    page_h = (sp["trim_h"] + 2 * sp["bleed"]) * PT
    safe = (sp["bleed"] + sp["safe"]) * PT
    dpi = 300
    px_w = int((sp["trim_w"] + sp["bleed"]) * dpi)
    px_h = int((sp["trim_h"] + 2 * sp["bleed"]) * dpi)

    title = book.get("title") or ""
    author = (book["data"].get("author_name") or "").strip()

    c = rl_canvas.Canvas(str(pdf_path), pagesize=(page_w, page_h))
    c.setTitle(title)
    if author:
        c.setAuthor(author)

    serif = "Times-Roman"
    serif_bold = "Times-Bold"
    try:
        pdfmetrics.getFont(serif)
    except Exception:                       # pragma: no cover - always present
        serif = serif_bold = "Helvetica"

    def wrap_lines(text: str, bw: float, size: float):
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if c.stringWidth(trial, serif, size) <= bw:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def draw_block(lines, size: float, box_pt, light_text: bool, scrim: bool):
        """The words, set inside the chosen box."""
        if not lines:
            return
        bx, by, bw, _bh = box_pt
        lead = size * 1.62
        block_h = len(lines) * lead
        # NO white panels — ever (Lars, 2026-08-29). The composition reserves
        # paper for the words; the zone scorer must find it. Ink goes on bare.
        c.setFillColorRGB(*( (1, 1, 1) if light_text else (0.07, 0.06, 0.05) ))
        c.setFont(serif, size)
        y = by + block_h - lead * 0.8
        for ln in lines:
            c.drawString(bx, y, ln)
            y -= lead

    def split_to_fit(text: str, box_pt):
        """The words that FIT the box — shrinking a step at a time first —
        and the remainder that must continue on the facing page. Text must
        never run off a page (Lars, 2026-08-28: the first spread's opening
        lines were drawn above the page top)."""
        if not text.strip():
            return None, ""
        bx, by, bw, bh = box_pt
        size = max(13.0, min(26.0, (sp["trim_w"] * PT) / 26))
        while size >= 13.0:
            lines = wrap_lines(text, bw, size)
            if len(lines) * size * 1.62 <= bh + 0.01:
                return (lines, size), ""
            size -= 1.0
        size = 13.0
        lines = wrap_lines(text, bw, size)
        n_fit = max(1, int(bh / (size * 1.62)))
        shown = lines[:n_fit]
        used = sum(len(ln.split()) for ln in shown)
        return (shown, size), " ".join(text.split()[used:])

    def white_page():
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
        c.showPage()

    def centred(lines, sizes, start_frac=0.58, colour=(0.08, 0.07, 0.06)):
        c.setFillColorRGB(1, 1, 1); c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
        c.setFillColorRGB(*colour)
        y = page_h * start_frac
        # nothing on these pages comes closer than 2cm to a page edge — a
        # long title steps its size down until it honours the margin
        max_w = page_w - 2 * (0.787 * 72)
        for ln, (fnt, sz) in zip(lines, sizes):
            if ln:
                while sz > 10 and c.stringWidth(ln, fnt, sz) > max_w:
                    sz -= 1
                c.setFont(fnt, sz)
                c.drawCentredString(page_w / 2, y, ln)
            y -= sz * 1.9
        c.showPage()

    holder = (get_setting("copyright_holder", "") or author or "").strip()
    pages_written = 0

    # ── FRONT MATTER
    # Page one IS the title page and carries the whole imprint: title,
    # subtitle, author, and the publisher's mark and name. A bare half-title
    # wastes the first thing anyone sees when the book is opened.
    import datetime as _dt
    year = _dt.date.today().year
    subtitle = str((ms_rec or {}).get("tagline") or "").strip()
    publisher = (get_setting("publisher_name", "") or "").strip()
    # parents[1] is engine/, and the mark lives in the project root
    logo_path = Path(__file__).resolve().parents[2] / "assets" / "olive-tree-logo.png"

    c.setFillColorRGB(1, 1, 1); c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
    c.setFillColorRGB(0.08, 0.07, 0.06)
    y = page_h * 0.70
    # THE TITLE RULE (Lars, 2026-08-29): generous margins on both sides —
    # the title lives inside a comfortable measure (72% of the page). Too
    # long for one line? It breaks at the most BALANCED natural word
    # boundary into two lines; the size only shrinks if even two lines
    # cannot hold it.
    t_size = 30
    max_tw = page_w * 0.72
    def _balanced_title(txt, size):
        if c.stringWidth(txt, serif_bold, size) <= max_tw:
            return [txt]
        ws = txt.split()
        best, gap = None, None
        for i in range(1, len(ws)):
            a, b = " ".join(ws[:i]), " ".join(ws[i:])
            wa = c.stringWidth(a, serif_bold, size)
            wb = c.stringWidth(b, serif_bold, size)
            if wa <= max_tw and wb <= max_tw:
                d = abs(wa - wb)
                if gap is None or d < gap:
                    best, gap = [a, b], d
        return best
    t_lines = _balanced_title(title, t_size)
    while t_lines is None and t_size > 14:
        t_size -= 1
        t_lines = _balanced_title(title, t_size)
    t_lines = t_lines or [title]
    c.setFont(serif_bold, t_size)
    for _i, ln in enumerate(t_lines):
        c.drawCentredString(page_w / 2, y, ln)
        if _i < len(t_lines) - 1:
            y -= t_size * 1.25
    if subtitle:
        y -= 34
        c.setFont(serif, 14)
        c.setFillColorRGB(0.30, 0.28, 0.26)
        c.drawCentredString(page_w / 2, y, subtitle)
        c.setFillColorRGB(0.08, 0.07, 0.06)
    if author:
        y -= 46
        c.setFont(serif, 16)
        c.drawCentredString(page_w / 2, y, author)
    # the imprint sits at the foot, mark above name, as a printed book does
    if logo_path.exists():
        # the mark is black art on transparency; flatten it onto white and
        # draw it plainly. A colour mask silently failed here and the logo
        # simply never appeared.
        lg = Image.open(logo_path).convert("RGBA")
        bbox = lg.split()[3].getbbox() or (0, 0, lg.width, lg.height)
        lg = lg.crop(bbox)
        flat = Image.new("RGB", lg.size, (255, 255, 255))
        flat.paste(lg, (0, 0), lg)
        buf = io.BytesIO(); flat.save(buf, format="PNG"); buf.seek(0)
        side = 42.0
        lw = side * (flat.width / flat.height)
        c.drawImage(ImageReader(buf), (page_w - lw) / 2, safe + 30,
                    width=lw, height=side)
    if publisher:
        c.setFillColorRGB(0.30, 0.28, 0.26)
        c.setFont(serif, 9.5)
        c.drawCentredString(page_w / 2, safe + 16, publisher.upper())
        c.setFont(serif, 8)
        c.drawCentredString(page_w / 2, safe + 5, "FRANCE")
        c.setFillColorRGB(0.45, 0.43, 0.41)
        c.setFont(serif, 6.5)
        c.drawCentredString(page_w / 2, safe - 5, str(year))
    c.showPage(); pages_written += 1

    # copyright page — the KDP essentials, including the AI disclosure
    c.setFillColorRGB(1, 1, 1); c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
    c.setFillColorRGB(0.28, 0.26, 0.24)
    isbn = str((book["data"].get("publishing") or {}).get("isbn") or "").strip()
    lines = [f"Copyright \u00a9 {year} {holder}".strip() if holder else f"Copyright \u00a9 {year}",
             "All rights reserved.",
             "",
             "No part of this book may be reproduced, stored in a retrieval",
             "system, or transmitted in any form or by any means without the",
             "prior written permission of the copyright holder.",
             "",
             "This is a work of fiction. Names, characters, places and incidents",
             "are the product of the author's imagination.",
             "",
             f"ISBN: {isbn}" if isbn else "",
             "",
             "Text and illustrations created with the assistance of artificial",
             "intelligence.",
             "",
             f"First edition {year}"]
    y = page_h * 0.42
    c.setFont(serif, 8.5)
    for ln in lines:
        if ln:
            c.drawCentredString(page_w / 2, y, ln)
        y -= 12
    c.showPage(); pages_written += 1

    # A spread's two halves must land on FACING pages — (4,5), (6,7) — not on
    # the front and back of one sheet. Facing pairs always start on an EVEN
    # page, so the story has to begin on one. With two pages of front matter
    # it began on page 3 and every illustration was split across a leaf.
    while pages_written % 2 != 1:
        white_page(); pages_written += 1

    # ── THE STORY — each spread runs across two facing pages, which is what a
    #    picture book is and what makes 14 spreads land on a 32-page book.
    half_px_w = px_w // 2
    chosen: dict = {}
    from ..database import get_setting as _gs
    house_prefs = _gs("childrens_layout_prefs", {}) or {}
    wash_left = {}
    wash_aw = {}
    crowded = []
    for i, s_ in enumerate(spreads):
        n = s_["n"]
        rel = art.get(str(n))
        if handle:
            handle.progress(0.1 + 0.8 * i / max(1, len(spreads)), "interior",
                            f"spread {n} of {len(spreads)}")
        img_path = (Path(OUTPUT_DIR) / catalog / rel) if rel else None
        if not (img_path and img_path.exists()):
            white_page(); white_page(); pages_written += 2
            continue

        im = Image.open(img_path).convert("RGB")
        # With bleed only on the outside edges the spread is exactly two pages
        # wide, so it cuts cleanly down the middle: two equal halves, one cut
        # line, nothing shown twice.
        spread_w = px_w * 2
        im = _fit_cover(im, spread_w, px_h)
        # GUARANTEED AIR (Lars, 2026-08-29): generation obeyed the reserved
        # text region only ~40% of the time, even with retries. So the paper
        # is composited deterministically — a feathered white wash over the
        # planned side, the art dissolving into it like a true vignette. The
        # words always get real paper; the art keeps its soft edge.
        import numpy as _np2
        _arr = _np2.asarray(im).astype(_np2.float32)
        _W2, _H2 = im.size
        _words = len((s_.get("text") or "").split())
        _fw = 0.47 if _words >= 45 else 0.34
        # THE WASH MUST NEVER ERASE A CHARACTER (Lars, 2026-08-29): measure
        # who stands in each page's air region; the wash contracts to stop
        # short of them, and flips to the other page when that side offers
        # more clean room. The text follows the wash.
        _halfL = im.crop((0, 0, _W2 // 2, _H2))
        _halfR = im.crop((_W2 // 2, 0, _W2, _H2))
        def _clean_air(is_left):
            # PAPER is measured directly — bright, flat columns running in
            # from the page's outer edge. (The character mask color-grows
            # through a flower field and cried wolf on real paper.)
            half = _halfL if is_left else _halfR
            g = _np2.asarray(half.convert("L").resize(
                (max(1, half.width // 8), max(1, half.height // 8))),
                dtype=_np2.float32)
            rows = g[: max(1, int(g.shape[0] * 0.60)), :]
            ok = (rows.mean(axis=0) > 224) & (rows.std(axis=0) < 32)
            idx = range(len(ok)) if is_left else range(len(ok) - 1, -1, -1)
            w = 0
            for j in idx:
                if ok[j]:
                    w += 1
                else:
                    break
            return w * 8
        _plan_left = (n % 2 == 1)
        _margin = int(0.035 * _W2)
        _clean_p = _clean_air(_plan_left) - _margin
        _aw_want = int(_W2 * _fw)
        _aw = min(_aw_want, max(0, _clean_p))
        if _aw < int(0.18 * _W2):
            _clean_o = _clean_air(not _plan_left) - _margin
            if _clean_o > _clean_p:
                _plan_left = not _plan_left
                _aw = min(_aw_want, max(0, _clean_o))
        if _aw < int(0.24 * _W2):
            # both pages crowded: the art left no honest room — flag the
            # spread for a hard-air redraw instead of contorting the layout
            crowded.append(n)
        _aw = max(_aw, int(0.16 * _W2))      # some paper must always exist
        wash_left[str(n)] = _plan_left
        wash_aw[str(n)] = _aw
        _x = _np2.arange(_W2, dtype=_np2.float32)
        if _plan_left:
            _gx = _np2.clip((_aw - _x) / (_aw * 0.45), 0, 1)
        else:
            _gx = _np2.clip((_x - (_W2 - _aw)) / (_aw * 0.45), 0, 1)
        _y = _np2.arange(_H2, dtype=_np2.float32)
        _gy = _np2.clip((_H2 * 0.88 - _y) / (_H2 * 0.26), 0, 1)
        _alpha = (_np2.minimum(_gx[None, :], _gy[:, None]) * 0.96)[..., None]
        _paper = _np2.array([252, 251, 249], dtype=_np2.float32)
        _arr = _arr * (1 - _alpha) + _paper * _alpha
        im = Image.fromarray(_arr.astype("uint8"))
        left_im = im.crop((0, 0, px_w, px_h))
        right_im = im.crop((px_w, 0, spread_w, px_h))

        safe_px = int((sp["bleed"] + sp["safe"]) * dpi)
        # text never closer than 2cm to the page edge (Lars, 2026-08-29)
        text_safe = max(safe_px, int(0.787 * dpi))
        size = max(13.0, min(26.0, (sp["trim_w"] * PT) / 26))
        est_lines = max(1, int(len(s_.get("text", "").split()) / 7) + 1)
        # the words go on whichever page has the quieter picture
        lay = (rec.get("layout") or {}).get(str(n)) or {}
        # this book's corrections sit on top of what the house has learned
        # across every book before it — otherwise book two starts from zero
        prefs = dict(house_prefs)
        for k, v in (rec.get("layout_prefs") or {}).items():
            prefs[k] = float(prefs.get(k, 0.0)) + float(v)
        lpx = int(size * 1.62 * dpi / PT)
        zone_l, light_l, scrim_l, key_l, score_l = _quiet_zone(
            left_im, text_safe, est_lines, lpx, prefs,
            lay.get("key") if lay.get("page") == "left" else "")
        zone_r, light_r, scrim_r, key_r, score_r = _quiet_zone(
            right_im, text_safe, est_lines, lpx, prefs,
            lay.get("key") if lay.get("page") == "right" else "")
        from PIL import ImageFilter, ImageStat
        busy = lambda img, z: ImageStat.Stat(
            img.convert("L").filter(ImageFilter.FIND_EDGES).crop(z)).mean[0]
        # the WASHED STRIP is guaranteed paper — offer it as the primary
        # zone on its page, however slim; a tall narrow column beats any
        # placement on art (Lars: the white field must never sit on a
        # character, and the text follows the wash)
        _wl = wash_left.get(str(n))
        _wa = wash_aw.get(str(n), 0)
        _solid = int(_wa * 0.55)
        if _wl is True:
            bx1 = _solid - int(0.10 * dpi)
            if bx1 - text_safe >= int(1.1 * dpi):
                zone_l = (text_safe, text_safe, bx1, int(px_h * 0.86))
                light_l, scrim_l, key_l, score_l = False, False, "wash", -1000.0
        elif _wl is False:
            bx0 = max(text_safe, px_w - _solid + int(0.10 * dpi))
            if px_w - text_safe - bx0 >= int(1.1 * dpi):
                zone_r = (bx0, text_safe, px_w - text_safe, int(px_h * 0.86))
                light_r, scrim_r, key_r, score_r = False, False, "wash", -1000.0
        # the illustration RESERVED a side for these words (odd spreads
        # left, even right) — honour the plan unless that side's best zone
        # is clearly worse (old full-bleed art, or the model ignored us)
        planned_left = wash_left.get(str(n), n % 2 == 1)
        if lay.get("page"):
            on_left = lay.get("page") == "left"
        elif (score_l - score_r <= 35) if planned_left else (score_r - score_l > 35):
            on_left = True
        else:
            on_left = False
        chosen[str(n)] = {"page": "left" if on_left else "right",
                          "key": key_l if on_left else key_r,
                          "manual": bool(lay.get("key"))}

        def to_box(zone):
            x0, y0, x1, y1 = zone
            return (x0 * PT / dpi, (px_h - y1) * PT / dpi,
                    (x1 - x0) * PT / dpi, (y1 - y0) * PT / dpi)

        # the words go on the chosen page IF they fit; a spread with more to
        # say flows across both pages in reading order instead of overflowing
        text_all = s_.get("text", "")
        assign = {}
        fitted, rest = split_to_fit(text_all, to_box(zone_l if on_left else zone_r))
        if fitted and not rest:
            key0 = "left" if on_left else "right"
            assign[key0] = (fitted, to_box(zone_l if on_left else zone_r),
                            (light_l if on_left else light_r),
                            (scrim_l if on_left else scrim_r))
        elif fitted:
            # balance the spread: break near the midpoint at a sentence end,
            # so neither page carries an orphan line of two or three words
            import re as _re
            sents = _re.split(r'(?<=[.!?\"]) +', text_all)
            if len(sents) >= 2:
                total_w = len(text_all.split())
                best, best_diff = 1, float("inf")
                for i in range(1, len(sents)):
                    diff = abs(len(" ".join(sents[:i]).split()) - total_w / 2)
                    if diff < best_diff:
                        best_diff, best = diff, i
                left_txt = " ".join(sents[:best])
                right_txt = " ".join(sents[best:])
            else:
                left_txt, right_txt = text_all, ""
            fit_l, rest_l = split_to_fit(left_txt, to_box(zone_l))
            assign["left"] = (fit_l, to_box(zone_l), light_l, scrim_l)
            rest_l = (rest_l + " " + right_txt).strip()
            if rest_l:
                fit_r, rest_r = split_to_fit(rest_l, to_box(zone_r))
                if rest_r:
                    # final guarantee: the right page opens its full safe
                    # column behind a scrim — everything fits at floor size
                    full = (text_safe, text_safe, px_w - text_safe, px_h - text_safe)
                    fit_r, _ = split_to_fit(rest_l, to_box(full))
                    assign["right"] = (fit_r, to_box(full), light_r, True)
                else:
                    assign["right"] = (fit_r, to_box(zone_r), light_r, scrim_r)

        for im_half, key in ((left_im, "left"), (right_im, "right")):
            buf = io.BytesIO()
            im_half.save(buf, format="JPEG", quality=92, optimize=True)
            buf.seek(0)
            c.drawImage(ImageReader(buf), 0, 0, width=page_w, height=page_h)
            if key in assign:
                (lines_and_size, box_pt, lite2, scrim2) = assign[key]
                if lines_and_size:
                    draw_block(lines_and_size[0], lines_and_size[1],
                               box_pt, lite2, scrim2)
            c.showPage(); pages_written += 1

    # ── BACK MATTER: at least one white page, then up to the binder's count
    white_page(); pages_written += 1
    while pages_written % 8 != 0:
        white_page(); pages_written += 1

    c.save()

    fresh = get_book_by_catalog(catalog)
    fd = dict(fresh["data"]); frec = dict(fd.get("childrens") or {})
    frec["layout_used"] = chosen
    fd["childrens"] = frec
    from ..database import update_book as _ub
    _ub(fresh["id"], fd, sections=["childrens"])

    return {
        "pdf": str(pdf_path),
        "pages": pages_written,
        "trim": f"{sp['trim_w']}x{sp['trim_h']}",
        "bleed_in": sp["bleed"],
        "page_size_in": [round(page_w / PT, 3), round(page_h / PT, 3)],
        "divisible_by_8": pages_written % 8 == 0,
        "spreads": len(spreads),
        "undrawn": [s["n"] for s in spreads if not art.get(str(s["n"]))],
        "crowded": crowded,
    }
