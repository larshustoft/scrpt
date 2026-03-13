"""
SCRPT Math Workbook Generator
================================
Creates math practice workbooks for Amazon KDP.

Supports problem types:
  - Addition (single to triple digit)
  - Subtraction
  - Multiplication
  - Division
  - Mixed operations

Each page has a grid of problems with space for handwritten answers.
Answer key at the back.
"""

import random
import math
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas


@dataclass
class MathProblem:
    """A single math problem."""
    num1: int
    num2: int
    operation: str  # +, -, *, /
    answer: float
    display: str    # "24 + 17 = ___"

    @property
    def answer_display(self) -> str:
        if self.answer == int(self.answer):
            return str(int(self.answer))
        return f"{self.answer:.1f}"


def generate_problems(
    operation: str = "mixed",
    difficulty: str = "medium",
    count: int = 20,
) -> list[MathProblem]:
    """Generate a set of math problems."""
    problems = []

    ranges = {
        "easy":   {"add": (1, 20),  "sub": (1, 20),  "mul": (1, 10),  "div": (1, 10)},
        "medium": {"add": (10, 100), "sub": (10, 100), "mul": (2, 12),  "div": (2, 12)},
        "hard":   {"add": (50, 999), "sub": (50, 999), "mul": (10, 99), "div": (2, 20)},
    }

    r = ranges.get(difficulty, ranges["medium"])

    ops = {
        "addition": ["+"],
        "subtraction": ["-"],
        "multiplication": ["*"],
        "division": ["/"],
        "mixed": ["+", "-", "*", "/"],
    }
    available_ops = ops.get(operation, ["+", "-", "*", "/"])

    for _ in range(count):
        op = random.choice(available_ops)

        if op == "+":
            lo, hi = r["add"]
            a, b = random.randint(lo, hi), random.randint(lo, hi)
            ans = a + b
            display = f"{a} + {b} = ___"

        elif op == "-":
            lo, hi = r["sub"]
            a, b = random.randint(lo, hi), random.randint(lo, hi)
            if a < b:
                a, b = b, a  # Ensure positive results
            ans = a - b
            display = f"{a} - {b} = ___"

        elif op == "*":
            lo, hi = r["mul"]
            a, b = random.randint(lo, hi), random.randint(lo, hi)
            ans = a * b
            display = f"{a} x {b} = ___"

        elif op == "/":
            lo, hi = r["div"]
            b = random.randint(lo, hi)
            ans = random.randint(lo, hi)
            a = b * ans  # Ensure clean division
            display = f"{a} / {b} = ___"

        else:
            continue

        problems.append(MathProblem(
            num1=a, num2=b, operation=op,
            answer=ans, display=display,
        ))

    return problems


# ── PDF Generation ───────────────────────────────────────────────

@dataclass
class MathBookConfig:
    title: str = "Math Practice Workbook"
    subtitle: str = "Addition & Subtraction"
    author: str = "Creative Puzzles Press"
    num_pages: int = 50             # Pages of problems
    problems_per_page: int = 20
    operation: str = "mixed"        # addition, subtraction, multiplication, division, mixed
    difficulty: str = "medium"      # easy, medium, hard
    large_print: bool = True
    trim_width: float = 8.5
    trim_height: float = 11.0
    margin_top: float = 0.75
    margin_bottom: float = 0.75
    margin_outside: float = 0.75
    margin_gutter: float = 0.5


def generate_math_book(config: MathBookConfig, output_path: Path) -> dict:
    """Generate a complete math workbook PDF."""
    page_w = config.trim_width * inch
    page_h = config.trim_height * inch

    c = canvas.Canvas(str(output_path), pagesize=(page_w, page_h))
    page_count = 0
    all_problems = []

    # Title page
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(page_w / 2, page_h - 3 * inch, config.title)
    c.setFont("Helvetica", 18)
    c.drawCentredString(page_w / 2, page_h - 3.7 * inch, config.subtitle)
    c.setFont("Helvetica", 14)
    c.drawCentredString(page_w / 2, page_h - 4.5 * inch,
                        f"{config.num_pages * config.problems_per_page}+ Problems")
    if config.large_print:
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(page_w / 2, page_h - 5.2 * inch, "LARGE PRINT")
    c.setFont("Helvetica", 14)
    c.drawCentredString(page_w / 2, page_h - 8 * inch, config.author)
    page_count += 1

    # Copyright
    c.showPage()
    c.setFont("Helvetica", 9)
    c.drawCentredString(page_w / 2, page_h - 2 * inch, f"(c) 2026 {config.author}")
    c.drawCentredString(page_w / 2, page_h - 2.2 * inch, "All rights reserved.")
    page_count += 1

    # Problem pages
    for page_num in range(config.num_pages):
        problems = generate_problems(
            operation=config.operation,
            difficulty=config.difficulty,
            count=config.problems_per_page,
        )
        all_problems.append(problems)

        c.showPage()
        is_left = (page_count % 2 == 0)
        _draw_math_page(c, problems, page_num + 1, config, page_w, page_h, is_left)
        page_count += 1

    # Answer key
    c.showPage()
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(page_w / 2, page_h / 2, "Answer Key")
    page_count += 1

    for page_idx, problems in enumerate(all_problems):
        c.showPage()
        is_left = (page_count % 2 == 0)
        _draw_answer_page(c, problems, page_idx + 1, config, page_w, page_h, is_left)
        page_count += 1

    # Pad to even
    if page_count % 2 != 0:
        c.showPage()
        page_count += 1

    c.save()

    return {
        "path": str(output_path),
        "page_count": page_count,
        "total_problems": config.num_pages * config.problems_per_page,
        "operation": config.operation,
        "difficulty": config.difficulty,
    }


def _draw_math_page(c, problems, page_num, config, page_w, page_h, is_left):
    """Draw a page of math problems in a grid layout."""
    ml = config.margin_gutter * inch if is_left else config.margin_outside * inch
    mr = config.margin_outside * inch if is_left else config.margin_gutter * inch
    mt = config.margin_top * inch
    mb = config.margin_bottom * inch

    usable_w = page_w - ml - mr
    usable_h = page_h - mt - mb

    # Header
    c.setFont("Helvetica-Bold", 12)
    c.drawString(ml, page_h - mt + 5, f"Page {page_num}")

    # Layout: 2 columns of problems
    font_size = 18 if config.large_print else 14
    line_height = font_size * 2.2
    col_width = usable_w / 2
    problems_per_col = math.ceil(len(problems) / 2)

    c.setFont("Helvetica", font_size)

    for idx, problem in enumerate(problems):
        col = idx // problems_per_col
        row = idx % problems_per_col

        x = ml + col * col_width + 15
        y = page_h - mt - 30 - row * line_height

        # Problem number
        c.setFont("Helvetica", font_size - 4)
        c.setFillColor(colors.Color(0.5, 0.5, 0.5))
        c.drawString(x, y, f"{idx + 1}.")
        c.setFillColor(colors.Color(0, 0, 0))

        # Problem text
        c.setFont("Helvetica", font_size)
        c.drawString(x + 30, y, problem.display)

    # Page number
    c.setFont("Helvetica", 9)
    c.drawCentredString(page_w / 2, mb / 2, str(page_num))


def _draw_answer_page(c, problems, page_num, config, page_w, page_h, is_left):
    """Draw an answer key page."""
    ml = config.margin_gutter * inch if is_left else config.margin_outside * inch
    mr = config.margin_outside * inch if is_left else config.margin_gutter * inch
    mt = config.margin_top * inch

    usable_w = page_w - ml - mr

    c.setFont("Helvetica-Bold", 10)
    c.drawString(ml, page_h - mt + 5, f"Answers — Page {page_num}")

    # Compact layout: 4 columns
    c.setFont("Helvetica", 9)
    cols = 4
    col_width = usable_w / cols
    rows_per_col = math.ceil(len(problems) / cols)

    for idx, problem in enumerate(problems):
        col = idx // rows_per_col
        row = idx % rows_per_col

        x = ml + col * col_width + 5
        y = page_h - mt - 20 - row * 14

        answer_text = problem.display.replace("___", problem.answer_display)
        c.drawString(x, y, f"{idx + 1}. {answer_text}")


if __name__ == "__main__":
    output = Path("/Users/tiger/Desktop/CATALOG ENGINE/bookr/output/test_math.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)

    config = MathBookConfig(
        title="Math Practice for Kids",
        subtitle="Addition & Subtraction — Grade 2",
        author="Creative Puzzles Press",
        num_pages=10,
        problems_per_page=20,
        operation="mixed",
        difficulty="easy",
        large_print=True,
    )

    result = generate_math_book(config, output)
    print(f"Generated: {result['path']}")
    print(f"Pages: {result['page_count']}")
    print(f"Problems: {result['total_problems']}")
