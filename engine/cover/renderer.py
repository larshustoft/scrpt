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

/* ── Force single-page PDF at exact content size ── */
@page {
    size: var(--total-width) var(--total-height);
    margin: 0;
}

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
    font-size: 42px;
    font-weight: bold;
    letter-spacing: 3px;
    white-space: nowrap;
    color: white;
    text-shadow: 0 2px 4px rgba(0,0,0,0.3);
    font-family: 'Georgia', serif;
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
            /* ── Background ── */
            .bleed-fill {
                background: linear-gradient(160deg, #0f2027 0%, #1a365d 35%, #203a5c 65%, #0f2027 100%);
            }
            .spine { background: #142d4c; }

            /* ── Back Cover ── */
            .back-cover {
                background: #142d4c;
                padding: 120px 90px 330px;
                color: white;
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            .back-header {
                font-size: 52px;
                font-family: Arial, Helvetica, sans-serif;
                font-weight: bold;
                color: #e2b44d;
                letter-spacing: 12px;
                margin-bottom: 40px;
                text-align: center;
                text-transform: uppercase;
            }
            .preview-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 36px;
                width: 100%;
                flex: 1;
            }
            .preview-card {
                background: white;
                border-radius: 10px;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                box-shadow: 0 6px 24px rgba(0,0,0,0.4);
            }
            .card-header {
                background: linear-gradient(135deg, #f0f0f0, #e4e4e4);
                padding: 14px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 2px solid #d0d0d0;
            }
            .card-num {
                font-size: 22px;
                font-weight: bold;
                color: #333;
                font-family: Arial, sans-serif;
            }
            .card-theme {
                font-size: 20px;
                color: #666;
                font-family: 'Georgia', serif;
                font-style: italic;
            }
            .card-grid-wrap {
                padding: 14px 18px 10px;
                flex: 1;
                display: flex;
                align-items: stretch;
                justify-content: stretch;
            }
            .card-grid {
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                grid-template-rows: repeat(7, 1fr);
                gap: 1px;
                width: 100%;
                border: 2px solid #bbb;
                background: #d0d0d0;
            }
            .card-grid span {
                font-size: 34px;
                font-family: 'Courier New', monospace;
                font-weight: bold;
                color: #444;
                background: white;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .card-grid span.h {
                background: #fef3c7;
                color: #b91c1c;
            }
            .card-words {
                padding: 12px 20px 16px;
                display: flex;
                gap: 18px;
                justify-content: center;
                background: #f8f8f8;
                border-top: 1px solid #e0e0e0;
                flex-wrap: wrap;
            }
            .card-words span {
                font-size: 20px;
                font-family: Arial, sans-serif;
                font-weight: bold;
                color: #555;
                letter-spacing: 2px;
            }
            .back-features {
                font-size: 38px;
                color: rgba(255,255,255,0.75);
                letter-spacing: 3px;
                margin-top: 45px;
                text-align: center;
                font-family: Arial, Helvetica, sans-serif;
                line-height: 1.9;
            }

            /* ── Front Cover — Bold dark design ── */
            .front-cover {
                background: linear-gradient(175deg, #0c2340 0%, #163a5f 40%, #1a4a6e 60%, #0c2340 100%);
                text-align: center;
                color: white;
                position: relative;
                overflow: hidden;
                justify-content: center;
                padding-top: 0;
                padding-bottom: 120px;
            }

            /* Grid pattern overlay */
            .front-cover::before {
                content: '';
                position: absolute;
                top: 0; left: 0; right: 0; bottom: 0;
                background-image:
                    linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
                background-size: 130px 130px;
                z-index: 0;
            }

            .front-cover > * { position: relative; z-index: 1; }

            /* ── LARGE PRINT banner at top ── */
            .top-banner {
                background: linear-gradient(135deg, #c0392b 0%, #e74c3c 50%, #c0392b 100%);
                color: white;
                padding: 22px 120px;
                font-size: 64px;
                font-weight: bold;
                letter-spacing: 10px;
                font-family: Arial, Helvetica, sans-serif;
                margin-bottom: 60px;
                box-shadow: 0 8px 25px rgba(0,0,0,0.4);
            }

            /* ── Main title "WORD SEARCH" huge ── */
            .title-main {
                font-size: 280px;
                font-weight: bold;
                font-family: Arial, Helvetica, sans-serif;
                line-height: 1.0;
                color: white;
                text-shadow: 4px 6px 12px rgba(0,0,0,0.3);
                letter-spacing: 6px;
                margin-bottom: 10px;
            }

            /* ── Sub-title target audience ── */
            .title-audience {
                font-size: 130px;
                font-weight: bold;
                font-family: 'Georgia', serif;
                color: #f4d03f;
                margin-bottom: 50px;
                text-shadow: 2px 4px 8px rgba(0,0,0,0.3);
            }

            .decorative {
                width: 600px;
                height: 6px;
                background: linear-gradient(90deg, transparent, rgba(244,208,63,0.6), transparent);
                margin: 10px auto 40px;
            }

            .subtitle {
                font-size: 80px;
                font-family: 'Georgia', serif;
                color: rgba(255,255,255,0.85);
                margin-bottom: 40px;
                font-style: italic;
            }

            /* ── Decorative word search grid ── */
            .grid-motif {
                display: grid;
                grid-template-columns: repeat(10, 1fr);
                gap: 4px;
                width: 1400px;
                margin: 40px auto 60px;
                padding: 40px;
                background: rgba(255,255,255,0.06);
                border-radius: 24px;
                border: 3px solid rgba(255,255,255,0.10);
            }
            .grid-motif span {
                font-size: 68px;
                font-family: 'Courier New', monospace;
                font-weight: bold;
                color: rgba(255,255,255,0.18);
                text-align: center;
                line-height: 1.4;
            }
            .grid-motif span.hl {
                color: #f4d03f;
                opacity: 0.8;
            }

            /* ── Puzzle count badge ── */
            .puzzle-badge {
                background: linear-gradient(135deg, #f4d03f 0%, #f39c12 100%);
                color: #0c2340;
                padding: 30px 100px;
                border-radius: 100px;
                font-size: 72px;
                font-weight: bold;
                font-family: Arial, Helvetica, sans-serif;
                margin-bottom: 25px;
                box-shadow: 0 8px 25px rgba(0,0,0,0.3);
                letter-spacing: 3px;
            }

            .features-text {
                font-size: 48px;
                color: rgba(255,255,255,0.65);
                margin-bottom: 40px;
                letter-spacing: 2px;
            }

            /* ── Bottom section ── */
            .bottom-section {
                width: 100%;
                text-align: center;
                margin-top: 60px;
            }

            .bottom-divider {
                width: 500px;
                height: 3px;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.25), transparent);
                margin: 0 auto 40px;
            }

            .author {
                font-size: 72px;
                color: rgba(255,255,255,0.75);
                font-family: 'Georgia', serif;
                letter-spacing: 4px;
            }

            /* ── Bottom accent ── */
            .bottom-accent {
                width: 100%;
                height: 50px;
                background: linear-gradient(90deg, #c0392b, #e74c3c, #c0392b);
                position: absolute;
                bottom: 0;
                left: 0;
                z-index: 2;
            }
        """,
        "front_cover_html": """
            <div class="top-banner">LARGE PRINT</div>
            <div class="title-main">WORD<br>SEARCH</div>
            <div class="title-audience">for Seniors</div>
            <div class="decorative"></div>
            <div class="subtitle">${subtitle}</div>
            <div class="grid-motif">
                <span class="hl">W</span><span>G</span><span>T</span><span class="hl">O</span><span>N</span><span>P</span><span class="hl">R</span><span>K</span><span class="hl">D</span><span>M</span>
                <span>A</span><span class="hl">S</span><span>M</span><span>B</span><span class="hl">E</span><span>Q</span><span>F</span><span class="hl">A</span><span>L</span><span>V</span>
                <span>H</span><span>R</span><span class="hl">R</span><span>D</span><span>U</span><span class="hl">C</span><span>W</span><span>E</span><span class="hl">H</span><span>J</span>
                <span class="hl">P</span><span>K</span><span>M</span><span class="hl">U</span><span>T</span><span>B</span><span class="hl">Z</span><span>O</span><span class="hl">Z</span><span>N</span>
                <span>Y</span><span class="hl">L</span><span>A</span><span>N</span><span class="hl">E</span><span>R</span><span>G</span><span class="hl">I</span><span>C</span><span>Q</span>
                <span>D</span><span>F</span><span class="hl">S</span><span>X</span><span>W</span><span class="hl">N</span><span>O</span><span>R</span><span>T</span><span class="hl">E</span>
                <span class="hl">B</span><span>I</span><span>V</span><span class="hl">G</span><span>J</span><span>A</span><span class="hl">M</span><span>H</span><span>K</span><span class="hl">F</span>
            </div>
            <div class="puzzle-badge">${puzzle_count} THEMED PUZZLES</div>
            <div class="features-text">Complete Answer Key Included</div>
            <div class="bottom-section">
                <div class="bottom-divider"></div>
                <div class="author">${author}</div>
            </div>
            <div class="bottom-accent"></div>
        """,
        "back_cover_html": """
            <div class="back-header">&#9733; Look Inside &#9733;</div>
            <div class="preview-grid">
                <div class="preview-card">
                    <div class="card-header">
                        <span class="card-num">Puzzle 1</span>
                        <span class="card-theme">Garden Flowers</span>
                    </div>
                    <div class="card-grid-wrap"><div class="card-grid">
                        <span>R</span><span>M</span><span>T</span><span>U</span><span>K</span><span>P</span><span>Q</span>
                        <span class="h">D</span><span class="h">A</span><span class="h">I</span><span class="h">S</span><span class="h">Y</span><span>W</span><span>B</span>
                        <span>A</span><span>O</span><span>N</span><span>F</span><span>J</span><span>G</span><span>V</span>
                        <span class="h">R</span><span>X</span><span>E</span><span>C</span><span>I</span><span>L</span><span>H</span>
                        <span class="h">O</span><span>H</span><span>A</span><span>R</span><span>N</span><span>S</span><span>W</span>
                        <span class="h">S</span><span class="h">T</span><span class="h">U</span><span class="h">L</span><span class="h">I</span><span class="h">P</span><span>E</span>
                        <span class="h">E</span><span>F</span><span>Q</span><span>Z</span><span>D</span><span>M</span><span>J</span>
                    </div></div>
                    <div class="card-words"><span>DAISY</span><span>TULIP</span><span>ROSE</span></div>
                </div>
                <div class="preview-card">
                    <div class="card-header">
                        <span class="card-num">Puzzle 14</span>
                        <span class="card-theme">Ocean Life</span>
                    </div>
                    <div class="card-grid-wrap"><div class="card-grid">
                        <span>B</span><span>O</span><span>C</span><span>E</span><span>A</span><span>N</span><span>F</span>
                        <span>S</span><span class="h">S</span><span class="h">H</span><span class="h">E</span><span class="h">L</span><span class="h">L</span><span>K</span>
                        <span class="h">W</span><span class="h">A</span><span class="h">V</span><span class="h">E</span><span class="h">S</span><span>D</span><span>P</span>
                        <span>T</span><span>I</span><span>D</span><span>E</span><span>G</span><span>R</span><span>M</span>
                        <span>Q</span><span>F</span><span>U</span><span>X</span><span class="h">C</span><span>J</span><span>L</span>
                        <span>N</span><span>A</span><span>H</span><span>Y</span><span class="h">O</span><span>V</span><span>Z</span>
                        <span>W</span><span>S</span><span>G</span><span>R</span><span class="h">R</span><span>B</span><span>D</span>
                    </div></div>
                    <div class="card-words"><span>SHELL</span><span>WAVES</span><span>CORAL</span></div>
                </div>
                <div class="preview-card">
                    <div class="card-header">
                        <span class="card-num">Puzzle 27</span>
                        <span class="card-theme">Sweet Treats</span>
                    </div>
                    <div class="card-grid-wrap"><div class="card-grid">
                        <span>L</span><span>M</span><span>N</span><span>G</span><span>R</span><span>P</span><span>W</span>
                        <span class="h">C</span><span class="h">O</span><span class="h">O</span><span class="h">K</span><span class="h">I</span><span class="h">E</span><span>V</span>
                        <span>D</span><span>A</span><span>B</span><span>F</span><span>T</span><span>Q</span><span class="h">C</span>
                        <span>H</span><span>X</span><span class="h">F</span><span class="h">U</span><span class="h">D</span><span class="h">G</span><span class="h">E</span>
                        <span>J</span><span>K</span><span>S</span><span>Y</span><span>Z</span><span>I</span><span>U</span>
                        <span>E</span><span>R</span><span>O</span><span>U</span><span>C</span><span>N</span><span>A</span>
                        <span class="h">C</span><span class="h">A</span><span class="h">K</span><span class="h">E</span><span>P</span><span>W</span><span>B</span>
                    </div></div>
                    <div class="card-words"><span>COOKIE</span><span>FUDGE</span><span>CAKE</span></div>
                </div>
                <div class="preview-card">
                    <div class="card-header">
                        <span class="card-num">Puzzle 42</span>
                        <span class="card-theme">At the Park</span>
                    </div>
                    <div class="card-grid-wrap"><div class="card-grid">
                        <span class="h">B</span><span>V</span><span>K</span><span>W</span><span>Q</span><span>M</span><span>J</span>
                        <span class="h">E</span><span>L</span><span class="h">T</span><span class="h">R</span><span class="h">E</span><span class="h">E</span><span class="h">S</span>
                        <span class="h">N</span><span>P</span><span>U</span><span>H</span><span>G</span><span>R</span><span>A</span>
                        <span class="h">C</span><span>D</span><span>F</span><span>X</span><span>I</span><span>O</span><span>N</span>
                        <span class="h">H</span><span>W</span><span>Y</span><span>M</span><span>B</span><span>S</span><span>L</span>
                        <span>Q</span><span>A</span><span>J</span><span class="h">P</span><span class="h">A</span><span class="h">T</span><span class="h">H</span>
                        <span>R</span><span>G</span><span>Z</span><span>C</span><span>N</span><span>F</span><span>D</span>
                    </div></div>
                    <div class="card-words"><span>BENCH</span><span>TREES</span><span>PATH</span></div>
                </div>
            </div>
            <div class="back-features">${puzzle_count} Themed Puzzles &middot; Large Print &middot; Full Answer Key</div>
        """,
        "spine_html": '<div class="spine-text">${title} &mdash; ${author}</div>',
    },

    "sudoku": {
        "template_css": """
            .bleed-fill { background: linear-gradient(160deg, #1a1a2e 0%, #2d3748 50%, #1a1a2e 100%); }
            .spine { background: #1a1a2e; }
            .back-cover { background: #1a1a2e; padding: 180px 140px; color: white; display: flex; flex-direction: column; justify-content: center; }
            .back-cover h3 { font-size: 72px; margin-bottom: 50px; color: #f6e05e; font-family: 'Georgia', serif; }
            .back-cover p { font-size: 42px; line-height: 1.7; opacity: 0.9; }
            .front-cover {
                background: linear-gradient(175deg, #fffef0 0%, #fef9c3 50%, #fde68a 100%);
                text-align: center; color: #2d3748;
                position: relative; overflow: hidden;
            }
            .front-cover::before {
                content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0;
                background-image:
                    linear-gradient(rgba(45,55,72,0.04) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(45,55,72,0.04) 1px, transparent 1px);
                background-size: 160px 160px;
                z-index: 0;
            }
            .front-cover::after {
                content: ''; position: absolute;
                top: 100px; left: 100px; right: 100px; bottom: 100px;
                border: 6px solid rgba(45,55,72,0.07); border-radius: 30px; z-index: 0;
            }
            .front-cover > * { position: relative; z-index: 1; }
            .top-accent { width: 100%; height: 60px; background: linear-gradient(90deg, #2d3748, #4a5568, #2d3748); position: absolute; top: 0; left: 0; z-index: 2; }
            .title { font-size: 200px; font-weight: bold; font-family: 'Georgia', serif; line-height: 1.12; margin-bottom: 40px; color: #2d3748; max-width: 90%; }
            .decorative { width: 500px; height: 8px; background: linear-gradient(90deg, transparent, #d69e2e, transparent); margin: 30px auto; }
            .subtitle { font-size: 90px; font-family: 'Georgia', serif; color: #92400e; margin-bottom: 60px; font-style: italic; }
            .badge { background: linear-gradient(135deg, #2d3748, #4a5568); color: #f6e05e; padding: 30px 100px; border-radius: 100px; font-size: 72px; font-weight: bold; letter-spacing: 8px; margin-bottom: 50px; box-shadow: 0 8px 30px rgba(45,55,72,0.25); }
            .author { font-size: 72px; color: #6b7280; font-family: 'Georgia', serif; letter-spacing: 2px; }
            .bottom-accent { width: 100%; height: 60px; background: linear-gradient(90deg, #2d3748, #4a5568, #2d3748); position: absolute; bottom: 0; left: 0; z-index: 2; }
            .bottom-section { margin-top: auto; width: 100%; text-align: center; }
            .bottom-divider { width: 300px; height: 4px; background: linear-gradient(90deg, transparent, rgba(45,55,72,0.2), transparent); margin: 0 auto 40px; }
        """,
        "front_cover_html": """
            <div class="top-accent"></div>
            <div class="title">${title}</div>
            <div class="decorative"></div>
            <div class="subtitle">${subtitle}</div>
            <div class="badge">LARGE PRINT</div>
            <div class="bottom-section">
                <div class="bottom-divider"></div>
                <div class="author">${author}</div>
            </div>
            <div class="bottom-accent"></div>
        """,
        "back_cover_html": """
            <h3>About This Book</h3>
            <p>Enjoy hours of brain-training fun with these carefully crafted sudoku puzzles.
            Large print format for easy reading. Complete answer key included.</p>
        """,
        "spine_html": '<div class="spine-text">${title} &mdash; ${author}</div>',
    },

    "cryptogram": {
        "template_css": """
            .bleed-fill { background: linear-gradient(160deg, #1e1b4b 0%, #312e81 50%, #1e1b4b 100%); }
            .spine { background: #1e1b4b; }
            .back-cover { background: #1e1b4b; padding: 180px 140px; color: white; display: flex; flex-direction: column; justify-content: center; }
            .back-cover h3 { font-size: 72px; margin-bottom: 50px; color: #a5b4fc; font-family: 'Georgia', serif; }
            .back-cover p { font-size: 42px; line-height: 1.7; opacity: 0.9; }
            .front-cover {
                background: linear-gradient(175deg, #eef2ff 0%, #e0e7ff 50%, #c7d2fe 100%);
                text-align: center; color: #1e1b4b;
                position: relative; overflow: hidden;
            }
            .front-cover::before {
                content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0;
                background-image:
                    linear-gradient(rgba(30,27,75,0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(30,27,75,0.03) 1px, transparent 1px);
                background-size: 120px 120px;
                z-index: 0;
            }
            .front-cover::after {
                content: ''; position: absolute;
                top: 100px; left: 100px; right: 100px; bottom: 100px;
                border: 6px solid rgba(30,27,75,0.07); border-radius: 30px; z-index: 0;
            }
            .front-cover > * { position: relative; z-index: 1; }
            .top-accent { width: 100%; height: 60px; background: linear-gradient(90deg, #312e81, #4338ca, #312e81); position: absolute; top: 0; left: 0; z-index: 2; }
            .title { font-size: 190px; font-weight: bold; font-family: 'Georgia', serif; line-height: 1.12; margin-bottom: 40px; color: #1e1b4b; max-width: 90%; }
            .decorative { width: 500px; height: 8px; background: linear-gradient(90deg, transparent, #6366f1, transparent); margin: 30px auto; }
            .subtitle { font-size: 90px; font-family: 'Georgia', serif; color: #4338ca; margin-bottom: 60px; font-style: italic; }
            .badge { background: linear-gradient(135deg, #312e81, #4338ca); color: white; padding: 30px 100px; border-radius: 100px; font-size: 72px; font-weight: bold; letter-spacing: 8px; margin-bottom: 50px; box-shadow: 0 8px 30px rgba(30,27,75,0.25); }
            .author { font-size: 72px; color: #6b7280; font-family: 'Georgia', serif; letter-spacing: 2px; }
            .bottom-accent { width: 100%; height: 60px; background: linear-gradient(90deg, #312e81, #4338ca, #312e81); position: absolute; bottom: 0; left: 0; z-index: 2; }
            .bottom-section { margin-top: auto; width: 100%; text-align: center; }
            .bottom-divider { width: 300px; height: 4px; background: linear-gradient(90deg, transparent, rgba(30,27,75,0.2), transparent); margin: 0 auto 40px; }
        """,
        "front_cover_html": """
            <div class="top-accent"></div>
            <div class="title">${title}</div>
            <div class="decorative"></div>
            <div class="subtitle">${subtitle}</div>
            <div class="badge">LARGE PRINT</div>
            <div class="bottom-section">
                <div class="bottom-divider"></div>
                <div class="author">${author}</div>
            </div>
            <div class="bottom-accent"></div>
        """,
        "back_cover_html": """
            <h3>About This Book</h3>
            <p>Decode famous quotes and sayings in these entertaining cryptogram puzzles.
            Large print for easy reading. Complete answer key included.</p>
        """,
        "spine_html": '<div class="spine-text">${title} &mdash; ${author}</div>',
    },

    "default": {
        "template_css": """
            .bleed-fill { background: linear-gradient(160deg, #1f2937 0%, #374151 50%, #1f2937 100%); }
            .spine { background: #1f2937; }
            .back-cover { background: #1f2937; padding: 180px 140px; color: white; display: flex; flex-direction: column; justify-content: center; }
            .back-cover h3 { font-size: 72px; margin-bottom: 50px; font-family: 'Georgia', serif; }
            .back-cover p { font-size: 42px; line-height: 1.7; opacity: 0.9; }
            .front-cover {
                background: linear-gradient(175deg, #f9fafb 0%, #f3f4f6 50%, #e5e7eb 100%);
                text-align: center; color: #1f2937;
                position: relative; overflow: hidden;
            }
            .front-cover::after {
                content: ''; position: absolute;
                top: 100px; left: 100px; right: 100px; bottom: 100px;
                border: 6px solid rgba(31,41,55,0.06); border-radius: 30px; z-index: 0;
            }
            .front-cover > * { position: relative; z-index: 1; }
            .top-accent { width: 100%; height: 60px; background: linear-gradient(90deg, #1f2937, #374151, #1f2937); position: absolute; top: 0; left: 0; z-index: 2; }
            .title { font-size: 200px; font-weight: bold; font-family: 'Georgia', serif; line-height: 1.12; margin-bottom: 40px; color: #1f2937; max-width: 90%; }
            .decorative { width: 500px; height: 8px; background: linear-gradient(90deg, transparent, #6b7280, transparent); margin: 30px auto; }
            .subtitle { font-size: 90px; font-family: 'Georgia', serif; color: #4b5563; margin-bottom: 60px; font-style: italic; }
            .author { font-size: 72px; color: #6b7280; font-family: 'Georgia', serif; letter-spacing: 2px; }
            .bottom-accent { width: 100%; height: 60px; background: linear-gradient(90deg, #1f2937, #374151, #1f2937); position: absolute; bottom: 0; left: 0; z-index: 2; }
            .bottom-section { margin-top: auto; width: 100%; text-align: center; }
            .bottom-divider { width: 300px; height: 4px; background: linear-gradient(90deg, transparent, rgba(31,41,55,0.2), transparent); margin: 0 auto 40px; }
        """,
        "front_cover_html": """
            <div class="top-accent"></div>
            <div class="title">${title}</div>
            <div class="decorative"></div>
            <div class="subtitle">${subtitle}</div>
            <div class="bottom-section">
                <div class="bottom-divider"></div>
                <div class="author">${author}</div>
            </div>
            <div class="bottom-accent"></div>
        """,
        "back_cover_html": """
            <h3>About This Book</h3>
            <p>A quality publication for your enjoyment.</p>
        """,
        "spine_html": '<div class="spine-text">${title} &mdash; ${author}</div>',
    },
}


def _png_to_pdf(png_path: str, pdf_path: str, dims: CoverDimensions):
    """Convert a full-spread PNG screenshot to a PDF at correct print dimensions.

    The PNG is at 300 DPI pixel resolution (e.g. 5252×3375 px).
    The PDF will be at the correct print dimensions (e.g. 17.5"×11.25").
    This ensures KDP gets a properly-sized single-page PDF.
    """
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader

    # PDF page size in points (1 inch = 72 points)
    page_w = dims.total_width * inch   # e.g. 17.5067 * 72 = 1260.5 pts
    page_h = dims.total_height * inch  # e.g. 11.25 * 72 = 810 pts

    c = rl_canvas.Canvas(pdf_path, pagesize=(page_w, page_h))
    img = ImageReader(png_path)
    # Draw the image to fill the entire page (300 DPI mapping)
    c.drawImage(img, 0, 0, width=page_w, height=page_h)
    c.save()


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

            # Export full spread as PNG screenshot (pixel-perfect at 300 DPI)
            full_png_path = output_dir / "cover-full.png"
            await page.screenshot(path=str(full_png_path), full_page=True)

            # Export front cover PNG for preview
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

            # Convert full spread PNG to PDF at correct print dimensions (300 DPI)
            _png_to_pdf(str(full_png_path), str(pdf_path), dims)

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
