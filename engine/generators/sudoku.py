"""
SCRPT Sudoku Generator
========================
Creates complete sudoku puzzle books for Amazon KDP.

Generates puzzles at 4 difficulty levels:
  - Easy: 35-40 clues
  - Medium: 28-34 clues
  - Hard: 22-27 clues
  - Expert: 17-21 clues

Each puzzle is algorithmically generated and verified to have
exactly one solution.
"""

import random
import math
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas


# ── Sudoku Puzzle Logic ──────────────────────────────────────────

def _generate_full_grid() -> list[list[int]]:
    """Generate a complete valid 9x9 sudoku grid using backtracking."""
    grid = [[0] * 9 for _ in range(9)]
    _fill_grid(grid)
    return grid


def _fill_grid(grid: list[list[int]]) -> bool:
    """Recursively fill the grid with valid numbers."""
    for row in range(9):
        for col in range(9):
            if grid[row][col] == 0:
                numbers = list(range(1, 10))
                random.shuffle(numbers)
                for num in numbers:
                    if _is_valid(grid, row, col, num):
                        grid[row][col] = num
                        if _fill_grid(grid):
                            return True
                        grid[row][col] = 0
                return False
    return True


def _is_valid(grid: list[list[int]], row: int, col: int, num: int) -> bool:
    """Check if placing num at (row, col) is valid."""
    # Check row
    if num in grid[row]:
        return False

    # Check column
    if num in [grid[r][col] for r in range(9)]:
        return False

    # Check 3x3 box
    box_row, box_col = 3 * (row // 3), 3 * (col // 3)
    for r in range(box_row, box_row + 3):
        for c in range(box_col, box_col + 3):
            if grid[r][c] == num:
                return False

    return True


def _count_solutions(grid: list[list[int]], limit: int = 2) -> int:
    """Count solutions up to limit (for uniqueness checking)."""
    count = [0]

    def solve(g):
        if count[0] >= limit:
            return
        for row in range(9):
            for col in range(9):
                if g[row][col] == 0:
                    for num in range(1, 10):
                        if _is_valid(g, row, col, num):
                            g[row][col] = num
                            solve(g)
                            g[row][col] = 0
                    return
        count[0] += 1

    solve(grid)
    return count[0]


def generate_sudoku(difficulty: str = "medium") -> tuple[list[list[int]], list[list[int]]]:
    """
    Generate a sudoku puzzle with a unique solution.

    Args:
        difficulty: easy, medium, hard, expert

    Returns:
        (puzzle_grid, solution_grid)
    """
    clue_ranges = {
        "easy": (35, 40),
        "medium": (28, 34),
        "hard": (22, 27),
        "expert": (17, 21),
    }

    min_clues, max_clues = clue_ranges.get(difficulty, (28, 34))
    target_clues = random.randint(min_clues, max_clues)

    # Generate complete solution
    solution = _generate_full_grid()
    puzzle = deepcopy(solution)

    # Remove cells to create puzzle
    cells = [(r, c) for r in range(9) for c in range(9)]
    random.shuffle(cells)

    removed = 0
    target_remove = 81 - target_clues

    for row, col in cells:
        if removed >= target_remove:
            break

        backup = puzzle[row][col]
        puzzle[row][col] = 0

        # Check uniqueness (this is the expensive part)
        test_grid = deepcopy(puzzle)
        if _count_solutions(test_grid, 2) == 1:
            removed += 1
        else:
            puzzle[row][col] = backup  # Restore — can't remove this

    return puzzle, solution


# ── PDF Generation ───────────────────────────────────────────────

@dataclass
class SudokuBookConfig:
    title: str = "Sudoku Puzzles"
    subtitle: str = "Volume 1"
    author: str = "Creative Puzzles Press"
    num_puzzles: int = 55
    difficulty: str = "medium"
    large_print: bool = True
    trim_width: float = 8.5
    trim_height: float = 11.0
    margin_top: float = 0.75
    margin_bottom: float = 0.75
    margin_outside: float = 0.75
    margin_gutter: float = 0.5


def generate_sudoku_book(config: SudokuBookConfig, output_path: Path) -> dict:
    """Generate a complete sudoku book PDF."""
    page_w = config.trim_width * inch
    page_h = config.trim_height * inch

    c = canvas.Canvas(str(output_path), pagesize=(page_w, page_h))

    page_count = 0
    puzzles = []

    # Title page
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(page_w / 2, page_h - 3 * inch, config.title)
    c.setFont("Helvetica", 18)
    c.drawCentredString(page_w / 2, page_h - 3.8 * inch, config.subtitle)
    c.setFont("Helvetica", 14)
    difficulty_label = config.difficulty.title()
    c.drawCentredString(page_w / 2, page_h - 4.5 * inch, f"{config.num_puzzles} {difficulty_label} Puzzles")
    if config.large_print:
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(page_w / 2, page_h - 5.2 * inch, "LARGE PRINT")
    c.setFont("Helvetica", 14)
    c.drawCentredString(page_w / 2, page_h - 8 * inch, config.author)
    page_count += 1

    # Copyright
    c.showPage()
    c.setFont("Helvetica", 9)
    c.drawCentredString(page_w / 2, page_h - 2 * inch, f"© 2026 {config.author}")
    c.drawCentredString(page_w / 2, page_h - 2.2 * inch, "All rights reserved.")
    page_count += 1

    # Generate puzzles
    for i in range(config.num_puzzles):
        puzzle, solution = generate_sudoku(config.difficulty)
        puzzles.append((puzzle, solution))

        c.showPage()
        is_left = (page_count % 2 == 0)
        _draw_sudoku_page(c, puzzle, i + 1, config, page_w, page_h, is_left)
        page_count += 1

    # Answer key
    c.showPage()
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(page_w / 2, page_h / 2, "Answer Key")
    page_count += 1

    # Answer pages (4 per page)
    answers_per_page = 4
    for batch_start in range(0, len(puzzles), answers_per_page):
        c.showPage()
        batch = puzzles[batch_start:batch_start + answers_per_page]
        is_left = (page_count % 2 == 0)
        _draw_answer_batch(c, batch, batch_start, config, page_w, page_h, is_left)
        page_count += 1

    # Pad to even
    if page_count % 2 != 0:
        c.showPage()
        page_count += 1

    c.save()

    return {
        "path": str(output_path),
        "page_count": page_count,
        "num_puzzles": len(puzzles),
        "difficulty": config.difficulty,
    }


def _draw_sudoku_page(c, puzzle, number, config, page_w, page_h, is_left):
    """Draw a single sudoku puzzle page."""
    ml = config.margin_gutter * inch if is_left else config.margin_outside * inch
    mr = config.margin_outside * inch if is_left else config.margin_gutter * inch
    mt = config.margin_top * inch

    usable_w = page_w - ml - mr

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(ml, page_h - mt + 5, f"Puzzle #{number}")
    c.setFont("Helvetica", 10)
    c.drawRightString(page_w - mr, page_h - mt + 5, config.difficulty.title())

    # Grid
    cell_size = 48 if config.large_print else 38
    grid_size = 9 * cell_size
    grid_left = ml + (usable_w - grid_size) / 2
    grid_top = page_h - mt - 40

    # Draw grid lines
    for i in range(10):
        line_width = 2.5 if i % 3 == 0 else 0.5
        c.setLineWidth(line_width)

        # Horizontal
        y = grid_top - i * cell_size
        c.line(grid_left, y, grid_left + grid_size, y)

        # Vertical
        x = grid_left + i * cell_size
        c.line(x, grid_top, x, grid_top - grid_size)

    # Fill in numbers
    font_size = 24 if config.large_print else 18
    c.setFont("Helvetica-Bold", font_size)

    for row in range(9):
        for col in range(9):
            val = puzzle[row][col]
            if val != 0:
                x = grid_left + col * cell_size + cell_size / 2
                y = grid_top - row * cell_size - cell_size * 0.65
                c.drawCentredString(x, y, str(val))

    # Page number
    c.setFont("Helvetica", 9)
    c.drawCentredString(page_w / 2, config.margin_bottom * inch / 2, str(number))


def _draw_answer_batch(c, batch, start_idx, config, page_w, page_h, is_left):
    """Draw multiple solution grids on one page (4 per page)."""
    ml = config.margin_gutter * inch if is_left else config.margin_outside * inch
    mt = config.margin_top * inch

    cell_size = 18
    grid_size = 9 * cell_size
    gap = 30

    positions = [
        (ml + 20, page_h - mt - 20),
        (ml + grid_size + gap + 40, page_h - mt - 20),
        (ml + 20, page_h - mt - grid_size - gap - 40),
        (ml + grid_size + gap + 40, page_h - mt - grid_size - gap - 40),
    ]

    for idx, (puzzle, solution) in enumerate(batch):
        if idx >= len(positions):
            break
        x_off, y_off = positions[idx]
        puzzle_num = start_idx + idx + 1

        # Label
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x_off, y_off + 5, f"#{puzzle_num}")

        # Mini grid
        for i in range(10):
            lw = 1.5 if i % 3 == 0 else 0.3
            c.setLineWidth(lw)
            y = y_off - i * cell_size
            c.line(x_off, y, x_off + grid_size, y)
            x = x_off + i * cell_size
            c.line(x, y_off, x, y_off - grid_size)

        # Numbers
        c.setFont("Helvetica", 9)
        for row in range(9):
            for col in range(9):
                x = x_off + col * cell_size + cell_size / 2
                y = y_off - row * cell_size - cell_size * 0.65
                c.drawCentredString(x, y, str(solution[row][col]))


if __name__ == "__main__":
    output = Path("/Users/tiger/Desktop/CATALOG ENGINE/bookr/output/test_sudoku.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)

    # Use fewer puzzles for quick test
    config = SudokuBookConfig(
        title="Large Print Sudoku",
        subtitle="Easy to Medium",
        author="Creative Puzzles Press",
        num_puzzles=10,  # Quick test
        difficulty="easy",
        large_print=True,
    )

    print("Generating sudoku book (this may take a moment)...")
    result = generate_sudoku_book(config, output)
    print(f"Generated: {result['path']}")
    print(f"Pages: {result['page_count']}")
    print(f"Puzzles: {result['num_puzzles']}")
