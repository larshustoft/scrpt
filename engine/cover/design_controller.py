"""
Cover Design Quality Controller
================================
Automated Claude Vision review loop that inspects rendered covers,
detects quality issues (text covering faces, readability problems,
amateur elements), generates CSS/HTML fixes, and re-renders until
the cover meets professional Amazon KDP bestseller standards.

Flow:
    Rendered cover PNG → Claude Vision review → Score 1-10
    If score < 7 → Apply CSS/HTML fixes → Re-render → Review again
    Max 2 iterations → Return best result
"""

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATA STRUCTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class CoverIssue:
    """A single quality issue found in the rendered cover."""
    category: str       # text_occlusion, readability, font_size, amateur_element, composition
    description: str    # Human-readable description
    severity: str       # critical, major, minor


@dataclass
class CoverReview:
    """Result of a quality review of a rendered cover."""
    overall_score: int              # 1-10
    issues: list[CoverIssue] = field(default_factory=list)
    fixed_css: Optional[str] = None
    fixed_html: Optional[str] = None
    passed: bool = False            # score >= 7
    review_notes: str = ""
    iteration: int = 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REVIEW PROMPT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

QUALITY_REVIEW_PROMPT = """You are a senior Amazon KDP book cover designer reviewing a rendered cover for quality.

REVIEW THIS COVER IMAGE against professional bestseller standards. Score it 1-10.

EVALUATION CRITERIA:

1. TEXT OCCLUSION (Critical — deduct 3+ points)
   Does any text overlap or cover important artwork elements?
   - Faces of people/characters → text MUST NOT cover faces
   - Key objects (books, animals, main scene elements)
   - The text should complement, not hide, the artwork
   Severity: CRITICAL if text covers a face, MAJOR if covers key objects
   Fix approach: Use justify-content: flex-start + padding-top to push ALL text
   to the top of the cover, where artwork backgrounds are usually simpler/lighter.
   Or use justify-content: flex-end + padding-bottom to push text to the bottom.
   Choose whichever area of the artwork has simpler backgrounds.

2. TEXT READABILITY (Critical — deduct 2+ points)
   Can every piece of text be read clearly against the artwork?
   - Title must be instantly readable at Amazon thumbnail size (~150px wide)
   - BEST approach: Position text where artwork is SIMPLEST (solid backgrounds,
     sky, gradients) and use HEAVY white text-shadow outlines:
     text-shadow: 4px 4px 0 #fff, -4px -4px 0 #fff, 4px -4px 0 #fff,
     -4px 4px 0 #fff, 0 6px 0 #fff, 0 -6px 0 #fff, 6px 0 0 #fff, -6px 0 0 #fff,
     0 0 30px rgba(255,255,255,0.8);
     This creates a white outline that's readable on any background while keeping
     the artwork visible — this is how bestselling KDP illustrated covers work.
   - Keep the title color BLACK (#000000) with white outline shadow for maximum contrast
   - For secondary text: Use solid colored banners matching the design palette
   - AVOID dark semi-transparent backgrounds (rgba(0,0,0,...)) on titles — they
     create ugly dark blocks that clash with warm illustrations. If you must use a
     background, use a warm color matching the artwork palette at 50-70% opacity.
   - Do NOT change the design color palette — work WITH the existing warm/cozy tones
   Severity: CRITICAL if title is unreadable at thumbnail, MAJOR for other text

3. FONT SIZING (Major — deduct 1-2 points)
   Is the title large enough to dominate the cover?
   - At 300 DPI on a 2550×3300px cover, title should be 300px+ font-size
   - Subtitle should be 100px+ font-size
   - Feature text should be 72px+ font-size
   Severity: MAJOR if title is too small to read at thumbnail

4. AMATEUR ELEMENTS (Major — deduct 1-2 points)
   Are there any unprofessional elements?
   - "Font Size" badges → set display: none in CSS
   - Excessive borders or frames that look cheap
   - Too many text elements cluttering the cover (max 5-6 visible elements)
   - Semi-transparent white panels that block artwork unnecessarily
   Severity: MAJOR

5. COMPOSITION & BALANCE (Minor — deduct 0-1 points)
   Does the overall layout look professional?
   - Text and artwork should work together harmoniously
   - Clear visual hierarchy: Title → Subtitle → Features → Author
   - Even spacing, no awkward gaps or crowding
   - Text positioned in areas where artwork is simpler/less detailed

SCORING (start at 10, deduct for issues):
- 9-10: Bestseller quality, ready for publishing
- 7-8: Professional, minor improvements possible but acceptable
- 5-6: Noticeable issues, needs fixes before publishing
- 3-4: Significant problems, major rework needed
- 1-2: Fundamentally broken layout

A cover with NO text occlusion, readable text, correct font sizes, and clean
composition should score 7+. Only deduct points for actual visible problems.

CURRENT CSS:
```
{style_css}
```

CURRENT FRONT HTML:
```
{front_html}
```

RENDERING CONTEXT:
- Front cover: 2550 × 3300 pixels at 300 DPI
- .front-cover is flex column, align-items: center, justify-content: center (base CSS)
- Your fixed CSS can override justify-content on .front-cover
- Template variables: ${{title}}, ${{author}}, ${{subtitle}}, ${{puzzle_count}}
- Artwork is background-image url('artwork.png') — do NOT remove this
- DO NOT add any new url() references

IF SCORE IS BELOW 7, provide COMPLETE fixed CSS and HTML.
The fixes must:
- Keep all existing class names (template system depends on them)
- Fix ALL identified issues in a single pass — the fixes will be rendered and
  reviewed again, so make sure they address every problem
- Keep url('artwork.png') reference in CSS
- Keep template variables (${{title}}, ${{author}}, ${{subtitle}}, ${{puzzle_count}})
- NOT add new url() references, @import, or JavaScript
- Position text where the artwork is simplest (usually top or bottom)
- Title: BLACK text (#000000) with HEAVY white outline text-shadow (see criteria #2)
- Do NOT use dark backgrounds (rgba(0,0,0,...)) on titles — use white outlines instead
- For secondary text: use solid colored banners from the design's color palette
- Remove any amateur elements (font-size badges, etc.)
- Keep at most 5-6 visible text elements — remove clutter

Return ONLY this JSON (no markdown fences, no commentary):
{{
  "overall_score": 7,
  "issues": [
    {{"category": "text_occlusion", "description": "Main title covers the person's face", "severity": "critical"}}
  ],
  "review_notes": "Brief summary of review findings and fixes applied",
  "fixed_css": "COMPLETE fixed style.css content — or null if score >= 7",
  "fixed_html": "COMPLETE fixed front.html content — or null if score >= 7"
}}"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE REVIEW FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _enforce_font_minimums(css: str) -> str:
    """
    Enforce minimum font sizes on QC-generated CSS fixes.
    Prevents the quality controller from shrinking fonts below
    Amazon KDP thumbnail-readable minimums.
    """
    min_sizes = {
        ".main-title": 320,     # Title must dominate at thumbnail
        ".subtitle": 100,       # Subtitle readable at thumbnail
        ".benefits-text": 70,   # Feature text readable
        ".large-print-badge": 64,
        ".easy-badge": 70,
    }

    for selector, min_px in min_sizes.items():
        # Find font-size for this selector
        pattern = re.compile(
            rf'({re.escape(selector)}\s*\{{[^}}]*?)font-size:\s*(\d+)px',
            re.DOTALL,
        )
        match = pattern.search(css)
        if match:
            current_size = int(match.group(2))
            if current_size < min_px:
                logger.info(f"Enforcing font minimum: {selector} {current_size}px → {min_px}px")
                css = css[:match.start(2)] + str(min_px) + css[match.end(2):]

    return css


def _resize_png_for_review(png_bytes: bytes, max_width: int = 1024) -> bytes:
    """
    Resize a cover PNG to fit within Claude Vision's 5MB limit.
    Converts to JPEG at 85% quality for smaller file size.
    """
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(png_bytes))
        # Resize proportionally
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # Convert to JPEG for smaller file size
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        result = buf.getvalue()
        logger.info(f"Resized cover for review: {len(png_bytes):,} → {len(result):,} bytes ({img.width}x{img.height})")
        return result
    except ImportError:
        # Pillow not available — return original and hope it's small enough
        logger.warning("Pillow not installed — cannot resize cover for review")
        return png_bytes


async def review_cover(
    cover_png_bytes: bytes,
    style_css: str,
    front_html: str,
) -> CoverReview:
    """
    Send rendered cover PNG to Claude Vision for quality review.

    Args:
        cover_png_bytes: Raw bytes of the rendered cover-front.png
        style_css: Current CSS for the cover
        front_html: Current front cover HTML

    Returns:
        CoverReview with score, issues, and optional fixes
    """
    from ..config import ANTHROPIC_API_KEY

    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping quality review")
        return CoverReview(overall_score=7, passed=True, review_notes="Skipped (no API key)")

    try:
        import anthropic

        # Resize image to fit Claude Vision's 5MB limit
        review_bytes = _resize_png_for_review(cover_png_bytes)
        image_b64 = base64.standard_b64encode(review_bytes).decode("utf-8")

        # Determine media type (JPEG after resize, PNG if resize failed)
        media_type = "image/jpeg" if review_bytes[:2] == b'\xff\xd8' else "image/png"

        prompt = QUALITY_REVIEW_PROMPT.format(
            style_css=style_css,
            front_html=front_html,
        )

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        response_text = message.content[0].text.strip()

        # Parse JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            logger.error("Quality reviewer did not return valid JSON")
            return CoverReview(overall_score=6, passed=False, review_notes="Failed to parse review response")

        parsed = json.loads(json_match.group())

        score = int(parsed.get("overall_score", 5))
        issues = [
            CoverIssue(
                category=i.get("category", "unknown"),
                description=i.get("description", ""),
                severity=i.get("severity", "minor"),
            )
            for i in parsed.get("issues", [])
        ]

        fixed_css = parsed.get("fixed_css")
        fixed_html = parsed.get("fixed_html")

        review = CoverReview(
            overall_score=score,
            issues=issues,
            fixed_css=fixed_css if score < 7 else None,
            fixed_html=fixed_html if score < 7 else None,
            passed=score >= 7,
            review_notes=parsed.get("review_notes", ""),
        )

        logger.info(
            f"Quality review: {score}/10 — {len(issues)} issues — "
            f"{'PASSED' if review.passed else 'NEEDS FIXES'}"
        )
        for issue in issues:
            logger.info(f"  [{issue.severity}] {issue.category}: {issue.description}")

        return review

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse quality review JSON: {e}")
        return CoverReview(overall_score=5, passed=False, review_notes=f"JSON parse error: {e}")
    except Exception as e:
        logger.error(f"Quality review failed: {e}")
        return CoverReview(overall_score=5, passed=False, review_notes=f"Review error: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# QUALITY CONTROL LOOP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def quality_control_loop(
    variant_dir: Path,
    title: str,
    subtitle: str,
    author: str,
    book_type: str,
    trim_size: str = "8.5x11",
    paper_type: str = "cream_bw",
    page_count: int = 120,
    puzzle_count: int = 55,
    max_iterations: int = 2,
) -> tuple[Path, CoverReview]:
    """
    Run the quality control loop: render → review → fix → re-render.

    Args:
        variant_dir: Path to the variant directory containing style.css, front.html, etc.
        title, subtitle, author: Book text for rendering
        book_type: e.g., "word_search"
        trim_size, paper_type, page_count, puzzle_count: Render parameters
        max_iterations: Max number of review-fix cycles

    Returns:
        (preview_dir, final_review) — path to the final rendered preview and the review
    """
    from .renderer import render_cover
    from .template_loader import get_template_loader
    from ..config import OUTPUT_DIR

    import uuid

    variant_id = variant_dir.name
    best_review = None
    best_preview_dir = None
    fixes_applied_after_last_render = False

    # Save original CSS/HTML so QC always starts from the design generator's output,
    # not from a previous QC run's accumulated fixes
    original_css_path = variant_dir / "style.original.css"
    original_html_path = variant_dir / "front.original.html"
    current_css = (variant_dir / "style.css").read_text(encoding="utf-8")
    current_html = (variant_dir / "front.html").read_text(encoding="utf-8")

    if original_css_path.exists():
        # Restore original CSS/HTML from before any QC modifications
        logger.info("Restoring original CSS/HTML from before previous QC run")
        original_css = original_css_path.read_text(encoding="utf-8")
        original_html = original_html_path.read_text(encoding="utf-8")
        (variant_dir / "style.css").write_text(original_css, encoding="utf-8")
        (variant_dir / "front.html").write_text(original_html, encoding="utf-8")
    else:
        # First QC run — save the originals
        logger.info("Saving original CSS/HTML for future QC runs")
        original_css_path.write_text(current_css, encoding="utf-8")
        original_html_path.write_text(current_html, encoding="utf-8")

    for iteration in range(max_iterations):
        logger.info(f"Quality control iteration {iteration + 1}/{max_iterations}")

        # Invalidate template cache to pick up any CSS/HTML changes
        get_template_loader().invalidate_cache(book_type)

        # Render the cover
        session_id = str(uuid.uuid4())[:8]
        preview_dir = OUTPUT_DIR / "_preview" / f"qc_{session_id}"
        preview_dir.mkdir(parents=True, exist_ok=True)

        result = await render_cover(
            page_count=page_count,
            trim_size=trim_size,
            paper_type=paper_type,
            title=title,
            subtitle=subtitle,
            author=author,
            book_type=book_type,
            output_dir=preview_dir,
            puzzle_count=puzzle_count,
            variant_id=variant_id,
        )

        if not result.get("success"):
            logger.error(f"Render failed during QC: {result.get('error', 'unknown')}")
            break

        # Read the rendered front cover PNG
        front_png_path = preview_dir / "cover-front.png"
        if not front_png_path.exists():
            logger.error("cover-front.png not found after render")
            break

        cover_png_bytes = front_png_path.read_bytes()
        fixes_applied_after_last_render = False

        # Read current CSS/HTML
        style_css = (variant_dir / "style.css").read_text(encoding="utf-8")
        front_html = (variant_dir / "front.html").read_text(encoding="utf-8")

        # Review the cover
        review = await review_cover(cover_png_bytes, style_css, front_html)
        review.iteration = iteration + 1

        # Track best result — use >= so later (fixed) iterations are preferred
        # when scores are equal, since fixes were applied between iterations
        if best_review is None or review.overall_score >= best_review.overall_score:
            best_review = review
            best_preview_dir = preview_dir

        if review.passed:
            logger.info(f"Quality control PASSED: {review.overall_score}/10 on iteration {iteration + 1}")
            break

        # Apply fixes if available
        if review.fixed_css and review.fixed_html:
            logger.info(f"Applying quality fixes (iteration {iteration + 1})...")

            # Validate the fixed CSS still has artwork reference
            if "artwork.png" not in review.fixed_css:
                # Re-inject artwork background if Claude removed it
                artwork_css = """
/* ── AI-generated artwork background ── */
.front-cover {
    background-image: url('artwork.png');
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
}
"""
                review.fixed_css = artwork_css + "\n" + review.fixed_css

            # Enforce font size minimums on QC-generated fixes
            review.fixed_css = _enforce_font_minimums(review.fixed_css)

            # Write fixed files
            (variant_dir / "style.css").write_text(review.fixed_css, encoding="utf-8")
            (variant_dir / "front.html").write_text(review.fixed_html, encoding="utf-8")
            fixes_applied_after_last_render = True
            logger.info("Fixed CSS/HTML written to variant directory")
        else:
            logger.warning(f"Score {review.overall_score}/10 but no fixes provided — stopping loop")
            break

    # ── Final render pass ──
    # If the last iteration applied CSS/HTML fixes that haven't been rendered yet,
    # do one final render so the user sees the improved version
    if fixes_applied_after_last_render:
        logger.info("Final render pass: rendering last-applied fixes...")
        get_template_loader().invalidate_cache(book_type)

        session_id = str(uuid.uuid4())[:8]
        final_dir = OUTPUT_DIR / "_preview" / f"qc_{session_id}"
        final_dir.mkdir(parents=True, exist_ok=True)

        result = await render_cover(
            page_count=page_count,
            trim_size=trim_size,
            paper_type=paper_type,
            title=title,
            subtitle=subtitle,
            author=author,
            book_type=book_type,
            output_dir=final_dir,
            puzzle_count=puzzle_count,
            variant_id=variant_id,
        )

        if result.get("success") and (final_dir / "cover-front.png").exists():
            best_preview_dir = final_dir
            logger.info(f"Final render complete: {final_dir.name}")
        else:
            logger.error("Final render failed — using previous best render")

    # Update variant.json with quality info
    variant_json_path = variant_dir / "variant.json"
    if variant_json_path.exists():
        try:
            meta = json.loads(variant_json_path.read_text(encoding="utf-8"))
            meta["quality_checked"] = True
            meta["quality_score"] = best_review.overall_score if best_review else 0
            meta["quality_issues"] = len(best_review.issues) if best_review else 0
            meta["quality_notes"] = best_review.review_notes if best_review else ""
            variant_json_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            logger.info(f"Updated variant.json: quality_score={meta['quality_score']}")
        except Exception as e:
            logger.error(f"Failed to update variant.json: {e}")

    if best_review is None:
        best_review = CoverReview(overall_score=0, passed=False, review_notes="Quality control failed to run")
    if best_preview_dir is None:
        best_preview_dir = preview_dir

    logger.info(
        f"Quality control complete: {best_review.overall_score}/10 "
        f"({'PASSED' if best_review.passed else 'BELOW THRESHOLD'}) "
        f"after {best_review.iteration} iteration(s)"
    )

    return best_preview_dir, best_review
