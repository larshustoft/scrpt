"""
Print cover: the house wrap, the designer package, and file validation.

THE OLIVE TREE SCRIPTS HOUSE STYLE
==================================
The front comes from the image model; SCRPT composes the back and spine around
it. These rules make the three panels read as one designed object, and they
apply to every book automatically.

TYPE
  - Display face (spine, tagline, series line) is MATCHED to the front cover:
    cover/typography.py looks at the finished artwork and picks the closest
    print face, cached on the book.
  - Back-cover BODY copy is set in the book's own INTERIOR face, so the cover
    and the pages inside agree.

COLOUR
  - Back and spine are WHITE. Print-on-demand bands and scuffs on large dark
    areas, and spine folds crack white; white also lets the mandatory barcode
    box vanish.
  - The accent (frame, tagline, series line) takes the AUTHOR NAME's colour
    from the front. If that name is white or very light it would disappear on
    white, so the accent falls back to black.

LAYOUT (bottom-up reserved bands — nothing may overlap)
    barcode clear zone -> series line -> gap -> body copy -> tagline
  - Body copy auto-fits: the largest size 14pt..10pt that fills its band,
    tightening leading before shrinking type, then centred in the space.
  - Tagline breaks one SENTENCE per line, never orphaning a word.
  - No descriptive category line ("An Action Thriller").

GENRE
  - Romance / historical drama: ornamental frame with corner flourishes; the
    imprint tucks inside it.
  - Thriller / action: no frame; a larger, punchier author name on the spine,
    and the imprint drops level with the barcode's bottom margin.

SPINE
  - AUTHOR at the head in the largest type, TITLE smaller beneath, both
    reading top-to-bottom, auto-fitted to the spine's run.
  - The tree mark sits at the foot, its base level with the back cover's frame.

IMPRINT
  - A fixed lockup on every book: the tree plus "OLIVE TREE SCRIPTS" in a
    clean sans, wordmark baseline level with the foot of the tree.

Also here: the designer package (spec sheet + guide template) for when a human
designs a cover, and validate_uploaded_cover() which checks any delivered file
against the computed KDP spec before it can be marked final.
"""

import io
from pathlib import Path

from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas as rl_canvas

from ..config import OUTPUT_DIR
from ..database import get_book_by_catalog
from .dimensions import calculate_cover, CoverDimensions

DPI = 300
TOLERANCE_IN = 0.06   # generous acceptance window on delivered file dimensions


def cover_spec_dict(page_count: int, trim_size: str, paper_type: str) -> dict:
    d = calculate_cover(page_count, trim_size, paper_type)
    return {
        "page_count": d.page_count,
        "trim_size": d.trim_size,
        "paper_type": d.paper_type,
        "spine_width_in": round(d.spine_width, 4),
        "spine_has_text": d.spine_has_text,
        "total_width_in": round(d.total_width, 4),
        "total_height_in": round(d.total_height, 4),
        "total_width_px": d.total_width_px,
        "total_height_px": d.total_height_px,
        "bleed_in": 0.125,
        "safe_zone_in": 0.25,
        "dpi": DPI,
    }


def spec_sheet_text(d: CoverDimensions, title: str) -> str:
    return f"""SCRPT COVER SPECIFICATION — {title}
================================================================
One single wrap file: BACK COVER + SPINE + FRONT COVER, left to right.

FULL FILE SIZE (includes 0.125" bleed on all four outer edges)
  {d.total_width:.3f} x {d.total_height:.3f} inches
  {d.total_width_px} x {d.total_height_px} pixels at 300 DPI

PANELS (from the left edge of the file)
  Back cover:  {d.back_cover_start_px}px to {d.back_cover_end_px}px
  Spine:       {d.spine_start_px}px to {d.spine_end_px}px  (width {d.spine_width:.4f}" / {d.spine_width_px}px)
  Front cover: {d.front_cover_start_px}px to {d.front_cover_end_px}px

RULES
  - Interior page count: {d.page_count} pages on {d.paper_type} paper.
    The spine width above is computed from this page count. If the page
    count changes, request an updated spec.
  - Spine text: {"allowed (keep 0.0625in clearance from both spine folds)" if d.spine_has_text else "NOT allowed (book is under 79 pages)"}
  - Keep all text and logos at least 0.25" inside the trim edges.
  - Leave the barcode zone empty: 2.0 x 1.2 inches, positioned
    {d.barcode_x_px}px, {d.barcode_y_px}px (top-left, from file top-left).
    Amazon prints its barcode there.
  - Flatten all layers. Embed all fonts. 300 DPI. sRGB or CMYK.
  - Deliver as PDF (preferred) or PNG/TIFF at exactly the pixel size above.
  - No crop marks, no printer marks, no template guides in the final file.
================================================================
"""


def generate_template_pdf(page_count: int, trim_size: str, paper_type: str,
                          out_path: str) -> str:
    """Draw a KDP-style cover template with guide lines at print size."""
    d = calculate_cover(page_count, trim_size, paper_type)
    W, H = d.total_width * 72, d.total_height * 72
    c = rl_canvas.Canvas(out_path, pagesize=(W, H))

    px = 72.0 / DPI  # convert px zone values to points

    def vline(x_px, color, dash=None, label=""):
        c.saveState()
        c.setStrokeColor(color)
        c.setLineWidth(0.75)
        if dash:
            c.setDash(dash, dash)
        x = x_px * px
        c.line(x, 0, x, H)
        if label:
            c.setFillColor(color)
            c.setFont("Helvetica", 7)
            c.saveState()
            c.translate(x + 4, H / 2)
            c.rotate(90)
            c.drawString(0, 0, label)
            c.restoreState()
        c.restoreState()

    bleed_pt = 0.125 * 72
    safe_pt = 0.25 * 72

    # bleed frame (red) — final trim happens here
    c.setStrokeColor(Color(0.85, 0.1, 0.1))
    c.setLineWidth(0.75)
    c.rect(bleed_pt, bleed_pt, W - 2 * bleed_pt, H - 2 * bleed_pt)

    # spine folds (blue)
    blue = Color(0.1, 0.3, 0.9)
    vline(d.spine_start_px, blue, label="SPINE FOLD")
    vline(d.spine_end_px, blue, label="SPINE FOLD")

    # safe zones (green dashed): inside trim on both panels
    green = Color(0.1, 0.6, 0.2)
    c.setStrokeColor(green)
    c.setDash(3, 3)
    c.setLineWidth(0.6)
    # back panel safe rect
    c.rect(bleed_pt + safe_pt, bleed_pt + safe_pt,
           d.trim_width * 72 - 2 * safe_pt, d.trim_height * 72 - 2 * safe_pt)
    # front panel safe rect
    front_x = d.front_cover_start_px * px
    c.rect(front_x + safe_pt, bleed_pt + safe_pt,
           d.trim_width * 72 - 2 * safe_pt, d.trim_height * 72 - 2 * safe_pt)
    c.setDash()

    # barcode zone (orange) — PDF y-axis is bottom-up
    orange = Color(0.95, 0.55, 0.1)
    bx = d.barcode_x_px * px
    by_top = d.barcode_y_px * px
    bh = 1.2 * 72
    bw = 2.0 * 72
    by = H - by_top - bh
    c.setStrokeColor(orange)
    c.setLineWidth(1)
    c.rect(bx, by, bw, bh)
    c.setFillColor(orange)
    c.setFont("Helvetica", 8)
    c.drawCentredString(bx + bw / 2, by + bh / 2 - 3, "BARCODE ZONE — LEAVE EMPTY")

    # header note
    c.setFillColor(Color(0.4, 0.4, 0.4))
    c.setFont("Helvetica", 8)
    c.drawString(bleed_pt + 6, H - bleed_pt - 12,
                 f"SCRPT template — {trim_size} / {paper_type} / {page_count} pages "
                 f"— spine {d.spine_width:.4f}\" — red=trim, blue=spine folds, "
                 f"green=safe zone, orange=barcode. Delete all guides before delivery.")
    c.showPage()
    c.save()
    return out_path


def validate_uploaded_cover(file_bytes: bytes, filename: str, page_count: int,
                            trim_size: str, paper_type: str) -> dict:
    """Check a delivered cover file against the computed spec."""
    d = calculate_cover(page_count, trim_size, paper_type)
    checks = []
    ok_all = True

    def check(name, ok, detail):
        nonlocal ok_all
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        ok_all = ok_all and bool(ok)

    name = filename.lower()
    if name.endswith(".pdf"):
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        check("single_page", doc.page_count == 1, f"{doc.page_count} page(s)")
        page = doc[0]
        w_in, h_in = page.rect.width / 72, page.rect.height / 72
        doc.close()
    elif name.endswith((".png", ".tif", ".tiff", ".jpg", ".jpeg")):
        from PIL import Image
        img = Image.open(io.BytesIO(file_bytes))
        w_in, h_in = img.width / DPI, img.height / DPI
        dpi = img.info.get("dpi", (DPI, DPI))
        check("resolution", round(dpi[0]) >= 300 or img.width >= d.total_width_px - 20,
              f"{img.width}x{img.height}px (need {d.total_width_px}x{d.total_height_px}px at 300 DPI)")
    else:
        return {"passed": False, "checks": [
            {"name": "format", "ok": False,
             "detail": f"Unsupported file type: {filename}. Use PDF, PNG or TIFF."}]}

    check("width", abs(w_in - d.total_width) <= TOLERANCE_IN,
          f"{w_in:.3f}in vs expected {d.total_width:.3f}in (spine {d.spine_width:.4f}in)")
    check("height", abs(h_in - d.total_height) <= TOLERANCE_IN,
          f"{h_in:.3f}in vs expected {d.total_height:.3f}in")

    return {"passed": ok_all, "checks": checks,
            "expected": cover_spec_dict(page_count, trim_size, paper_type)}


def write_designer_package(catalog: str, title: str, page_count: int,
                           trim_size: str, paper_type: str) -> dict:
    out_dir = Path(OUTPUT_DIR) / catalog / "designer_package"
    out_dir.mkdir(parents=True, exist_ok=True)
    d = calculate_cover(page_count, trim_size, paper_type)
    spec_path = out_dir / "COVER_SPEC.txt"
    spec_path.write_text(spec_sheet_text(d, title))
    template_path = out_dir / "cover_template.pdf"
    generate_template_pdf(page_count, trim_size, paper_type, str(template_path))
    return {"spec_sheet": str(spec_path), "template_pdf": str(template_path),
            "spec": cover_spec_dict(page_count, trim_size, paper_type)}


# ── the full wrap composer ───────────────────────────────────────
# Delivers the actual KDP print file: back cover + spine + front cover in one
# PDF at exact wrap dimensions with 0.125" bleed. The front panel is the
# book's cover art; back and spine are composed from a palette sampled from
# that art, with the blurb set in crisp vector type (never rasterized text).

def _sample_palette(art_png: bytes, white_house_style: bool = True) -> dict:
    """Colours for the back and spine.

    HOUSE STANDARD: a white ground with dark text. Not only for consistency —
    on print-on-demand, large solid dark areas band and scuff, and the spine
    fold cracks white. White prints reliably, reads best, and lets the
    mandatory barcode box disappear instead of punching a hole in the design.

    The ACCENT (frame, tagline, imprint rules) is still sampled from the front
    so each book's wrap belongs to its own cover.
    """
    from PIL import Image
    im = Image.open(io.BytesIO(art_png)).convert("RGB")
    whole = list(im.resize((48, 64)).getdata())

    def avg(rows):
        n = len(rows) or 1
        return (sum(p[0] for p in rows) // n, sum(p[1] for p in rows) // n,
                sum(p[2] for p in rows) // n)

    # accent: the most saturated mid-tone on the cover, deepened for print
    def sat(p):
        return max(p) - min(p)
    vivid = sorted(whole, key=sat, reverse=True)[: max(6, len(whole) // 12)]
    ar, ag, ab = avg(vivid)
    accent = (max(60, int(ar * 0.78)), max(50, int(ag * 0.78)), max(40, int(ab * 0.78)))
    if sat(accent) < 18:                       # near-greyscale cover
        accent = (150, 122, 66)                # fall back to antique gold

    if not white_house_style:
        whole.sort(key=lambda p: p[0] + p[1] + p[2])
        lum = sum(0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in whole) / len(whole)
        if lum < 115:
            dr, dg, db = avg(whole[: len(whole) // 3])
            return {"cream": (max(14, int(dr * .55)), max(12, int(dg * .55)),
                              max(12, int(db * .55))),
                    "ink": (232, 226, 214), "gold": accent, "dark": True}

    return {"cream": (255, 255, 255), "ink": (26, 24, 22), "gold": accent,
            "dark": False}


def _wrap_text(text: str, font, size, max_width, canv, min_last: int = 5):
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = (line + " " + w).strip()
        if canv.stringWidth(trial, font, size) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    # THE ORPHAN RULE (Lars, 2026-08-29): a paragraph must never end on a
    # line of one to four words — it reads as a design mistake. Words are
    # pulled down from the line above until the last line carries at least
    # `min_last`, without starving the line above or overflowing the column.
    if len(lines) >= 2:
        while len(lines[-1].split()) < min_last:
            prev = lines[-2].split()
            if len(prev) <= min_last:
                break
            cand = prev[-1] + " " + lines[-1]
            if canv.stringWidth(cand, font, size) > max_width:
                break
            lines[-2] = " ".join(prev[:-1])
            lines[-1] = cand
    return lines


def _tint(logo_rgba, rgb) -> "io.BytesIO":
    """Recolor a transparent logo to a target ink/gold tone, keeping its alpha,
    so the imprint matches the cover palette instead of looking pasted on."""
    from PIL import Image
    a = logo_rgba.split()[-1]
    solid = Image.new("RGBA", logo_rgba.size, (rgb[0], rgb[1], rgb[2], 255))
    solid.putalpha(a)
    buf = io.BytesIO()
    solid.save(buf, format="PNG")
    buf.seek(0)
    return buf


def compose_print_wrap(catalog: str, title: str, author: str, blurb: str,
                       tagline: str, series_line: str, category_line: str,
                       page_count: int, trim_size: str, paper_type: str,
                       genre_preset: str = "", preview_barcode: bool = False,
                       list_price: float = 0.0, isbn: str = "") -> dict:
    """Compose the finished wrap PDF from the installed front cover art."""
    from PIL import Image
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # front source: the highest-fidelity art available — a print master or the
    # publisher's clean original beats an AI-edited derivative every time
    base = Path(OUTPUT_DIR) / catalog
    front_src = next((base / n for n in (
        "cover-art-print.png", "publisher-cover-source.png",
        "cover-art-original.png", "cover-art.png") if (base / n).exists()), None)
    if front_src is None:
        raise ValueError("No front cover art installed for this book")
    art = front_src.read_bytes()

    d = calculate_cover(page_count, trim_size, paper_type)
    pal = _sample_palette(art)
    cream_c = Color(*[v / 255 for v in pal["cream"]])
    ink_c = Color(*[v / 255 for v in pal["ink"]])

    # Type is matched to the FRONT cover so the wrap reads as one design:
    # the family is chosen by looking at the finished artwork (see
    # cover/typography.py) and cached on the book.
    from .typography import DEFAULT_FAMILY, register_family, register_interior
    book_rec = get_book_by_catalog(catalog)
    _cov = (book_rec or {}).get("data", {}).get("cover") or {}
    _fonts = _cov.get("fonts") or {}
    fam = _fonts.get("family") or DEFAULT_FAMILY
    F, FB, FI = register_family(fam)          # display: spine + headings
    tag_fam = _fonts.get("tagline_family") or fam
    TF, TFB, TFI = register_family(tag_fam)   # the front's own tagline face
    _fmt = (book_rec or {}).get("data", {}).get("format") or {}
    BR, BB, BI = register_interior(_fmt.get("font_preset") or "garamond")
    BODY = BR or F                            # body copy = the book's own face
    BODY_I = BI or FI

    # Rules 4 & 8: the frame and tagline take the AUTHOR NAME's colour from the
    # front cover; a white author name would vanish on white, so it goes black.
    _ac = _fonts.get("author_color") or [0, 0, 0]
    accent_rgb = tuple(int(v) for v in _ac[:3])
    gold_c = Color(*[v / 255 for v in accent_rgb])

    # An ornamental frame suits romance and period drama; thrillers want the
    # cleaner, unbordered back their shelf expects. Decided once — the spine
    # scale and the imprint position both depend on it.
    framed = any(k in (genre_preset or "").lower()
                 for k in ("romance", "drama", "historical"))

    W, H = d.total_width * 72, d.total_height * 72
    bleed = 0.125 * 72
    safe = 0.25 * 72
    trim_w = d.trim_width * 72
    spine_w = d.spine_width * 72
    # A previewed barcode is for the publisher's eyes only — Amazon prints its
    # own. It is written to a SEPARATE file so the upload file stays clean.
    out = (Path(OUTPUT_DIR) / catalog /
           ("cover-wrap-preview.pdf" if preview_barcode else "cover-wrap.pdf"))
    c = rl_canvas.Canvas(str(out), pagesize=(W, H))

    # ground: cream across back + spine so the wrap reads as one book with the
    # front; the front panel is painted over this on the right
    c.setFillColor(cream_c)
    c.rect(0, 0, W, H, stroke=0, fill=1)

    # front panel (right third) — art fills panel + bleed, 2x upsampled for print
    im = Image.open(io.BytesIO(art)).convert("RGB")
    im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    front_x = bleed + trim_w + spine_w
    from reportlab.lib.utils import ImageReader
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=95)
    buf.seek(0)
    # cover the full panel incl. outer bleed, preserving aspect by center-crop
    panel_w, panel_h = trim_w + bleed, H
    ar_panel = panel_w / panel_h
    ar_im = im.width / im.height
    if ar_im > ar_panel:
        crop_w = int(im.height * ar_panel)
        x0 = (im.width - crop_w) // 2
        im2 = im.crop((x0, 0, x0 + crop_w, im.height))
    else:
        crop_h = int(im.width / ar_panel)
        y0 = (im.height - crop_h) // 2
        im2 = im.crop((0, y0, im.width, y0 + crop_h))
    buf2 = io.BytesIO()
    im2.save(buf2, format="JPEG", quality=95)
    buf2.seek(0)
    c.drawImage(ImageReader(buf2), front_x, 0, panel_w, panel_h)

    # spine — ONE row: title · author, running top-to-bottom, in a light hand.
    # The publisher imprint logo sits at the foot of the spine with a margin.
    spine_cx = bleed + trim_w + spine_w / 2
    logo_reserve = 0
    logo_path = next((p for p in (base / "spine-logo.png",
                                  Path(OUTPUT_DIR).parent / "assets" / "olive-tree-logo.png")
                      if p.exists()), None)
    if logo_path is not None:
        from reportlab.lib.utils import ImageReader
        from PIL import Image as _Img
        lg = _Img.open(str(logo_path)).convert("RGBA")
        lw = min(spine_w - 14, 18)          # small mark, centered on the spine
        lh = lw * lg.height / lg.width
        # sit the FOOT of the tree on the same horizontal line as the back
        # cover's frame, so the wrap lines up across the fold
        logo_y = bleed + safe * 0.7 + 4.2      # optical nudge (~1.5mm)
        c.drawImage(ImageReader(_tint(lg, pal["ink"])),
                    spine_cx - lw / 2, logo_y, lw, lh, mask="auto")
        logo_reserve = (logo_y - bleed) + lh + 10

    if d.spine_has_text:
        # Author name largest at the HEAD of the spine, title smaller below it,
        # both reading top-to-bottom and centred across the spine width.
        author_u, title_u = author.upper(), title.upper()
        head_gap = bleed + safe + 6
        run = H - head_gap - bleed - logo_reserve - 10     # usable spine length

        # Thrillers shout on the shelf: a bigger author name, with the title
        # pulled back further beneath it. Romance keeps a more refined scale.
        punchy = not framed
        a_size = min(34 if punchy else 24,
                     max(11, spine_w * (0.95 if punchy else 0.70)))
        t_ratio = 0.56 if punchy else 0.66
        gap = 26
        for _ in range(60):
            t_size = a_size * t_ratio
            need = (c.stringWidth(author_u, FB, a_size) + gap
                    + c.stringWidth(title_u, F, t_size))
            if need <= run or a_size <= 8:
                break
            a_size -= 0.5
        t_size = a_size * t_ratio

        c.saveState()
        c.translate(spine_cx, H - head_gap)   # origin at the head of the spine
        c.rotate(-90)                          # +x now runs DOWN the spine
        c.setFillColor(ink_c)
        c.setFont(FB, a_size)
        c._charSpace = 0.9
        c.drawString(0, -a_size * 0.34, author_u)
        x_after = c.stringWidth(author_u, FB, a_size) + gap
        c.setFont(F, t_size)
        c._charSpace = 0.7
        c.drawString(x_after, -t_size * 0.34, title_u)
        c._charSpace = 0
        c.restoreState()

    # ── back panel ────────────────────────────────────────────────
    # a gold double-rule frame with corner flourishes echoes the front's
    # ornamental border, so the two panels read as one designed object
    fx0, fy0 = bleed + safe * 0.7, bleed + safe * 0.7
    fx1, fy1 = bleed + trim_w - safe * 0.7, H - bleed - safe * 0.7
    if framed:
        c.setStrokeColor(gold_c)
        c.setLineWidth(1.4)
        c.rect(fx0, fy0, fx1 - fx0, fy1 - fy0, stroke=1, fill=0)
        c.setLineWidth(0.6)
        c.rect(fx0 + 4, fy0 + 4, fx1 - fx0 - 8, fy1 - fy0 - 8, stroke=1, fill=0)

    def _flourish(cx, cy, sx, sy):
        """A small drawn corner bracket — vector, so it renders in any face."""
        c.saveState()
        c.setStrokeColor(gold_c)
        c.setLineWidth(0.9)
        L, off = 13, 7
        x, y = cx + sx * off, cy + sy * off
        c.line(x, y, x + sx * L, y)
        c.line(x, y, x, y + sy * L)
        c.setFillColor(gold_c)
        c.circle(x + sx * (L + 3.5), y, 1.3, stroke=0, fill=1)
        c.circle(x, y + sy * (L + 3.5), 1.3, stroke=0, fill=1)
        c.restoreState()
    if framed:
        for sx, sy, cx, cy in ((1, 1, fx0, fy0), (-1, 1, fx1, fy0),
                               (1, -1, fx0, fy1), (-1, -1, fx1, fy1)):
            _flourish(cx, cy, sx, sy)

    # generous inset so text never crowds the gold frame
    pad = 26
    bx0, bx1 = bleed + safe + pad, bleed + trim_w - safe - pad
    bw = bx1 - bx0
    y = H - bleed - safe - pad - 24

    # tagline — the accent line, centred in gold italic with a small rule
    if tagline:
        # one SENTENCE per line — never a single orphan word on line two
        import re as _re
        parts = [t.strip() for t in _re.split(r"(?<=[.!?])\s+", tagline) if t.strip()]
        # sans tagline faces read wrong in a forced italic — use the roman
        TAG = TFI if tag_fam in ("Didot", "Bodoni 72", "Big Caslon", "Cochin",
                                 "Hoefler Text", "Iowan Old Style",
                                 "Baskerville", "Superclarendon") else TF
        size = 18.0
        while size > 11 and any(c.stringWidth(t, TAG, size) > bw for t in parts):
            size -= 0.5
        c.setFont(TAG, size)
        c.setFillColor(gold_c)
        for t in parts:
            for ln in _wrap_text(t, TAG, size, bw, c):
                c.drawCentredString((bx0 + bx1) / 2, y, ln)
                y -= size * 1.35
        y -= 12                       # air between tagline and its rule
        c.setStrokeColor(gold_c)
        c.setLineWidth(0.7)
        cxm = (bx0 + bx1) / 2
        c.line(cxm - 34, y - 4, cxm - 9, y - 4)
        c.line(cxm + 9, y - 4, cxm + 34, y - 4)
        c.setFillColor(gold_c)
        pth = c.beginPath()          # small diamond
        pth.moveTo(cxm, y - 0.5); pth.lineTo(cxm + 3.5, y - 4)
        pth.lineTo(cxm, y - 7.5); pth.lineTo(cxm - 3.5, y - 4)
        pth.close()
        c.drawPath(pth, stroke=0, fill=1)
        y -= 40      # generous air before the body copy begins

    # blurb — ink serif, comfortable leading
    # The block runs from just under the tagline down to the imprint/barcode
    # band. Pick the LARGEST size whose lines fill that space — a back cover
    # with a pool of empty white below the copy looks unfinished.
    # Bands reserved from the bottom up, so nothing can ever collide:
    #   barcode clear zone -> series line -> (gap) -> body copy
    barcode_top = bleed + safe + 1.2 * 72 + 10
    series_y = barcode_top + 22
    floor = series_y + 34
    avail = y - floor
    paras = [t.strip() for t in (blurb or "").split("\n") if t.strip()][:14]

    def layout(size, lead_ratio=1.60, gap_ratio=0.80, texts=None):
        lead = size * lead_ratio
        para_gap = size * gap_ratio
        out, total = [], 0.0
        for t in (texts if texts is not None else paras):
            lines = _wrap_text(t, BODY, size, bw, c)
            out.append(lines)
            total += len(lines) * lead + para_gap
        return out, total - para_gap, lead, para_gap

    def best_fit(texts):
        """Largest readable setting that fits the band, or None."""
        for lead_ratio in (1.60, 1.50, 1.42):
            size = 14.0
            while size >= 8.5:
                laid, total, lead, para_gap = layout(size, lead_ratio, texts=texts)
                if total <= avail:
                    return laid, lead, para_gap, size
                size -= 0.25
        return None

    # The back cover must never overflow into the series line or the barcode.
    # If the copy cannot fit even at the smallest readable setting, drop MIDDLE
    # paragraphs — the opening and the closing hook are the two that sell the
    # book, so they are kept to the last.
    working = list(paras)
    chosen = best_fit(working)
    dropped = 0
    while chosen is None and len(working) > 2:
        working.pop(len(working) // 2)
        dropped += 1
        chosen = best_fit(working)
    if chosen is None:
        chosen = layout(8.5, 1.42, texts=working)
        chosen = (chosen[0], chosen[2], chosen[3], 8.5)
    laid, lead, para_gap, size = chosen
    if dropped:
        print(f"  cover copy trimmed: {dropped} middle paragraph(s) dropped "
              f"to fit {catalog}'s back cover")

    c.setFillColor(ink_c)
    c.setFont(BODY, size)
    mid_x = (bx0 + bx1) / 2
    for lines in laid:
        for ln in lines:
            if y < floor:          # structural guard — never cross the band
                break
            c.drawCentredString(mid_x, y, ln)
            y -= lead
        y -= para_gap
        if y < floor:
            break

    # footer — series + category, gold small caps above the barcode zone
    if series_line:
        c.setFont(FB, 10)
        c.setFillColor(gold_c)
        c._charSpace = 1.3
        c.drawCentredString((bx0 + bx1) / 2, series_y, series_line.upper())
        c._charSpace = 0
    # (no descriptive category line — the cover says what the book is)

    # KDP barcode zone: white box (required), with a thin gold keyline so it
    # sits deliberately rather than looking like a hole
    bcw, bch = 2 * 72, 1.2 * 72
    bcx, bcy = bleed + trim_w - safe - bcw, bleed + safe
    c.setFillColor(Color(1, 1, 1))
    c.rect(bcx, bcy, bcw, bch, stroke=0, fill=1)
    if preview_barcode:
        # A faithful proof of what KDP prints: EAN-13 from the ISBN plus the
        # EAN-5 price add-on, together inside the reserved 2" x 1.2" zone.
        # Amazon generates the real one — this is for judging the object only.
        from reportlab.graphics.barcode import eanbc
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF

        code = "".join(ch for ch in (isbn or "") if ch.isdigit())
        if len(code) != 13:
            code = "9798000000000"        # placeholder in KDP's own 979-8 range
        if list_price and 0 < list_price < 100:
            addon = f"5{int(round(list_price * 100)):04d}"   # 5 = USD
        else:
            addon = "90000"                                   # no fixed price
        try:
            main = eanbc.Ean13BarcodeWidget(code)
            side = eanbc.Ean5BarcodeWidget(addon)
            mx0, my0, mx1, my1 = main.getBounds()
            sx0, sy0, sx1, sy1 = side.getBounds()
            gap = 6.0
            grp_w = (mx1 - mx0) + gap + (sx1 - sx0)
            grp_h = max(my1 - my0, sy1 - sy0)
            k = min((bcw - 20) / grp_w, (bch - 24) / grp_h)
            dr = Drawing(grp_w, grp_h)
            dr.add(main)
            side.x = (mx1 - mx0) + gap
            dr.add(side)
            c.saveState()
            c.translate(bcx + (bcw - grp_w * k) / 2,
                        bcy + (bch - grp_h * k) / 2 + 4)
            c.scale(k, k)
            renderPDF.draw(dr, c, 0, 0)
            c.restoreState()
            c.setFillColor(Color(0, 0, 0))
            c.setFont("Helvetica", 4.6)
            c.drawCentredString(bcx + bcw / 2, bcy + 2.5,
                                "PREVIEW ONLY - Amazon prints the real barcode")
        except Exception as e:      # never fail a wrap over a proof barcode
            c.setFillColor(Color(0.45, 0.45, 0.45))
            c.setFont("Helvetica", 5)
            c.drawCentredString(bcx + bcw / 2, bcy + bch / 2,
                                f"barcode preview unavailable: {str(e)[:40]}")
    if pal.get("dark"):          # only outline it when the ground is dark
        c.setStrokeColor(gold_c)
        c.setLineWidth(0.5)
        c.rect(bcx, bcy, bcw, bch, stroke=1, fill=0)

    # publisher imprint — logo + wordmark, bottom-left of the back panel
    if logo_path is not None:
        from reportlab.lib.utils import ImageReader
        from PIL import Image as _Img
        lg = _Img.open(str(logo_path)).convert("RGBA")
        # A fixed imprint lockup: identical on every book — black mark, clean
        # sans wordmark, no country line.
        isz = 24
        # Framed books tuck the imprint inside the frame; unframed thrillers
        # drop it to the barcode's bottom margin, level with the spine tree.
        ix = bleed + safe + (pad if framed else 0)
        iy = (bleed + safe + pad) if framed else (bleed + safe)
        c.drawImage(ImageReader(_tint(lg, (26, 24, 22))), ix, iy, isz, isz,
                    mask="auto")
        try:
            from reportlab.pdfbase import pdfmetrics as _pm
            from reportlab.pdfbase.ttfonts import TTFont as _TT
            _pm.registerFont(_TT("Imprint-Sans",
                                 "/System/Library/Fonts/Supplemental/Futura.ttc",
                                 subfontIndex=0))
            imprint_font = "Imprint-Sans"
        except Exception:
            imprint_font = "Helvetica"
        c.setFillColor(Color(26 / 255, 24 / 255, 22 / 255))
        c.setFont(imprint_font, 7.5)
        c._charSpace = 1.2
        # baseline sits on the foot of the tree, not its middle
        c.drawString(ix + isz + 8, iy + 1, "OLIVE TREE SCRIPTS")
        c._charSpace = 0

    c.showPage()
    c.save()
    report = validate_uploaded_cover(out.read_bytes(), "cover-wrap.pdf",
                                     page_count, trim_size, paper_type)
    return {"path": str(out), "spec": cover_spec_dict(page_count, trim_size, paper_type),
            "validation": report}
