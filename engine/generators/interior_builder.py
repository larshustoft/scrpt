"""
SCRPT Interior Builder
========================
Orchestrator that dispatches to the correct generator based on book type.
This is the single entry point for all interior PDF generation.

Usage:
    from engine.generators.interior_builder import build_interior
    result = build_interior(book_data, output_dir)
"""

import json
from pathlib import Path
from dataclasses import asdict

from .word_search import WordSearchBookConfig, generate_word_search_book
from .sudoku import SudokuBookConfig, generate_sudoku_book
from .math_workbook import MathBookConfig, generate_math_book


def build_interior(book_data: dict, output_dir: Path) -> dict:
    """
    Generate a book interior PDF based on book type and config.

    Args:
        book_data: Book metadata dict (from database)
        output_dir: Directory to write the PDF into

    Returns:
        Dict with generation results (path, page_count, etc.)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    book_type = book_data.get("book_type", "")
    title = book_data.get("title", "Untitled Book")  # from parent
    author = book_data.get("author_name", "Creative Puzzles Press")
    page_count = book_data.get("page_count", 120)
    trim_size = book_data.get("trim_size", "8.5x11")
    gen_config = book_data.get("generator_config", {})

    # Parse trim size
    trim_w, trim_h = _parse_trim(trim_size)

    output_path = output_dir / "interior.pdf"

    # ── Dispatch to generator ────────────────────────────────
    if book_type == "word_search":
        config = WordSearchBookConfig(
            title=title,
            subtitle=gen_config.get("subtitle", "Large Print Puzzles"),
            author=author,
            num_puzzles=gen_config.get("num_puzzles", 55),
            grid_size=gen_config.get("grid_size", 15),
            words_per_puzzle=gen_config.get("words_per_puzzle", 15),
            difficulty=gen_config.get("difficulty", "medium"),
            large_print=gen_config.get("large_print", True),
            trim_width=trim_w,
            trim_height=trim_h,
        )
        return generate_word_search_book(config, output_path)

    elif book_type == "sudoku":
        config = SudokuBookConfig(
            title=title,
            subtitle=gen_config.get("subtitle", "Volume 1"),
            author=author,
            num_puzzles=gen_config.get("num_puzzles", 55),
            difficulty=gen_config.get("difficulty", "medium"),
            large_print=gen_config.get("large_print", True),
            trim_width=trim_w,
            trim_height=trim_h,
        )
        return generate_sudoku_book(config, output_path)

    elif book_type == "math_workbook":
        config = MathBookConfig(
            title=title,
            subtitle=gen_config.get("subtitle", "Practice Problems"),
            author=author,
            num_pages=gen_config.get("num_pages", 50),
            problems_per_page=gen_config.get("problems_per_page", 20),
            operation=gen_config.get("operation", "mixed"),
            difficulty=gen_config.get("difficulty", "medium"),
            large_print=gen_config.get("large_print", True),
            trim_width=trim_w,
            trim_height=trim_h,
        )
        return generate_math_book(config, output_path)

    elif book_type == "cryptogram":
        try:
            from .cryptogram import CryptogramBookConfig, generate_cryptogram_book
            config = CryptogramBookConfig(
                title=title,
                subtitle=gen_config.get("subtitle", "Cryptogram Puzzles"),
                author=author,
                num_puzzles=gen_config.get("num_puzzles", 55),
                large_print=gen_config.get("large_print", True),
                trim_width=trim_w,
                trim_height=trim_h,
            )
            return generate_cryptogram_book(config, output_path)
        except ImportError:
            return _not_implemented(book_type, output_path)

    elif book_type == "maze":
        try:
            from .maze import MazeBookConfig, generate_maze_book
            config = MazeBookConfig(
                title=title,
                subtitle=gen_config.get("subtitle", "Maze Puzzles"),
                author=author,
                num_puzzles=gen_config.get("num_puzzles", 50),
                difficulty=gen_config.get("difficulty", "medium"),
                large_print=gen_config.get("large_print", True),
                trim_width=trim_w,
                trim_height=trim_h,
            )
            return generate_maze_book(config, output_path)
        except ImportError:
            return _not_implemented(book_type, output_path)

    elif book_type in ("password_log", "journal"):
        try:
            from .log_book import LogBookConfig, generate_log_book
            log_type = "password" if book_type == "password_log" else "gratitude"
            config = LogBookConfig(
                title=title,
                subtitle=gen_config.get("subtitle", ""),
                author=author,
                log_type=gen_config.get("log_type", log_type),
                num_pages=page_count - 4,  # Subtract title/copyright/etc
                trim_width=trim_w,
                trim_height=trim_h,
            )
            return generate_log_book(config, output_path)
        except ImportError:
            return _not_implemented(book_type, output_path)

    elif book_type in ("coloring_book", "color_by_number", "kids_activity"):
        # These need AI-generated images (ComfyUI) — Phase 4
        return _not_implemented(book_type, output_path)

    else:
        return _not_implemented(book_type, output_path)


def _parse_trim(trim_size: str) -> tuple[float, float]:
    """Parse trim size string like '8.5x11' into (width, height)."""
    try:
        parts = trim_size.lower().split("x")
        return float(parts[0]), float(parts[1])
    except (ValueError, IndexError):
        return 8.5, 11.0


def _not_implemented(book_type: str, output_path: Path) -> dict:
    """Placeholder for generators not yet implemented."""
    return {
        "path": str(output_path),
        "page_count": 0,
        "error": f"Generator for '{book_type}' not yet implemented",
        "status": "not_implemented",
    }


def get_available_generators() -> dict:
    """Return which generators are available and ready."""
    generators = {
        "word_search": True,
        "sudoku": True,
        "math_workbook": True,
        "cryptogram": False,
        "maze": False,
        "password_log": False,
        "journal": False,
        "coloring_book": False,
        "color_by_number": False,
        "kids_activity": False,
    }

    # Check if optional generators are importable
    try:
        from .cryptogram import generate_cryptogram_book
        generators["cryptogram"] = True
    except ImportError:
        pass

    try:
        from .maze import generate_maze_book
        generators["maze"] = True
    except ImportError:
        pass

    try:
        from .log_book import generate_log_book
        generators["password_log"] = True
        generators["journal"] = True
    except ImportError:
        pass

    return generators
