"""
House typesetting rules shared by every print builder.

THE TITLE-LINE RULE (Lars, 2026-09-09): a title that must be divided over
several lines never puts one word alone on a line — every line carries at
least three words, and the lines are balanced in length. If the words do
not allow that, the type shrinks until the title fits on one line.
"""
from __future__ import annotations

from typing import Callable, Optional

MIN_WORDS = 3


def title_lines(title: str, width: Callable[[str], float], max_w: float,
                min_words: int = MIN_WORDS, max_lines: int = 3) -> Optional[list[str]]:
    """Split `title` into balanced lines that each fit `max_w` (measured by
    `width`) and each carry ≥ min_words words. None when no such split exists."""
    title = " ".join(title.split())
    if width(title) <= max_w:
        return [title]
    ws = title.split()
    best, best_score = None, None
    for k in range(2, max_lines + 1):
        if len(ws) < k * min_words:
            break
        # every composition of len(ws) into k parts, each ≥ min_words
        def parts(start, left):
            if left == 1:
                if len(ws) - start >= min_words:
                    yield [ws[start:]]
                return
            for n in range(min_words, len(ws) - start - min_words * (left - 1) + 1):
                for rest in parts(start + n, left - 1):
                    yield [ws[start:start + n]] + rest
        for split in parts(0, k):
            lines = [" ".join(p) for p in split]
            widths = [width(l) for l in lines]
            if max(widths) > max_w:
                continue
            score = (k, max(widths) - min(widths))      # fewer lines first, then balance
            if best_score is None or score < best_score:
                best, best_score = lines, score
        if best is not None:
            return best
    return None


def fit_title(title: str, width_at: Callable[[str, float], float], max_w: float,
              size: float, floor: float, step: float = 1.0) -> tuple[list[str], float]:
    """Shrink from `size` to `floor` until the title-line rule can be met;
    below the floor the title goes on one line at the floor size regardless."""
    s = size
    while s >= floor:
        lines = title_lines(title, lambda t: width_at(t, s), max_w)
        if lines:
            return lines, s
        s -= step
    return [" ".join(title.split())], floor


# THE HOUSE MARK (Lars, 2026-09-09: "The TigerWorks logo is a little too large.
# Make it 20% smaller. And make that a rule."): the lockup's side, in inches.
HOUSE_MARK_IN = {"title_page": 0.8, "back_cover": 0.51, "workbook_title": 0.8, "picture_title": 0.47}
