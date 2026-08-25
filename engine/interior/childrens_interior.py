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
    W, H = img.size
    block_h = min(int(n_lines * line_px * 1.55) + int(safe_px * 0.5), int(H * 0.40))
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    grey = img.convert("L")
    prefs = prefs or {}

    avail = W - 2 * safe_px
    widths = {"wide": avail, "column": int(avail * 0.62), "narrow": int(avail * 0.48)}
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
                score = (e.mean[0] + e.stddev[0] * 0.8       # busy art
                         + g.stddev[0] * 0.35                 # mottled tone
                         + (bw / avail) * 6.0)                # prefer a column
                key = f"{bname}-{cname}-{wname}"
                score -= float(prefs.get(key, 0.0)) * 3.0     # what we learned
                light = g.mean[0] < 128
                contrast_ok = abs(g.mean[0] - (255 if light else 0)) > 105
                out.append({
                    "key": key, "band": bname, "column": cname, "width": wname,
                    "box": list(box), "score": round(score, 2),
                    "light_text": light,
                    "scrim": (not contrast_ok) or e.mean[0] > 14,
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
    return tuple(pick["box"]), pick["light_text"], pick["scrim"], pick["key"]


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

    def draw_text(text: str, box_pt, light_text: bool, scrim: bool):
        """The words, set inside the chosen box."""
        if not text.strip():
            return
        bx, by, bw, _bh = box_pt
        size = max(13.0, min(26.0, (sp["trim_w"] * PT) / 26))
        lead = size * 1.34
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
        block_h = len(lines) * lead
        if scrim:                    # only where the picture would swallow letters
            c.saveState()
            if light_text:
                c.setFillColorRGB(0, 0, 0, alpha=0.38)
            else:
                c.setFillColorRGB(1, 1, 1, alpha=0.55)
            c.roundRect(bx - 12, by - 10, bw + 24, block_h + 20, 12, stroke=0, fill=1)
            c.restoreState()
        c.setFillColorRGB(*( (1, 1, 1) if light_text else (0.07, 0.06, 0.05) ))
        c.setFont(serif, size)
        y = by + block_h - lead * 0.8
        for ln in lines:
            c.drawString(bx, y, ln)
            y -= lead

    def white_page():
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
        c.showPage()

    def centred(lines, sizes, start_frac=0.58, colour=(0.08, 0.07, 0.06)):
        c.setFillColorRGB(1, 1, 1); c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
        c.setFillColorRGB(*colour)
        y = page_h * start_frac
        for ln, (fnt, sz) in zip(lines, sizes):
            if ln:
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
    c.setFont(serif_bold, 30)
    c.drawCentredString(page_w / 2, y, title)
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
        left_im = im.crop((0, 0, px_w, px_h))
        right_im = im.crop((px_w, 0, spread_w, px_h))

        safe_px = int((sp["bleed"] + sp["safe"]) * dpi)
        size = max(13.0, min(26.0, (sp["trim_w"] * PT) / 26))
        est_lines = max(1, int(len(s_.get("text", "").split()) / 7) + 1)
        # the words go on whichever page has the quieter picture
        lay = (rec.get("layout") or {}).get(str(n)) or {}
        # this book's corrections sit on top of what the house has learned
        # across every book before it — otherwise book two starts from zero
        prefs = dict(house_prefs)
        for k, v in (rec.get("layout_prefs") or {}).items():
            prefs[k] = float(prefs.get(k, 0.0)) + float(v)
        lpx = int(size * 1.34 * dpi / PT)
        zone_l, light_l, scrim_l, key_l = _quiet_zone(
            left_im, safe_px, est_lines, lpx, prefs,
            lay.get("key") if lay.get("page") == "left" else "")
        zone_r, light_r, scrim_r, key_r = _quiet_zone(
            right_im, safe_px, est_lines, lpx, prefs,
            lay.get("key") if lay.get("page") == "right" else "")
        from PIL import ImageFilter, ImageStat
        busy = lambda img, z: ImageStat.Stat(
            img.convert("L").filter(ImageFilter.FIND_EDGES).crop(z)).mean[0]
        on_left = (lay.get("page") == "left") if lay.get("page") else (
            busy(left_im, zone_l) <= busy(right_im, zone_r))
        chosen[str(n)] = {"page": "left" if on_left else "right",
                          "key": key_l if on_left else key_r,
                          "manual": bool(lay.get("key"))}

        for side, (im_half, zone, lite, scrim) in enumerate((
                (left_im, zone_l, light_l, scrim_l),
                (right_im, zone_r, light_r, scrim_r))):
            buf = io.BytesIO()
            im_half.save(buf, format="JPEG", quality=92, optimize=True)
            buf.seek(0)
            c.drawImage(ImageReader(buf), 0, 0, width=page_w, height=page_h)
            if (side == 0) == on_left:
                x0, y0, x1, y1 = zone
                box_pt = (x0 * PT / dpi,
                          (px_h - y1) * PT / dpi,
                          (x1 - x0) * PT / dpi,
                          (y1 - y0) * PT / dpi)
                draw_text(s_.get("text", ""), box_pt, lite, scrim)
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
    _ub(fresh["id"], fd)

    return {
        "pdf": str(pdf_path),
        "pages": pages_written,
        "trim": f"{sp['trim_w']}x{sp['trim_h']}",
        "bleed_in": sp["bleed"],
        "page_size_in": [round(page_w / PT, 3), round(page_h / PT, 3)],
        "divisible_by_8": pages_written % 8 == 0,
        "spreads": len(spreads),
        "undrawn": [s["n"] for s in spreads if not art.get(str(s["n"]))],
    }
