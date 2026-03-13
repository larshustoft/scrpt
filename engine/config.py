"""
SCRPT Configuration
====================
Central configuration for all file paths, constants, and settings.
Everything runs locally — no cloud dependencies.
"""

import os
from pathlib import Path

# ── Project Root ─────────────────────────────────────────────────
# scrpt/ is the project root, engine/ is where this file lives
ENGINE_DIR = Path(__file__).parent
PROJECT_ROOT = ENGINE_DIR.parent

# ── Data & Output Directories ───────────────────────────────────
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
TEMPLATES_DIR = ENGINE_DIR / "cover" / "templates"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Database ─────────────────────────────────────────────────────
DATABASE_PATH = DATA_DIR / "scrpt.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# ── Server ───────────────────────────────────────────────────────
API_HOST = "127.0.0.1"  # Companion mode: only accessible locally
API_PORT = 8000
FRONTEND_URL = "http://localhost:3000"
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3002",
    "https://scrpt.ai",
    "https://www.scrpt.ai",
]

# ── Amazon KDP ───────────────────────────────────────────────────
KDP_MAX_UPLOADS_PER_DAY = 3
KDP_MIN_PAGES = 24
KDP_MAX_PAGES = 828
KDP_PRINT_DPI = 300

# ── Quality Thresholds ──────────────────────────────────────────
QUALITY_SCORE_MINIMUM = 85          # Minimum design quality score (0-100)
AI_VISION_SCORE_MINIMUM = 80       # Minimum AI review score (0-100)
DIMENSION_TOLERANCE = 0.005         # inches — Amazon cross-check tolerance

# ── ComfyUI (Local Stable Diffusion) ────────────────────────────
COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_OUTPUT_DIR = Path.home() / "ComfyUI" / "output"

# ── Catalog Numbering ───────────────────────────────────────────
CATALOG_PREFIX = "SC"  # SC-001, SC-002, etc.

# ── Cover Constants (from cover_dimensions.py) ──────────────────
BLEED = 0.125           # inches on each side
SAFE_ZONE = 0.25        # keep text/art this far from trim edges
BARCODE_WIDTH = 2.0     # inches
BARCODE_HEIGHT = 1.2    # inches
MIN_SPINE_FOR_TEXT = 79  # pages

# ── Pricing Strategy ────────────────────────────────────────────
# Always price above $9.98 to get 60% royalty instead of 50%
MINIMUM_LIST_PRICE = 9.99
DEFAULT_PRICES = {
    "word_search":      12.97,
    "coloring_book":    9.99,
    "cryptogram":       11.97,
    "kids_activity":    9.99,
    "password_log":     7.99,
    "color_by_number":  11.97,
    "sudoku":           9.97,
    "maze":             9.97,
    "math_workbook":    12.97,
    "journal":          9.99,
}

# ── Book Types ───────────────────────────────────────────────────
BOOK_TYPES = {
    "word_search": {
        "name": "Word Search",
        "default_trim": "8.5x11",
        "default_pages": 120,
        "default_paper": "white_bw",
        "generator": "word_search",
    },
    "coloring_book": {
        "name": "Coloring Book",
        "default_trim": "8.5x8.5",
        "default_pages": 50,
        "default_paper": "white_bw",
        "generator": "coloring",
    },
    "cryptogram": {
        "name": "Cryptogram Puzzle",
        "default_trim": "8.5x11",
        "default_pages": 120,
        "default_paper": "white_bw",
        "generator": "cryptogram",
    },
    "kids_activity": {
        "name": "Kids Activity Book",
        "default_trim": "8.5x11",
        "default_pages": 100,
        "default_paper": "white_bw",
        "generator": "activity",
    },
    "password_log": {
        "name": "Password Organizer",
        "default_trim": "6x9",
        "default_pages": 120,
        "default_paper": "white_bw",
        "generator": "log_book",
    },
    "color_by_number": {
        "name": "Color by Number",
        "default_trim": "8.5x11",
        "default_pages": 80,
        "default_paper": "white_bw",
        "generator": "color_by_number",
    },
    "sudoku": {
        "name": "Sudoku",
        "default_trim": "8.5x11",
        "default_pages": 120,
        "default_paper": "white_bw",
        "generator": "sudoku",
    },
    "maze": {
        "name": "Maze Book",
        "default_trim": "8.5x11",
        "default_pages": 100,
        "default_paper": "white_bw",
        "generator": "maze",
    },
    "math_workbook": {
        "name": "Math Workbook",
        "default_trim": "8.5x11",
        "default_pages": 100,
        "default_paper": "white_bw",
        "generator": "math_workbook",
    },
    "journal": {
        "name": "Journal / Planner",
        "default_trim": "6x9",
        "default_pages": 200,
        "default_paper": "cream_bw",
        "generator": "log_book",
    },
}

# ── Trim Sizes ───────────────────────────────────────────────────
TRIM_SIZE_OPTIONS = [
    {"value": "5x8",       "label": "5\" × 8\"",        "width": 5.0,   "height": 8.0},
    {"value": "5.25x8",    "label": "5.25\" × 8\"",     "width": 5.25,  "height": 8.0},
    {"value": "5.5x8.5",   "label": "5.5\" × 8.5\"",    "width": 5.5,   "height": 8.5},
    {"value": "6x9",       "label": "6\" × 9\"",        "width": 6.0,   "height": 9.0},
    {"value": "6.14x9.21", "label": "6.14\" × 9.21\"",  "width": 6.14,  "height": 9.21},
    {"value": "6.69x9.61", "label": "6.69\" × 9.61\"",  "width": 6.69,  "height": 9.61},
    {"value": "7x10",      "label": "7\" × 10\"",       "width": 7.0,   "height": 10.0},
    {"value": "7.44x9.69", "label": "7.44\" × 9.69\"",  "width": 7.44,  "height": 9.69},
    {"value": "7.5x9.25",  "label": "7.5\" × 9.25\"",   "width": 7.5,   "height": 9.25},
    {"value": "8x10",      "label": "8\" × 10\"",       "width": 8.0,   "height": 10.0},
    {"value": "8.5x8.5",   "label": "8.5\" × 8.5\"",    "width": 8.5,   "height": 8.5},
    {"value": "8.5x11",    "label": "8.5\" × 11\"",     "width": 8.5,   "height": 11.0},
]

# ── Paper Types ──────────────────────────────────────────────────
PAPER_TYPE_OPTIONS = [
    {"value": "white_bw",       "label": "White (B&W)"},
    {"value": "cream_bw",       "label": "Cream (B&W)"},
    {"value": "standard_color", "label": "Standard Color"},
    {"value": "premium_color",  "label": "Premium Color"},
]

# ── Status Flow ──────────────────────────────────────────────────
BOOK_STATUSES = [
    "draft",            # Initial creation
    "generating",       # Interior/cover being generated
    "quality_check",    # Running through 5-gate QC
    "ready",            # Passed QC, ready for upload
    "uploading",        # Being submitted to KDP
    "in_review",        # KDP reviewing
    "live",             # Published and for sale
    "rejected",         # KDP rejected — needs fixes
    "paused",           # Temporarily pulled
]
