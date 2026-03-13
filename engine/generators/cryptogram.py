"""
SCRPT Cryptogram Generator
=============================
Creates complete cryptogram puzzle books ready for Amazon KDP.

A cryptogram replaces each letter in a famous quote with a different
letter via a random substitution cipher. The solver must deduce the
mapping to decode the original quote.

Each puzzle:
  - Encodes a quote using a random substitution cipher (no letter maps to itself)
  - Shows the encoded text with numbered blanks for the solver
  - Provides a hint (the author of the quote)
  - Includes answer key pages at the back

Output: KDP-compliant PDF at standard trim size with proper margins.
"""

import random
import string
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas


# -- Cipher Logic ------------------------------------------------------------

def _generate_cipher() -> dict[str, str]:
    """
    Generate a random substitution cipher where no letter maps to itself.

    Uses a derangement algorithm (Sattolo's variant with rejection)
    to guarantee every letter maps to a *different* letter.

    Returns:
        Dictionary mapping each uppercase letter to its cipher letter.
    """
    letters = list(string.ascii_uppercase)
    while True:
        shuffled = list(letters)
        random.shuffle(shuffled)
        # A derangement has no fixed points
        if all(a != b for a, b in zip(letters, shuffled)):
            break
    return dict(zip(letters, shuffled))


def encode_text(plaintext: str, cipher: dict[str, str]) -> str:
    """
    Encode plaintext using the substitution cipher.

    Only alphabetic characters are substituted; punctuation, spaces,
    and digits pass through unchanged.
    """
    result = []
    for ch in plaintext.upper():
        if ch in cipher:
            result.append(cipher[ch])
        else:
            result.append(ch)
    return "".join(result)


def decode_text(ciphertext: str, cipher: dict[str, str]) -> str:
    """Decode ciphertext back to plaintext using the cipher mapping."""
    reverse = {v: k for k, v in cipher.items()}
    result = []
    for ch in ciphertext.upper():
        if ch in reverse:
            result.append(reverse[ch])
        else:
            result.append(ch)
    return "".join(result)


# -- Quote Bank --------------------------------------------------------------

QUOTES = [
    # Motivation & perseverance
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("In the middle of difficulty lies opportunity.", "Albert Einstein"),
    ("It does not matter how slowly you go as long as you do not stop.", "Confucius"),
    ("Believe you can and you are halfway there.", "Theodore Roosevelt"),
    ("The future belongs to those who believe in the beauty of their dreams.", "Eleanor Roosevelt"),
    ("Success is not final failure is not fatal it is the courage to continue that counts.", "Winston Churchill"),
    ("What you get by achieving your goals is not as important as what you become.", "Zig Ziglar"),
    ("The best time to plant a tree was twenty years ago the second best time is now.", "Chinese Proverb"),
    ("Your time is limited so do not waste it living someone elses life.", "Steve Jobs"),
    ("Strive not to be a success but rather to be of value.", "Albert Einstein"),

    # Wisdom & philosophy
    ("The unexamined life is not worth living.", "Socrates"),
    ("Happiness is not something ready made it comes from your own actions.", "Dalai Lama"),
    ("Be the change that you wish to see in the world.", "Mahatma Gandhi"),
    ("To be yourself in a world that is constantly trying to make you something else is the greatest accomplishment.", "Ralph Waldo Emerson"),
    ("The only true wisdom is in knowing you know nothing.", "Socrates"),
    ("Life is what happens when you are busy making other plans.", "John Lennon"),
    ("Turn your wounds into wisdom.", "Oprah Winfrey"),
    ("An unexamined life is not worth living.", "Socrates"),
    ("The mind is everything what you think you become.", "Buddha"),
    ("We are what we repeatedly do excellence then is not an act but a habit.", "Aristotle"),

    # Courage & strength
    ("Courage is not the absence of fear but the triumph over it.", "Nelson Mandela"),
    ("You must be the change you wish to see in the world.", "Mahatma Gandhi"),
    ("It is during our darkest moments that we must focus to see the light.", "Aristotle"),
    ("Do not go where the path may lead go instead where there is no path and leave a trail.", "Ralph Waldo Emerson"),
    ("The greatest glory in living lies not in never falling but in rising every time we fall.", "Nelson Mandela"),
    ("Nothing is impossible the word itself says I am possible.", "Audrey Hepburn"),
    ("In three words I can sum up everything I learned about life it goes on.", "Robert Frost"),
    ("The purpose of our lives is to be happy.", "Dalai Lama"),
    ("Life is either a daring adventure or nothing at all.", "Helen Keller"),
    ("Many of lifes failures are people who did not realize how close they were to success when they gave up.", "Thomas Edison"),

    # Knowledge & learning
    ("Education is the most powerful weapon which you can use to change the world.", "Nelson Mandela"),
    ("The more that you read the more things you will know the more that you learn the more places you will go.", "Dr. Seuss"),
    ("Live as if you were to die tomorrow learn as if you were to live forever.", "Mahatma Gandhi"),
    ("Anyone who stops learning is old whether at twenty or eighty.", "Henry Ford"),
    ("Tell me and I forget teach me and I remember involve me and I learn.", "Benjamin Franklin"),
    ("The only person you are destined to become is the person you decide to be.", "Ralph Waldo Emerson"),
    ("A room without books is like a body without a soul.", "Marcus Tullius Cicero"),
    ("It is not what you look at that matters it is what you see.", "Henry David Thoreau"),
    ("Imagination is more important than knowledge.", "Albert Einstein"),
    ("The beautiful thing about learning is that nobody can take it away from you.", "B.B. King"),

    # Action & determination
    ("Do what you can with what you have where you are.", "Theodore Roosevelt"),
    ("Act as if what you do makes a difference because it does.", "William James"),
    ("Well done is better than well said.", "Benjamin Franklin"),
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("Quality is not an act it is a habit.", "Aristotle"),
    ("It always seems impossible until it is done.", "Nelson Mandela"),
    ("What we achieve inwardly will change outer reality.", "Plutarch"),
    ("I have not failed I have just found ten thousand ways that will not work.", "Thomas Edison"),
    ("The best revenge is massive success.", "Frank Sinatra"),
    ("If you want to lift yourself up lift up someone else.", "Booker T. Washington"),

    # Creativity & imagination
    ("Creativity is intelligence having fun.", "Albert Einstein"),
    ("Logic will get you from A to B imagination will take you everywhere.", "Albert Einstein"),
    ("Every artist was first an amateur.", "Ralph Waldo Emerson"),
    ("You can never cross the ocean until you have the courage to lose sight of the shore.", "Christopher Columbus"),
    ("The pen is mightier than the sword.", "Edward Bulwer-Lytton"),
    ("Everything you can imagine is real.", "Pablo Picasso"),
    ("Art is not what you see but what you make others see.", "Edgar Degas"),
    ("The chief enemy of creativity is good sense.", "Pablo Picasso"),
    ("To live a creative life we must lose our fear of being wrong.", "Joseph Chilton Pearce"),
    ("Have no fear of perfection you will never reach it.", "Salvador Dali"),
]


@dataclass
class CryptogramPuzzle:
    """A single cryptogram puzzle with its cipher and solution."""
    quote: str
    author: str
    cipher: dict
    encoded_text: str
    puzzle_number: int = 0


def generate_puzzle(quote: str, author: str, puzzle_number: int = 0) -> CryptogramPuzzle:
    """
    Generate a single cryptogram puzzle from a quote.

    Args:
        quote: The plaintext quote to encode.
        author: Attribution for the hint line.
        puzzle_number: Sequence number within the book.

    Returns:
        CryptogramPuzzle with cipher mapping and encoded text.
    """
    cipher = _generate_cipher()
    encoded = encode_text(quote, cipher)

    return CryptogramPuzzle(
        quote=quote.upper(),
        author=author,
        cipher=cipher,
        encoded_text=encoded,
        puzzle_number=puzzle_number,
    )


# -- PDF Generation -----------------------------------------------------------

@dataclass
class CryptogramBookConfig:
    """Configuration for a cryptogram puzzle book."""
    title: str = "Cryptogram Puzzles"
    subtitle: str = "Decode Famous Quotes"
    author: str = "Creative Puzzles Press"
    num_puzzles: int = 55
    large_print: bool = True
    trim_width: float = 8.5        # inches
    trim_height: float = 11.0      # inches
    margin_top: float = 0.75
    margin_bottom: float = 0.75
    margin_outside: float = 0.75
    margin_gutter: float = 0.5     # inside margin (near spine)


def generate_cryptogram_book(
    config: CryptogramBookConfig,
    output_path: Path,
) -> dict:
    """
    Generate a complete cryptogram book PDF.

    Args:
        config: Book configuration settings.
        output_path: Where to write the PDF file.

    Returns:
        Dict with path, page_count, and num_puzzles.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_w = config.trim_width * inch
    page_h = config.trim_height * inch

    c = canvas.Canvas(str(output_path), pagesize=(page_w, page_h))

    page_count = 0
    puzzles: list[CryptogramPuzzle] = []

    # Select quotes for the book (cycle if we need more than the bank holds)
    selected_quotes = []
    shuffled_quotes = list(QUOTES)
    random.shuffle(shuffled_quotes)
    while len(selected_quotes) < config.num_puzzles:
        remaining = config.num_puzzles - len(selected_quotes)
        selected_quotes.extend(shuffled_quotes[:remaining])
        random.shuffle(shuffled_quotes)

    # -- Title Page -----------------------------------------------------------
    _draw_title_page(c, config, page_w, page_h)
    page_count += 1

    # -- Copyright Page -------------------------------------------------------
    c.showPage()
    _draw_copyright_page(c, config, page_w, page_h)
    page_count += 1

    # -- How to Solve Page ----------------------------------------------------
    c.showPage()
    _draw_instructions_page(c, config, page_w, page_h)
    page_count += 1

    # -- Puzzle Pages ---------------------------------------------------------
    for i in range(config.num_puzzles):
        quote_text, quote_author = selected_quotes[i]
        puzzle = generate_puzzle(quote_text, quote_author, puzzle_number=i + 1)
        puzzles.append(puzzle)

        c.showPage()
        is_left = (page_count % 2 == 0)
        _draw_puzzle_page(c, puzzle, config, page_w, page_h, is_left, page_count)
        page_count += 1

    # -- Answer Key Section ---------------------------------------------------
    c.showPage()
    _draw_section_header(c, "Answer Key", page_w, page_h)
    page_count += 1

    # Answer pages (2 answers per page for readability)
    answers_per_page = 2
    for batch_start in range(0, len(puzzles), answers_per_page):
        batch = puzzles[batch_start:batch_start + answers_per_page]
        c.showPage()
        is_left = (page_count % 2 == 0)
        _draw_answer_page(c, batch, config, page_w, page_h, is_left, page_count)
        page_count += 1

    # -- Pad to even page count (KDP requirement) -----------------------------
    if page_count % 2 != 0:
        c.showPage()
        page_count += 1

    c.save()

    return {
        "path": str(output_path),
        "page_count": page_count,
        "num_puzzles": len(puzzles),
    }


# -- Page Drawing Helpers -----------------------------------------------------

def _get_margins(config: CryptogramBookConfig, is_left: bool) -> tuple[float, float, float, float]:
    """Return (ml, mr, mt, mb) in points for the given page side."""
    ml = config.margin_gutter * inch if is_left else config.margin_outside * inch
    mr = config.margin_outside * inch if is_left else config.margin_gutter * inch
    mt = config.margin_top * inch
    mb = config.margin_bottom * inch
    return ml, mr, mt, mb


def _draw_title_page(c, config, page_w, page_h):
    """Draw the book title page."""
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(page_w / 2, page_h - 3 * inch, config.title)

    c.setFont("Helvetica", 18)
    c.drawCentredString(page_w / 2, page_h - 3.8 * inch, config.subtitle)

    c.setFont("Helvetica", 14)
    c.drawCentredString(
        page_w / 2,
        page_h - 4.8 * inch,
        f"{config.num_puzzles} Puzzles",
    )

    if config.large_print:
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(page_w / 2, page_h - 5.5 * inch, "LARGE PRINT")

    c.setFont("Helvetica", 14)
    c.drawCentredString(page_w / 2, page_h - 8 * inch, config.author)


def _draw_copyright_page(c, config, page_w, page_h):
    """Draw the copyright / legal page."""
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


def _draw_instructions_page(c, config, page_w, page_h):
    """Draw a 'How to Solve' instructions page."""
    ml = config.margin_outside * inch
    mr = config.margin_outside * inch

    y = page_h - 1.5 * inch

    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(page_w / 2, y, "How to Solve Cryptograms")
    y -= 50

    c.setFont("Helvetica", 13 if config.large_print else 11)
    line_height = 22 if config.large_print else 18
    instructions = [
        "A cryptogram is a type of puzzle where each letter in a",
        "quote has been replaced by a different letter. Your goal",
        "is to figure out the original quote by finding the correct",
        "letter substitutions.",
        "",
        "Tips:",
        "",
        "  1.  Start with short words. One-letter words are usually",
        "      A or I. Two-letter words are often OF, TO, IN, IS,",
        "      IT, IF, or ON.",
        "",
        "  2.  Look for common patterns. THE, AND, THAT, and TION",
        "      appear frequently in English.",
        "",
        "  3.  Apostrophes help. Letters after an apostrophe are",
        "      usually S, T, D, M, LL, or RE.",
        "",
        "  4.  Double letters are useful clues. Common doubles",
        "      include LL, SS, EE, OO, TT, and FF.",
        "",
        "  5.  Use the hint! The author's name is provided to give",
        "      you context about the type of quote.",
        "",
        "  6.  Each puzzle uses a different cipher. The letter",
        "      substitutions change from puzzle to puzzle.",
        "",
        "  Each letter in the cipher text maps to exactly one letter",
        "  in the original text, and no letter maps to itself.",
    ]
    for line in instructions:
        c.drawString(ml, y, line)
        y -= line_height


def _draw_section_header(c, title, page_w, page_h):
    """Draw a section divider page."""
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(page_w / 2, page_h / 2 + 20, title)


def _wrap_text(text: str, max_chars_per_line: int) -> list[str]:
    """
    Word-wrap text to fit within a given character width.

    Splits on spaces and never breaks a word in the middle.
    """
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        if current_line and len(current_line) + 1 + len(word) > max_chars_per_line:
            lines.append(current_line)
            current_line = word
        else:
            current_line = f"{current_line} {word}" if current_line else word

    if current_line:
        lines.append(current_line)

    return lines


def _draw_puzzle_page(c, puzzle: CryptogramPuzzle, config, page_w, page_h, is_left, page_num):
    """Draw a single cryptogram puzzle page."""
    ml, mr, mt, mb = _get_margins(config, is_left)
    usable_w = page_w - ml - mr

    # Font sizes
    if config.large_print:
        cipher_font_size = 20
        blank_font_size = 16
        hint_font_size = 14
        header_font_size = 14
        char_width = 16
    else:
        cipher_font_size = 16
        blank_font_size = 13
        hint_font_size = 12
        header_font_size = 12
        char_width = 13

    # -- Header ---------------------------------------------------------------
    y = page_h - mt
    c.setFont("Helvetica-Bold", header_font_size)
    c.drawString(ml, y + 5, f"Puzzle #{puzzle.puzzle_number}")

    # -- Hint (author) --------------------------------------------------------
    c.setFont("Helvetica-Oblique", hint_font_size)
    c.drawRightString(page_w - mr, y + 5, f"Hint: {puzzle.author}")

    y -= 40

    # -- Encoded text with blanks underneath ----------------------------------
    # Calculate how many characters fit per line
    max_chars = int(usable_w / char_width)
    encoded_lines = _wrap_text(puzzle.encoded_text, max_chars)
    plain_lines = _wrap_text(puzzle.quote, max_chars)

    # We need matching line breaks, so re-wrap based on encoded text word splits
    # Process the encoded text word by word to maintain alignment
    encoded_words = puzzle.encoded_text.split()
    plain_words = puzzle.quote.split()

    # Rebuild lines keeping cipher and plain words paired
    encoded_display_lines: list[list[str]] = []
    current_enc_line: list[str] = []
    current_len = 0

    for word in encoded_words:
        needed = len(word) + (1 if current_enc_line else 0)
        if current_enc_line and current_len + needed > max_chars:
            encoded_display_lines.append(current_enc_line)
            current_enc_line = [word]
            current_len = len(word)
        else:
            current_enc_line.append(word)
            current_len += needed
    if current_enc_line:
        encoded_display_lines.append(current_enc_line)

    # Determine line spacing based on mode
    if config.large_print:
        cipher_to_blank_gap = 6      # gap between cipher letter row and blank row
        line_group_spacing = 52       # total vertical space per cipher+blank group
    else:
        cipher_to_blank_gap = 4
        line_group_spacing = 42

    # Draw each line of the encoded text
    word_index = 0
    for line_words in encoded_display_lines:
        x = ml

        # -- Cipher letters (top row) --
        c.setFont("Helvetica-Bold", cipher_font_size)
        for w_idx, enc_word in enumerate(line_words):
            if w_idx > 0:
                x += char_width  # space between words

            for ch in enc_word:
                c.drawCentredString(x + char_width / 2, y, ch)
                x += char_width

        # -- Blank underlines (bottom row, below the cipher letters) --
        x = ml
        blank_y = y - cipher_font_size - cipher_to_blank_gap

        c.setFont("Helvetica", blank_font_size)
        for w_idx, enc_word in enumerate(line_words):
            if w_idx > 0:
                x += char_width  # space between words

            for ch in enc_word:
                if ch.isalpha():
                    # Draw underline blank
                    line_x_start = x + 1
                    line_x_end = x + char_width - 1
                    c.setLineWidth(0.8)
                    c.line(line_x_start, blank_y - 2, line_x_end, blank_y - 2)
                x += char_width

        y -= line_group_spacing

    # -- Cipher alphabet reference at the bottom ------------------------------
    # Show a letter frequency guide: which cipher letters appear in this puzzle
    y -= 20
    c.setLineWidth(0.5)
    c.setStrokeColor(colors.Color(0.6, 0.6, 0.6))
    c.line(ml, y, page_w - mr, y)
    c.setStrokeColor(colors.Color(0, 0, 0))

    y -= 25
    c.setFont("Helvetica-Bold", 11 if config.large_print else 9)
    c.drawString(ml, y, "Cipher Alphabet:")
    y -= 22

    # Collect unique cipher letters used in this puzzle
    used_cipher_letters = sorted(set(
        ch for ch in puzzle.encoded_text if ch.isalpha()
    ))

    # Draw the cipher letters used with blanks beneath them
    ref_char_width = 22 if config.large_print else 18
    max_per_row = int(usable_w / ref_char_width)
    rows = [used_cipher_letters[i:i + max_per_row]
            for i in range(0, len(used_cipher_letters), max_per_row)]

    for row_letters in rows:
        x = ml
        c.setFont("Helvetica-Bold", 14 if config.large_print else 11)
        for letter in row_letters:
            c.drawCentredString(x + ref_char_width / 2, y, letter)
            # Blank line below
            c.setLineWidth(0.6)
            c.line(x + 2, y - 16, x + ref_char_width - 2, y - 16)
            x += ref_char_width
        y -= 36

    # -- Page number ----------------------------------------------------------
    c.setFont("Helvetica", 9)
    c.drawCentredString(page_w / 2, mb / 2, str(page_num))


def _draw_answer_page(c, puzzles_batch: list, config, page_w, page_h, is_left, page_num):
    """Draw an answer key page showing decoded quotes and cipher maps."""
    ml, mr, mt, mb = _get_margins(config, is_left)
    usable_w = page_w - ml - mr

    y = page_h - mt

    for puzzle in puzzles_batch:
        # Puzzle number header
        c.setFont("Helvetica-Bold", 13)
        c.drawString(ml, y, f"Puzzle #{puzzle.puzzle_number}")
        y -= 20

        # Original quote
        c.setFont("Helvetica", 11)
        max_chars = int(usable_w / 6.5)  # approximate character width at 11pt
        quote_lines = _wrap_text(puzzle.quote, max_chars)
        for line in quote_lines:
            c.drawString(ml + 10, y, line)
            y -= 15
        y -= 5

        # Author
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(ml + 10, y, f"-- {puzzle.author}")
        y -= 22

        # Cipher key table (compact, two-row format)
        c.setFont("Helvetica", 8)
        c.drawString(ml + 10, y, "Cipher key:")
        y -= 14

        # Sort by plain letter for easy reference
        sorted_pairs = sorted(puzzle.cipher.items(), key=lambda p: p[0])

        # Only show letters that actually appear in the quote
        used_plain = set(ch for ch in puzzle.quote if ch.isalpha())
        relevant_pairs = [(plain, cipher) for plain, cipher in sorted_pairs if plain in used_plain]

        cell_w = 17
        max_cols = min(len(relevant_pairs), int(usable_w / cell_w) - 1)

        # Split into rows if needed
        pair_rows = [relevant_pairs[i:i + max_cols]
                     for i in range(0, len(relevant_pairs), max_cols)]

        for pair_row in pair_rows:
            x = ml + 10

            # Cipher letter row (top)
            c.setFont("Helvetica-Bold", 8)
            for plain, cipher_letter in pair_row:
                c.drawCentredString(x + cell_w / 2, y, cipher_letter)
                x += cell_w
            y -= 11

            # Plain letter row (bottom, with arrow indicator)
            x = ml + 10
            c.setFont("Helvetica", 8)
            for plain, cipher_letter in pair_row:
                c.drawCentredString(x + cell_w / 2, y, plain)
                x += cell_w
            y -= 18

        # Divider line
        c.setLineWidth(0.3)
        c.setStrokeColor(colors.Color(0.7, 0.7, 0.7))
        c.line(ml, y, page_w - mr, y)
        c.setStrokeColor(colors.Color(0, 0, 0))
        y -= 25

    # Page number
    c.setFont("Helvetica", 9)
    c.drawCentredString(page_w / 2, mb / 2, str(page_num))


# -- Main (for testing) -------------------------------------------------------

if __name__ == "__main__":
    output = Path("/Users/tiger/Desktop/CATALOG ENGINE/bookr/output/test_cryptogram.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)

    config = CryptogramBookConfig(
        title="Large Print Cryptogram Puzzles",
        subtitle="Decode Famous Quotes",
        author="Creative Puzzles Press",
        num_puzzles=10,  # Quick test
        large_print=True,
    )

    print("Generating cryptogram book...")
    result = generate_cryptogram_book(config, output)
    print(f"Generated: {result['path']}")
    print(f"Pages: {result['page_count']}")
    print(f"Puzzles: {result['num_puzzles']}")
