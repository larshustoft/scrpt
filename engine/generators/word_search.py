"""
SCRPT Word Search Generator
=============================
Creates complete word search puzzle books ready for Amazon KDP.

Each puzzle:
  - Places words in a grid (horizontal, vertical, diagonal, reversed)
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


# ── Puzzle Grid Logic ────────────────────────────────────────────

DIRECTIONS = [
    (0, 1),   # right
    (1, 0),   # down
    (0, -1),  # left
    (-1, 0),  # up
    (1, 1),   # diagonal down-right
    (1, -1),  # diagonal down-left
    (-1, 1),  # diagonal up-right
    (-1, -1), # diagonal up-left
]


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
) -> WordSearchPuzzle:
    """
    Generate a single word search puzzle.

    Args:
        words: List of words to hide in the grid
        grid_size: Width and height of the grid
        max_attempts: Max placement attempts per word

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

        placed_word = _try_place_word(grid, word_upper, grid_size, max_attempts)
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
) -> Optional[PlacedWord]:
    """Try to place a word in the grid."""
    directions = list(DIRECTIONS)

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

        puzzle = generate_puzzle(words, config.grid_size)
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
    """Draw the book's title page."""
    # Title
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(page_w / 2, page_h - 3 * inch, config.title)

    # Subtitle
    c.setFont("Helvetica", 18)
    c.drawCentredString(page_w / 2, page_h - 3.8 * inch, config.subtitle)

    # Puzzle count
    c.setFont("Helvetica", 14)
    c.drawCentredString(
        page_w / 2,
        page_h - 4.8 * inch,
        f"{config.num_puzzles} Puzzles"
    )

    # Large print badge
    if config.large_print:
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(page_w / 2, page_h - 5.5 * inch, "LARGE PRINT")

    # Author
    c.setFont("Helvetica", 14)
    c.drawCentredString(page_w / 2, page_h - 8 * inch, config.author)


def _draw_copyright_page(c, config, page_w, page_h):
    """Draw the copyright page."""
    y = page_h - 2 * inch
    c.setFont("Helvetica", 9)
    lines = [
        f"© 2026 {config.author}",
        "",
        "All rights reserved. No part of this publication may be",
        "reproduced, distributed, or transmitted in any form.",
        "",
        f"Published by {config.author}",
        "",
        "This book was independently published.",
        "",
        "Printed in the United States of America.",
        "",
        "First Edition",
    ]
    for line in lines:
        c.drawCentredString(page_w / 2, y, line)
        y -= 14


def _draw_section_header(c, title, page_w, page_h):
    """Draw a section divider page."""
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(page_w / 2, page_h / 2 + 20, title)
    c.setFont("Helvetica", 12)


def _draw_puzzle_page(c, puzzle, config, page_w, page_h, grid_fs, word_fs, title_fs, header_fs, is_left):
    """Draw a single puzzle page with grid and word list."""
    # Margins
    ml = config.margin_gutter * inch if is_left else config.margin_outside * inch
    mr = config.margin_outside * inch if is_left else config.margin_gutter * inch
    mt = config.margin_top * inch
    mb = config.margin_bottom * inch

    usable_w = page_w - ml - mr
    usable_h = page_h - mt - mb

    # Header
    c.setFont("Helvetica-Bold", title_fs)
    c.drawString(ml, page_h - mt + 5, f"Puzzle #{puzzle.puzzle_number} — {puzzle.title}")

    c.setFont("Helvetica", header_fs)
    c.drawRightString(
        page_w - mr,
        page_h - mt + 5,
        f"Find all {len(puzzle.words)} words!"
    )

    # Grid area — center it
    cell_size = grid_fs * 1.5  # Space per cell
    grid_total = puzzle.size * cell_size

    # Start grid below header
    grid_top = page_h - mt - 25
    grid_left = ml + (usable_w - grid_total) / 2

    # Draw grid
    c.setFont("Helvetica", grid_fs)
    for row in range(puzzle.size):
        for col in range(puzzle.size):
            x = grid_left + col * cell_size + cell_size / 2
            y = grid_top - row * cell_size - cell_size * 0.7
            c.drawCentredString(x, y, puzzle.grid[row][col])

    # Word list below grid
    word_list_top = grid_top - puzzle.size * cell_size - 30
    c.setFont("Helvetica", word_fs)

    # Arrange words in columns
    words_sorted = sorted(puzzle.words)
    cols = 3
    col_width = usable_w / cols
    rows_needed = math.ceil(len(words_sorted) / cols)

    for idx, word in enumerate(words_sorted):
        col_idx = idx // rows_needed
        row_idx = idx % rows_needed
        x = ml + col_idx * col_width + 10
        y = word_list_top - row_idx * (word_fs + 6)
        c.drawString(x, y, word)

    # Page number
    c.setFont("Helvetica", 9)
    c.drawCentredString(page_w / 2, mb / 2, str(puzzle.puzzle_number))


def _draw_answer_page(c, puzzle, config, page_w, page_h, is_left):
    """Draw an answer key page (smaller grid with answers highlighted)."""
    ml = config.margin_gutter * inch if is_left else config.margin_outside * inch
    mr = config.margin_outside * inch if is_left else config.margin_gutter * inch
    mt = config.margin_top * inch
    mb = config.margin_bottom * inch
    usable_w = page_w - ml - mr

    # Header
    c.setFont("Helvetica-Bold", 11)
    c.drawString(ml, page_h - mt + 5, f"Answer #{puzzle.puzzle_number} — {puzzle.title}")

    # Smaller grid for answer key
    answer_font = 12
    cell_size = answer_font * 1.4
    grid_total = puzzle.size * cell_size

    grid_top = page_h - mt - 20
    grid_left = ml + (usable_w - grid_total) / 2

    # Build set of answer cells
    answer_cells = set()
    for pw in puzzle.placed_words:
        for cell in pw.cells:
            answer_cells.add(cell)

    # Draw grid with answers in bold
    for row in range(puzzle.size):
        for col in range(puzzle.size):
            x = grid_left + col * cell_size + cell_size / 2
            y = grid_top - row * cell_size - cell_size * 0.7

            is_answer = (row, col) in answer_cells
            if is_answer:
                # Highlight answer cells
                c.setFillColor(colors.Color(0.9, 0.95, 1.0))
                c.rect(
                    grid_left + col * cell_size + 1,
                    y - 2,
                    cell_size - 2,
                    cell_size - 2,
                    fill=1,
                    stroke=0,
                )
                c.setFillColor(colors.Color(0, 0, 0))
                c.setFont("Helvetica-Bold", answer_font)
            else:
                c.setFont("Helvetica", answer_font)
                c.setFillColor(colors.Color(0.7, 0.7, 0.7))

            c.drawCentredString(x, y, puzzle.grid[row][col])
            c.setFillColor(colors.Color(0, 0, 0))

    # Word list
    word_list_top = grid_top - puzzle.size * cell_size - 20
    c.setFont("Helvetica", 9)
    words_text = ", ".join(sorted(puzzle.words))
    c.drawString(ml, word_list_top, words_text[:120])
    if len(words_text) > 120:
        c.drawString(ml, word_list_top - 12, words_text[120:])


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
