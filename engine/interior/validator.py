"""
KDP interior validation.
Numbers verified against official KDP help pages (docs/KDP_INTERIOR_SPEC.md).
"""

from dataclasses import dataclass, field

# gutter minimum by total page count: (max_pages_inclusive, gutter_inches)
GUTTER_TABLE = [
    (150, 0.375),
    (300, 0.500),
    (500, 0.625),
    (700, 0.750),
    (828, 0.875),
]

OUTSIDE_MARGIN_MIN_NO_BLEED = 0.25
OUTSIDE_MARGIN_MIN_BLEED = 0.375

# paperback page-count limits per paper type
PAPER_LIMITS = {
    "white_bw": (24, 828),
    "cream_bw": (24, 776),
    "standard_color": (72, 600),
    "premium_color": (24, 828),
}

# trims whose max B&W page count is lower than 828
TRIM_MAX_OVERRIDES = {
    "8.25x6": 800,
    "8.25x8.25": 800,
    "8.5x8.5": 590,
    "8.5x11": 590,
}

MIN_FONT_PT = 7.0
PT_PER_IN = 72.0


def min_gutter(page_count: int) -> float:
    for max_pages, gutter in GUTTER_TABLE:
        if page_count <= max_pages:
            return gutter
    return GUTTER_TABLE[-1][1]


@dataclass
class ValidationReport:
    passed: bool = True
    checks: list[dict] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str):
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            self.passed = False

    def as_dict(self) -> dict:
        return {"passed": self.passed, "checks": self.checks}


def validate_interior_pdf(
    pdf_path: str,
    trim_w: float,
    trim_h: float,
    paper_type: str,
    trim_key: str,
    gutter_used: float,
    outside_margin_used: float,
    body_font_pt: float,
    bleed: bool = False,
) -> dict:
    """Open the exported PDF and verify it against KDP submission rules."""
    import fitz  # PyMuPDF

    report = ValidationReport()
    doc = fitz.open(pdf_path)
    n = doc.page_count

    # 1. page size: every page must be exactly trim (or trim+bleed allowance)
    exp_w = (trim_w + 0.125 if bleed else trim_w) * PT_PER_IN
    exp_h = (trim_h + 0.25 if bleed else trim_h) * PT_PER_IN
    bad_pages = [
        i + 1 for i, page in enumerate(doc)
        if abs(page.rect.width - exp_w) > 0.75 or abs(page.rect.height - exp_h) > 0.75
    ]
    report.check(
        "page_size",
        not bad_pages,
        f"expected {exp_w/72:.3f}x{exp_h/72:.3f}in"
        + (f"; wrong pages: {bad_pages[:5]}" if bad_pages else " — all pages exact"),
    )

    # 2. page count within limits
    lo, hi = PAPER_LIMITS.get(paper_type, (24, 828))
    hi = min(hi, TRIM_MAX_OVERRIDES.get(trim_key, hi))
    report.check("page_count", lo <= n <= hi, f"{n} pages (allowed {lo}-{hi} for {paper_type} at {trim_key})")

    # 3. even page count (KDP pads anyway; we control it ourselves)
    report.check("even_pages", n % 2 == 0, f"{n} pages")

    # 4. gutter for this page count
    need = min_gutter(n)
    report.check(
        "gutter",
        gutter_used >= need - 1e-6,
        f"gutter {gutter_used:.3f}in vs required {need:.3f}in at {n} pages",
    )

    # 5. outside margins
    need_outside = OUTSIDE_MARGIN_MIN_BLEED if bleed else OUTSIDE_MARGIN_MIN_NO_BLEED
    report.check(
        "outside_margin",
        outside_margin_used >= need_outside - 1e-6,
        f"outside {outside_margin_used:.3f}in vs required {need_outside:.3f}in",
    )

    # 6. minimum font size
    report.check("font_size", body_font_pt >= MIN_FONT_PT, f"body {body_font_pt}pt (min {MIN_FONT_PT}pt)")

    # 7. fonts embedded (Chromium subsets+embeds; verify none are unembedded)
    unembedded = set()
    for i in range(n):
        for f in doc.get_page_fonts(i, full=True):
            # fitz font tuple: (xref, ext, type, basefont, name, encoding, referencer)
            xref, ftype, basefont = f[0], f[2], f[3]
            if ftype == "Type3":
                # Type3 glyphs are inline PDF drawing ops — embedded by construction
                continue
            if xref and not doc.extract_font(xref)[3]:
                unembedded.add(basefont or ftype)
    report.check(
        "fonts_embedded",
        not unembedded,
        "all fonts embedded" if not unembedded else f"NOT embedded: {sorted(unembedded)[:5]}",
    )

    doc.close()
    return report.as_dict()
