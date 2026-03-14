"""
AI Cover Design Generator
==========================
Uses Claude Vision API to analyze a reference book cover image and
generate CSS/HTML that replicates the design style. Output follows
the exact template structure used by TemplateLoader so it plugs
directly into the existing rendering pipeline.

Usage:
    image_bytes = await fetch_cover_image(url)
    design = await generate_design_from_reference(image_bytes, "word_search", "word search")
    if design.success:
        path = await save_generated_design(design, "word_search", "ai_B0GJ6M19MD", "B0GJ6M19MD")
"""

import base64
import json
import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GeneratedDesign:
    """Output from the AI design generator."""
    template_css: str
    front_cover_html: str
    back_cover_html: str
    spine_html: str
    design_notes: str
    reference_asin: str
    success: bool
    error: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLAUDE VISION PROMPT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DESIGN_GENERATION_PROMPT = """You are a professional Amazon KDP book cover designer. Analyze the reference cover image and generate CSS + HTML that closely replicates its design style for a book cover template system.

RENDERING CONTEXT:
- Covers are rendered at 300 DPI via headless Chromium (Playwright)
- The full cover spread (back + spine + front) is ~5250 x 3375 pixels
- The FRONT COVER alone is ~2550 x 3300 pixels
- All font sizes are in px — remember 72px = ~0.24 inches at 300 DPI

TEMPLATE SYSTEM:
- A base CSS file handles layout positioning (.cover, .back-cover, .spine, .front-cover)
- .front-cover is a flex column (align-items: center, justify-content: center) with padding
- .bleed-fill is the full-spread background (position: absolute, covers entire area, z-index: -1)
- Your CSS styles WITHIN these sections — never override base layout
- Dynamic values use Python Template syntax: ${{title}}, ${{author}}, ${{subtitle}}, ${{puzzle_count}}

YOU GENERATE 3 HTML FRAGMENTS (not a full page):
1. front.html — content inside <div class="front-cover">
2. back.html — content inside <div class="back-cover"> (above the barcode zone)
3. spine.html — content inside <div class="spine">

DESIGN ANALYSIS — Study the reference image for:
1. COLOR SCHEME: Background gradients, text colors, accent colors. Extract hex values.
2. TYPOGRAPHY: Font families (use web-safe: Arial, Georgia, 'Courier New', Verdana, Helvetica), sizes, weights, letter-spacing
3. LAYOUT: Element positions (top banner, centered title, bottom author, decorative elements)
4. DECORATIVE ELEMENTS: Recreate borders, gradients, patterns, badges, dividers in pure CSS
5. VISUAL HIERARCHY: What draws the eye first → second → third
6. OVERALL MOOD: Professional/playful/elegant/bold — match the feeling

CSS RULES:
- ONLY web-safe fonts (Arial, Georgia, 'Times New Roman', 'Courier New', Verdana, Helvetica)
- NO url() references — no external images
- NO @import statements
- NO JavaScript expressions
- NO position: fixed
- Use CSS gradients, box-shadows, borders, pseudo-elements for all decoration
- Title text should be the largest, highest-contrast element (at least 200px font-size)
- Maintain clear hierarchy: title > subtitle/audience > decorative > author

BOOK TYPE: {book_type}
NICHE: {niche_keyword}

OUTPUT — Return ONLY this JSON (no markdown, no code fences):
{{
  "design_notes": "Brief description of design approach and key color choices",
  "style_css": "Complete CSS for style.css — styles .bleed-fill, .spine, .back-cover, .front-cover, and all custom classes",
  "front_html": "HTML fragment for front.html — uses ${{title}}, ${{author}}, ${{subtitle}}, ${{puzzle_count}}",
  "back_html": "HTML fragment for back.html — clean description area",
  "spine_html": "<div class=\\"spine-text\\">${{title}} &mdash; ${{author}}</div>"
}}"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VALIDATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def validate_generated_css(css: str) -> tuple[bool, list[str]]:
    """
    Security and compatibility validation for AI-generated CSS.
    Returns (is_valid, list_of_issues).
    """
    issues = []

    # Check for external resource references
    if re.search(r'url\s*\(', css, re.IGNORECASE):
        issues.append("Contains url() references — external resources not allowed")

    # Check for @import
    if re.search(r'@import', css, re.IGNORECASE):
        issues.append("Contains @import — not allowed")

    # Check for JavaScript expressions
    if re.search(r'expression\s*\(', css, re.IGNORECASE):
        issues.append("Contains expression() — JavaScript not allowed")

    if re.search(r'behavior\s*:', css, re.IGNORECASE):
        issues.append("Contains behavior: — not allowed")

    # Check for position: fixed (breaks print layout)
    if re.search(r'position\s*:\s*fixed', css, re.IGNORECASE):
        issues.append("Contains position: fixed — breaks print layout")

    # Should not override base layout classes entirely
    if re.search(r'body\s*\{', css) and 'width' in css:
        issues.append("Overrides body width — conflicts with base layout")

    return (len(issues) == 0, issues)


def validate_generated_html(html: str) -> tuple[bool, list[str]]:
    """
    Validate AI-generated HTML fragments for security.
    Returns (is_valid, list_of_issues).
    """
    issues = []

    if '<script' in html.lower():
        issues.append("Contains <script> tag")

    if re.search(r'\bon\w+\s*=', html, re.IGNORECASE):
        issues.append("Contains on* event attributes")

    if re.search(r'<(iframe|object|embed|form)', html, re.IGNORECASE):
        issues.append("Contains forbidden element (iframe/object/embed/form)")

    if re.search(r'src\s*=\s*["\']https?://', html, re.IGNORECASE):
        issues.append("Contains external resource reference")

    return (len(issues) == 0, issues)


def _sanitize_css(css: str) -> str:
    """Remove dangerous patterns from CSS while keeping valid styles."""
    # Remove url() references
    css = re.sub(r'url\s*\([^)]*\)', '/* removed url() */', css, flags=re.IGNORECASE)
    # Remove @import
    css = re.sub(r'@import[^;]*;', '/* removed @import */', css, flags=re.IGNORECASE)
    # Remove expression()
    css = re.sub(r'expression\s*\([^)]*\)', '/* removed expression() */', css, flags=re.IGNORECASE)
    # Remove position: fixed
    css = re.sub(r'position\s*:\s*fixed', 'position: absolute', css, flags=re.IGNORECASE)
    return css


def _sanitize_html(html: str) -> str:
    """Remove dangerous patterns from HTML."""
    # Remove script tags
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.IGNORECASE | re.DOTALL)
    # Remove on* event attributes
    html = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', html, flags=re.IGNORECASE)
    # Remove iframes etc
    html = re.sub(r'<(iframe|object|embed)[^>]*>.*?</\1>', '', html, flags=re.IGNORECASE | re.DOTALL)
    return html


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE GENERATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def generate_design_from_reference(
    reference_image_bytes: bytes,
    book_type: str,
    niche_keyword: str,
    reference_asin: str = "",
) -> GeneratedDesign:
    """
    Use Claude Vision API to analyze a reference cover and generate
    CSS/HTML that replicates the design style.

    Args:
        reference_image_bytes: Raw bytes of the reference cover image
        book_type: Book type key (e.g., "word_search")
        niche_keyword: Niche description for context
        reference_asin: Optional ASIN for tracking

    Returns:
        GeneratedDesign with CSS/HTML or error
    """
    from ..config import ANTHROPIC_API_KEY

    if not ANTHROPIC_API_KEY:
        return GeneratedDesign(
            template_css="", front_cover_html="", back_cover_html="",
            spine_html="", design_notes="", reference_asin=reference_asin,
            success=False,
            error="ANTHROPIC_API_KEY not set. Add it to .env to enable AI cover design.",
        )

    # Check cache first
    from ..config import TEMPLATES_DIR
    variant_id = f"ai_{reference_asin}" if reference_asin else "ai_custom"
    cached_dir = TEMPLATES_DIR / book_type / "variants" / variant_id
    if cached_dir.exists() and (cached_dir / "style.css").exists():
        logger.info(f"Using cached design variant: {variant_id}")
        return GeneratedDesign(
            template_css=(cached_dir / "style.css").read_text(encoding="utf-8"),
            front_cover_html=(cached_dir / "front.html").read_text(encoding="utf-8"),
            back_cover_html=(cached_dir / "back.html").read_text(encoding="utf-8"),
            spine_html=(cached_dir / "spine.html").read_text(encoding="utf-8"),
            design_notes="Loaded from cache",
            reference_asin=reference_asin,
            success=True,
        )

    # Encode image as base64
    image_b64 = base64.standard_b64encode(reference_image_bytes).decode("utf-8")

    # Determine media type
    if reference_image_bytes[:3] == b'\xff\xd8\xff':
        media_type = "image/jpeg"
    elif reference_image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        media_type = "image/png"
    else:
        media_type = "image/jpeg"  # Assume JPEG for Amazon images

    # Build the prompt
    prompt = DESIGN_GENERATION_PROMPT.format(
        book_type=book_type,
        niche_keyword=niche_keyword,
    )

    try:
        import anthropic

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

        # Parse the response
        response_text = message.content[0].text.strip()

        # Try to extract JSON from the response
        # Claude might wrap it in markdown code fences
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            return GeneratedDesign(
                template_css="", front_cover_html="", back_cover_html="",
                spine_html="", design_notes="", reference_asin=reference_asin,
                success=False,
                error="Claude did not return valid JSON",
            )

        parsed = json.loads(json_match.group())

        style_css = parsed.get("style_css", "")
        front_html = parsed.get("front_html", "")
        back_html = parsed.get("back_html", "")
        spine_html = parsed.get("spine_html", '<div class="spine-text">${title} &mdash; ${author}</div>')
        design_notes = parsed.get("design_notes", "")

        # Validate and sanitize
        css_valid, css_issues = validate_generated_css(style_css)
        if not css_valid:
            logger.warning(f"CSS validation issues: {css_issues}")
            style_css = _sanitize_css(style_css)

        front_valid, front_issues = validate_generated_html(front_html)
        if not front_valid:
            logger.warning(f"Front HTML validation issues: {front_issues}")
            front_html = _sanitize_html(front_html)

        back_valid, back_issues = validate_generated_html(back_html)
        if not back_valid:
            logger.warning(f"Back HTML validation issues: {back_issues}")
            back_html = _sanitize_html(back_html)

        return GeneratedDesign(
            template_css=style_css,
            front_cover_html=front_html,
            back_cover_html=back_html,
            spine_html=spine_html,
            design_notes=design_notes,
            reference_asin=reference_asin,
            success=True,
        )

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        return GeneratedDesign(
            template_css="", front_cover_html="", back_cover_html="",
            spine_html="", design_notes="", reference_asin=reference_asin,
            success=False,
            error=f"Failed to parse AI response: {e}",
        )
    except Exception as e:
        logger.error(f"Claude API call failed: {e}")
        return GeneratedDesign(
            template_css="", front_cover_html="", back_cover_html="",
            spine_html="", design_notes="", reference_asin=reference_asin,
            success=False,
            error=f"AI design generation failed: {e}",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SAVE GENERATED DESIGN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def save_generated_design(
    design: GeneratedDesign,
    niche: str,
    variant_id: str,
    reference_asin: str = "",
) -> Path:
    """
    Save an AI-generated design as a file-based variant.

    Creates:
        templates/{niche}/variants/{variant_id}/
            style.css
            front.html
            back.html
            spine.html
            variant.json

    Returns:
        Path to the variant directory.
    """
    from ..config import TEMPLATES_DIR

    variant_dir = TEMPLATES_DIR / niche / "variants" / variant_id
    variant_dir.mkdir(parents=True, exist_ok=True)

    # Write template files
    (variant_dir / "style.css").write_text(design.template_css, encoding="utf-8")
    (variant_dir / "front.html").write_text(design.front_cover_html, encoding="utf-8")
    (variant_dir / "back.html").write_text(design.back_cover_html, encoding="utf-8")
    (variant_dir / "spine.html").write_text(design.spine_html, encoding="utf-8")

    # Write variant metadata
    variant_meta = {
        "name": f"AI Generated ({reference_asin or 'custom'})",
        "reference": f"ref_{reference_asin}.jpg" if reference_asin else "",
        "description": design.design_notes,
        "inspired_by": f"Amazon ASIN: {reference_asin}" if reference_asin else "Custom reference",
        "generated": True,
    }
    (variant_dir / "variant.json").write_text(
        json.dumps(variant_meta, indent=2), encoding="utf-8"
    )

    logger.info(f"Saved AI-generated design variant: {variant_dir}")
    return variant_dir
