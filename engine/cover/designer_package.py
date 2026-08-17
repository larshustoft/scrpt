"""
Designer package + external cover validation.

When a human designer makes the cover, SCRPT hands them exactly what KDP's
Cover Calculator would: a plain-language spec sheet and a print-size template
PDF with trim/fold/safe/barcode guides. When the file comes back, we validate
it against the computed spec before it can be marked final.
"""

import io
from pathlib import Path

from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas as rl_canvas

from ..config import OUTPUT_DIR
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
