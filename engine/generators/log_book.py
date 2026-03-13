"""
SCRPT Log Book Generator
===========================
Creates complete template-based log book / planner PDFs for Amazon KDP.

Unlike puzzle generators, log books repeat the same page layout throughout.
Each page type draws its own form with labels, lines, and boxes.

Supported log types:
  - password_organizer: Alphabetical tabs with site/username/password/notes
  - fitness_log: Date, exercise, sets, reps, weight, notes
  - gratitude_journal: Date, 3 things grateful for, daily reflection
  - reading_log: Title, author, start/end date, rating, notes
  - expense_tracker: Date, description, category, amount, balance
  - blood_pressure_log: Date, time, systolic, diastolic, pulse, notes
  - garden_planner: Date, plant, location, water schedule, notes

Output: KDP-compliant PDF at trim size with proper margins.
"""

import string
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas


# ── Configuration ────────────────────────────────────────────────

LOG_TYPES = [
    "password_organizer",
    "fitness_log",
    "gratitude_journal",
    "reading_log",
    "expense_tracker",
    "blood_pressure_log",
    "garden_planner",
]

# How many content pages each letter gets in the password organizer
PAGES_PER_LETTER = 4

# Light gray for gridlines and table borders
GRAY_LINE = colors.Color(0.75, 0.75, 0.75)
GRAY_LIGHT = colors.Color(0.92, 0.92, 0.92)
BLACK = colors.Color(0, 0, 0)


@dataclass
class LogBookConfig:
    """Configuration for a log book / planner."""
    title: str = "My Log Book"
    subtitle: str = ""
    author: str = "SCRPT Publishing"
    log_type: str = "password_organizer"
    num_pages: int = 120
    trim_width: float = 6.0       # inches
    trim_height: float = 9.0      # inches
    margin_top: float = 0.65
    margin_bottom: float = 0.65
    margin_outside: float = 0.60
    margin_gutter: float = 0.75   # inside margin (near spine)


# ── Helpers ──────────────────────────────────────────────────────

def _margins(config: LogBookConfig, page_w: float, page_h: float, is_left: bool):
    """Return (ml, mr, mt, mb) in points, with gutter alternation."""
    if is_left:
        ml = config.margin_gutter * inch
        mr = config.margin_outside * inch
    else:
        ml = config.margin_outside * inch
        mr = config.margin_gutter * inch
    mt = config.margin_top * inch
    mb = config.margin_bottom * inch
    return ml, mr, mt, mb


def _usable_area(config, page_w, page_h, is_left):
    """Return (ml, mr, mt, mb, usable_w, usable_h)."""
    ml, mr, mt, mb = _margins(config, page_w, page_h, is_left)
    usable_w = page_w - ml - mr
    usable_h = page_h - mt - mb
    return ml, mr, mt, mb, usable_w, usable_h


def _draw_page_number(c, page_num, page_w, mb):
    """Draw centered page number at foot."""
    c.setFont("Helvetica", 8)
    c.setFillColor(BLACK)
    c.drawCentredString(page_w / 2, mb / 2, str(page_num))


def _draw_horizontal_rule(c, x, y, width, color=GRAY_LINE, line_width=0.5):
    """Draw a single horizontal line."""
    c.setStrokeColor(color)
    c.setLineWidth(line_width)
    c.line(x, y, x + width, y)


def _draw_label(c, text, x, y, font="Helvetica", size=8, color=BLACK):
    """Draw a small field label."""
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawString(x, y, text)


# ── Title Page ───────────────────────────────────────────────────

def _draw_title_page(c, config, page_w, page_h):
    """Draw the book title page."""
    # Title
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(BLACK)
    c.drawCentredString(page_w / 2, page_h - 3 * inch, config.title)

    # Subtitle
    if config.subtitle:
        c.setFont("Helvetica", 16)
        c.drawCentredString(page_w / 2, page_h - 3.7 * inch, config.subtitle)

    # Type badge
    nice_type = config.log_type.replace("_", " ").title()
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.Color(0.4, 0.4, 0.4))
    c.drawCentredString(page_w / 2, page_h - 4.6 * inch, nice_type)

    # Author
    c.setFont("Helvetica", 12)
    c.setFillColor(BLACK)
    c.drawCentredString(page_w / 2, page_h - 7 * inch, config.author)


# ── Copyright Page ───────────────────────────────────────────────

def _draw_copyright_page(c, config, page_w, page_h):
    """Draw the copyright / legal page."""
    y = page_h - 2 * inch
    c.setFont("Helvetica", 8)
    c.setFillColor(BLACK)
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
        y -= 13


# ── Password Organizer ───────────────────────────────────────────

def _draw_password_page(c, config, page_w, page_h, is_left, page_num, letter, letter_page_idx):
    """
    Draw one page of the password organizer.

    Each page has a large letter tab at the top, then 3 entry blocks.
    Each entry has fields: Website / Service, Username, Password, Notes.
    """
    ml, mr, mt, mb, usable_w, usable_h = _usable_area(config, page_w, page_h, is_left)

    # ── Alphabetical tab header ──
    tab_height = 36
    tab_y = page_h - mt - tab_height

    # Background bar
    c.setFillColor(colors.Color(0.93, 0.93, 0.93))
    c.rect(ml, tab_y, usable_w, tab_height, fill=1, stroke=0)

    # Large letter
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(BLACK)
    c.drawString(ml + 10, tab_y + 8, letter)

    # Small alphabet strip showing all letters, current highlighted
    strip_x = ml + 50
    letter_spacing = (usable_w - 60) / 26
    c.setFont("Helvetica", 7)
    for i, ch in enumerate(string.ascii_uppercase):
        cx = strip_x + i * letter_spacing
        if ch == letter:
            c.setFont("Helvetica-Bold", 8)
            c.setFillColor(BLACK)
        else:
            c.setFont("Helvetica", 7)
            c.setFillColor(colors.Color(0.6, 0.6, 0.6))
        c.drawCentredString(cx, tab_y + 12, ch)

    c.setFillColor(BLACK)

    # ── Entry blocks (3 per page) ──
    entries_per_page = 3
    block_gap = 18
    cursor_y = tab_y - 20

    field_defs = [
        ("Website / Service", 1.0),
        ("Username", 1.0),
        ("Password", 1.0),
        ("Notes", 1.0),
    ]

    for entry_idx in range(entries_per_page):
        if cursor_y < mb + 40:
            break

        # Entry number label
        global_entry = letter_page_idx * entries_per_page + entry_idx + 1
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.Color(0.5, 0.5, 0.5))
        c.drawString(ml, cursor_y, f"Entry {global_entry}")
        c.setFillColor(BLACK)
        cursor_y -= 6

        for label_text, _weight in field_defs:
            cursor_y -= 18
            if cursor_y < mb:
                break
            _draw_label(c, label_text, ml, cursor_y + 4, size=8,
                        color=colors.Color(0.35, 0.35, 0.35))
            _draw_horizontal_rule(c, ml, cursor_y, usable_w)

        cursor_y -= block_gap

    _draw_page_number(c, page_num, page_w, mb)


# ── Fitness Log ──────────────────────────────────────────────────

def _draw_fitness_page(c, config, page_w, page_h, is_left, page_num):
    """
    Fitness log page with a table: rows for exercises.

    Header row: Date | Exercise | Sets | Reps | Weight | Notes
    Then 12-14 ruled rows for entries.
    """
    ml, mr, mt, mb, usable_w, usable_h = _usable_area(config, page_w, page_h, is_left)

    # Page header
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(BLACK)
    c.drawString(ml, page_h - mt + 4, "Fitness Log")

    # Date field at top right
    _draw_label(c, "Date: _______________", ml + usable_w - 140, page_h - mt + 4, size=9)

    # Table setup
    table_top = page_h - mt - 20
    col_specs = [
        ("Exercise", 0.30),
        ("Sets", 0.10),
        ("Reps", 0.10),
        ("Weight", 0.13),
        ("Notes", 0.37),
    ]
    row_height = 26
    header_height = 20

    # Column x positions
    col_positions = []
    cx = ml
    for label, frac in col_specs:
        col_positions.append((cx, frac * usable_w, label))
        cx += frac * usable_w

    # Header background
    c.setFillColor(colors.Color(0.93, 0.93, 0.93))
    c.rect(ml, table_top - header_height, usable_w, header_height, fill=1, stroke=0)

    # Header labels
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(BLACK)
    for col_x, col_w, label in col_positions:
        c.drawString(col_x + 4, table_top - header_height + 6, label)

    # Vertical column lines across entire table
    num_rows = int((table_top - header_height - mb - 10) / row_height)
    table_bottom = table_top - header_height - num_rows * row_height

    c.setStrokeColor(GRAY_LINE)
    c.setLineWidth(0.5)
    for col_x, col_w, _ in col_positions:
        c.line(col_x, table_top, col_x, table_bottom)
    # Right edge
    c.line(ml + usable_w, table_top, ml + usable_w, table_bottom)

    # Horizontal row lines
    for i in range(num_rows + 1):
        y = table_top - header_height - i * row_height
        lw = 0.7 if i == 0 else 0.4
        _draw_horizontal_rule(c, ml, y, usable_w, GRAY_LINE, lw)

    # Alternating row shading
    for i in range(num_rows):
        if i % 2 == 1:
            y = table_top - header_height - i * row_height - row_height
            c.setFillColor(GRAY_LIGHT)
            c.rect(ml, y, usable_w, row_height, fill=1, stroke=0)

    # Redraw lines on top of shading
    c.setStrokeColor(GRAY_LINE)
    c.setLineWidth(0.4)
    for i in range(num_rows + 1):
        y = table_top - header_height - i * row_height
        c.line(ml, y, ml + usable_w, y)
    for col_x, col_w, _ in col_positions:
        c.line(col_x, table_top - header_height, col_x, table_bottom)
    c.line(ml + usable_w, table_top - header_height, ml + usable_w, table_bottom)

    # Outer border
    c.setStrokeColor(GRAY_LINE)
    c.setLineWidth(0.7)
    c.rect(ml, table_bottom, usable_w, table_top - table_bottom, fill=0, stroke=1)

    _draw_page_number(c, page_num, page_w, mb)


# ── Gratitude Journal ────────────────────────────────────────────

def _draw_gratitude_page(c, config, page_w, page_h, is_left, page_num):
    """
    Gratitude journal page.

    - Date field
    - "3 Things I'm Grateful For" with numbered lines
    - "Daily Reflection" with lined writing area
    """
    ml, mr, mt, mb, usable_w, usable_h = _usable_area(config, page_w, page_h, is_left)

    cursor_y = page_h - mt

    # Page header
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(BLACK)
    c.drawString(ml, cursor_y + 4, "Gratitude Journal")
    cursor_y -= 28

    # Date
    _draw_label(c, "Date:", ml, cursor_y + 4, size=9,
                color=colors.Color(0.35, 0.35, 0.35))
    _draw_horizontal_rule(c, ml + 35, cursor_y, usable_w - 35)
    cursor_y -= 30

    # Section: 3 Things I'm Grateful For
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(BLACK)
    c.drawString(ml, cursor_y, "3 Things I'm Grateful For")
    cursor_y -= 8

    line_spacing = 42
    for i in range(1, 4):
        cursor_y -= 14
        # Number circle
        circle_x = ml + 10
        circle_y = cursor_y + 3
        c.setStrokeColor(GRAY_LINE)
        c.setLineWidth(0.8)
        c.circle(circle_x, circle_y, 7, fill=0, stroke=1)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.Color(0.5, 0.5, 0.5))
        c.drawCentredString(circle_x, circle_y - 3, str(i))
        c.setFillColor(BLACK)

        # Writing line
        line_x = ml + 24
        _draw_horizontal_rule(c, line_x, cursor_y - 2, usable_w - 24)
        # Second line for more space
        cursor_y -= 22
        _draw_horizontal_rule(c, line_x, cursor_y - 2, usable_w - 24)
        cursor_y -= 6

    cursor_y -= 16

    # Section: Daily Reflection
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(BLACK)
    c.drawString(ml, cursor_y, "Daily Reflection")
    cursor_y -= 12

    # Ruled lines filling the rest of the page
    line_spacing = 24
    while cursor_y > mb + 20:
        cursor_y -= line_spacing
        _draw_horizontal_rule(c, ml, cursor_y, usable_w)

    _draw_page_number(c, page_num, page_w, mb)


# ── Reading Log ──────────────────────────────────────────────────

def _draw_reading_page(c, config, page_w, page_h, is_left, page_num):
    """
    Reading log page with 3 book entry blocks.

    Each block: Title, Author, Start Date, End Date, Rating (stars), Notes.
    """
    ml, mr, mt, mb, usable_w, usable_h = _usable_area(config, page_w, page_h, is_left)

    # Page header
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(BLACK)
    c.drawString(ml, page_h - mt + 4, "Reading Log")

    cursor_y = page_h - mt - 22
    entries = 3
    block_gap = 20

    for entry_idx in range(entries):
        if cursor_y < mb + 60:
            break

        # Separator line for entries after the first
        if entry_idx > 0:
            c.setStrokeColor(colors.Color(0.82, 0.82, 0.82))
            c.setLineWidth(1.0)
            c.line(ml + usable_w * 0.1, cursor_y + 10,
                   ml + usable_w * 0.9, cursor_y + 10)

        # Book number badge
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.Color(0.5, 0.5, 0.5))
        c.drawString(ml, cursor_y, f"Book {entry_idx + 1}")
        c.setFillColor(BLACK)
        cursor_y -= 6

        # Title
        cursor_y -= 18
        _draw_label(c, "Title:", ml, cursor_y + 4, size=8,
                    color=colors.Color(0.35, 0.35, 0.35))
        _draw_horizontal_rule(c, ml + 35, cursor_y, usable_w - 35)

        # Author
        cursor_y -= 22
        _draw_label(c, "Author:", ml, cursor_y + 4, size=8,
                    color=colors.Color(0.35, 0.35, 0.35))
        _draw_horizontal_rule(c, ml + 42, cursor_y, usable_w - 42)

        # Start / End on same row, split
        cursor_y -= 22
        half_w = usable_w / 2 - 10
        _draw_label(c, "Start Date:", ml, cursor_y + 4, size=8,
                    color=colors.Color(0.35, 0.35, 0.35))
        _draw_horizontal_rule(c, ml + 60, cursor_y, half_w - 60)

        right_x = ml + usable_w / 2 + 10
        _draw_label(c, "End Date:", right_x, cursor_y + 4, size=8,
                    color=colors.Color(0.35, 0.35, 0.35))
        _draw_horizontal_rule(c, right_x + 55, cursor_y, half_w - 55)

        # Rating (star outlines)
        cursor_y -= 22
        _draw_label(c, "Rating:", ml, cursor_y + 4, size=8,
                    color=colors.Color(0.35, 0.35, 0.35))
        star_x = ml + 44
        c.setStrokeColor(GRAY_LINE)
        c.setLineWidth(0.6)
        for s in range(5):
            _draw_star_outline(c, star_x + s * 18, cursor_y + 4, 6)

        # Notes (2 lines)
        cursor_y -= 22
        _draw_label(c, "Notes:", ml, cursor_y + 4, size=8,
                    color=colors.Color(0.35, 0.35, 0.35))
        _draw_horizontal_rule(c, ml + 38, cursor_y, usable_w - 38)
        cursor_y -= 20
        _draw_horizontal_rule(c, ml, cursor_y, usable_w)
        cursor_y -= 20
        _draw_horizontal_rule(c, ml, cursor_y, usable_w)

        cursor_y -= block_gap

    _draw_page_number(c, page_num, page_w, mb)


def _draw_star_outline(c, x, y, radius):
    """Draw a 5-pointed star outline at (x, y)."""
    import math
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        r = radius if i % 2 == 0 else radius * 0.45
        px = x + r * math.cos(angle)
        py = y + r * math.sin(angle)
        points.append((px, py))

    p = c.beginPath()
    p.moveTo(points[0][0], points[0][1])
    for px, py in points[1:]:
        p.lineTo(px, py)
    p.close()
    c.setStrokeColor(GRAY_LINE)
    c.setLineWidth(0.6)
    c.setFillColor(colors.Color(1, 1, 1))
    c.drawPath(p, fill=0, stroke=1)
    c.setFillColor(BLACK)


# ── Expense Tracker ──────────────────────────────────────────────

def _draw_expense_page(c, config, page_w, page_h, is_left, page_num):
    """
    Expense tracker page with a table.

    Columns: Date | Description | Category | Amount | Balance
    """
    ml, mr, mt, mb, usable_w, usable_h = _usable_area(config, page_w, page_h, is_left)

    # Page header
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(BLACK)
    c.drawString(ml, page_h - mt + 4, "Expense Tracker")

    # Month / Period field
    _draw_label(c, "Period: ___________________", ml + usable_w - 160, page_h - mt + 4, size=9)

    # Table setup
    table_top = page_h - mt - 20
    col_specs = [
        ("Date", 0.15),
        ("Description", 0.32),
        ("Category", 0.18),
        ("Amount", 0.15),
        ("Balance", 0.20),
    ]
    row_height = 24
    header_height = 18

    col_positions = []
    cx = ml
    for label, frac in col_specs:
        col_positions.append((cx, frac * usable_w, label))
        cx += frac * usable_w

    # Header background
    c.setFillColor(colors.Color(0.93, 0.93, 0.93))
    c.rect(ml, table_top - header_height, usable_w, header_height, fill=1, stroke=0)

    # Header labels
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(BLACK)
    for col_x, col_w, label in col_positions:
        c.drawString(col_x + 3, table_top - header_height + 5, label)

    num_rows = int((table_top - header_height - mb - 10) / row_height)
    table_bottom = table_top - header_height - num_rows * row_height

    # Alternating row shading
    for i in range(num_rows):
        if i % 2 == 1:
            y = table_top - header_height - i * row_height - row_height
            c.setFillColor(GRAY_LIGHT)
            c.rect(ml, y, usable_w, row_height, fill=1, stroke=0)

    # Grid lines
    c.setStrokeColor(GRAY_LINE)
    c.setLineWidth(0.4)
    for i in range(num_rows + 1):
        y = table_top - header_height - i * row_height
        c.line(ml, y, ml + usable_w, y)
    for col_x, col_w, _ in col_positions:
        c.line(col_x, table_top, col_x, table_bottom)
    c.line(ml + usable_w, table_top, ml + usable_w, table_bottom)

    # Outer border
    c.setStrokeColor(GRAY_LINE)
    c.setLineWidth(0.7)
    c.rect(ml, table_bottom, usable_w, table_top - table_bottom, fill=0, stroke=1)

    # Totals row at bottom
    c.setFillColor(colors.Color(0.88, 0.88, 0.88))
    c.rect(ml, table_bottom, usable_w, row_height, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(BLACK)
    c.drawString(ml + 4, table_bottom + 7, "TOTAL")
    # Redraw bottom lines
    c.setStrokeColor(GRAY_LINE)
    c.setLineWidth(0.7)
    c.rect(ml, table_bottom, usable_w, row_height, fill=0, stroke=1)

    _draw_page_number(c, page_num, page_w, mb)


# ── Blood Pressure Log ───────────────────────────────────────────

def _draw_blood_pressure_page(c, config, page_w, page_h, is_left, page_num):
    """
    Blood pressure log page with a table.

    Columns: Date | Time | Systolic | Diastolic | Pulse | Notes
    """
    ml, mr, mt, mb, usable_w, usable_h = _usable_area(config, page_w, page_h, is_left)

    # Page header
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(BLACK)
    c.drawString(ml, page_h - mt + 4, "Blood Pressure Log")

    # Name / Doctor fields
    name_y = page_h - mt - 14
    _draw_label(c, "Name: _________________________", ml, name_y, size=8,
                color=colors.Color(0.4, 0.4, 0.4))
    _draw_label(c, "Doctor: _________________________", ml + usable_w / 2, name_y, size=8,
                color=colors.Color(0.4, 0.4, 0.4))

    # Table setup
    table_top = name_y - 16
    col_specs = [
        ("Date", 0.15),
        ("Time", 0.12),
        ("SYS", 0.12),
        ("DIA", 0.12),
        ("Pulse", 0.12),
        ("Notes", 0.37),
    ]
    row_height = 24
    header_height = 18

    col_positions = []
    cx = ml
    for label, frac in col_specs:
        col_positions.append((cx, frac * usable_w, label))
        cx += frac * usable_w

    # Header background
    c.setFillColor(colors.Color(0.93, 0.93, 0.93))
    c.rect(ml, table_top - header_height, usable_w, header_height, fill=1, stroke=0)

    # Header labels
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(BLACK)
    for col_x, col_w, label in col_positions:
        c.drawString(col_x + 3, table_top - header_height + 5, label)

    num_rows = int((table_top - header_height - mb - 10) / row_height)
    table_bottom = table_top - header_height - num_rows * row_height

    # Alternating row shading
    for i in range(num_rows):
        if i % 2 == 1:
            y = table_top - header_height - i * row_height - row_height
            c.setFillColor(GRAY_LIGHT)
            c.rect(ml, y, usable_w, row_height, fill=1, stroke=0)

    # Grid lines
    c.setStrokeColor(GRAY_LINE)
    c.setLineWidth(0.4)
    for i in range(num_rows + 1):
        y = table_top - header_height - i * row_height
        c.line(ml, y, ml + usable_w, y)
    for col_x, col_w, _ in col_positions:
        c.line(col_x, table_top, col_x, table_bottom)
    c.line(ml + usable_w, table_top, ml + usable_w, table_bottom)

    # Outer border
    c.setStrokeColor(GRAY_LINE)
    c.setLineWidth(0.7)
    c.rect(ml, table_bottom, usable_w, table_top - table_bottom, fill=0, stroke=1)

    _draw_page_number(c, page_num, page_w, mb)


# ── Garden Planner ───────────────────────────────────────────────

def _draw_garden_page(c, config, page_w, page_h, is_left, page_num):
    """
    Garden planner page with 4 plant entry blocks.

    Each block: Date, Plant, Location, Water Schedule, Notes.
    """
    ml, mr, mt, mb, usable_w, usable_h = _usable_area(config, page_w, page_h, is_left)

    # Page header
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(BLACK)
    c.drawString(ml, page_h - mt + 4, "Garden Planner")

    cursor_y = page_h - mt - 22
    entries = 4
    block_gap = 16

    for entry_idx in range(entries):
        if cursor_y < mb + 50:
            break

        # Light separator
        if entry_idx > 0:
            c.setStrokeColor(colors.Color(0.82, 0.82, 0.82))
            c.setLineWidth(0.8)
            c.line(ml, cursor_y + 8, ml + usable_w, cursor_y + 8)

        # Entry badge
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.Color(0.5, 0.5, 0.5))
        c.drawString(ml, cursor_y, f"Plant {entry_idx + 1}")
        c.setFillColor(BLACK)
        cursor_y -= 6

        # Date + Plant on same row
        cursor_y -= 18
        _draw_label(c, "Date:", ml, cursor_y + 4, size=8,
                    color=colors.Color(0.35, 0.35, 0.35))
        half = usable_w / 2 - 10
        _draw_horizontal_rule(c, ml + 32, cursor_y, half - 32)

        right_x = ml + usable_w / 2 + 10
        _draw_label(c, "Plant:", right_x, cursor_y + 4, size=8,
                    color=colors.Color(0.35, 0.35, 0.35))
        _draw_horizontal_rule(c, right_x + 36, cursor_y, half - 36)

        # Location + Water Schedule on same row
        cursor_y -= 22
        _draw_label(c, "Location:", ml, cursor_y + 4, size=8,
                    color=colors.Color(0.35, 0.35, 0.35))
        _draw_horizontal_rule(c, ml + 50, cursor_y, half - 50)

        _draw_label(c, "Water Schedule:", right_x, cursor_y + 4, size=8,
                    color=colors.Color(0.35, 0.35, 0.35))
        _draw_horizontal_rule(c, right_x + 82, cursor_y, half - 82)

        # Notes (2 lines)
        cursor_y -= 22
        _draw_label(c, "Notes:", ml, cursor_y + 4, size=8,
                    color=colors.Color(0.35, 0.35, 0.35))
        _draw_horizontal_rule(c, ml + 38, cursor_y, usable_w - 38)
        cursor_y -= 20
        _draw_horizontal_rule(c, ml, cursor_y, usable_w)

        cursor_y -= block_gap

    _draw_page_number(c, page_num, page_w, mb)


# ── Page Dispatch ────────────────────────────────────────────────

def _draw_content_page(c, config, page_w, page_h, is_left, page_num, **kwargs):
    """Dispatch to the correct page drawer based on log_type."""
    lt = config.log_type

    if lt == "password_organizer":
        letter = kwargs.get("letter", "A")
        letter_page_idx = kwargs.get("letter_page_idx", 0)
        _draw_password_page(c, config, page_w, page_h, is_left, page_num,
                            letter, letter_page_idx)
    elif lt == "fitness_log":
        _draw_fitness_page(c, config, page_w, page_h, is_left, page_num)
    elif lt == "gratitude_journal":
        _draw_gratitude_page(c, config, page_w, page_h, is_left, page_num)
    elif lt == "reading_log":
        _draw_reading_page(c, config, page_w, page_h, is_left, page_num)
    elif lt == "expense_tracker":
        _draw_expense_page(c, config, page_w, page_h, is_left, page_num)
    elif lt == "blood_pressure_log":
        _draw_blood_pressure_page(c, config, page_w, page_h, is_left, page_num)
    elif lt == "garden_planner":
        _draw_garden_page(c, config, page_w, page_h, is_left, page_num)
    else:
        raise ValueError(f"Unknown log_type: {lt!r}. Choose from: {LOG_TYPES}")


# ── Main Generator ───────────────────────────────────────────────

def generate_log_book(config: LogBookConfig, output_path: Path) -> dict:
    """
    Generate a complete log book PDF.

    Args:
        config: LogBookConfig with book parameters.
        output_path: Where to save the PDF file.

    Returns:
        Dict with metadata about the generated book.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_w = config.trim_width * inch
    page_h = config.trim_height * inch

    c = canvas.Canvas(str(output_path), pagesize=(page_w, page_h))

    page_count = 0

    # ── Title page ────────────────────────────────────────────
    _draw_title_page(c, config, page_w, page_h)
    page_count += 1

    # ── Copyright page ────────────────────────────────────────
    c.showPage()
    _draw_copyright_page(c, config, page_w, page_h)
    page_count += 1

    # ── Content pages ─────────────────────────────────────────
    if config.log_type == "password_organizer":
        # Special handling: alphabetical tabs, multiple pages per letter
        content_pages = 0
        for letter in string.ascii_uppercase:
            for lp_idx in range(PAGES_PER_LETTER):
                if content_pages >= config.num_pages:
                    break
                c.showPage()
                is_left = (page_count % 2 == 0)
                page_count += 1
                content_pages += 1
                _draw_content_page(
                    c, config, page_w, page_h, is_left, page_count - 2,
                    letter=letter, letter_page_idx=lp_idx,
                )
            if content_pages >= config.num_pages:
                break
    else:
        for i in range(config.num_pages):
            c.showPage()
            is_left = (page_count % 2 == 0)
            page_count += 1
            _draw_content_page(
                c, config, page_w, page_h, is_left, page_count - 2,
            )

    # ── Pad to even page count (KDP requirement) ──────────────
    if page_count % 2 != 0:
        c.showPage()
        page_count += 1

    c.save()

    return {
        "path": str(output_path),
        "page_count": page_count,
        "log_type": config.log_type,
        "title": config.title,
        "trim": f"{config.trim_width}x{config.trim_height}",
    }


# ── Main (for testing) ───────────────────────────────────────────

if __name__ == "__main__":
    output = Path("/Users/tiger/Desktop/CATALOG ENGINE/bookr/output/test_log_book.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)

    config = LogBookConfig(
        title="Internet Password Organizer",
        subtitle="Keep Your Passwords Safe & Organized",
        author="SCRPT Publishing",
        log_type="password_organizer",
        num_pages=120,
        trim_width=6.0,
        trim_height=9.0,
    )

    print(f"Generating {config.log_type} log book...")
    result = generate_log_book(config, output)
    print(f"Generated: {result['path']}")
    print(f"Pages: {result['page_count']}")
    print(f"Type: {result['log_type']}")
    print(f"Trim: {result['trim']}")
