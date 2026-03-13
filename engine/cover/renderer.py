"""
SCRPT Cover Renderer
======================
Renders HTML/CSS cover templates to print-ready PDFs at 300 DPI
using Playwright's headless browser.

The workflow:
1. Calculate cover dimensions (from dimensions.py)
2. Inject CSS variables into the HTML template
3. Render via Playwright at 300 DPI (deviceScaleFactor)
4. Export as PDF and PNG

This gives us full CSS typography, any font, gradients,
borders, shadows — everything a professional cover needs.
"""

import asyncio
from pathlib import Path
from string import Template
from typing import Optional

from .dimensions import calculate_cover, generate_cover_css, CoverDimensions


# ── Template System ──────────────────────────────────────────────

COVER_TEMPLATE_HTML = Template("""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
/* ── Injected cover dimensions ── */
${cover_css}

/* ── Base layout ── */
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    width: var(--total-width);
    height: var(--total-height);
    overflow: hidden;
    font-family: 'Georgia', 'Times New Roman', serif;
}

.cover {
    position: relative;
    width: var(--total-width);
    height: var(--total-height);
    display: flex;
    flex-direction: row;
}

/* ── Cover sections ── */
.back-cover {
    position: absolute;
    left: var(--bleed);
    top: var(--bleed);
    width: var(--back-cover-width);
    height: calc(var(--total-height) - 2 * var(--bleed));
    overflow: hidden;
}

.spine {
    position: absolute;
    left: var(--spine-start);
    top: var(--bleed);
    width: var(--spine-width);
    height: calc(var(--total-height) - 2 * var(--bleed));
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
}

.spine-text {
    writing-mode: vertical-rl;
    text-orientation: mixed;
    transform: rotate(180deg);
    font-size: 14px;
    font-weight: bold;
    letter-spacing: 1px;
    white-space: nowrap;
    color: white;
    text-shadow: 0 1px 2px rgba(0,0,0,0.3);
}

.front-cover {
    position: absolute;
    left: var(--front-start);
    top: var(--bleed);
    width: var(--front-cover-width);
    height: calc(var(--total-height) - 2 * var(--bleed));
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    padding: var(--safe-zone);
}

/* ── Barcode zone ── */
.barcode-zone {
    position: absolute;
    left: var(--barcode-x);
    top: var(--barcode-y);
    width: var(--barcode-width);
    height: var(--barcode-height);
    border: 2px dashed rgba(255,255,255,0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    color: rgba(255,255,255,0.5);
}

/* ── Bleed area (background extends into it) ── */
.bleed-fill {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: -1;
}

/* ── Custom template styles ── */
${template_css}
</style>
</head>
<body>
<div class="cover">
    <div class="bleed-fill" id="bleed-fill"></div>

    <!-- Back Cover -->
    <div class="back-cover" id="back-cover">
        ${back_cover_html}
        <div class="barcode-zone">ISBN BARCODE</div>
    </div>

    <!-- Spine -->
    <div class="spine" id="spine">
        ${spine_html}
    </div>

    <!-- Front Cover -->
    <div class="front-cover" id="front-cover">
        ${front_cover_html}
    </div>
</div>
</body>
</html>""")


# ── Niche-specific template content ─────────────────────────────

NICHE_TEMPLATES = {
    "word_search": {
        "template_css": """
            .bleed-fill {
                background: linear-gradient(135deg, #1a365d 0%, #2d3748 40%, #1a365d 100%);
            }
            .spine { background: #1a365d; }
            .back-cover {
                background: #1a365d;
                padding: 80px;
                color: white;
            }
            .back-cover h3 {
                font-size: 28px;
                margin-bottom: 20px;
                font-family: 'Georgia', serif;
            }
            .back-cover p {
                font-size: 16px;
                line-height: 1.6;
                opacity: 0.9;
            }
            .front-cover {
                background: linear-gradient(180deg, #ebf8ff 0%, #bee3f8 100%);
                text-align: center;
                color: #1a365d;
            }
            .title {
                font-size: 72px;
                font-weight: bold;
                font-family: 'Georgia', serif;
                line-height: 1.1;
                margin-bottom: 20px;
                color: #1a365d;
            }
            .subtitle {
                font-size: 32px;
                font-family: 'Georgia', serif;
                color: #2b6cb0;
                margin-bottom: 40px;
            }
            .badge {
                background: #1a365d;
                color: white;
                padding: 12px 36px;
                border-radius: 50px;
                font-size: 22px;
                font-weight: bold;
                letter-spacing: 2px;
                margin-bottom: 30px;
            }
            .puzzle-count {
                font-size: 24px;
                color: #4a5568;
                margin-bottom: 60px;
            }
            .author {
                font-size: 28px;
                color: #4a5568;
                font-family: 'Georgia', serif;
            }
            .decorative {
                width: 120px;
                height: 4px;
                background: #2b6cb0;
                margin: 20px auto;
                border-radius: 2px;
            }
        """,
        "front_cover_html": """
            <div class="title">${title}</div>
            <div class="decorative"></div>
            <div class="subtitle">${subtitle}</div>
            <div class="badge">LARGE PRINT</div>
            <div class="puzzle-count">${puzzle_count} Puzzles</div>
            <div class="author">${author}</div>
        """,
        "back_cover_html": """
            <h3>About This Book</h3>
            <p>Challenge your mind with ${puzzle_count} carefully crafted word search puzzles.
            Large print format makes every letter easy to see.
            Perfect for relaxing at home or on the go.</p>
            <p style="margin-top: 30px;">Features:</p>
            <p>&#8226; Large, easy-to-read letters</p>
            <p>&#8226; ${puzzle_count} unique themed puzzles</p>
            <p>&#8226; Complete answer key included</p>
            <p>&#8226; Premium quality paper</p>
        """,
        "spine_html": '<div class="spine-text">${title} &mdash; ${author}</div>',
    },

    "sudoku": {
        "template_css": """
            .bleed-fill { background: linear-gradient(135deg, #2d3748 0%, #4a5568 100%); }
            .spine { background: #2d3748; }
            .back-cover { background: #2d3748; padding: 80px; color: white; }
            .back-cover h3 { font-size: 28px; margin-bottom: 20px; }
            .back-cover p { font-size: 16px; line-height: 1.6; opacity: 0.9; }
            .front-cover {
                background: linear-gradient(180deg, #fefcbf 0%, #f6e05e 100%);
                text-align: center; color: #2d3748;
            }
            .title { font-size: 72px; font-weight: bold; font-family: 'Georgia', serif; line-height: 1.1; margin-bottom: 20px; }
            .subtitle { font-size: 32px; color: #4a5568; margin-bottom: 30px; }
            .badge { background: #2d3748; color: #f6e05e; padding: 12px 36px; border-radius: 50px; font-size: 22px; font-weight: bold; letter-spacing: 2px; margin-bottom: 30px; }
            .author { font-size: 28px; color: #4a5568; margin-top: 40px; }
            .decorative { width: 120px; height: 4px; background: #d69e2e; margin: 20px auto; border-radius: 2px; }
        """,
        "front_cover_html": """
            <div class="title">${title}</div>
            <div class="decorative"></div>
            <div class="subtitle">${subtitle}</div>
            <div class="badge">LARGE PRINT</div>
            <div class="author">${author}</div>
        """,
        "back_cover_html": """
            <h3>About This Book</h3>
            <p>Enjoy hours of brain-training fun with these carefully crafted sudoku puzzles.</p>
        """,
        "spine_html": '<div class="spine-text">${title} &mdash; ${author}</div>',
    },

    "cryptogram": {
        "template_css": """
            .bleed-fill { background: linear-gradient(135deg, #2c5282 0%, #2b6cb0 100%); }
            .spine { background: #2c5282; }
            .back-cover { background: #2c5282; padding: 80px; color: white; }
            .back-cover h3 { font-size: 28px; margin-bottom: 20px; }
            .back-cover p { font-size: 16px; line-height: 1.6; opacity: 0.9; }
            .front-cover {
                background: linear-gradient(180deg, #ebf4ff 0%, #c3dafe 100%);
                text-align: center; color: #2c5282;
            }
            .title { font-size: 66px; font-weight: bold; font-family: 'Georgia', serif; line-height: 1.1; margin-bottom: 20px; }
            .subtitle { font-size: 28px; color: #4c51bf; margin-bottom: 30px; }
            .badge { background: #2c5282; color: white; padding: 12px 36px; border-radius: 50px; font-size: 22px; font-weight: bold; margin-bottom: 30px; }
            .author { font-size: 28px; color: #4a5568; margin-top: 40px; }
            .decorative { width: 120px; height: 4px; background: #4c51bf; margin: 20px auto; }
        """,
        "front_cover_html": """
            <div class="title">${title}</div>
            <div class="decorative"></div>
            <div class="subtitle">${subtitle}</div>
            <div class="badge">LARGE PRINT</div>
            <div class="author">${author}</div>
        """,
        "back_cover_html": """
            <h3>About This Book</h3>
            <p>Decode famous quotes and sayings in these entertaining cryptogram puzzles. Complete answer key included.</p>
        """,
        "spine_html": '<div class="spine-text">${title} &mdash; ${author}</div>',
    },

    "default": {
        "template_css": """
            .bleed-fill { background: linear-gradient(135deg, #2d3748 0%, #4a5568 100%); }
            .spine { background: #2d3748; }
            .back-cover { background: #2d3748; padding: 80px; color: white; }
            .back-cover h3 { font-size: 28px; margin-bottom: 20px; }
            .back-cover p { font-size: 16px; line-height: 1.6; opacity: 0.9; }
            .front-cover {
                background: linear-gradient(180deg, #f7fafc 0%, #edf2f7 100%);
                text-align: center; color: #2d3748;
            }
            .title { font-size: 66px; font-weight: bold; font-family: 'Georgia', serif; line-height: 1.1; margin-bottom: 20px; }
            .subtitle { font-size: 28px; color: #4a5568; margin-bottom: 30px; }
            .author { font-size: 28px; color: #4a5568; margin-top: 40px; }
            .decorative { width: 120px; height: 4px; background: #4a5568; margin: 20px auto; }
        """,
        "front_cover_html": """
            <div class="title">${title}</div>
            <div class="decorative"></div>
            <div class="subtitle">${subtitle}</div>
            <div class="author">${author}</div>
        """,
        "back_cover_html": """
            <h3>About This Book</h3>
            <p>A quality publication for your enjoyment.</p>
        """,
        "spine_html": '<div class="spine-text">${title} &mdash; ${author}</div>',
    },
}


def build_cover_html(
    dims: CoverDimensions,
    title: str,
    subtitle: str = "",
    author: str = "",
    book_type: str = "default",
    puzzle_count: int = 55,
) -> str:
    """
    Build the complete HTML for a book cover.

    Args:
        dims: Calculated cover dimensions
        title: Book title
        subtitle: Book subtitle
        author: Author/publisher name
        book_type: Which niche template to use
        puzzle_count: Number of puzzles (for template text)

    Returns:
        Complete HTML string ready for Playwright rendering
    """
    # Get niche template or fall back to default
    niche = NICHE_TEMPLATES.get(book_type, NICHE_TEMPLATES["default"])

    # Get CSS variables from dimensions
    cover_css = generate_cover_css(dims)

    # Build template variables
    template_vars = {
        "title": title,
        "subtitle": subtitle or "",
        "author": author or "",
        "puzzle_count": str(puzzle_count),
    }

    # Substitute variables in niche template content
    front_html = Template(niche["front_cover_html"]).safe_substitute(template_vars)
    back_html = Template(niche["back_cover_html"]).safe_substitute(template_vars)
    spine_html = Template(niche["spine_html"]).safe_substitute(template_vars)

    # Don't render spine text if book is too thin
    if not dims.spine_has_text:
        spine_html = ""

    # Build final HTML
    html = COVER_TEMPLATE_HTML.substitute(
        cover_css=cover_css,
        template_css=niche["template_css"],
        front_cover_html=front_html,
        back_cover_html=back_html,
        spine_html=spine_html,
    )

    return html


async def render_cover(
    page_count: int,
    trim_size: str,
    paper_type: str,
    title: str,
    subtitle: str = "",
    author: str = "",
    book_type: str = "default",
    output_dir: Optional[Path] = None,
    puzzle_count: int = 55,
) -> dict:
    """
    Generate a complete book cover — HTML → PDF + PNG via Playwright.

    Args:
        page_count: Interior page count
        trim_size: e.g., "8.5x11"
        paper_type: e.g., "white_bw"
        title: Book title
        subtitle: Book subtitle
        author: Author name
        book_type: Niche template key
        output_dir: Where to save files
        puzzle_count: For template text

    Returns:
        Dict with paths to cover.pdf and cover-front.png
    """
    # Calculate dimensions
    dims = calculate_cover(page_count, trim_size, paper_type)

    # Build HTML
    html = build_cover_html(
        dims=dims,
        title=title,
        subtitle=subtitle,
        author=author,
        book_type=book_type,
        puzzle_count=puzzle_count,
    )

    if output_dir is None:
        output_dir = Path(".")
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "cover.html"
    pdf_path = output_dir / "cover.pdf"
    png_path = output_dir / "cover-front.png"

    # Save HTML for debugging
    html_path.write_text(html, encoding="utf-8")

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={
                    "width": dims.total_width_px,
                    "height": dims.total_height_px,
                },
                device_scale_factor=1,  # Already at 300 DPI via pixel sizing
            )

            await page.set_content(html, wait_until="networkidle")

            # Export full cover PDF
            await page.pdf(
                path=str(pdf_path),
                width=f"{dims.total_width}in",
                height=f"{dims.total_height}in",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )

            # Export front cover PNG for preview
            # Crop to just the front cover area
            await page.screenshot(
                path=str(png_path),
                clip={
                    "x": dims.front_cover_start_px,
                    "y": 0,
                    "width": dims.trim_width_px + dims.bleed_px,
                    "height": dims.total_height_px,
                },
            )

            await browser.close()

        return {
            "success": True,
            "cover_pdf": str(pdf_path),
            "cover_png": str(png_path),
            "cover_html": str(html_path),
            "dimensions": {
                "total_width_px": dims.total_width_px,
                "total_height_px": dims.total_height_px,
                "spine_width": round(dims.spine_width, 4),
            },
        }

    except ImportError:
        # Playwright not installed — generate HTML only
        return {
            "success": True,
            "cover_html": str(html_path),
            "cover_pdf": None,
            "cover_png": None,
            "note": "Playwright not installed. HTML template saved. Install with: pip3 install playwright && python3 -m playwright install chromium",
            "dimensions": {
                "total_width_px": dims.total_width_px,
                "total_height_px": dims.total_height_px,
                "spine_width": round(dims.spine_width, 4),
            },
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "cover_html": str(html_path),
        }


def render_cover_sync(
    page_count: int,
    trim_size: str,
    paper_type: str,
    title: str,
    subtitle: str = "",
    author: str = "",
    book_type: str = "default",
    output_dir: Optional[Path] = None,
    puzzle_count: int = 55,
) -> dict:
    """Synchronous wrapper for render_cover."""
    return asyncio.run(render_cover(
        page_count=page_count,
        trim_size=trim_size,
        paper_type=paper_type,
        title=title,
        subtitle=subtitle,
        author=author,
        book_type=book_type,
        output_dir=output_dir,
        puzzle_count=puzzle_count,
    ))


if __name__ == "__main__":
    # Test cover generation
    output = Path("/Users/tiger/Desktop/CATALOG ENGINE/bookr/output/test_cover")
    result = render_cover_sync(
        page_count=120,
        trim_size="8.5x11",
        paper_type="white_bw",
        title="Ultimate Word Search",
        subtitle="Large Print Puzzles for Seniors",
        author="Creative Puzzles Press",
        book_type="word_search",
        output_dir=output,
        puzzle_count=55,
    )
    print(f"Cover generated:")
    for k, v in result.items():
        print(f"  {k}: {v}")
