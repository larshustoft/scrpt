"""
Cover typography matching.

The front cover comes from the image model with its own display type. If the
spine and back are then set in an unrelated face, the wrap looks assembled
rather than designed. So SCRPT LOOKS at the finished front, identifies the
typographic family, and sets the rest of the wrap in the closest match from
the print-quality faces available.
"""

from pathlib import Path
from typing import Optional

from ..database import get_book_by_catalog, update_book

SUPP = "/System/Library/Fonts/Supplemental"

# Families offered to the matcher, each with (file, subfont index) per weight.
# Chosen because they are genuine book faces, not UI fonts.
FONT_FAMILIES: dict[str, dict] = {
    "Didot": {                      # high-contrast neoclassical — fashion/romance
        "regular": ("Didot.ttc", 0), "italic": ("Didot.ttc", 1),
        "bold": ("Didot.ttc", 2),
        "note": "high-contrast, elegant, thin hairlines",
    },
    "Bodoni 72": {                  # high-contrast display, slightly heavier
        "regular": ("Bodoni 72.ttc", 0), "italic": ("Bodoni 72.ttc", 1),
        "bold": ("Bodoni 72.ttc", 2),
        "note": "high-contrast display serif, geometric",
    },
    "Big Caslon": {                 # classic literary display
        "regular": ("BigCaslon.ttf", None), "italic": ("BigCaslon.ttf", None),
        "bold": ("BigCaslon.ttf", None),
        "note": "classic old-style display serif, literary",
    },
    "Cochin": {                     # refined French old-style, period feel
        "regular": ("Cochin.ttc", 0), "italic": ("Cochin.ttc", 2),
        "bold": ("Cochin.ttc", 1),
        "note": "refined old-style, period/regency feel",
    },
    "Hoefler Text": {               # warm bookish serif
        "regular": ("Hoefler Text.ttc", 0), "italic": ("Hoefler Text.ttc", 2),
        "bold": ("Hoefler Text.ttc", 1),
        "note": "warm classical book serif",
    },
    "Iowan Old Style": {            # sturdy readable serif
        "regular": ("Iowan Old Style.ttc", 0), "italic": ("Iowan Old Style.ttc", 2),
        "bold": ("Iowan Old Style.ttc", 1),
        "note": "sturdy old-style serif, readable",
    },
    "Baskerville": {                # transitional serif, neutral
        "regular": ("Baskerville.ttc", 0), "italic": ("Baskerville.ttc", 2),
        "bold": ("Baskerville.ttc", 1),
        "note": "transitional serif, neutral and clean",
    },
    "Superclarendon": {             # slab serif — punchy, non-fiction/thriller
        "regular": ("SuperClarendon.ttc", 0), "italic": ("SuperClarendon.ttc", 1),
        "bold": ("SuperClarendon.ttc", 5),
        "note": "slab serif, punchy and modern",
    },
    "Futura": {                     # geometric sans — modern/thriller
        "regular": ("Futura.ttc", 0), "italic": ("Futura.ttc", 1),
        "bold": ("Futura.ttc", 2),
        "note": "geometric sans, modern and clean",
    },
    "Impact": {                     # heavy condensed — action thriller display
        "regular": ("Impact.ttf", None), "italic": ("Impact.ttf", None),
        "bold": ("Impact.ttf", None),
        "note": "heavy condensed sans, blockbuster thriller display",
    },
    "Futura Condensed": {           # condensed sans, medium weight
        "regular": ("Futura.ttc", 3), "italic": ("Futura.ttc", 3),
        "bold": ("Futura.ttc", 4),
        "note": "condensed geometric sans, medium weight — not heavy",
    },
    "Avenir": {                     # clean humanist sans, light//book weight
        "regular": ("Avenir.ttc", 0), "italic": ("Avenir.ttc", 1),
        "bold": ("Avenir.ttc", 4),
        "note": "clean humanist sans, book weight, quiet and modern",
    },
    "Helvetica Neue": {             # neutral grotesque
        "regular": ("HelveticaNeue.ttc", 0), "italic": ("HelveticaNeue.ttc", 2),
        "bold": ("HelveticaNeue.ttc", 1),
        "note": "neutral grotesque sans, plain and unfussy",
    },
    "Optima": {                     # humanist, flared — elegant sans
        "regular": ("Optima.ttc", 0), "italic": ("Optima.ttc", 2),
        "bold": ("Optima.ttc", 1),
        "note": "elegant flared humanist sans, refined",
    },
}

DEFAULT_FAMILY = "Baskerville"

# The interior's own faces (same files the print engine uses), so the back
# cover body text is set in exactly the type the reader meets inside.
INTERIOR_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "fonts"
INTERIOR_FACES = {
    "garamond":     ("EBGaramond-Regular.ttf", "EBGaramond-Bold.ttf", "EBGaramond-Italic.ttf"),
    "ebgaramond_lg": ("EBGaramond-Regular.ttf", "EBGaramond-Bold.ttf", "EBGaramond-Italic.ttf"),
    "crimson":      ("CrimsonPro-Regular.ttf", "CrimsonPro-Bold.ttf", "CrimsonPro-Italic.ttf"),
    "literata":     ("Literata-Regular.ttf", "Literata-Bold.ttf", "Literata-Italic.ttf"),
    "sourceserif":  ("SourceSerif4-Regular.ttf", "SourceSerif4-Bold.ttf", "SourceSerif4-Italic.ttf"),
}


def register_interior(font_preset: str) -> tuple[str, str, str]:
    """Register the book's interior face for the back-cover body copy."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    files = INTERIOR_FACES.get(font_preset or "", INTERIOR_FACES["garamond"])
    out = []
    for kind, fname in zip(("reg", "bold", "ital"), files):
        tag = f"IN-{font_preset or 'garamond'}-{kind}"
        path = INTERIOR_DIR / fname
        try:
            if not path.exists():
                raise FileNotFoundError(str(path))
            pdfmetrics.registerFont(TTFont(tag, str(path)))
            out.append(tag)
        except Exception:
            out.append(None)
    # fall back to the matched display family if an interior file is missing
    return tuple(out)  # type: ignore[return-value]


def register_family(name: str) -> tuple[str, str, str]:
    """Register a family with reportlab. Returns (regular, bold, italic) names."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    fam = FONT_FAMILIES.get(name) or FONT_FAMILIES[DEFAULT_FAMILY]
    out = []
    for weight in ("regular", "bold", "italic"):
        file, idx = fam[weight]
        tag = f"CW-{name}-{weight}".replace(" ", "")
        try:
            if idx is None:
                pdfmetrics.registerFont(TTFont(tag, f"{SUPP}/{file}"))
            else:
                pdfmetrics.registerFont(TTFont(tag, f"{SUPP}/{file}", subfontIndex=idx))
            out.append(tag)
        except Exception:
            out.append("Helvetica")
    return out[0], out[1], out[2]


async def match_fonts(catalog: str, force: bool = False) -> dict:
    """Look at the finished front cover and choose the closest type family.

    Cached on the book: the front rarely changes, and the wrap must be
    reproducible.
    """
    from ..config import OUTPUT_DIR
    from ..writing.client import complete_vision, extract_json

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    cover = book["data"].get("cover") or {}
    if cover.get("fonts") and not force:
        return cover["fonts"]

    art = Path(OUTPUT_DIR) / catalog / "cover-art.png"
    if not art.exists():
        return {"family": DEFAULT_FAMILY, "reason": "no front cover art"}

    options = "\n".join(f"- {k}: {v['note']}" for k, v in FONT_FAMILIES.items())
    raw = await complete_vision(
        "You are a book typographer matching type across a cover wrap.",
        "This is the FRONT cover of a book. The spine and back cover must be "
        "set in type that looks like it belongs to the same design.\n\n"
        "Look at the TITLE and AUTHOR lettering. Choose the ONE family below "
        "whose letterforms come closest — weight, contrast between thick and "
        "thin strokes, serif shape, and overall period feel.\n\n"
        "SEPARATELY, look at the TAGLINE line (the small selling line, often "
        "above the title). Covers usually set it in a LIGHTER, plainer face "
        "than the title. Choose the family that matches THAT lettering — if it "
        "is clearly the same face as the title, say so by naming the same "
        "family.\n\n"
        f"{options}\n\n"
        "ALSO report the colour of the AUTHOR NAME as printed on the front "
        "cover, as a hex code, plus whether it is essentially white.\n\n"
        'Return JSON only: {"family": "exact name from the list", '
        '"tagline_family": "exact name from the list — the TAGLINE\'s face", '
        '"observed": "8-15 words describing the front\'s lettering", '
        '"author_color": "#rrggbb", "author_is_white": true|false, '
        '"confidence": "high|medium|low"}',
        art.read_bytes(), max_tokens=1500)
    try:
        out = extract_json(raw)
    except ValueError:
        out = {}
    family = str(out.get("family", "")).strip()
    if family not in FONT_FAMILIES:
        family = DEFAULT_FAMILY
    tag_family = str(out.get("tagline_family", "")).strip()
    if tag_family not in FONT_FAMILIES:
        tag_family = family
    # the author name's colour drives the back cover's frame and tagline;
    # a white author name would vanish on white, so those go black instead
    hexv = str(out.get("author_color", "") or "").strip().lstrip("#")
    rgb = None
    if len(hexv) == 6:
        try:
            rgb = tuple(int(hexv[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            rgb = None
    # judge by luminance, not by min channel: a cream (#F3EAD1) author name
    # is not "white" by RGB but is just as invisible on a white back cover
    lum = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) if rgb else 0
    is_white = bool(out.get("author_is_white")) or lum > 200
    if is_white or rgb is None:
        rgb = (0, 0, 0)
    result = {"family": family, "tagline_family": tag_family,
              "observed": out.get("observed", ""),
              "confidence": out.get("confidence", ""),
              "author_color": list(rgb), "author_was_white": is_white}

    fresh = get_book_by_catalog(catalog)
    data = dict(fresh["data"])
    cov = dict(data.get("cover") or {})
    cov["fonts"] = result
    data["cover"] = cov
    update_book(fresh["id"], data)
    return result
