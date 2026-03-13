"""
SCRPT Maze Generator
======================
Creates complete maze puzzle books for Amazon KDP.

Generates mazes at 3 difficulty levels using recursive backtracking (DFS):
  - Easy: 15x15 grid
  - Medium: 20x20 grid
  - Hard: 25x25 grid

Each maze has a single entrance (top-left area) and a single exit
(bottom-right area).  The answer key shows the solution path highlighted.

Output: KDP-compliant PDF at trim size with proper alternating margins.
"""

import random
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas


# ── Maze Grid Logic ─────────────────────────────────────────────

# Directions: (row_delta, col_delta)
_N = (-1, 0)
_S = (1, 0)
_E = (0, 1)
_W = (0, -1)

_OPPOSITE = {
    _N: _S,
    _S: _N,
    _E: _W,
    _W: _E,
}

_ALL_DIRS = [_N, _S, _E, _W]


@dataclass
class MazeCell:
    """A single cell in the maze grid."""
    row: int
    col: int
    walls: dict  # direction -> bool (True = wall present)
    visited: bool = False


class Maze:
    """A 2-D rectangular maze generated with recursive backtracking."""

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self.grid: list[list[MazeCell]] = []
        self.entrance: tuple[int, int] = (0, 0)
        self.exit: tuple[int, int] = (rows - 1, cols - 1)
        self.solution_path: list[tuple[int, int]] = []

        self._build_grid()
        self._carve_passages()
        self._open_entrance_exit()
        self.solution_path = self._solve()

    # ── Grid initialisation ──────────────────────────────────

    def _build_grid(self):
        """Create the grid with all walls intact."""
        self.grid = []
        for r in range(self.rows):
            row = []
            for c in range(self.cols):
                cell = MazeCell(
                    row=r,
                    col=c,
                    walls={_N: True, _S: True, _E: True, _W: True},
                )
                row.append(cell)
            self.grid.append(row)

    # ── Recursive backtracking (DFS) ─────────────────────────

    def _carve_passages(self):
        """Carve passages using iterative DFS (avoids stack overflow on
        large grids while producing identical results to the recursive
        variant)."""
        start_r, start_c = 0, 0
        stack: list[tuple[int, int]] = [(start_r, start_c)]
        self.grid[start_r][start_c].visited = True

        while stack:
            r, c = stack[-1]
            neighbours = self._unvisited_neighbours(r, c)

            if neighbours:
                direction, nr, nc = random.choice(neighbours)
                # Remove wall between current cell and chosen neighbour
                self.grid[r][c].walls[direction] = False
                self.grid[nr][nc].walls[_OPPOSITE[direction]] = False
                self.grid[nr][nc].visited = True
                stack.append((nr, nc))
            else:
                stack.pop()

    def _unvisited_neighbours(self, r: int, c: int):
        """Return list of (direction, row, col) for unvisited neighbours."""
        result = []
        for d in _ALL_DIRS:
            nr, nc = r + d[0], c + d[1]
            if 0 <= nr < self.rows and 0 <= nc < self.cols:
                if not self.grid[nr][nc].visited:
                    result.append((d, nr, nc))
        random.shuffle(result)
        return result

    # ── Entrance / Exit ──────────────────────────────────────

    def _open_entrance_exit(self):
        """Open the outer walls at the entrance and exit cells."""
        # Entrance: top wall of top-left cell
        er, ec = self.entrance
        self.grid[er][ec].walls[_N] = False

        # Exit: bottom wall of bottom-right cell
        xr, xc = self.exit
        self.grid[xr][xc].walls[_S] = False

    # ── Solver (BFS for shortest path) ───────────────────────

    def _solve(self) -> list[tuple[int, int]]:
        """Find shortest path from entrance to exit using BFS."""
        start = self.entrance
        end = self.exit

        visited = {start}
        parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        queue = deque([start])

        while queue:
            r, c = queue.popleft()
            if (r, c) == end:
                break

            cell = self.grid[r][c]
            for d in _ALL_DIRS:
                if not cell.walls[d]:  # passage open
                    nr, nc = r + d[0], c + d[1]
                    if 0 <= nr < self.rows and 0 <= nc < self.cols:
                        if (nr, nc) not in visited:
                            visited.add((nr, nc))
                            parent[(nr, nc)] = (r, c)
                            queue.append((nr, nc))

        # Reconstruct path
        path: list[tuple[int, int]] = []
        node: tuple[int, int] | None = end
        while node is not None:
            path.append(node)
            node = parent.get(node)
        path.reverse()
        return path


def generate_maze(difficulty: str = "medium") -> Maze:
    """
    Generate a maze at the requested difficulty.

    Args:
        difficulty: "easy" (15x15), "medium" (20x20), or "hard" (25x25)

    Returns:
        Maze object with grid and solved path
    """
    size_map = {
        "easy": 15,
        "medium": 20,
        "hard": 25,
    }
    size = size_map.get(difficulty, 20)
    return Maze(rows=size, cols=size)


# ── PDF Generation ───────────────────────────────────────────────

@dataclass
class MazeBookConfig:
    """Configuration for a maze puzzle book."""
    title: str = "Amazing Mazes"
    subtitle: str = "Volume 1"
    author: str = "Creative Puzzles Press"
    num_puzzles: int = 50
    difficulty: str = "medium"        # easy, medium, hard
    large_print: bool = True
    trim_width: float = 8.5           # inches
    trim_height: float = 11.0         # inches
    margin_top: float = 0.75
    margin_bottom: float = 0.75
    margin_outside: float = 0.75
    margin_gutter: float = 0.5        # inside margin (near spine)


def generate_maze_book(config: MazeBookConfig, output_path: Path) -> dict:
    """
    Generate a complete maze book PDF.

    Returns:
        Dict with metadata about the generated book.
    """
    page_w = config.trim_width * inch
    page_h = config.trim_height * inch

    c = canvas.Canvas(str(output_path), pagesize=(page_w, page_h))

    page_count = 0
    mazes: list[Maze] = []

    # ── Title Page ────────────────────────────────────────────
    _draw_title_page(c, config, page_w, page_h)
    page_count += 1

    # ── Copyright Page ────────────────────────────────────────
    c.showPage()
    _draw_copyright_page(c, config, page_w, page_h)
    page_count += 1

    # ── Puzzle Pages ──────────────────────────────────────────
    for i in range(config.num_puzzles):
        maze = generate_maze(config.difficulty)
        mazes.append(maze)

        c.showPage()
        is_left = (page_count % 2 == 0)  # even pages are left (verso)
        _draw_maze_page(c, maze, i + 1, config, page_w, page_h, is_left)
        page_count += 1

    # ── Answer Key Section ────────────────────────────────────
    c.showPage()
    _draw_section_header(c, "Answer Key", page_w, page_h)
    page_count += 1

    # Answer pages — 2 per page
    answers_per_page = 2
    for batch_start in range(0, len(mazes), answers_per_page):
        c.showPage()
        batch = mazes[batch_start:batch_start + answers_per_page]
        is_left = (page_count % 2 == 0)
        _draw_answer_page(c, batch, batch_start, config, page_w, page_h, is_left)
        page_count += 1

    # Pad to even page count (KDP requirement)
    if page_count % 2 != 0:
        c.showPage()
        page_count += 1

    c.save()

    return {
        "path": str(output_path),
        "page_count": page_count,
        "num_puzzles": len(mazes),
        "difficulty": config.difficulty,
    }


# ── Internal Drawing Helpers ─────────────────────────────────────

def _draw_title_page(c, config: MazeBookConfig, page_w: float, page_h: float):
    """Draw the book's title page."""
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(page_w / 2, page_h - 3 * inch, config.title)

    c.setFont("Helvetica", 18)
    c.drawCentredString(page_w / 2, page_h - 3.8 * inch, config.subtitle)

    c.setFont("Helvetica", 14)
    difficulty_label = config.difficulty.title()
    c.drawCentredString(
        page_w / 2,
        page_h - 4.5 * inch,
        f"{config.num_puzzles} {difficulty_label} Puzzles",
    )

    if config.large_print:
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(page_w / 2, page_h - 5.2 * inch, "LARGE PRINT")

    c.setFont("Helvetica", 14)
    c.drawCentredString(page_w / 2, page_h - 8 * inch, config.author)


def _draw_copyright_page(c, config: MazeBookConfig, page_w: float, page_h: float):
    """Draw the copyright page."""
    y = page_h - 2 * inch
    c.setFont("Helvetica", 9)
    lines = [
        f"\u00a9 2026 {config.author}",
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


def _draw_section_header(c, title: str, page_w: float, page_h: float):
    """Draw a section divider page (e.g. 'Answer Key')."""
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(page_w / 2, page_h / 2 + 20, title)


def _draw_maze_page(
    c,
    maze: Maze,
    number: int,
    config: MazeBookConfig,
    page_w: float,
    page_h: float,
    is_left: bool,
):
    """Draw a single maze puzzle page with wall-based line drawing."""
    ml = config.margin_gutter * inch if is_left else config.margin_outside * inch
    mr = config.margin_outside * inch if is_left else config.margin_gutter * inch
    mt = config.margin_top * inch
    mb = config.margin_bottom * inch

    usable_w = page_w - ml - mr
    usable_h = page_h - mt - mb

    # ── Header ────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.drawString(ml, page_h - mt + 5, f"Puzzle #{number}")
    c.setFont("Helvetica", 10)
    c.drawRightString(page_w - mr, page_h - mt + 5, config.difficulty.title())

    # ── Compute cell size so the maze fits with room to spare ─
    header_gap = 40  # pts below header
    footer_gap = 30  # pts above page number
    available_h = usable_h - header_gap - footer_gap
    available_w = usable_w

    cell_size = min(available_w / maze.cols, available_h / maze.rows)

    grid_w = maze.cols * cell_size
    grid_h = maze.rows * cell_size

    # Centre the maze in the usable area
    grid_left = ml + (usable_w - grid_w) / 2
    grid_top = page_h - mt - header_gap

    # ── Entrance / Exit arrows ────────────────────────────────
    _draw_entrance_exit(c, maze, grid_left, grid_top, cell_size)

    # ── Draw walls ────────────────────────────────────────────
    wall_width = 2.0 if config.large_print else 1.5
    c.setLineWidth(wall_width)
    c.setStrokeColor(colors.Color(0, 0, 0))
    c.setLineCap(1)  # round cap for cleaner corners

    for r in range(maze.rows):
        for col in range(maze.cols):
            cell = maze.grid[r][col]
            x = grid_left + col * cell_size
            y = grid_top - r * cell_size

            # North wall
            if cell.walls[_N]:
                c.line(x, y, x + cell_size, y)

            # West wall
            if cell.walls[_W]:
                c.line(x, y, x, y - cell_size)

            # East wall (only draw for rightmost column)
            if col == maze.cols - 1 and cell.walls[_E]:
                c.line(x + cell_size, y, x + cell_size, y - cell_size)

            # South wall (only draw for bottom row)
            if r == maze.rows - 1 and cell.walls[_S]:
                c.line(x, y - cell_size, x + cell_size, y - cell_size)

    # ── Page number ───────────────────────────────────────────
    c.setFont("Helvetica", 9)
    c.drawCentredString(page_w / 2, mb / 2, str(number))


def _draw_entrance_exit(
    c,
    maze: Maze,
    grid_left: float,
    grid_top: float,
    cell_size: float,
):
    """Draw small arrow markers at the maze entrance and exit."""
    arrow_len = cell_size * 0.6
    c.setLineWidth(1.5)
    c.setStrokeColor(colors.Color(0.3, 0.3, 0.3))

    # Entrance arrow — pointing down into the maze from above top-left cell
    er, ec = maze.entrance
    ex = grid_left + ec * cell_size + cell_size / 2
    ey_top = grid_top - er * cell_size
    # Shaft
    c.line(ex, ey_top + arrow_len, ex, ey_top + 2)
    # Arrowhead
    c.line(ex, ey_top + 2, ex - 4, ey_top + 10)
    c.line(ex, ey_top + 2, ex + 4, ey_top + 10)

    # "Start" label
    c.setFont("Helvetica", 7)
    c.drawCentredString(ex, ey_top + arrow_len + 4, "START")

    # Exit arrow — pointing down out of the maze from below bottom-right cell
    xr, xc = maze.exit
    xx = grid_left + xc * cell_size + cell_size / 2
    xy_bottom = grid_top - (xr + 1) * cell_size
    # Shaft
    c.setLineWidth(1.5)
    c.setStrokeColor(colors.Color(0.3, 0.3, 0.3))
    c.line(xx, xy_bottom - 2, xx, xy_bottom - arrow_len)
    # Arrowhead
    c.line(xx, xy_bottom - arrow_len, xx - 4, xy_bottom - arrow_len + 8)
    c.line(xx, xy_bottom - arrow_len, xx + 4, xy_bottom - arrow_len + 8)

    # "End" label
    c.setFont("Helvetica", 7)
    c.drawCentredString(xx, xy_bottom - arrow_len - 10, "END")


def _draw_answer_page(
    c,
    batch: list[Maze],
    start_idx: int,
    config: MazeBookConfig,
    page_w: float,
    page_h: float,
    is_left: bool,
):
    """Draw answer-key mazes (2 per page) with the solution path highlighted."""
    ml = config.margin_gutter * inch if is_left else config.margin_outside * inch
    mr = config.margin_outside * inch if is_left else config.margin_gutter * inch
    mt = config.margin_top * inch
    mb = config.margin_bottom * inch

    usable_w = page_w - ml - mr
    usable_h = page_h - mt - mb

    # Two mazes stacked vertically
    slot_h = (usable_h - 30) / 2  # 30 pts gap between the two

    for idx, maze in enumerate(batch):
        if idx >= 2:
            break

        puzzle_num = start_idx + idx + 1

        # Slot vertical offset
        slot_top = page_h - mt - idx * (slot_h + 30)

        # Label
        c.setFont("Helvetica-Bold", 10)
        c.drawString(ml, slot_top + 4, f"#{puzzle_num}")

        # Compute cell size for the mini maze
        label_gap = 16
        available_h = slot_h - label_gap
        available_w = usable_w

        cell_size = min(available_w / maze.cols, available_h / maze.rows)
        grid_w = maze.cols * cell_size
        grid_h = maze.rows * cell_size

        grid_left = ml + (usable_w - grid_w) / 2
        grid_top_y = slot_top - label_gap

        # ── Draw solution path highlight ──────────────────────
        solution_set = set(maze.solution_path)
        highlight_color = colors.Color(0.85, 0.93, 1.0)

        for (r, col) in maze.solution_path:
            x = grid_left + col * cell_size
            y = grid_top_y - r * cell_size
            c.setFillColor(highlight_color)
            c.rect(x, y - cell_size, cell_size, cell_size, fill=1, stroke=0)

        # Draw the solution line through cell centres
        c.setStrokeColor(colors.Color(0.2, 0.5, 0.9))
        c.setLineWidth(max(1.0, cell_size * 0.15))
        c.setLineCap(1)

        path = maze.solution_path
        if len(path) >= 2:
            p = c.beginPath()
            r0, c0 = path[0]
            sx = grid_left + c0 * cell_size + cell_size / 2
            sy = grid_top_y - r0 * cell_size - cell_size / 2
            p.moveTo(sx, sy)
            for (r, col) in path[1:]:
                nx = grid_left + col * cell_size + cell_size / 2
                ny = grid_top_y - r * cell_size - cell_size / 2
                p.lineTo(nx, ny)
            c.drawPath(p, fill=0, stroke=1)

        # ── Draw walls (thin) ────────────────────────────────
        c.setStrokeColor(colors.Color(0, 0, 0))
        c.setLineWidth(0.6)
        c.setLineCap(1)

        for r in range(maze.rows):
            for col in range(maze.cols):
                cell = maze.grid[r][col]
                x = grid_left + col * cell_size
                y = grid_top_y - r * cell_size

                if cell.walls[_N]:
                    c.line(x, y, x + cell_size, y)
                if cell.walls[_W]:
                    c.line(x, y, x, y - cell_size)
                if col == maze.cols - 1 and cell.walls[_E]:
                    c.line(x + cell_size, y, x + cell_size, y - cell_size)
                if r == maze.rows - 1 and cell.walls[_S]:
                    c.line(x, y - cell_size, x + cell_size, y - cell_size)

        c.setFillColor(colors.Color(0, 0, 0))

    # Page number
    c.setFont("Helvetica", 9)
    page_num = (start_idx // 2) + config.num_puzzles + 4  # approximate
    c.drawCentredString(page_w / 2, mb / 2, str(page_num))


# ── Main (for testing) ───────────────────────────────────────────

if __name__ == "__main__":
    output = Path("/Users/tiger/Desktop/CATALOG ENGINE/bookr/output/test_maze.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)

    config = MazeBookConfig(
        title="Amazing Large Print Mazes",
        subtitle="Fun Puzzles for All Ages",
        author="Creative Puzzles Press",
        num_puzzles=10,  # Quick test
        difficulty="medium",
        large_print=True,
    )

    print("Generating maze book...")
    result = generate_maze_book(config, output)
    print(f"Generated: {result['path']}")
    print(f"Pages: {result['page_count']}")
    print(f"Puzzles: {result['num_puzzles']}")
    print(f"Difficulty: {result['difficulty']}")
