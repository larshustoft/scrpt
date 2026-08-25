"""
Interior PDF export.

Renders the frontend's /print/<catalog> route in headless Chromium and prints
it to a vector PDF at exact trim size. The /print route runs the SAME
pagination engine as the Formatting Studio preview, so the PDF is pixel-true
to what the user saw.

The print page contract:
  - window.__PAGINATION_DONE__ === true when layout is final
  - window.__PAGE_SPEC__ = {
      widthIn, heightIn, pageCount,
      gutterIn, outsideIn, bodyFontPt, trimKey, paperType
    }
"""

from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

from ..config import FRONTEND_URL, OUTPUT_DIR
from ..database import get_book_by_catalog, update_book
from .validator import validate_interior_pdf


async def export_interior(catalog: str, base_url: str = "") -> dict:
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError(f"Book {catalog} not found")

    base = (base_url or FRONTEND_URL).rstrip("/")
    out_dir = Path(OUTPUT_DIR) / catalog
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "interior.pdf"

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{base}/print/{catalog}", wait_until="networkidle",
                            timeout=60000)
            await page.wait_for_function("window.__PAGINATION_DONE__ === true",
                                         timeout=120000)
            spec = await page.evaluate("window.__PAGE_SPEC__")
            if not spec:
                raise RuntimeError("Print page did not expose __PAGE_SPEC__")

            await page.emulate_media(media="print")
            await page.pdf(
                path=str(pdf_path),
                width=f"{spec['widthIn']}in",
                height=f"{spec['heightIn']}in",
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                print_background=True,
                prefer_css_page_size=False,
            )
        finally:
            await browser.close()

    # a printed book always has an even page count: when the layout ends
    # on an odd page, append one blank page (the last verso) ourselves
    _pad_even(str(pdf_path))

    validation = validate_interior_pdf(
        str(pdf_path),
        trim_w=spec["widthIn"],
        trim_h=spec["heightIn"],
        paper_type=spec.get("paperType", "cream_bw"),
        trim_key=spec.get("trimKey", ""),
        gutter_used=spec.get("gutterIn", 0),
        outside_margin_used=spec.get("outsideIn", 0),
        body_font_pt=spec.get("bodyFontPt", 11),
        bleed=False,
    )

    # persist interior state on the book
    data = dict(book["data"])
    interior = data.get("interior", {})
    interior.update({
        "page_count": validation and _pdf_pages(str(pdf_path)),
        "pdf_path": str(pdf_path),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "validation": validation,
    })
    data["interior"] = interior

    # flag the cover stale if it was built for a different page count
    cover = data.get("cover") or {}
    if cover.get("spec_page_count") and cover["spec_page_count"] != interior["page_count"]:
        cover["status"] = "stale"
        data["cover"] = cover

    update_book(book["id"], data)
    return {"pdf_path": str(pdf_path), "page_count": interior["page_count"],
            "validation": validation}


def _pad_even(path: str) -> int:
    import fitz
    doc = fitz.open(path)
    try:
        if doc.page_count % 2 == 1:
            last = doc[-1]
            doc.new_page(width=last.rect.width, height=last.rect.height)
            doc.save(path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        return doc.page_count
    finally:
        doc.close()


def _pdf_pages(path: str) -> int:
    import fitz
    doc = fitz.open(path)
    try:
        return doc.page_count
    finally:
        doc.close()
