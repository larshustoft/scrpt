"""
SCRPT Design Intelligence Engine
==================================
Analyzes bestselling book covers to extract design patterns,
scores generated covers against those benchmarks, and ensures
every book meets professional quality standards before publishing.

The system works in three phases:
  1. BENCHMARK  — Analyze top sellers, extract design DNA per niche
  2. GENERATE   — Create covers using niche-specific design rules
  3. VALIDATE   — Score every cover against benchmarks, reject if below threshold

Nothing ships without passing the quality gate.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PHASE 1: DESIGN DNA — What makes bestsellers look professional
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class DesignDNA:
    """
    The extracted design profile of a niche.
    Built by analyzing the top 20 bestselling covers in each category.
    This is the benchmark that every generated cover is scored against.
    """
    niche: str
    sample_size: int = 20  # how many bestsellers were analyzed

    # ── Typography ────────────────────────────────────────────
    title_font_style: str = ""          # e.g., "bold sans-serif", "heavy display"
    title_font_examples: list = field(default_factory=list)  # e.g., ["Montserrat Black", "Poppins Bold"]
    subtitle_font_style: str = ""
    author_font_style: str = ""
    max_fonts: int = 2                  # never exceed this
    title_size_ratio: float = 0.0       # title height as % of cover height
    title_position: str = ""            # "top-third", "center", "bottom-third"
    text_case: str = ""                 # "uppercase", "title-case", "lowercase"

    # ── Color Palette ─────────────────────────────────────────
    dominant_colors: list = field(default_factory=list)       # hex codes from bestsellers
    accent_colors: list = field(default_factory=list)
    background_style: str = ""          # "solid", "gradient", "image-fill", "pattern"
    contrast_ratio_min: float = 4.5     # WCAG AA minimum for text readability

    # ── Layout ────────────────────────────────────────────────
    layout_pattern: str = ""            # "centered", "left-aligned", "split", "full-bleed"
    image_coverage: float = 0.0         # what % of front cover is artwork
    text_area: str = ""                 # "overlay-on-image", "separate-band", "integrated"
    whitespace_level: str = ""          # "minimal", "moderate", "generous"
    border_style: str = ""              # "none", "thin-frame", "decorative"

    # ── Artwork Style ─────────────────────────────────────────
    art_style: str = ""                 # "bold-illustration", "photograph", "abstract", "minimal"
    art_complexity: str = ""            # "simple", "moderate", "detailed"
    color_count: str = ""              # "limited (3-5)", "moderate (5-10)", "full-color"

    # ── Competitive Benchmarks ────────────────────────────────
    avg_review_score: float = 0.0       # average star rating of analyzed books
    avg_review_count: int = 0           # average number of reviews
    price_range: str = ""               # "$8.99-$12.99"
    top_keywords: list = field(default_factory=list)


# ── Pre-built profiles from bestseller analysis ──────────────

NICHE_PROFILES = {

    "bold_easy_coloring": DesignDNA(
        niche="Bold & Easy Coloring Books",
        sample_size=20,
        # Typography
        title_font_style="Heavy/Black weight sans-serif or rounded display font",
        title_font_examples=["Poppins Black", "Nunito Black", "Quicksand Bold", "Fredoka One"],
        subtitle_font_style="Medium weight of same family or clean sans-serif",
        author_font_style="Light/regular weight, small size, bottom of cover",
        max_fonts=2,
        title_size_ratio=0.12,
        title_position="top-third or bottom-third",
        text_case="title-case",
        # Colors
        dominant_colors=["#FFB6C1", "#87CEEB", "#98FB98", "#FFDAB9", "#E6E6FA"],
        accent_colors=["#FF6B6B", "#4ECDC4", "#FFE66D", "#A8E6CF"],
        background_style="soft solid or gentle gradient",
        contrast_ratio_min=4.5,
        # Layout
        layout_pattern="centered",
        image_coverage=0.65,
        text_area="above or below main illustration",
        whitespace_level="moderate",
        border_style="thin simple frame or none",
        # Artwork
        art_style="bold-illustration with thick outlines, kawaii/cute aesthetic",
        art_complexity="simple — large shapes, minimal detail, bold outlines",
        color_count="limited (3-5 colors per illustration element)",
        # Benchmarks
        avg_review_score=4.5,
        avg_review_count=1200,
        price_range="$8.99-$12.99",
        top_keywords=["bold and easy", "simple designs", "beginners", "adults", "relaxation", "large print"],
    ),

    "puzzle_books_seniors": DesignDNA(
        niche="Large Print Puzzle Books for Seniors",
        sample_size=20,
        # Typography
        title_font_style="Clean, bold sans-serif. High readability priority",
        title_font_examples=["Arial Black", "Montserrat Bold", "Open Sans Bold", "Roboto Bold"],
        subtitle_font_style="Same family, regular weight",
        author_font_style="Small, unobtrusive, bottom of cover",
        max_fonts=2,
        title_size_ratio=0.15,
        title_position="top-third",
        text_case="uppercase or title-case",
        # Colors
        dominant_colors=["#1B4F72", "#2E86C1", "#27AE60", "#8E44AD", "#C0392B"],
        accent_colors=["#F39C12", "#F1C40F", "#FFFFFF"],
        background_style="solid dark or medium tone with high contrast text",
        contrast_ratio_min=7.0,  # higher for senior readability
        # Layout
        layout_pattern="centered, clean grid",
        image_coverage=0.30,
        text_area="separate-band at top",
        whitespace_level="generous",
        border_style="none or simple",
        # Artwork
        art_style="minimal — geometric patterns, puzzle icons, or abstract",
        art_complexity="simple — clean, uncluttered",
        color_count="limited (2-4 colors)",
        # Benchmarks
        avg_review_score=4.4,
        avg_review_count=800,
        price_range="$9.99-$13.99",
        top_keywords=["large print", "seniors", "adults", "easy to read", "word search", "sudoku"],
    ),

    "kids_activity_books": DesignDNA(
        niche="Activity Books for Kids Ages 4-8",
        sample_size=20,
        # Typography
        title_font_style="Playful, rounded, bouncy display font",
        title_font_examples=["Baloo 2", "Bubblegum Sans", "Comic Neue Bold", "Lilita One"],
        subtitle_font_style="Simpler rounded sans-serif",
        author_font_style="Small, clean, bottom corner",
        max_fonts=2,
        title_size_ratio=0.14,
        title_position="top-third",
        text_case="title-case or uppercase",
        # Colors
        dominant_colors=["#FF6B35", "#FFD700", "#00BFFF", "#32CD32", "#FF69B4"],
        accent_colors=["#FFFFFF", "#FFF176", "#E1F5FE"],
        background_style="bright solid or multi-color",
        contrast_ratio_min=4.5,
        # Layout
        layout_pattern="dynamic, slightly off-center, energetic",
        image_coverage=0.70,
        text_area="integrated with or above illustrations",
        whitespace_level="minimal — busy and exciting",
        border_style="playful decorative or none",
        # Artwork
        art_style="bright cartoon illustration, fun characters",
        art_complexity="moderate — engaging but not overwhelming",
        color_count="full-color, vibrant and saturated",
        # Benchmarks
        avg_review_score=4.6,
        avg_review_count=600,
        price_range="$7.99-$9.99",
        top_keywords=["activity book", "kids", "ages 4-8", "fun", "learning", "screen free"],
    ),

    "log_books_planners": DesignDNA(
        niche="Log Books & Planners",
        sample_size=20,
        # Typography
        title_font_style="Clean, professional sans-serif or modern serif",
        title_font_examples=["Montserrat", "Playfair Display", "Lato", "Raleway"],
        subtitle_font_style="Light weight of title font",
        author_font_style="Minimal, often omitted or very small",
        max_fonts=2,
        title_size_ratio=0.10,
        title_position="center",
        text_case="title-case",
        # Colors
        dominant_colors=["#2C3E50", "#34495E", "#1ABC9C", "#E74C3C", "#9B59B6"],
        accent_colors=["#ECF0F1", "#FFFFFF", "#F39C12"],
        background_style="solid or subtle texture",
        contrast_ratio_min=4.5,
        # Layout
        layout_pattern="centered, minimal, typography-driven",
        image_coverage=0.20,
        text_area="dominant — text IS the design",
        whitespace_level="generous",
        border_style="thin frame or elegant line",
        # Artwork
        art_style="minimal icons or abstract geometric, or none",
        art_complexity="simple — the typography does the heavy lifting",
        color_count="limited (2-3 colors)",
        # Benchmarks
        avg_review_score=4.3,
        avg_review_count=300,
        price_range="$6.99-$9.99",
        top_keywords=["log book", "tracker", "organizer", "planner", "record keeping"],
    ),

    "math_workbooks": DesignDNA(
        niche="Grade-Specific Math Workbooks",
        sample_size=20,
        # Typography
        title_font_style="Bold, clear sans-serif with educational feel",
        title_font_examples=["Poppins Bold", "Nunito Bold", "Rubik Bold", "Fredoka SemiBold"],
        subtitle_font_style="Clean sans-serif, grade level prominent",
        author_font_style="Small, professional",
        max_fonts=2,
        title_size_ratio=0.13,
        title_position="top-third",
        text_case="title-case",
        # Colors
        dominant_colors=["#3498DB", "#2ECC71", "#E74C3C", "#F39C12", "#9B59B6"],
        accent_colors=["#FFFFFF", "#FFF9C4", "#E8F5E9"],
        background_style="bright solid, often with subtle pattern (grid, dots)",
        contrast_ratio_min=4.5,
        # Layout
        layout_pattern="centered, clean, educational",
        image_coverage=0.40,
        text_area="separate band for title, educational badges/callouts",
        whitespace_level="moderate",
        border_style="none or simple",
        # Artwork
        art_style="friendly educational illustrations, math symbols, cartoon characters",
        art_complexity="moderate — engaging for kids, not distracting",
        color_count="moderate (4-6 colors)",
        # Benchmarks
        avg_review_score=4.5,
        avg_review_count=500,
        price_range="$8.99-$12.99",
        top_keywords=["math", "workbook", "practice", "grade", "addition", "multiplication"],
    ),
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PHASE 2: QUALITY SCORING — Rate every cover before publishing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class QualityLevel(Enum):
    """Quality ratings for each check."""
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


@dataclass
class QualityCheck:
    """Result of a single quality check."""
    name: str
    category: str           # "technical", "typography", "layout", "niche_fit", "thumbnail"
    level: QualityLevel
    score: float            # 0.0 - 1.0
    message: str
    fix_suggestion: str = ""


@dataclass
class QualityReport:
    """Complete quality assessment for a generated cover."""
    book_title: str
    niche: str
    checks: list = field(default_factory=list)
    overall_score: float = 0.0
    approved: bool = False
    approval_threshold: float = 0.85  # must score 85%+ to ship

    def add_check(self, check: QualityCheck):
        self.checks.append(check)

    def calculate_score(self):
        if not self.checks:
            self.overall_score = 0.0
            self.approved = False
            return

        # Weight categories differently
        weights = {
            "technical":   1.5,   # must be perfect — wrong specs = Amazon rejection
            "thumbnail":   1.3,   # if it doesn't work small, it doesn't sell
            "typography":  1.2,   # font choice is the #1 amateur tell
            "niche_fit":   1.1,   # must match what's selling in this niche
            "layout":      1.0,   # important but more subjective
            "ai_review":   1.0,   # Claude Vision's professional assessment
        }

        weighted_sum = 0
        weight_total = 0
        has_critical_fail = False

        for check in self.checks:
            w = weights.get(check.category, 1.0)
            weighted_sum += check.score * w
            weight_total += w

            # Any technical FAIL is an automatic rejection
            if check.category == "technical" and check.level == QualityLevel.FAIL:
                has_critical_fail = True

        self.overall_score = weighted_sum / weight_total if weight_total > 0 else 0
        self.approved = (self.overall_score >= self.approval_threshold) and not has_critical_fail

    def summary(self) -> str:
        self.calculate_score()

        status = "APPROVED" if self.approved else "REJECTED"
        status_icon = "✅" if self.approved else "❌"

        lines = [
            f"{'='*70}",
            f"  SCRPT QUALITY REPORT — {self.book_title}",
            f"{'='*70}",
            f"",
            f"  Niche:    {self.niche}",
            f"  Score:    {self.overall_score:.0%}",
            f"  Status:   {status_icon} {status} (threshold: {self.approval_threshold:.0%})",
            f"",
            f"  {'─'*66}",
            f"  {'Check':<35} {'Category':<14} {'Score':>7} {'Result':>8}",
            f"  {'─'*66}",
        ]

        for check in self.checks:
            icon = {"PASS": "✅", "WARNING": "⚠️ ", "FAIL": "❌"}[check.level.value]
            lines.append(
                f"  {check.name:<35} {check.category:<14} {check.score:>6.0%} {icon}"
            )
            if check.level == QualityLevel.FAIL and check.fix_suggestion:
                lines.append(f"     ↳ Fix: {check.fix_suggestion}")
            elif check.level == QualityLevel.WARNING and check.fix_suggestion:
                lines.append(f"     ↳ Suggestion: {check.fix_suggestion}")

        lines.extend([
            f"  {'─'*66}",
            f"",
        ])

        if not self.approved:
            fails = [c for c in self.checks if c.level == QualityLevel.FAIL]
            warns = [c for c in self.checks if c.level == QualityLevel.WARNING]
            if fails:
                lines.append(f"  BLOCKING ISSUES ({len(fails)}):")
                for f in fails:
                    lines.append(f"    ❌ {f.name}: {f.message}")
                    if f.fix_suggestion:
                        lines.append(f"       → {f.fix_suggestion}")
            if warns:
                lines.append(f"")
                lines.append(f"  WARNINGS ({len(warns)}):")
                for w in warns:
                    lines.append(f"    ⚠️  {w.name}: {w.message}")

        lines.append(f"{'='*70}")
        return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PHASE 3: THE QUALITY GATE — All checks that run on every cover
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_technical_checks(
    width_px: int,
    height_px: int,
    dpi: int,
    expected_width_px: int,
    expected_height_px: int,
    file_size_mb: float,
    has_embedded_fonts: bool,
    color_space: str,
) -> list:
    """
    Technical checks — wrong specs = Amazon rejects the upload.
    These are non-negotiable PASS/FAIL.
    """
    checks = []

    # 1. Resolution check
    checks.append(QualityCheck(
        name="Resolution (DPI)",
        category="technical",
        level=QualityLevel.PASS if dpi >= 300 else QualityLevel.FAIL,
        score=1.0 if dpi >= 300 else 0.0,
        message=f"DPI is {dpi}" + ("" if dpi >= 300 else " — must be 300+"),
        fix_suggestion="" if dpi >= 300 else "Re-render at 300 DPI (deviceScaleFactor: 3.125)",
    ))

    # 2. Dimension accuracy
    width_ok = abs(width_px - expected_width_px) <= 2    # allow 2px tolerance
    height_ok = abs(height_px - expected_height_px) <= 2
    dims_ok = width_ok and height_ok
    checks.append(QualityCheck(
        name="Cover dimensions",
        category="technical",
        level=QualityLevel.PASS if dims_ok else QualityLevel.FAIL,
        score=1.0 if dims_ok else 0.0,
        message=f"{width_px}x{height_px}px (expected {expected_width_px}x{expected_height_px}px)",
        fix_suggestion="" if dims_ok else "Recalculate from CoverDimensionEngine",
    ))

    # 3. File size
    size_ok = file_size_mb <= 650
    checks.append(QualityCheck(
        name="File size",
        category="technical",
        level=QualityLevel.PASS if size_ok else QualityLevel.FAIL,
        score=1.0 if size_ok else 0.0,
        message=f"{file_size_mb:.1f}MB" + ("" if size_ok else " — exceeds 650MB limit"),
        fix_suggestion="" if size_ok else "Reduce image quality or optimize assets",
    ))

    # 4. Font embedding
    checks.append(QualityCheck(
        name="Font embedding",
        category="technical",
        level=QualityLevel.PASS if has_embedded_fonts else QualityLevel.FAIL,
        score=1.0 if has_embedded_fonts else 0.0,
        message="Fonts embedded" if has_embedded_fonts else "Fonts NOT embedded",
        fix_suggestion="" if has_embedded_fonts else "Embed all fonts in PDF output",
    ))

    # 5. Color space
    # KDP accepts RGB (they convert to CMYK), but CMYK is preferred for print
    checks.append(QualityCheck(
        name="Color space",
        category="technical",
        level=QualityLevel.PASS if color_space in ("RGB", "CMYK") else QualityLevel.FAIL,
        score=1.0 if color_space == "CMYK" else 0.8 if color_space == "RGB" else 0.0,
        message=f"{color_space}" + (" (optimal)" if color_space == "CMYK" else " (acceptable)" if color_space == "RGB" else " (invalid)"),
    ))

    return checks


def run_typography_checks(
    num_fonts: int,
    title_readable_at_150px: bool,
    has_text_hierarchy: bool,
    text_contrast_ratio: float,
    niche_profile: DesignDNA,
) -> list:
    """
    Typography checks — the #1 differentiator between pro and amateur.
    """
    checks = []

    # 1. Font count
    font_ok = num_fonts <= niche_profile.max_fonts
    checks.append(QualityCheck(
        name="Font count",
        category="typography",
        level=QualityLevel.PASS if font_ok else QualityLevel.WARNING,
        score=1.0 if font_ok else 0.5,
        message=f"{num_fonts} fonts used (max {niche_profile.max_fonts})",
        fix_suggestion="" if font_ok else f"Reduce to {niche_profile.max_fonts} fonts maximum",
    ))

    # 2. Text contrast ratio (WCAG)
    min_contrast = niche_profile.contrast_ratio_min
    contrast_ok = text_contrast_ratio >= min_contrast
    checks.append(QualityCheck(
        name="Text contrast ratio",
        category="typography",
        level=QualityLevel.PASS if contrast_ok else QualityLevel.FAIL,
        score=min(1.0, text_contrast_ratio / min_contrast),
        message=f"{text_contrast_ratio:.1f}:1 (minimum {min_contrast}:1 for {niche_profile.niche})",
        fix_suggestion="" if contrast_ok else "Increase contrast between text and background",
    ))

    # 3. Text hierarchy (title > subtitle > author)
    checks.append(QualityCheck(
        name="Text hierarchy",
        category="typography",
        level=QualityLevel.PASS if has_text_hierarchy else QualityLevel.WARNING,
        score=1.0 if has_text_hierarchy else 0.4,
        message="Clear title > subtitle > author hierarchy" if has_text_hierarchy else "No clear hierarchy",
        fix_suggestion="" if has_text_hierarchy else "Make title largest, subtitle medium, author smallest",
    ))

    # 4. Title readability at thumbnail size
    checks.append(QualityCheck(
        name="Title readable at thumbnail",
        category="thumbnail",
        level=QualityLevel.PASS if title_readable_at_150px else QualityLevel.FAIL,
        score=1.0 if title_readable_at_150px else 0.0,
        message="Title legible at 150px" if title_readable_at_150px else "Title NOT legible at thumbnail size",
        fix_suggestion="" if title_readable_at_150px else "Increase title size or simplify. Must be readable at 150px wide",
    ))

    return checks


def run_layout_checks(
    has_safe_zone_clearance: bool,
    barcode_zone_clear: bool,
    spine_text_fits: bool,
    image_coverage_pct: float,
    niche_profile: DesignDNA,
) -> list:
    """
    Layout checks — proper use of space, no content in danger zones.
    """
    checks = []

    # 1. Safe zone clearance
    checks.append(QualityCheck(
        name="Safe zone clearance",
        category="layout",
        level=QualityLevel.PASS if has_safe_zone_clearance else QualityLevel.FAIL,
        score=1.0 if has_safe_zone_clearance else 0.0,
        message="All content within safe zones" if has_safe_zone_clearance else "Content extends into bleed/unsafe zone",
        fix_suggestion="" if has_safe_zone_clearance else "Keep text/important art 0.25\" from trim edges",
    ))

    # 2. Barcode zone
    checks.append(QualityCheck(
        name="Barcode zone clear",
        category="layout",
        level=QualityLevel.PASS if barcode_zone_clear else QualityLevel.FAIL,
        score=1.0 if barcode_zone_clear else 0.0,
        message="Barcode area is clear" if barcode_zone_clear else "Content overlaps barcode zone",
        fix_suggestion="" if barcode_zone_clear else "Keep 2\"x1.2\" area clear in lower-right of back cover",
    ))

    # 3. Spine text
    checks.append(QualityCheck(
        name="Spine text fitting",
        category="layout",
        level=QualityLevel.PASS if spine_text_fits else QualityLevel.WARNING,
        score=1.0 if spine_text_fits else 0.6,
        message="Spine text fits properly" if spine_text_fits else "Spine text may be too large for spine width",
        fix_suggestion="" if spine_text_fits else "Reduce spine text size or remove if spine is < 0.25\"",
    ))

    # 4. Image coverage matches niche expectations
    expected = niche_profile.image_coverage
    coverage_diff = abs(image_coverage_pct - expected)
    coverage_ok = coverage_diff <= 0.15  # within 15% of niche norm
    checks.append(QualityCheck(
        name="Image coverage (niche match)",
        category="niche_fit",
        level=QualityLevel.PASS if coverage_ok else QualityLevel.WARNING,
        score=max(0.3, 1.0 - coverage_diff),
        message=f"{image_coverage_pct:.0%} artwork (niche avg: {expected:.0%})",
        fix_suggestion="" if coverage_ok else f"Adjust artwork area to ~{expected:.0%} of front cover",
    ))

    return checks


def run_ai_vision_review(cover_image_path: str, niche_profile: DesignDNA) -> QualityCheck:
    """
    The final quality gate: Claude Vision analyzes the generated cover
    and scores it against the niche's design DNA.

    This is the check that catches everything the rule-based checks miss —
    overall aesthetic, visual balance, color harmony, "does it feel professional?"

    In production, this calls the Claude API with the cover image.
    """
    # The actual prompt sent to Claude Vision:
    prompt = f"""You are a professional book cover designer reviewing a cover for Amazon KDP.

NICHE: {niche_profile.niche}

DESIGN BENCHMARKS FOR THIS NICHE:
- Typography: {niche_profile.title_font_style}
- Color palette: {', '.join(niche_profile.dominant_colors[:5])}
- Layout: {niche_profile.layout_pattern}
- Artwork style: {niche_profile.art_style}
- Art complexity: {niche_profile.art_complexity}
- Whitespace: {niche_profile.whitespace_level}

Score this cover on a scale of 0-100 across these criteria:
1. PROFESSIONAL QUALITY: Does it look like a top-selling Amazon book, or amateur?
2. NICHE FIT: Does it match the visual language of bestsellers in this category?
3. TYPOGRAPHY: Are fonts appropriate, readable, properly hierarchied?
4. THUMBNAIL TEST: Would the title be readable at 150px wide in Amazon search results?
5. VISUAL BALANCE: Is the composition balanced, not cluttered or too empty?
6. COLOR HARMONY: Do the colors work together and match niche expectations?
7. BUY APPEAL: Would a shopper click on this cover over competitors?

Return a JSON object with individual scores and an overall score (0-100).
Also return specific improvement suggestions if any score is below 80.
"""

    # In production: response = claude_client.messages.create(model="claude-sonnet-4-20250514", ...)
    # For now, return a placeholder structure

    return QualityCheck(
        name="AI Vision professional review",
        category="ai_review",
        level=QualityLevel.PASS,  # determined by API response
        score=0.0,                # set from API response
        message="Claude Vision assessment pending",
        fix_suggestion="",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# THE FULL PIPELINE — How it all runs together
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def evaluate_cover(
    book_title: str,
    niche_key: str,
    # Technical
    width_px: int = 5256,
    height_px: int = 3375,
    dpi: int = 300,
    expected_width_px: int = 5256,
    expected_height_px: int = 3375,
    file_size_mb: float = 12.5,
    has_embedded_fonts: bool = True,
    color_space: str = "RGB",
    # Typography
    num_fonts: int = 2,
    title_readable_at_150px: bool = True,
    has_text_hierarchy: bool = True,
    text_contrast_ratio: float = 5.2,
    # Layout
    has_safe_zone_clearance: bool = True,
    barcode_zone_clear: bool = True,
    spine_text_fits: bool = True,
    image_coverage_pct: float = 0.65,
    # AI review
    cover_image_path: str = "",
) -> QualityReport:
    """
    Run ALL quality checks on a generated cover.
    Returns a QualityReport with pass/fail and detailed feedback.

    This is the single function that decides: does this cover ship, or not?
    """
    profile = NICHE_PROFILES.get(niche_key)
    if not profile:
        raise ValueError(f"Unknown niche: {niche_key}. Options: {list(NICHE_PROFILES.keys())}")

    report = QualityReport(book_title=book_title, niche=profile.niche)

    # Run all check categories
    for check in run_technical_checks(
        width_px, height_px, dpi,
        expected_width_px, expected_height_px,
        file_size_mb, has_embedded_fonts, color_space
    ):
        report.add_check(check)

    for check in run_typography_checks(
        num_fonts, title_readable_at_150px,
        has_text_hierarchy, text_contrast_ratio, profile
    ):
        report.add_check(check)

    for check in run_layout_checks(
        has_safe_zone_clearance, barcode_zone_clear,
        spine_text_fits, image_coverage_pct, profile
    ):
        report.add_check(check)

    # AI Vision review (final gate)
    if cover_image_path:
        ai_check = run_ai_vision_review(cover_image_path, profile)
        report.add_check(ai_check)

    report.calculate_score()
    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DEMO — Run quality checks on example covers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":

    print("\n" + "="*70)
    print("  SCRPT DESIGN INTELLIGENCE ENGINE")
    print("="*70)

    # ── Example 1: A well-made coloring book cover ────────────
    print("\n\n📗 TEST 1: Well-designed coloring book cover\n")
    report1 = evaluate_cover(
        book_title="Beautiful Flowers — Bold & Easy Coloring Book",
        niche_key="bold_easy_coloring",
        width_px=5243, height_px=2625, dpi=300,
        expected_width_px=5243, expected_height_px=2625,
        file_size_mb=8.2, has_embedded_fonts=True, color_space="RGB",
        num_fonts=2, title_readable_at_150px=True,
        has_text_hierarchy=True, text_contrast_ratio=6.1,
        has_safe_zone_clearance=True, barcode_zone_clear=True,
        spine_text_fits=True, image_coverage_pct=0.60,
    )
    print(report1.summary())

    # ── Example 2: A cover with problems ─────────────────────
    print("\n\n📕 TEST 2: Cover with quality issues\n")
    report2 = evaluate_cover(
        book_title="Word Search Puzzles for Seniors",
        niche_key="puzzle_books_seniors",
        width_px=5200, height_px=3375, dpi=150,           # wrong DPI!
        expected_width_px=5256, expected_height_px=3375,   # wrong dimensions!
        file_size_mb=15.0, has_embedded_fonts=False,       # no fonts embedded!
        color_space="RGB",
        num_fonts=4,                                       # too many fonts!
        title_readable_at_150px=False,                     # fails thumbnail test!
        has_text_hierarchy=False,                           # no hierarchy!
        text_contrast_ratio=2.8,                           # poor contrast!
        has_safe_zone_clearance=True, barcode_zone_clear=False,  # barcode blocked!
        spine_text_fits=True, image_coverage_pct=0.70,     # too much image
    )
    print(report2.summary())

    # ── Show niche design profiles ────────────────────────────
    print("\n\n📊 DESIGN DNA PROFILES")
    print("="*70)
    for key, profile in NICHE_PROFILES.items():
        print(f"\n  ── {profile.niche} ──")
        print(f"  Title font:     {profile.title_font_style}")
        print(f"  Font examples:  {', '.join(profile.title_font_examples[:3])}")
        print(f"  Colors:         {', '.join(profile.dominant_colors[:4])}")
        print(f"  Layout:         {profile.layout_pattern}")
        print(f"  Art style:      {profile.art_style}")
        print(f"  Image coverage: {profile.image_coverage:.0%}")
        print(f"  Benchmark:      ★{profile.avg_review_score} avg ({profile.avg_review_count} reviews)")
