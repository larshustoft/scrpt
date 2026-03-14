"""
SCRPT Cover Dimension Engine
=============================
Replicates Amazon KDP's cover calculator exactly.
Given page count, trim size, paper type, and binding → outputs exact cover dimensions.

Every measurement is in inches, then converted to pixels at 300 DPI for rendering.
"""

from dataclasses import dataclass
from typing import Literal

# ── Paper thickness per page (inches) ─────────────────────────
PAPER_THICKNESS = {
    "white_bw":       0.002252,   # White paper, black & white ink
    "cream_bw":       0.002500,   # Cream paper, black & white ink
    "standard_color": 0.002347,   # White paper, standard color ink
    "premium_color":  0.002602,   # White paper, premium color ink
}

# ── Common trim sizes (width × height in inches) ─────────────
TRIM_SIZES = {
    "5x8":       (5.0,    8.0),
    "5.25x8":    (5.25,   8.0),
    "5.5x8.5":   (5.5,    8.5),
    "6x9":       (6.0,    9.0),
    "6.14x9.21": (6.14,   9.21),
    "6.69x9.61": (6.69,   9.61),
    "7x10":      (7.0,   10.0),
    "7.44x9.69": (7.44,   9.69),
    "7.5x9.25":  (7.5,    9.25),
    "8x10":      (8.0,   10.0),
    "8.5x8.5":   (8.5,    8.5),    # Square — popular for coloring books
    "8.5x11":    (8.5,   11.0),    # US Letter — popular for workbooks
}

# ── Minimum gutter margins by page count ──────────────────────
GUTTER_MARGINS = [
    (150,  0.375),   # 24-150 pages
    (300,  0.500),   # 151-300 pages
    (500,  0.625),   # 301-500 pages
    (700,  0.750),   # 501-700 pages
    (828,  0.875),   # 701-828 pages
]

# ── Constants ─────────────────────────────────────────────────
BLEED = 0.125           # inches on each side
SAFE_ZONE = 0.25        # keep text/art this far from trim edges
BARCODE_WIDTH = 2.0     # inches
BARCODE_HEIGHT = 1.2    # inches
BARCODE_BOTTOM_MARGIN = 0.76  # inches — KDP min distance from bottom trim edge
MIN_SPINE_FOR_TEXT = 79 # pages — KDP only prints spine text if 79+ pages
DPI = 300               # print resolution


@dataclass
class CoverDimensions:
    """Complete cover specification for one book."""
    # Input parameters
    page_count: int
    trim_size: str
    paper_type: str

    # Trim dimensions (single page)
    trim_width: float       # inches
    trim_height: float      # inches

    # Calculated spine
    spine_width: float      # inches
    spine_has_text: bool    # True if 79+ pages

    # Full cover dimensions (back + spine + front + bleed)
    total_width: float      # inches
    total_height: float     # inches

    # Pixel dimensions at 300 DPI
    total_width_px: int
    total_height_px: int
    spine_width_px: int
    trim_width_px: int
    trim_height_px: int
    bleed_px: int

    # Interior margins
    gutter_margin: float    # inches (inside margin)
    outside_margin: float   # inches (top, bottom, outside)

    # Zones (pixel positions from left edge)
    back_cover_start_px: int
    back_cover_end_px: int
    spine_start_px: int
    spine_end_px: int
    front_cover_start_px: int
    front_cover_end_px: int
    barcode_x_px: int       # barcode top-left X
    barcode_y_px: int       # barcode top-left Y
    safe_zone_px: int

    def summary(self) -> str:
        """Human-readable summary of all dimensions."""
        lines = [
            f"{'='*60}",
            f"  SCRPT COVER DIMENSIONS",
            f"{'='*60}",
            f"",
            f"  Book: {self.page_count} pages on {self.paper_type} paper",
            f"  Trim: {self.trim_size} ({self.trim_width}\" x {self.trim_height}\")",
            f"",
            f"  SPINE",
            f"  -----",
            f"  Spine width:     {self.spine_width:.4f}\" ({self.spine_width_px}px)",
            f"  Spine text:      {'Yes' if self.spine_has_text else 'No (< 79 pages)'}",
            f"",
            f"  FULL COVER (back + spine + front + bleed)",
            f"  -----------------------------------------",
            f"  Total width:     {self.total_width:.4f}\" ({self.total_width_px}px)",
            f"  Total height:    {self.total_height:.4f}\" ({self.total_height_px}px)",
            f"  Bleed:           {BLEED}\" ({self.bleed_px}px) on each side",
            f"  Safe zone:       {SAFE_ZONE}\" ({self.safe_zone_px}px) from trim",
            f"",
            f"  LAYOUT ZONES (pixel positions from left)",
            f"  -----------------------------------------",
            f"  Back cover:      {self.back_cover_start_px}px - {self.back_cover_end_px}px",
            f"  Spine:           {self.spine_start_px}px - {self.spine_end_px}px",
            f"  Front cover:     {self.front_cover_start_px}px - {self.front_cover_end_px}px",
            f"",
            f"  BARCODE ZONE (back cover, lower right)",
            f"  ---------------------------------------",
            f"  Position:        ({self.barcode_x_px}px, {self.barcode_y_px}px)",
            f"  Size:            {int(BARCODE_WIDTH * DPI)}px x {int(BARCODE_HEIGHT * DPI)}px",
            f"",
            f"  INTERIOR MARGINS",
            f"  ----------------",
            f"  Gutter (inside): {self.gutter_margin}\"",
            f"  Outside margins: {self.outside_margin}\"",
            f"{'='*60}",
        ]
        return "\n".join(lines)


def calculate_cover(
    page_count: int,
    trim_size: str = "8.5x11",
    paper_type: str = "white_bw",
) -> CoverDimensions:
    """
    Calculate exact cover dimensions for a KDP book.

    Args:
        page_count: Number of interior pages (must be even, 24-828)
        trim_size:  One of TRIM_SIZES keys (e.g., "6x9", "8.5x11", "8.5x8.5")
        paper_type: One of PAPER_THICKNESS keys

    Returns:
        CoverDimensions with all measurements in inches and pixels
    """
    # ── Validate inputs ───────────────────────────────────────
    if trim_size not in TRIM_SIZES:
        raise ValueError(f"Unknown trim size: {trim_size}. Options: {list(TRIM_SIZES.keys())}")
    if paper_type not in PAPER_THICKNESS:
        raise ValueError(f"Unknown paper type: {paper_type}. Options: {list(PAPER_THICKNESS.keys())}")
    if page_count < 24:
        raise ValueError(f"Minimum page count is 24. Got: {page_count}")
    if page_count > 828:
        raise ValueError(f"Maximum page count is 828. Got: {page_count}")
    if page_count % 2 != 0:
        raise ValueError(f"Page count must be even. Got: {page_count}")

    # ── Get base measurements ─────────────────────────────────
    trim_w, trim_h = TRIM_SIZES[trim_size]
    thickness = PAPER_THICKNESS[paper_type]

    # ── Calculate spine width ─────────────────────────────────
    spine = page_count * thickness
    spine_has_text = page_count >= MIN_SPINE_FOR_TEXT

    # ── Calculate full cover dimensions ───────────────────────
    total_w = BLEED + trim_w + spine + trim_w + BLEED
    total_h = BLEED + trim_h + BLEED

    # ── Convert to pixels at 300 DPI ──────────────────────────
    total_w_px  = round(total_w * DPI)
    total_h_px  = round(total_h * DPI)
    spine_px    = round(spine * DPI)
    trim_w_px   = round(trim_w * DPI)
    trim_h_px   = round(trim_h * DPI)
    bleed_px    = round(BLEED * DPI)
    safe_px     = round(SAFE_ZONE * DPI)

    # ── Calculate layout zones ────────────────────────────────
    back_start  = 0
    back_end    = bleed_px + trim_w_px              # bleed + back cover width
    spine_start = back_end
    spine_end   = spine_start + spine_px
    front_start = spine_end
    front_end   = total_w_px                        # front cover + bleed

    # ── Barcode zone (lower-right of back cover WHEN VIEWED) ────
    # In full-spread coords, the "right side when viewed from back" = LEFT side of back panel
    # (away from spine). KDP requires ≥0.76" from bottom, ≥0.25" from outer edges.
    barcode_w_px = round(BARCODE_WIDTH * DPI)
    barcode_h_px = round(BARCODE_HEIGHT * DPI)
    barcode_bottom_px = round(BARCODE_BOTTOM_MARGIN * DPI)
    barcode_x = bleed_px + safe_px                                  # outer edge of back cover (right when viewed)
    barcode_y = total_h_px - bleed_px - barcode_h_px - barcode_bottom_px  # 0.76" above bottom trim

    # ── Gutter margin ─────────────────────────────────────────
    gutter = 0.375  # default
    for max_pages, margin in GUTTER_MARGINS:
        if page_count <= max_pages:
            gutter = margin
            break

    # Outside margin depends on bleed setting
    outside_margin = 0.375 if True else 0.25  # with bleed: 0.375", without: 0.25"

    return CoverDimensions(
        page_count=page_count,
        trim_size=trim_size,
        paper_type=paper_type,
        trim_width=trim_w,
        trim_height=trim_h,
        spine_width=spine,
        spine_has_text=spine_has_text,
        total_width=total_w,
        total_height=total_h,
        total_width_px=total_w_px,
        total_height_px=total_h_px,
        spine_width_px=spine_px,
        trim_width_px=trim_w_px,
        trim_height_px=trim_h_px,
        bleed_px=bleed_px,
        gutter_margin=gutter,
        outside_margin=outside_margin,
        back_cover_start_px=back_start,
        back_cover_end_px=back_end,
        spine_start_px=spine_start,
        spine_end_px=spine_end,
        front_cover_start_px=front_start,
        front_cover_end_px=front_end,
        barcode_x_px=barcode_x,
        barcode_y_px=barcode_y,
        safe_zone_px=safe_px,
    )


def generate_cover_css(dims: CoverDimensions) -> str:
    """
    Generate CSS custom properties for a cover template.
    These variables are injected into the HTML template so it
    automatically adapts to any book's dimensions.
    """
    return f""":root {{
    /* ── Dimensions (pixels at 300 DPI) ────────────── */
    --total-width: {dims.total_width_px}px;
    --total-height: {dims.total_height_px}px;
    --bleed: {dims.bleed_px}px;
    --safe-zone: {dims.safe_zone_px}px;

    /* ── Cover sections ────────────────────────────── */
    --back-cover-width: {dims.trim_width_px}px;
    --spine-width: {dims.spine_width_px}px;
    --front-cover-width: {dims.trim_width_px}px;

    /* ── Zone positions (from left) ────────────────── */
    --back-start: {dims.back_cover_start_px}px;
    --back-end: {dims.back_cover_end_px}px;
    --spine-start: {dims.spine_start_px}px;
    --spine-end: {dims.spine_end_px}px;
    --front-start: {dims.front_cover_start_px}px;
    --front-end: {dims.front_cover_end_px}px;

    /* ── Barcode zone ──────────────────────────────── */
    --barcode-x: {dims.barcode_x_px}px;
    --barcode-y: {dims.barcode_y_px}px;
    --barcode-width: {round(BARCODE_WIDTH * DPI)}px;
    --barcode-height: {round(BARCODE_HEIGHT * DPI)}px;

    /* ── Spine text ────────────────────────────────── */
    --spine-has-text: {1 if dims.spine_has_text else 0};

    /* ── Measurements (inches) ─────────────────────── */
    --trim-width-in: {dims.trim_width};
    --trim-height-in: {dims.trim_height};
    --spine-width-in: {dims.spine_width:.4f};
    --total-width-in: {dims.total_width:.4f};
    --total-height-in: {dims.total_height:.4f};
}}"""


# ── Demo: show how dimensions change per book ────────────────
if __name__ == "__main__":
    examples = [
        # (pages, trim,      paper,       description)
        (50,    "8.5x8.5",  "white_bw",   "Coloring book (50 pages)"),
        (100,   "8.5x8.5",  "white_bw",   "Coloring book (100 pages)"),
        (120,   "8.5x11",   "white_bw",   "Puzzle book (120 pages)"),
        (200,   "8.5x11",   "white_bw",   "Activity book (200 pages)"),
        (300,   "6x9",      "cream_bw",   "Journal (300 pages)"),
        (80,    "8.5x11",   "standard_color", "Color workbook (80 pages)"),
    ]

    print("\n" + "="*80)
    print("  SCRPT COVER DIMENSION ENGINE — Dynamic Sizing Demo")
    print("="*80)

    for pages, trim, paper, desc in examples:
        dims = calculate_cover(pages, trim, paper)
        print(f"\n{'─'*60}")
        print(f"  {desc}")
        print(f"  {pages} pages | {trim} trim | {paper}")
        print(f"{'─'*60}")
        print(f"  Spine:       {dims.spine_width:.4f}\" → {dims.spine_width_px}px")
        print(f"  Full cover:  {dims.total_width:.4f}\" x {dims.total_height:.4f}\"")
        print(f"  Pixels:      {dims.total_width_px} x {dims.total_height_px} @ 300 DPI")
        print(f"  Spine text:  {'Yes' if dims.spine_has_text else 'No'}")

    # Show full detail for one example
    print("\n")
    dims = calculate_cover(120, "8.5x11", "white_bw")
    print(dims.summary())

    print("\n\nCSS Variables for template injection:")
    print("─"*60)
    print(generate_cover_css(dims))
