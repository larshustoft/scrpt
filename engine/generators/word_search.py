"""
SCRPT Word Search Generator
=============================
Creates complete word search puzzle books ready for Amazon KDP.

Each puzzle:
  - Places words in a grid (horizontal, vertical, and optionally diagonal,
    including reversed)
  - Fills remaining cells with random letters
  - Generates a word list for the solver
  - Includes answer key pages at the back

Output: KDP-compliant PDF at 300 DPI with proper margins.
"""

import random
import string
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.enums import TA_CENTER


# ── Puzzle Grid Logic ────────────────────────────────────────────

DIRECTIONS_HV = [
    (0, 1),   # right
    (1, 0),   # down
    (0, -1),  # left
    (-1, 0),  # up
]

DIRECTIONS_DIAGONAL = [
    (1, 1),   # down-right
    (1, -1),  # down-left
    (-1, 1),  # up-right
    (-1, -1), # up-left
]

DIRECTIONS_ALL = DIRECTIONS_HV + DIRECTIONS_DIAGONAL


@dataclass
class PlacedWord:
    """A word successfully placed in the grid."""
    word: str
    row: int
    col: int
    direction: tuple
    cells: list  # [(row, col), ...]


@dataclass
class WordSearchPuzzle:
    """A single word search puzzle with grid and word list."""
    grid: list  # 2D array of characters
    size: int
    words: list  # words to find
    placed_words: list  # PlacedWord objects
    title: str = ""
    puzzle_number: int = 0


def generate_puzzle(
    words: list[str],
    grid_size: int = 15,
    max_attempts: int = 100,
    allow_diagonal: bool = False,
) -> WordSearchPuzzle:
    """
    Generate a single word search puzzle.

    Args:
        words: List of words to hide in the grid
        grid_size: Width and height of the grid
        max_attempts: Max placement attempts per word
        allow_diagonal: If True, words can be placed diagonally too

    Returns:
        WordSearchPuzzle with filled grid
    """
    # Initialize empty grid
    grid = [['_' for _ in range(grid_size)] for _ in range(grid_size)]
    placed = []

    # Sort words by length (longest first for better placement)
    sorted_words = sorted(words, key=len, reverse=True)

    for word in sorted_words:
        word_upper = word.upper().replace(" ", "")
        if len(word_upper) > grid_size:
            continue  # Skip words too long for the grid

        placed_word = _try_place_word(grid, word_upper, grid_size, max_attempts, allow_diagonal)
        if placed_word:
            placed.append(placed_word)

    # Fill empty cells with random letters
    for r in range(grid_size):
        for c in range(grid_size):
            if grid[r][c] == '_':
                grid[r][c] = random.choice(string.ascii_uppercase)

    return WordSearchPuzzle(
        grid=grid,
        size=grid_size,
        words=[pw.word for pw in placed],
        placed_words=placed,
    )


def _try_place_word(
    grid: list,
    word: str,
    grid_size: int,
    max_attempts: int,
    allow_diagonal: bool = False,
) -> Optional[PlacedWord]:
    """Try to place a word in the grid."""
    directions = list(DIRECTIONS_ALL if allow_diagonal else DIRECTIONS_HV)

    for _ in range(max_attempts):
        direction = random.choice(directions)
        dr, dc = direction

        # Calculate valid starting positions
        word_len = len(word)

        if dr == 0:
            row_range = range(grid_size)
        elif dr > 0:
            row_range = range(grid_size - word_len + 1)
        else:
            row_range = range(word_len - 1, grid_size)

        if dc == 0:
            col_range = range(grid_size)
        elif dc > 0:
            col_range = range(grid_size - word_len + 1)
        else:
            col_range = range(word_len - 1, grid_size)

        row_list = list(row_range)
        col_list = list(col_range)
        if not row_list or not col_list:
            continue

        row = random.choice(row_list)
        col = random.choice(col_list)

        # Check if word fits
        cells = []
        can_place = True
        for i, letter in enumerate(word):
            r = row + i * dr
            c = col + i * dc
            if grid[r][c] != '_' and grid[r][c] != letter:
                can_place = False
                break
            cells.append((r, c))

        if can_place:
            # Place the word
            for i, letter in enumerate(word):
                r, c = cells[i]
                grid[r][c] = letter

            return PlacedWord(
                word=word,
                row=row,
                col=col,
                direction=direction,
                cells=cells,
            )

    return None


# ── Word Lists by Theme ─────────────────────────────────────────

WORD_THEMES = {
    "animals": [
        "ELEPHANT", "GIRAFFE", "PENGUIN", "DOLPHIN", "BUTTERFLY",
        "KANGAROO", "CROCODILE", "FLAMINGO", "TORTOISE", "CHEETAH",
        "SQUIRREL", "LEOPARD", "PARROT", "OCTOPUS", "HAMSTER",
        "FALCON", "GAZELLE", "WALRUS", "PELICAN", "BUFFALO",
    ],
    "nature": [
        "MOUNTAIN", "WATERFALL", "SUNRISE", "RAINBOW", "BLOSSOM",
        "MEADOW", "GLACIER", "VOLCANO", "FOREST", "CANYON",
        "DESERT", "ISLAND", "OCEAN", "BREEZE", "THUNDER",
        "CRYSTAL", "HARVEST", "GARDEN", "STREAM", "FLOWER",
    ],
    "food": [
        "CHOCOLATE", "PANCAKE", "SPAGHETTI", "BLUEBERRY", "CINNAMON",
        "SANDWICH", "AVOCADO", "MUSHROOM", "PINEAPPLE", "BROCCOLI",
        "BISCUIT", "LASAGNA", "POPCORN", "PRETZEL", "MUFFIN",
        "WAFFLE", "COCONUT", "ALMOND", "CHERRY", "LEMON",
    ],
    "travel": [
        "AIRPORT", "PASSPORT", "LUGGAGE", "COMPASS", "JOURNEY",
        "EXPLORE", "ADVENTURE", "VACATION", "SOUVENIR", "TOURIST",
        "CRUISE", "HOTEL", "BEACH", "TEMPLE", "CASTLE",
        "MUSEUM", "MARKET", "BRIDGE", "HARBOR", "SAFARI",
    ],
    "music": [
        "MELODY", "HARMONY", "RHYTHM", "TRUMPET", "GUITAR",
        "VIOLIN", "CONCERT", "SYMPHONY", "CHORUS", "ACOUSTIC",
        "MAESTRO", "BALLAD", "ENCORE", "TREBLE", "SONATA",
        "FLUTE", "PIANO", "OPERA", "TEMPO", "DRUMS",
    ],
    "space": [
        "GALAXY", "NEBULA", "ASTEROID", "COMET", "SATURN",
        "JUPITER", "MERCURY", "ECLIPSE", "METEOR", "COSMOS",
        "GRAVITY", "ORBITAL", "STELLAR", "QUANTUM", "PHOTON",
        "QUASAR", "PULSAR", "ROCKET", "LAUNCH", "SHUTTLE",
    ],
    "sports": [
        "BASKETBALL", "FOOTBALL", "BASEBALL", "SWIMMING", "CYCLING",
        "MARATHON", "ARCHERY", "FENCING", "JAVELIN", "CRICKET",
        "TENNIS", "SOCCER", "HOCKEY", "BOXING", "ROWING",
        "SKIING", "SURFING", "SPRINT", "HURDLE", "RELAY",
    ],
    "weather": [
        "SUNSHINE", "BLIZZARD", "TORNADO", "THUNDER", "RAINBOW",
        "MONSOON", "DRIZZLE", "BREEZE", "CLIMATE", "FORECAST",
        "CELSIUS", "HUMIDITY", "CYCLONE", "WEATHER", "TEMPEST",
        "CLOUDY", "STORMY", "FOGGY", "WINDY", "FROST",
    ],
    "garden": [
        "SUNFLOWER", "LAVENDER", "ROSEMARY", "JASMINE", "ORCHID",
        "TULIP", "DAFFODIL", "PETUNIA", "DAHLIA", "HIBISCUS",
        "COMPOST", "TRELLIS", "PRUNING", "HARVEST", "SEEDLING",
        "BLOSSOM", "GARDEN", "POLLEN", "NECTAR", "SPROUT",
    ],
    "ocean": [
        "DOLPHIN", "SEAHORSE", "STARFISH", "JELLYFISH", "LOBSTER",
        "SEASHELL", "CURRENT", "TIDE", "CORAL", "ANCHOR",
        "HARBOR", "LIGHTHOUSE", "MERMAID", "CAPTAIN", "VOYAGER",
        "TRIDENT", "BREAKER", "VESSEL", "DIVING", "WHALE",
    ],
    "kitchen": [
        "SPATULA", "BLENDER", "COLANDER", "SKILLET", "WHISKER",
        "GRATER", "TOASTER", "ROLLING", "SAUCEPAN", "CUTTING",
        "RECIPE", "SIMMER", "GARNISH", "SEASON", "MINCE",
        "BAKING", "ROAST", "STEAM", "SAUTE", "GRILL",
    ],
    "autumn": [
        "HARVEST", "PUMPKIN", "LEAVES", "ACORN", "CIDER",
        "SWEATER", "BONFIRE", "FLANNEL", "HAYRIDE", "SCARECROW",
        "CHESTNUT", "FESTIVAL", "EQUINOX", "MIGRATE", "CRIMSON",
        "AMBER", "RUSTIC", "CRISP", "MAPLE", "GOLDEN",
    ],
}

# Extended themes for variety across a full book
ALL_THEME_NAMES = list(WORD_THEMES.keys())


def get_words_for_puzzle(
    theme: Optional[str] = None,
    count: int = 15,
    difficulty: str = "medium",
) -> tuple[list[str], str]:
    """
    Get a set of words for a puzzle.

    Args:
        theme: Theme name or None for random
        count: Number of words
        difficulty: easy (short words), medium, hard (long words)

    Returns:
        (word_list, theme_name)
    """
    if theme and theme in WORD_THEMES:
        theme_name = theme
    else:
        theme_name = random.choice(ALL_THEME_NAMES)

    words = list(WORD_THEMES[theme_name])
    random.shuffle(words)

    # Filter by difficulty
    if difficulty == "easy":
        words = [w for w in words if len(w) <= 6] or words[:count]
    elif difficulty == "hard":
        words = [w for w in words if len(w) >= 7] or words[:count]

    return words[:count], theme_name


# ── Drawing Helpers ──────────────────────────────────────────────


def _draw_ornamental_divider(c, x_center, y, width, style="line"):
    """Draw a centered horizontal ornament."""
    c.saveState()
    half = width / 2

    if style == "line":
        # Thin rule with a small diamond in the center
        c.setStrokeColor(colors.Color(0.45, 0.45, 0.45))
        c.setLineWidth(0.6)
        gap = 6
        c.line(x_center - half, y, x_center - gap, y)
        c.line(x_center + gap, y, x_center + half, y)
        # Small diamond in the gap
        d = 4
        p = c.beginPath()
        p.moveTo(x_center, y + d)
        p.lineTo(x_center + d, y)
        p.lineTo(x_center, y - d)
        p.lineTo(x_center - d, y)
        p.close()
        c.setFillColor(colors.Color(0.45, 0.45, 0.45))
        c.drawPath(p, fill=1, stroke=0)

    elif style == "dots":
        c.setFillColor(colors.Color(0.55, 0.55, 0.55))
        num_dots = 7
        spacing = width / (num_dots - 1)
        for i in range(num_dots):
            cx = x_center - half + i * spacing
            c.circle(cx, y, 1.5, fill=1, stroke=0)

    elif style == "diamond":
        # Three diamonds with connecting lines
        c.setStrokeColor(colors.Color(0.4, 0.4, 0.4))
        c.setFillColor(colors.Color(0.4, 0.4, 0.4))
        c.setLineWidth(0.5)
        # Lines
        c.line(x_center - half, y, x_center - 12, y)
        c.line(x_center + 12, y, x_center + half, y)
        # Center diamond (larger)
        d = 5
        p = c.beginPath()
        p.moveTo(x_center, y + d)
        p.lineTo(x_center + d, y)
        p.lineTo(x_center, y - d)
        p.lineTo(x_center - d, y)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
        # Side diamonds (smaller)
        for offset in [-half * 0.35, half * 0.35]:
            sd = 3
            sp = c.beginPath()
            sp.moveTo(x_center + offset, y + sd)
            sp.lineTo(x_center + offset + sd, y)
            sp.lineTo(x_center + offset, y - sd)
            sp.lineTo(x_center + offset - sd, y)
            sp.close()
            c.drawPath(sp, fill=1, stroke=0)

    c.restoreState()


def _draw_page_footer(c, page_num, page_w, mb, show_divider=True):
    """Draw a standardized page footer with optional divider."""
    c.saveState()
    if show_divider:
        c.setStrokeColor(colors.Color(0.8, 0.8, 0.8))
        c.setLineWidth(0.4)
        rule_w = 100
        c.line(page_w / 2 - rule_w / 2, mb * 0.65 + 10, page_w / 2 + rule_w / 2, mb * 0.65 + 10)
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.Color(0.4, 0.4, 0.4))
    c.drawCentredString(page_w / 2, mb * 0.45, str(page_num))
    c.restoreState()


# ── PDF Generation ───────────────────────────────────────────────

@dataclass
class WordSearchBookConfig:
    """Configuration for a word search book."""
    title: str = "Ultimate Word Search"
    subtitle: str = "Large Print Puzzles for Adults"
    author: str = "Creative Puzzles Press"
    num_puzzles: int = 55          # ~110 pages (puzzle + word list)
    grid_size: int = 15            # 15x15 grid
    words_per_puzzle: int = 15
    difficulty: str = "medium"     # easy, medium, hard
    allow_diagonal: bool = False   # If True, some puzzles include diagonal words
    large_print: bool = True       # Large print for seniors market
    trim_width: float = 8.5        # inches
    trim_height: float = 11.0      # inches
    margin_top: float = 0.75
    margin_bottom: float = 0.75
    margin_outside: float = 0.75
    margin_gutter: float = 0.5     # inside margin (near spine)


def generate_word_search_book(
    config: WordSearchBookConfig,
    output_path: Path,
) -> dict:
    """
    Generate a complete word search book PDF.

    Returns:
        Dict with metadata about the generated book
    """
    page_w = config.trim_width * inch
    page_h = config.trim_height * inch

    c = canvas.Canvas(
        str(output_path),
        pagesize=(page_w, page_h),
    )

    # Font sizes for large print
    if config.large_print:
        grid_font_size = 22
        word_list_font_size = 16
        title_font_size = 14
        header_font_size = 10
    else:
        grid_font_size = 18
        word_list_font_size = 14
        title_font_size = 12
        header_font_size = 9

    page_count = 0
    puzzles = []

    # ── Title Page ───────────────────────────────────────────
    _draw_title_page(c, config, page_w, page_h)
    page_count += 1

    # ── Copyright Page ───────────────────────────────────────
    c.showPage()
    _draw_copyright_page(c, config, page_w, page_h)
    page_count += 1

    # ── Puzzle Pages ─────────────────────────────────────────
    used_themes = []
    for i in range(config.num_puzzles):
        # Cycle through themes
        theme = ALL_THEME_NAMES[i % len(ALL_THEME_NAMES)]
        words, theme_name = get_words_for_puzzle(
            theme=theme,
            count=config.words_per_puzzle,
            difficulty=config.difficulty,
        )
        used_themes.append(theme_name)

        puzzle = generate_puzzle(words, config.grid_size, allow_diagonal=config.allow_diagonal)
        puzzle.puzzle_number = i + 1
        puzzle.title = theme_name.replace("_", " ").title()
        puzzles.append(puzzle)

        # Puzzle page
        c.showPage()
        is_left = (page_count % 2 == 0)  # even pages are left (verso)
        _draw_puzzle_page(c, puzzle, config, page_w, page_h, grid_font_size, word_list_font_size, title_font_size, header_font_size, is_left)
        page_count += 1

    # ── Answer Key Section ───────────────────────────────────
    c.showPage()
    _draw_section_header(c, "Answer Key", page_w, page_h)
    page_count += 1

    for puzzle in puzzles:
        c.showPage()
        is_left = (page_count % 2 == 0)
        _draw_answer_page(c, puzzle, config, page_w, page_h, is_left)
        page_count += 1

    # Pad to even page count (KDP requirement)
    if page_count % 2 != 0:
        c.showPage()
        page_count += 1

    c.save()

    return {
        "path": str(output_path),
        "page_count": page_count,
        "num_puzzles": len(puzzles),
        "themes_used": list(set(used_themes)),
        "grid_size": config.grid_size,
        "words_per_puzzle": config.words_per_puzzle,
    }


def _draw_title_page(c, config, page_w, page_h):
    """Draw a professional title page with decorative border and text wrapping."""
    c.saveState()

    # ── Decorative double border ──
    inset = 40
    border_x = inset
    border_y = inset
    border_w = page_w - 2 * inset
    border_h = page_h - 2 * inset

    # Outer border
    c.setStrokeColor(colors.Color(0.25, 0.25, 0.25))
    c.setLineWidth(2.0)
    c.rect(border_x, border_y, border_w, border_h, stroke=1, fill=0)

    # Inner border
    c.setLineWidth(0.5)
    c.rect(border_x + 7, border_y + 7, border_w - 14, border_h - 14, stroke=1, fill=0)

    # ── Corner ornaments (small cross marks at each corner) ──
    c.setLineWidth(0.8)
    c.setStrokeColor(colors.Color(0.35, 0.35, 0.35))
    corner_len = 16
    corners = [
        (border_x + 18, border_y + border_h - 18),   # top-left
        (border_x + border_w - 18, border_y + border_h - 18),  # top-right
        (border_x + 18, border_y + 18),               # bottom-left
        (border_x + border_w - 18, border_y + 18),    # bottom-right
    ]
    for (cx, cy) in corners:
        c.line(cx - corner_len / 2, cy, cx + corner_len / 2, cy)
        c.line(cx, cy - corner_len / 2, cx, cy + corner_len / 2)

    # ── Title (auto-wrapping via Paragraph) ──
    max_text_width = border_w - 100  # generous padding inside border
    title_style = ParagraphStyle(
        "BookTitle",
        fontName="Helvetica-Bold",
        fontSize=32,
        leading=39,
        alignment=TA_CENTER,
        textColor=colors.Color(0.08, 0.08, 0.08),
    )
    title_para = Paragraph(config.title, title_style)
    tw, th = title_para.wrap(max_text_width, 200)
    title_top_y = page_h - 2.8 * inch
    title_para.drawOn(c, (page_w - max_text_width) / 2, title_top_y - th)

    # ── Ornamental divider below title ──
    divider_y = title_top_y - th - 22
    _draw_ornamental_divider(c, page_w / 2, divider_y, 140, style="diamond")

    # ── Subtitle (also wrapped) ──
    subtitle_style = ParagraphStyle(
        "BookSubtitle",
        fontName="Helvetica",
        fontSize=18,
        leading=23,
        alignment=TA_CENTER,
        textColor=colors.Color(0.22, 0.22, 0.22),
    )
    sub_para = Paragraph(config.subtitle, subtitle_style)
    sw, sh = sub_para.wrap(max_text_width, 100)
    subtitle_y = divider_y - 28
    sub_para.drawOn(c, (page_w - max_text_width) / 2, subtitle_y - sh)

    # ── Puzzle count ──
    info_y = subtitle_y - sh - 32
    c.setFont("Helvetica", 14)
    c.setFillColor(colors.Color(0.3, 0.3, 0.3))
    c.drawCentredString(page_w / 2, info_y, f"{config.num_puzzles} Themed Puzzles")

    # ── LARGE PRINT badge (rounded rect outline) ──
    if config.large_print:
        badge_y = info_y - 38
        badge_text = "LARGE PRINT"
        c.setFont("Helvetica-Bold", 11)
        text_w = stringWidth(badge_text, "Helvetica-Bold", 11)
        badge_w = text_w + 28
        badge_h = 24
        badge_x = (page_w - badge_w) / 2

        c.setStrokeColor(colors.Color(0.3, 0.3, 0.3))
        c.setLineWidth(1.0)
        c.roundRect(badge_x, badge_y - 5, badge_w, badge_h, 4, stroke=1, fill=0)
        c.setFillColor(colors.Color(0.15, 0.15, 0.15))
        c.drawCentredString(page_w / 2, badge_y + 2, badge_text)

    # ── Second divider above author ──
    author_divider_y = page_h - 7.0 * inch
    _draw_ornamental_divider(c, page_w / 2, author_divider_y, 100, style="dots")

    # ── Author ──
    c.setFont("Helvetica", 14)
    c.setFillColor(colors.Color(0.2, 0.2, 0.2))
    c.drawCentredString(page_w / 2, page_h - 7.8 * inch, config.author)

    c.restoreState()


def _draw_copyright_page(c, config, page_w, page_h):
    """Draw the copyright page (text in lower third, standard publishing convention)."""
    c.saveState()

    margin_x = config.margin_outside * inch
    y = page_h * 0.35  # lower third of the page

    # Thin rule above copyright block
    c.setStrokeColor(colors.Color(0.75, 0.75, 0.75))
    c.setLineWidth(0.4)
    c.line(margin_x + 60, y + 22, page_w - margin_x - 60, y + 22)

    c.setFont("Helvetica", 10)
    c.setFillColor(colors.Color(0.3, 0.3, 0.3))
    line_height = 16

    lines = [
        f"\u00a9 2026 {config.author}",
        "",
        "All rights reserved. No part of this publication may be reproduced,",
        "distributed, or transmitted in any form or by any means without",
        "the prior written permission of the publisher.",
        "",
        f"Published by {config.author}",
        "",
        "This book was independently published.",
        "Printed in the United States of America.",
        "",
        "First Edition",
    ]
    for line in lines:
        c.drawCentredString(page_w / 2, y, line)
        y -= line_height

    c.restoreState()


def _draw_section_header(c, title, page_w, page_h):
    """Draw a section divider page with ornamental dividers."""
    c.saveState()

    center_y = page_h / 2 + 10

    # Divider above
    _draw_ornamental_divider(c, page_w / 2, center_y + 40, 160, style="line")

    # Title
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(colors.Color(0.1, 0.1, 0.1))
    c.drawCentredString(page_w / 2, center_y, title)

    # Divider below
    _draw_ornamental_divider(c, page_w / 2, center_y - 22, 160, style="line")

    c.restoreState()


def _draw_puzzle_page(c, puzzle, config, page_w, page_h, grid_fs, word_fs, title_fs, header_fs, is_left):
    """Draw a single puzzle page with header bar, gridlined grid, and styled word list."""
    c.saveState()

    # ── Margins ──
    ml = config.margin_gutter * inch if is_left else config.margin_outside * inch
    mr = config.margin_outside * inch if is_left else config.margin_gutter * inch
    mt = config.margin_top * inch
    mb = config.margin_bottom * inch
    usable_w = page_w - ml - mr

    # ── Header bar (light gray background strip) ──
    header_h = 26
    header_y = page_h - mt - header_h

    c.setFillColor(colors.Color(0.92, 0.92, 0.92))
    c.rect(ml, header_y, usable_w, header_h, fill=1, stroke=0)
    # Thin bottom rule on header
    c.setStrokeColor(colors.Color(0.75, 0.75, 0.75))
    c.setLineWidth(0.5)
    c.line(ml, header_y, ml + usable_w, header_y)

    # Puzzle number (left)
    c.setFont("Helvetica-Bold", title_fs)
    c.setFillColor(colors.Color(0.12, 0.12, 0.12))
    c.drawString(ml + 10, header_y + 7, f"Puzzle #{puzzle.puzzle_number}")

    # Theme name (center)
    c.setFont("Helvetica", header_fs + 1)
    c.setFillColor(colors.Color(0.35, 0.35, 0.35))
    center_x = ml + usable_w / 2
    c.drawCentredString(center_x, header_y + 8, puzzle.title)

    # Word count (right)
    c.setFont("Helvetica", header_fs)
    c.setFillColor(colors.Color(0.4, 0.4, 0.4))
    c.drawRightString(ml + usable_w - 10, header_y + 8, f"Find all {len(puzzle.words)} words!")

    # ── Grid ──
    cell_size = grid_fs * 1.5
    grid_total = puzzle.size * cell_size

    grid_top = header_y - 14
    grid_left = ml + (usable_w - grid_total) / 2

    # Grid outer border (heavier)
    c.setStrokeColor(colors.Color(0.3, 0.3, 0.3))
    c.setLineWidth(1.5)
    c.rect(grid_left, grid_top - grid_total, grid_total, grid_total, stroke=1, fill=0)

    # Grid inner lines (light)
    c.setStrokeColor(colors.Color(0.82, 0.82, 0.82))
    c.setLineWidth(0.3)
    for i in range(1, puzzle.size):
        # Horizontal
        y = grid_top - i * cell_size
        c.line(grid_left, y, grid_left + grid_total, y)
        # Vertical
        x = grid_left + i * cell_size
        c.line(x, grid_top, x, grid_top - grid_total)

    # Grid letters
    c.setFont("Helvetica", grid_fs)
    c.setFillColor(colors.Color(0.1, 0.1, 0.1))
    for row in range(puzzle.size):
        for col in range(puzzle.size):
            x = grid_left + col * cell_size + cell_size / 2
            y = grid_top - row * cell_size - cell_size * 0.7
            c.drawCentredString(x, y, puzzle.grid[row][col])

    # ── Word list section ──
    word_section_top = grid_top - grid_total - 18

    # "FIND THESE WORDS:" label
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.Color(0.4, 0.4, 0.4))
    c.drawString(ml, word_section_top + 2, "FIND THESE WORDS:")

    # Thin rule under label
    rule_y = word_section_top - 4
    c.setStrokeColor(colors.Color(0.78, 0.78, 0.78))
    c.setLineWidth(0.4)
    c.line(ml, rule_y, ml + usable_w, rule_y)

    # Words in 3 columns
    words_sorted = sorted(puzzle.words)
    cols = 3
    col_width = usable_w / cols
    rows_needed = math.ceil(len(words_sorted) / cols)

    c.setFont("Helvetica", word_fs)
    c.setFillColor(colors.Color(0.15, 0.15, 0.15))

    for idx, word in enumerate(words_sorted):
        col_idx = idx // rows_needed
        row_idx = idx % rows_needed
        x = ml + col_idx * col_width + 10
        y = rule_y - 16 - row_idx * (word_fs + 6)
        c.drawString(x, y, word)

    # ── Page footer ──
    _draw_page_footer(c, puzzle.puzzle_number, page_w, mb)

    c.restoreState()


def _draw_answer_page(c, puzzle, config, page_w, page_h, is_left):
    """Draw an answer key page with gridlines and highlighted answers."""
    c.saveState()

    ml = config.margin_gutter * inch if is_left else config.margin_outside * inch
    mr = config.margin_outside * inch if is_left else config.margin_gutter * inch
    mt = config.margin_top * inch
    mb = config.margin_bottom * inch
    usable_w = page_w - ml - mr

    # ── Header bar (matching puzzle page style) ──
    header_h = 22
    header_y = page_h - mt - header_h

    c.setFillColor(colors.Color(0.92, 0.92, 0.92))
    c.rect(ml, header_y, usable_w, header_h, fill=1, stroke=0)
    c.setStrokeColor(colors.Color(0.75, 0.75, 0.75))
    c.setLineWidth(0.5)
    c.line(ml, header_y, ml + usable_w, header_y)

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.Color(0.12, 0.12, 0.12))
    c.drawString(ml + 10, header_y + 5, f"Answer #{puzzle.puzzle_number} \u2014 {puzzle.title}")

    # ── Grid ──
    answer_font = 12
    cell_size = answer_font * 1.4
    grid_total = puzzle.size * cell_size

    grid_top = header_y - 10
    grid_left = ml + (usable_w - grid_total) / 2

    # Build set of answer cells
    answer_cells = set()
    for pw in puzzle.placed_words:
        for cell in pw.cells:
            answer_cells.add(cell)

    # Draw answer cell highlights (background, before gridlines)
    for row in range(puzzle.size):
        for col in range(puzzle.size):
            if (row, col) in answer_cells:
                cell_x = grid_left + col * cell_size
                cell_y = grid_top - (row + 1) * cell_size
                c.setFillColor(colors.Color(0.87, 0.92, 1.0))
                c.rect(cell_x, cell_y, cell_size, cell_size, fill=1, stroke=0)

    # Grid inner lines
    c.setStrokeColor(colors.Color(0.85, 0.85, 0.85))
    c.setLineWidth(0.25)
    for i in range(1, puzzle.size):
        y = grid_top - i * cell_size
        c.line(grid_left, y, grid_left + grid_total, y)
        x = grid_left + i * cell_size
        c.line(x, grid_top, x, grid_top - grid_total)

    # Grid outer border
    c.setStrokeColor(colors.Color(0.45, 0.45, 0.45))
    c.setLineWidth(1.0)
    c.rect(grid_left, grid_top - grid_total, grid_total, grid_total, stroke=1, fill=0)

    # Grid letters
    for row in range(puzzle.size):
        for col in range(puzzle.size):
            x = grid_left + col * cell_size + cell_size / 2
            y = grid_top - row * cell_size - cell_size * 0.7

            is_answer = (row, col) in answer_cells
            if is_answer:
                c.setFont("Helvetica-Bold", answer_font)
                c.setFillColor(colors.Color(0.08, 0.08, 0.45))  # dark blue
            else:
                c.setFont("Helvetica", answer_font)
                c.setFillColor(colors.Color(0.72, 0.72, 0.72))  # light gray

            c.drawCentredString(x, y, puzzle.grid[row][col])

    # ── Word list (wrapped via Paragraph) ──
    c.setFillColor(colors.Color(0, 0, 0))
    word_list_top = grid_top - grid_total - 14
    words_text = "Words: " + ", ".join(sorted(puzzle.words))
    word_style = ParagraphStyle(
        "AnswerWords",
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.Color(0.35, 0.35, 0.35),
    )
    word_para = Paragraph(words_text, word_style)
    ww, wh = word_para.wrap(usable_w, 60)
    word_para.drawOn(c, ml, word_list_top - wh)

    c.restoreState()


# ── Main (for testing) ───────────────────────────────────────────

if __name__ == "__main__":
    output = Path("/Users/tiger/Desktop/CATALOG ENGINE/bookr/output/test_word_search.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)

    config = WordSearchBookConfig(
        title="Ultimate Large Print Word Search",
        subtitle="Relaxing Puzzles for Seniors",
        author="Creative Puzzles Press",
        num_puzzles=55,
        grid_size=15,
        words_per_puzzle=15,
        large_print=True,
    )

    result = generate_word_search_book(config, output)
    print(f"Generated: {result['path']}")
    print(f"Pages: {result['page_count']}")
    print(f"Puzzles: {result['num_puzzles']}")
    print(f"Themes: {result['themes_used']}")
