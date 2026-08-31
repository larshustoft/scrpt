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


def _dash_dialogue(text: str) -> list:
    """Traditional dialogue setting (Lars, 2026-08-30): every spoken line
    begins its own line with a plain dash and no quote marks (Lars: the em dash is too long) — the classic
    picture-book convention, and easier for small readers to follow.
    Returns the text as paragraphs: narration blocks and dash lines."""
    import re
    parts = (text or "").split('"')
    if len(parts) < 3:
        return [text.strip()] if (text or "").strip() else []
    paras, narr, i = [], parts[0].strip(), 1
    while i < len(parts):
        quoted = parts[i].strip()
        after = parts[i + 1] if i + 1 < len(parts) else ""
        m = re.match(r"\s*([^.!?]*[.!?])(.*)", after, re.S)
        attach, rest = "", after.strip()
        if m and quoted and len(m.group(1).strip()) <= 70:
            cand = m.group(1).strip()
            head = " ".join(cand.split()[:5]).lower()
            _verbs = ("said", "cried", "asked", "called", "whispered",
                      "answered", "shouted", "sang", "replied", "chirped",
                      "puffed", "wobbl", "added", "sniff", "laughed")
            if cand[:1].islower() or any(v in head for v in _verbs):
                attach, rest = cand, m.group(2).strip()
        if narr:
            paras.append(narr)
        if quoted:
            paras.append(("- " + quoted + (" " + attach if attach else "")).strip())
        narr = rest
        i += 2
    if narr:
        paras.append(narr)
    return [x for x in paras if x]


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
        # EVERY character counts (Lars, 2026-08-30): keeping only the
        # largest blob protected Glitter and let the field bury Princess.
        # Any blob at least a fifth of the largest is somebody.
        # a fifth of the largest blob missed Pip — a bird is a character
        # too. Anyone bigger than a few cells counts (Lars, 2026-08-30).
        floor = max(9, int(sizes.max() * 0.06))
        for bi, sz in enumerate(sizes, start=1):
            if bi != big and sz >= floor:
                char_mask |= (lab == bi)
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

    def wrap_paras(text: str, bw: float, size: float):
        lines = []
        for para in _dash_dialogue(text):
            lines.extend(wrap_lines(para, bw, size))
        return lines

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
            lines = wrap_paras(text, bw, size)
            if len(lines) * size * 1.62 <= bh + 0.01:
                return (lines, size), ""
            size -= 1.0
        size = 13.0
        lines = wrap_paras(text, bw, size)
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
    _assets = Path(__file__).resolve().parents[2] / "assets"
    logo_path = (_assets / "tigerworks-logo.png"
                 if (_assets / "tigerworks-logo.png").exists()
                 else _assets / "olive-tree-logo.png")

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
        # TEXT ONLY ON WHITE FIELDS (Lars, 2026-08-30). The old wash
        # measured "clean air" by column brightness, so bright mist read as
        # paper: the wash landed on characters, shrank to a sliver, and the
        # words fell back onto art. The contract is now word-first and
        # absolute: measure the WORDS, wash a true-paper field wide enough
        # for them on the page whose outer column holds the fewest
        # character pixels, and set the words inside the field — never
        # anywhere else.
        import numpy as _np2
        text_all = (s_.get("text") or "").strip()
        safe_px = int((sp["bleed"] + sp["safe"]) * dpi)
        # text never closer than 2cm to the page edge (Lars, 2026-08-29)
        text_safe = max(safe_px, int(0.787 * dpi))
        size = max(13.0, min(26.0, (sp["trim_w"] * PT) / 26))
        lay = (rec.get("layout") or {}).get(str(n)) or {}
        chosen[str(n)] = {"page": "", "key": "wash", "manual": bool(lay.get("page"))}

        text_safe_pt = text_safe * PT / dpi
        usable_h_pt = page_h - 2 * text_safe_pt
        pad_px = int(0.32 * dpi)              # air between field edge and ink

        # the narrowest column the words genuinely fit at full size wins —
        # longer lines where space allows (Lars), never a cramped sliver
        fit_frac, fit_lines = 0.50, None
        for frac in (0.32, 0.36, 0.40, 0.44, 0.48, 0.50):
            col_pt = (px_w - 2 * text_safe - 2 * pad_px) * frac * PT / dpi
            lines_try = wrap_paras(text_all, col_pt, size) if text_all else []
            if len(lines_try) * size * 1.62 <= usable_h_pt * 0.80:
                fit_frac, fit_lines = frac, lines_try
                break
        if fit_lines is None and text_all:
            col_pt = (px_w - 2 * text_safe - 2 * pad_px) * 0.50 * PT / dpi
            fit_lines = wrap_paras(text_all, col_pt, size)

        col_px = int((px_w - 2 * text_safe - 2 * pad_px) * fit_frac)
        aw = min(int(px_w * 0.62), text_safe + col_px + 2 * pad_px)

        # who is standing in each candidate field? (the one measurement
        # that matters — characters, not brightness)
        _, _char = _subject_mask(im)
        _cw = _char.shape[1]
        _reach = aw + int(0.6 * max(int(0.5 * dpi), int(0.42 * aw)))
        _aw8 = max(1, int(_reach / (im.width / _cw)))
        occ_l = float(_char[:, :_aw8].mean())
        occ_r = float(_char[:, _cw - _aw8:].mean())

        # THE CLEAN RUN: how far in from each outer edge before a real
        # character body stands (a column is blocked only at body-density
        # — scattered flowers don't count). The field and its feather must
        # end before that (Lars, 2026-08-30: the feather kept clipping
        # whoever stood just past the field).
        _col_d = _char.mean(axis=0)
        _sc8 = im.width / _cw
        def _clean_run(from_left):
            idx = range(_cw) if from_left else range(_cw - 1, -1, -1)
            run = 0
            for j in idx:
                if _col_d[j] > 0.25:
                    break
                run += 1
            return int(run * _sc8)
        clean_l, clean_r = _clean_run(True), _clean_run(False)
        if lay.get("page"):
            _plan_left = lay.get("page") == "left"
        else:
            _plan_left = (n % 2 == 1)
            occ_p, occ_o = (occ_l, occ_r) if _plan_left else (occ_r, occ_l)
            if occ_p > occ_o + 0.02:
                _plan_left = not _plan_left
        # NEVER the framed-art page (Lars, 2026-08-30: "this kind of lazy
        # solution is not acceptable — the previous look was better"). A
        # spread whose art cannot host the field keeps the full-bleed look
        # and goes on the REDRAW QUEUE: its illustration is re-created
        # with a real built-in white field (illustrate(only=n,
        # hard_air=True)), then the interior rebuilds on honest air.
        album = False
        if bool(text_all) and min(occ_l, occ_r) > 0.10:
            crowded.append(n)
        wash_left[str(n)] = _plan_left
        wash_aw[str(n)] = aw
        chosen[str(n)]["page"] = "left" if _plan_left else "right"
        chosen[str(n)]["key"] = "album" if album else "wash"

        # the field never reaches past its side's clean run: shrink the
        # column (floor: a narrow-but-honest 0.24 page) before ever letting
        # the feather touch someone
        _feather_w = max(int(0.5 * dpi), int(0.42 * aw))
        _clean = clean_l if _plan_left else clean_r
        _max_aw = max(0, _clean - int(0.55 * _feather_w))
        # the words outrank everything: the column may never shrink below
        # what the FULL text needs at floor size — dropped sentences are a
        # worse sin than a feather touching someone (Lars's order of law)
        _fit_col = None
        if text_all:
            for _fr in (0.24, 0.28, 0.32, 0.38, 0.44, 0.50):
                _cpx = int((px_w - 2 * text_safe - 2 * pad_px) * _fr)
                _lines_f = wrap_paras(text_all, _cpx * PT / dpi, 13.0)
                if len(_lines_f) * 13.0 * 1.62 <= usable_h_pt:
                    _fit_col = _cpx
                    break
            if _fit_col is None:
                _fit_col = int((px_w - 2 * text_safe - 2 * pad_px) * 0.50)
        if aw > _max_aw:
            _min_col = max(_fit_col or 0,
                           int((px_w - 2 * text_safe - 2 * pad_px) * 0.24))
            aw_floor = text_safe + _min_col + 2 * pad_px
            if _max_aw >= aw_floor:
                aw = _max_aw
                col_px = aw - text_safe - 2 * pad_px
            else:
                _other = clean_r if _plan_left else clean_l
                if _other - int(0.55 * _feather_w) >= aw_floor and not lay.get("page"):
                    _plan_left = not _plan_left
                    wash_left[str(n)] = _plan_left
                    chosen[str(n)]["page"] = "left" if _plan_left else "right"
                    aw = min(aw, _other - int(0.55 * _feather_w))
                    col_px = aw - text_safe - 2 * pad_px
                else:
                    # neither side is clean enough: the words win — keep a
                    # column the full text fits, feather where it must
                    aw = max(aw_floor, min(aw, _max_aw if _max_aw >= aw_floor else aw))
                    col_px = aw - text_safe - 2 * pad_px

        if album:
            from PIL import ImageDraw as _ID, ImageFilter as _IF
            _paper_rgb = (253, 252, 250)
            _m = int(0.55 * dpi)
            _box_w, _box_h = px_w - 2 * _m, px_h - 2 * _m
            # crop the wide spread to the CHARACTERS' region first, so the
            # framed picture fills the portrait page instead of floating
            # as a thin band — every character stays inside, by the mask
            import numpy as _np3
            _cols = _np3.where(_char.any(axis=0))[0]
            if len(_cols):
                _s8 = im.width / _char.shape[1]
                _cx0 = max(0, int(_cols.min() * _s8 - 0.16 * im.width))
                _cx1 = min(im.width, int((_cols.max() + 1) * _s8 + 0.16 * im.width))
                _min_w = int(im.height * 1.05)   # never narrower than ~square
                if _cx1 - _cx0 < _min_w:
                    _pad = (_min_w - (_cx1 - _cx0)) // 2
                    _cx0 = max(0, _cx0 - _pad)
                    _cx1 = min(im.width, _cx1 + _pad)
                im = im.crop((_cx0, 0, _cx1, im.height))
            _iw, _ih = im.size
            _sc = min(_box_w / _iw, _box_h / _ih)
            _art = im.resize((int(_iw * _sc), int(_ih * _sc)), Image.LANCZOS)
            _mask = Image.new("L", _art.size, 0)
            _rad = int(0.22 * dpi)
            _ID.Draw(_mask).rounded_rectangle(
                [_rad // 2, _rad // 2, _art.width - _rad // 2,
                 _art.height - _rad // 2], radius=_rad, fill=255)
            _mask = _mask.filter(_IF.GaussianBlur(int(0.14 * dpi)))
            _page_art = Image.new("RGB", (px_w, px_h), _paper_rgb)
            _page_art.paste(_art, ((px_w - _art.width) // 2,
                                   (px_h - _art.height) // 2), _mask)
            _page_txt = Image.new("RGB", (px_w, px_h), _paper_rgb)
            if _plan_left:
                left_im, right_im = _page_txt, _page_art
            else:
                left_im, right_im = _page_art, _page_txt
        elif text_all:
            # the field: solid true paper under every line, a wide cosine
            # feather dissolving into the art — a paper edge, never a panel
            _W2, _H2 = im.size
            _arr = _np2.asarray(im).astype(_np2.float32)
            feather = max(int(0.5 * dpi), int(0.42 * aw))
            _x = _np2.arange(_W2, dtype=_np2.float32)
            if _plan_left:
                _t = _np2.clip((_x - aw) / feather, 0, 1)
            else:
                _t = _np2.clip(((_W2 - aw) - _x) / feather, 0, 1)
            _alpha = (0.5 + 0.5 * _np2.cos(_np2.pi * (1 - _t)))[None, :, None]
            _alpha = 1.0 - _alpha            # 1 inside the field, 0 in the art
            _paper = _np2.array([253, 252, 250], dtype=_np2.float32)
            _arr = _arr * (1 - _alpha) + _paper * _alpha
            im = Image.fromarray(_arr.astype("uint8"))

        if not album:
            left_im = im.crop((0, 0, px_w, px_h))
            right_im = im.crop((px_w, 0, spread_w, px_h))

        # the words, set inside the field core — top third, breathing room
        assign = {}
        if text_all:
            # the column lives INSIDE the washed field — which sits at the
            # left page's left edge or the right page's right edge. Using
            # left coordinates on a right-side field put the words on art
            # while their paper sat empty beside them (2026-08-30).
            if album:
                x0 = (px_w - col_px) // 2       # a pure-paper page: centred
            elif _plan_left:
                x0 = text_safe + pad_px
            else:
                x0 = px_w - text_safe - pad_px - col_px
            box_px = (x0, text_safe, x0 + col_px, px_h - text_safe)
            bx0, by0, bx1, by1 = box_px
            box_pt0 = (bx0 * PT / dpi, (px_h - by1) * PT / dpi,
                       (bx1 - bx0) * PT / dpi, (by1 - by0) * PT / dpi)
            fitted, rest = split_to_fit(text_all, box_pt0)
            if fitted:
                f_lines, f_size = fitted
                block_h = len(f_lines) * f_size * 1.62
                y_top = max(text_safe_pt,
                            text_safe_pt + (usable_h_pt - block_h) * 0.34)
                box_pt = (box_pt0[0], page_h - y_top - block_h,
                          box_pt0[2], block_h + 2)
                assign["left" if _plan_left else "right"] = (
                    (f_lines, f_size), box_pt, False, False)

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

    # ── BACK MATTER: the binder's padding, EARNED (Lars, 2026-08-30:
    # "why are there so many white pages?"). If the book belongs to a
    # universe, the spare leaves become a lullaby sing-along page and a
    # series page before the final blanks.
    def _universe_profile():
        try:
            import json as _json
            from ..database import get_setting as _gs
            _v = _gs("universes", "")
            reg = _v if isinstance(_v, dict) else _json.loads(_v or "{}")
            root = Path(__file__).resolve().parents[2]
            for u in reg.values():
                prof = _json.loads((root / u["profile"]).read_text())
                if catalog in (prof.get("members") or []):
                    return prof
        except Exception:
            pass
        return {}

    _prof = _universe_profile()
    _spare = (8 - (pages_written % 8)) % 8
    if _prof and _spare >= 3:
        _lyr = _prof.get("lullaby_lyrics_short") or []
        if _lyr:
            centred(["The Unicorn Lullaby", ""] + list(_lyr)
                    + ["", "Sung at the end of every episode."],
                    [(serif, 22), (serif, 14)] + [(serif, 15)] * len(_lyr)
                    + [(serif, 14), (serif, 12)], start_frac=0.68)
            pages_written += 1
        _ttl = _prof.get("season_titles") or []
        if _ttl:
            centred(["More adventures in Rainbow Forest", ""] + list(_ttl)
                    + ["", "...and many more.",
                       str(_prof.get("domain") or "")],
                    [(serif, 20), (serif, 14)] + [(serif, 14)] * len(_ttl)
                    + [(serif, 12), (serif, 13), (serif, 13)],
                    start_frac=0.72)
            pages_written += 1
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
