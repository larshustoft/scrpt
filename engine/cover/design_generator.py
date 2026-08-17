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
    artwork_path: Optional[str] = None
    image_prompt: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLAUDE VISION PROMPT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DESIGN_GENERATION_PROMPT = """You are a senior book cover designer creating a bestselling Amazon KDP cover. Study the reference cover to understand what sells in this niche, then create a PROFESSIONAL design that would compete on the Amazon bestseller page.

━━━ DESIGN PHILOSOPHY ━━━
The cover must look like it was designed by a professional book designer, NOT like AI-generated art. Key principles:
- RESTRAINT over excess: fewer elements, more impact
- TYPOGRAPHY is the hero — professional covers are defined by strong type, not busy illustrations
- SOPHISTICATED color palettes: muted, harmonious, 2-3 colors max
- CLEAN NEGATIVE SPACE: don't fill every inch with decoration
- The cover must read clearly at Amazon thumbnail size (120 × 160 pixels)

━━━ YOUR TASK ━━━
1. Study the reference cover's design STRATEGY (not just its surface details)
2. Generate an image_prompt for artwork that enhances (not competes with) the typography
3. Generate CSS/HTML with professional typography and restrained layout

━━━ RENDERING CONTEXT ━━━
- Front cover: 2550 × 3300 pixels (rendered at 300 DPI)
- Full spread (back + spine + front): ~5250 × 3375 pixels
- Font sizes in px: 300px ≈ 1 inch, 150px ≈ 0.5 inch at 300 DPI
- AI artwork fills the entire front-cover as background-image
- Your CSS/HTML overlays text on top of the artwork

━━━ TEMPLATE SYSTEM ━━━
- Base CSS positions .front-cover, .back-cover, .spine, .bleed-fill
- .front-cover is flex column, align-items: center, justify-content: center, padding: safe-zone
- You style WITHIN these sections (never override position/size)
- Template variables: ${{title}}, ${{author}}, ${{subtitle}}, ${{puzzle_count}}
- 3 HTML fragments: front.html, back.html, spine.html

━━━ IMAGE PROMPT — PROFESSIONAL ARTWORK ━━━
Create artwork that SUPPORTS the typography, not competes with it:
- Art style should be PAINTERLY, TEXTURED, or GRAPHIC — never glossy digital illustration
- Good styles: oil painting texture, watercolor wash, lino-cut/woodblock print, vintage lithograph, subtle botanical illustration, abstract geometric, paper texture with pattern
- BAD styles (look AI-generated): hyper-detailed digital art, glossy gradients, cartoon clip-art, photorealistic renders, overly saturated colors
- Keep the TOP 40% of the image simpler (solid color, subtle texture, or sky) — this is where the title goes
- Use a MUTED, SOPHISTICATED palette — not bright primary colors
- Describe specific textures: paper grain, canvas texture, brush strokes, ink wash
- Aspect ratio is portrait 2:3 (book cover format)
- CRITICAL: End with "No text, no words, no letters, no numbers, no writing of any kind."

━━━ TEXT OVERLAY CSS — PROFESSIONAL TYPOGRAPHY ━━━
FONT SIZE RULES (at 300 DPI, these are MINIMUM sizes):
- Main title: 280px+ font-size (MUST be the dominant visual element)
- Subtitle/tagline: 80px-120px font-size
- Author name: 55px-80px font-size

AVAILABLE GOOGLE FONTS (pre-loaded — use these, NOT web-safe fallbacks):
SERIF (elegant, editorial):
- 'Playfair Display' — high-contrast serif, perfect for bold display titles
- 'Cormorant Garamond' — refined, light, elegant serif
- 'DM Serif Display' — strong, modern serif display face
- 'Lora' — well-balanced contemporary serif
- 'Merriweather' — designed for readability, warm
- 'Libre Baskerville' — classic, editorial serif
- 'Source Serif 4' — clean, versatile serif

SANS-SERIF (clean, modern):
- 'Montserrat' — geometric, works great for subtitles and callouts
- 'Raleway' — thin/elegant sans-serif, great for letter-spaced subtitles
- 'Josefin Sans' — distinctive, geometric, vintage-modern feel

PROFESSIONAL FONT PAIRING EXAMPLES:
- Title: 'Playfair Display', serif (weight 700-900) + Subtitle: 'Montserrat', sans-serif (weight 400-500, letter-spacing: 6px)
- Title: 'DM Serif Display', serif (weight 400) + Subtitle: 'Raleway', sans-serif (weight 500, uppercase)
- Title: 'Merriweather', serif (weight 900) + Subtitle: 'Josefin Sans', sans-serif (weight 300)
- Title: 'Cormorant Garamond', serif (weight 700, large size) + Subtitle: 'Montserrat', sans-serif (weight 600)

TYPOGRAPHY RULES:
- Use TWO contrasting fonts: one serif for title, one sans-serif for subtitle/callouts (or vice versa)
- TITLE: Choose a distinctive serif with WEIGHT CONTRAST — use 700-900 weight
- SUBTITLE: Use a CONTRASTING family at lighter weight (300-500) with LETTER-SPACING (4px-12px) and often text-transform: uppercase
- AUTHOR: Small, understated, letter-spaced sans-serif at bottom
- Use COLOR in typography — title color should complement artwork (deep navy, burgundy, forest green, warm brown — NOT plain black)
- Create hierarchy through SIZE + WEIGHT + FAMILY contrast, not through colored boxes or badges
- Limit front cover to MAX 3-4 text elements: title, subtitle, author (plus one optional callout integrated as a line, not a badge)

WHAT LOOKS AMATEUR (NEVER DO THIS):
- All caps black Arial/Helvetica for everything
- Background-color boxes behind each line of text
- Stacked colored badges (WORD SEARCH / 55 WORDS / LARGE PRINT)
- Same font family and weight for all elements
- Plain black text on everything
- Gray/white semi-transparent boxes behind text

READABILITY ON ARTWORK:
- PREFERRED: Position title in the top portion where artwork is simpler
- Use text-shadow for readability: 2px 2px 6px rgba(0,0,0,0.5) for dark text on light art, or 2px 2px 6px rgba(0,0,0,0.8) for light text on darker art
- For a professional callout: use a thin horizontal rule (border-top: 2px solid) as a divider, not a colored badge
- If you MUST use a badge: ONE only, thin, with subtle border instead of solid background

CSS RULES:
- Use Google Fonts listed above (they are pre-loaded via <link>)
- NO url() references (artwork injected separately)
- NO @import for fonts (already loaded), NO position: fixed, NO JavaScript
- .bleed-fill background: use a color from the artwork's palette
- Override .front-cover justify-content if needed (e.g., flex-start for top-anchored titles)

DESIGN QUALITY CHECKLIST:
✓ Uses TWO contrasting Google Fonts (serif + sans-serif pairing)
✓ Title has a distinctive color (not plain black) that complements the artwork
✓ Subtitle uses contrasting font family, lighter weight, letter-spacing
✓ MAX 3-4 text elements on front cover
✓ NO colored background boxes behind text — use text-shadow instead
✓ Typography creates clear hierarchy through size, weight, and family contrast
✓ Would look credible on Amazon's bestseller page next to professionally designed books

BOOK TYPE: {book_type}
NICHE: {niche_keyword}

━━━ OUTPUT ━━━
Return ONLY this JSON (no markdown fences, no commentary):
{{
  "design_notes": "Design strategy: typography approach, color palette (#hex values), artwork style, how text and art work together",
  "image_prompt": "Professional artwork description. Specify painterly/textured style, muted palette, composition with clear text zones. End with: No text, no words, no letters, no numbers, no writing of any kind.",
  "style_css": "CSS with professional typography — letter-spacing, restrained palette, max 4 front elements",
  "front_html": "HTML fragment — MAX 4 elements. Uses ${{title}}, ${{author}}, ${{subtitle}}, ${{puzzle_count}}",
  "back_html": "HTML fragment for professional back cover",
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

    # Check for external resource references (allow artwork.png only)
    url_matches = re.findall(r'url\s*\([^)]*\)', css, re.IGNORECASE)
    for url_match in url_matches:
        if 'artwork.png' not in url_match:
            issues.append(f"Contains disallowed url() reference: {url_match}")

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
    # Remove url() references EXCEPT artwork.png
    def _remove_non_artwork_urls(match):
        if 'artwork.png' in match.group(0):
            return match.group(0)
        return '/* removed url() */'
    css = re.sub(r'url\s*\([^)]*\)', _remove_non_artwork_urls, css, flags=re.IGNORECASE)
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


def _enforce_design_quality(style_css: str, front_html: str) -> tuple[str, str]:
    """
    Quality gate: enforce minimum professional standards for KDP covers.
    Fixes common AI generation issues that make covers look amateurish.

    Returns (fixed_css, fixed_html)
    """
    fixes = []

    # 1. Boost any title font-size below 280px to 320px
    def _boost_title_size(match):
        full = match.group(0)
        size_match = re.search(r'font-size\s*:\s*(\d+)px', full)
        if size_match:
            size = int(size_match.group(1))
            if size < 280:
                fixes.append(f"Title font {size}px → 320px")
                return full.replace(f"font-size: {size}px", "font-size: 320px")
        return full

    # Look for main-title or title-section with small fonts
    style_css = re.sub(
        r'\.main-title\s*\{[^}]+\}',
        _boost_title_size,
        style_css,
        flags=re.IGNORECASE
    )

    # 2. Boost any subtitle font-size below 90px
    def _boost_subtitle_size(match):
        full = match.group(0)
        size_match = re.search(r'font-size\s*:\s*(\d+)px', full)
        if size_match:
            size = int(size_match.group(1))
            if size < 90:
                fixes.append(f"Subtitle font {size}px → 100px")
                return full.replace(f"font-size: {size}px", "font-size: 100px")
        return full

    style_css = re.sub(
        r'\.subtitle\s*\{[^}]+\}',
        _boost_subtitle_size,
        style_css,
        flags=re.IGNORECASE
    )

    # 3. Remove "font size" badge elements from HTML (they look cheap)
    front_html = re.sub(
        r'<div[^>]*class="[^"]*font-size[^"]*"[^>]*>.*?</div>',
        '',
        front_html,
        flags=re.IGNORECASE | re.DOTALL
    )

    # 4. Ensure text-shadow on main title for artwork readability
    if '.main-title' in style_css and 'text-shadow' not in style_css.split('.main-title')[1].split('}')[0]:
        style_css = style_css.replace(
            '.main-title {',
            '.main-title { text-shadow: 3px 3px 0 rgba(0,0,0,0.3), 0 0 20px rgba(0,0,0,0.15);'
        )
        fixes.append("Added text-shadow to title")

    if fixes:
        logger.info(f"Quality gate applied {len(fixes)} fixes: {', '.join(fixes)}")

    return style_css, front_html


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ARTWORK GENERATION (OpenAI GPT Image)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def generate_cover_artwork(
    image_prompt: str,
    output_path: Path,
    size: str = "1024x1536",
) -> Optional[Path]:
    """
    Generate cover artwork using OpenAI's gpt-image-1.

    Args:
        image_prompt: Detailed prompt for artwork generation (no text)
        output_path: Directory to save the artwork PNG
        size: Image dimensions ("1024x1536" for portrait book cover)

    Returns:
        Path to saved artwork.png, or None on failure
    """
    from ..config import OPENAI_API_KEY

    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — skipping artwork generation")
        return None

    try:
        import asyncio
        from openai import OpenAI

        # Reinforce professional quality and no-text rules
        full_prompt = (
            f"Create a PROFESSIONAL book cover artwork that looks like it was painted or "
            f"illustrated by a skilled human artist — NOT like AI-generated art. "
            f"Portrait orientation (2:3 aspect ratio). "
            f"{image_prompt} "
            "STYLE REQUIREMENTS: Use visible brush strokes, paper texture, or print grain. "
            "Avoid glossy digital perfection — add subtle imperfections that make it look handmade. "
            "Use a MUTED, SOPHISTICATED color palette — no oversaturated or neon colors. "
            "COMPOSITION: The TOP 40% must have simpler, calmer areas (sky, solid color, subtle pattern) "
            "where title text will be overlaid — the text is added separately. "
            "The image must contain absolutely NO text, NO words, NO letters, "
            "NO numbers, NO writing of any kind. Pure artwork and illustration only."
        )

        logger.info(f"Generating cover artwork via gpt-image-1 ({size})...")
        logger.info(f"Prompt: {full_prompt[:120]}...")

        # Run synchronous OpenAI call in executor to avoid blocking
        client = OpenAI(api_key=OPENAI_API_KEY)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: client.images.generate(
                model="gpt-image-1",
                prompt=full_prompt,
                size=size,
                n=1,
            ),
        )

        # Save the image
        artwork_path = output_path / "artwork.png"
        image_data = result.data[0]

        if hasattr(image_data, 'b64_json') and image_data.b64_json:
            image_bytes = base64.b64decode(image_data.b64_json)
        elif hasattr(image_data, 'url') and image_data.url:
            import httpx
            resp = httpx.get(image_data.url, timeout=30)
            resp.raise_for_status()
            image_bytes = resp.content
        else:
            logger.error("No image data returned from OpenAI")
            return None

        artwork_path.write_bytes(image_bytes)
        logger.info(f"Saved generated artwork: {artwork_path} ({len(image_bytes):,} bytes)")
        return artwork_path

    except Exception as e:
        logger.error(f"Artwork generation failed: {e}")
        return None


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
        cached_artwork = cached_dir / "artwork.png"
        return GeneratedDesign(
            template_css=(cached_dir / "style.css").read_text(encoding="utf-8"),
            front_cover_html=(cached_dir / "front.html").read_text(encoding="utf-8"),
            back_cover_html=(cached_dir / "back.html").read_text(encoding="utf-8"),
            spine_html=(cached_dir / "spine.html").read_text(encoding="utf-8"),
            design_notes="Loaded from cache",
            reference_asin=reference_asin,
            success=True,
            artwork_path=str(cached_artwork) if cached_artwork.exists() else None,
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
        image_prompt = parsed.get("image_prompt", "")

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

        # Apply quality gate — enforce minimum font sizes, remove cheap elements
        style_css, front_html = _enforce_design_quality(style_css, front_html)

        # Generate cover artwork via OpenAI if we have an image prompt
        artwork_path = None
        if image_prompt:
            from ..config import TEMPLATES_DIR
            variant_id_local = f"ai_{reference_asin}" if reference_asin else "ai_custom"
            artwork_dir = TEMPLATES_DIR / book_type / "variants" / variant_id_local
            artwork_dir.mkdir(parents=True, exist_ok=True)

            artwork_path = await generate_cover_artwork(
                image_prompt=image_prompt,
                output_path=artwork_dir,
                size="1024x1536",
            )

        # If artwork was generated, inject it as front-cover background
        if artwork_path:
            artwork_css = """
/* ── AI-generated artwork background ── */
.front-cover {
    background-image: url('artwork.png');
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
}
"""
            style_css = artwork_css + "\n" + style_css
            design_notes = f"[Artwork generated] {design_notes}"

        return GeneratedDesign(
            template_css=style_css,
            front_cover_html=front_html,
            back_cover_html=back_html,
            spine_html=spine_html,
            design_notes=design_notes,
            reference_asin=reference_asin,
            success=True,
            artwork_path=str(artwork_path) if artwork_path else None,
            image_prompt=image_prompt,
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
        "has_artwork": design.artwork_path is not None,
        "image_prompt": design.image_prompt or "",
    }
    (variant_dir / "variant.json").write_text(
        json.dumps(variant_meta, indent=2), encoding="utf-8"
    )

    logger.info(f"Saved AI-generated design variant: {variant_dir}")
    return variant_dir
