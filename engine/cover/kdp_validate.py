"""
Ground-truth validation of our cover maths against Amazon's own template.

Secondary sources disagree about whether KDP adds a cover allowance to the
spine, and about the colour-paper multipliers. Rather than trust any of them,
this drives KDP's official Cover Template Generator, downloads the template
Amazon produces for a given trim/paper/page-count, measures it, and compares
it with engine/cover/dimensions.py. If we are wrong, this says so in inches.
"""

import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

from ..market.browser import Page
from .dimensions import calculate_cover

GEN_URL = "https://kdp.amazon.com/en_US/cover-templates"

TRIM_VALUES = {"5.5x8.5": "5_5X8_5IN", "6x9": "6X9IN"}
PAPER_VALUES = {"white_bw": "WHITE", "cream_bw": "CREAM",
                "standard_color": "COLOR", "premium_color": "COLOR",
                "groundwood": "GROUNDWOOD"}
INTERIOR_VALUES = {"white_bw": "BLACK_AND_WHITE", "cream_bw": "BLACK_AND_WHITE",
                   "groundwood": "BLACK_AND_WHITE",
                   "standard_color": "STANDARD_COLOR",
                   "premium_color": "PREMIUM_COLOR"}


async def fetch_kdp_template(trim: str, paper: str, pages: int,
                             out_dir: Optional[str] = None) -> dict:
    """Download Amazon's own template and measure its real dimensions."""
    trim_v = TRIM_VALUES.get(trim)
    if not trim_v:
        return {"ok": False, "error": f"trim {trim} not offered in the picker"}

    async with Page() as page:
        await page.goto(GEN_URL, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3500)

        async def pick(sel_id: str, value: str):
            await page.select_option(f"#{sel_id}", value)
            await page.wait_for_timeout(600)

        # The form enables one field at a time, in order — binding first.
        try:
            await pick("binding-type-dropdown", "PAPERBACK")
            await pick("cover-type-dropdown", "MATTE")
            await pick("interior-type-dropdown",
                       INTERIOR_VALUES.get(paper, "BLACK_AND_WHITE"))
            await pick("paper-type-dropdown", PAPER_VALUES.get(paper, "WHITE"))
            await pick("reading-direction-dropdown", "LEFT_TO_RIGHT")
            await pick("measurement-units-dropdown", "INCHES")
            await pick("trim-size-dropdown", trim_v)
            await page.fill("#page-count-input", str(pages))
            await page.wait_for_timeout(800)
        except Exception as e:
            return {"ok": False, "error": f"form fill failed: {e}"[:220]}

        try:
            async with page.expect_download(timeout=60000) as dl:
                await page.click("input[type=submit]")
            download = await dl.value
            buf = Path(out_dir or "/tmp") / (download.suggested_filename or "kdp.zip")
            await download.save_as(str(buf))
        except Exception as e:
            return {"ok": False, "error": f"no template download: {e}"[:200]}

    # the template arrives as a zip of PDF + PNG; measure the PDF
    measured = {}
    try:
        with zipfile.ZipFile(buf) as z:
            names = z.namelist()
            pdf_name = next((n for n in names if n.lower().endswith(".pdf")), None)
            measured["files"] = names[:6]
            if pdf_name:
                import fitz
                doc = fitz.open(stream=z.read(pdf_name), filetype="pdf")
                r = doc[0].rect
                measured["width_in"] = round(r.width / 72, 4)
                measured["height_in"] = round(r.height / 72, 4)
                doc.close()
            # KDP names the file with its own computed dimensions
            for n in names:
                m = re.search(r"(\d+\.?\d*)\s*x\s*(\d+\.?\d*)", n)
                if m:
                    measured["from_filename"] = f"{m.group(1)} x {m.group(2)}"
                    break
    except Exception as e:
        return {"ok": False, "error": f"could not read template: {e}"[:200],
                "saved": str(buf)}

    ours = calculate_cover(pages, trim, paper)
    delta_w = round(measured.get("width_in", 0) - ours.total_width, 4)
    delta_h = round(measured.get("height_in", 0) - ours.total_height, 4)
    return {
        "ok": True,
        "inputs": {"trim": trim, "paper": paper, "pages": pages},
        "kdp": measured,
        "scrpt": {"width_in": round(ours.total_width, 4),
                  "height_in": round(ours.total_height, 4),
                  "spine_in": round(ours.spine_width, 4)},
        "delta_width_in": delta_w,
        "delta_height_in": delta_h,
        "match": abs(delta_w) <= 0.02 and abs(delta_h) <= 0.02,
        "saved": str(buf),
    }
