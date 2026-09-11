"""
THE COVER FIT CONTROL (Lars, 2026-09-10).

A Princess workbook cover (Maze Meadow, SC-089) shipped with its title
running off the top of the page and "Unicorn" misspelled in the title
graphic. Nothing in the line looked at the finished picture before it
became the cover. This module is the control, and every cover path goes
through it:

  1. PREVENT — `safe_zone_line()` tells the image engine, in the brief, that
     the picture is trimmed and that every word must sit well inside with a
     clear margin from every edge.
  2. SEE — `trim_view()` produces exactly what the install step keeps (and
     `ebook_view()` the narrower Amazon crop), so checks and previews look
     at the real thing, never the raw canvas.
  3. MEASURE — macOS text recognition (the Vision framework, on-device, no
     cost) returns the bounding box of every piece of text. The nearest
     text to each edge must clear a floor of SAFE_INCHES: the print wrap
     cuts 0.125" of bleed off the picture and KDP wants text a further
     margin inside the trim. Maze Meadow's title measured -0.5% from the
     top (it crossed the edge); Freddie the Farmer's measured 6.6%.
  4. READ — a vision model reads the title back. Every letter visible, no
     word clipped, and the title spelled as the book is titled.
  5. STOP — a cover that fails is not installed. The generators redraw a
     bounded number of times with the reason, then halt.

A check nobody calls is not a check — see [[checks-must-be-wired]]. Callers:
front_cover.generate_front_cover, generate_cover_variants, the cover upload
route, and the launch gate's "Cover fits the format" item.
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import re
from typing import Optional

# The floor every piece of text must clear on every edge, in inches of the
# finished trim: 0.125" bleed cut + 0.175" real margin. On an 8.5x11 page
# that is 2.7% of the height and 3.5% of the width.
SAFE_INCHES = 0.45   # KDP refuses text within 0.375in of a trim edge (Star Map, 2026-09-11) — 0.45 leaves room
# the brief asks for more than the floor so a slightly generous draw still
# clears it comfortably
BRIEF_TOP_BOTTOM = 0.10
BRIEF_SIDES = 0.08
MAX_ATTEMPTS = 3   # first draw + two redraws, then the line stops


def _dims(trim: str, default=(5.5, 8.5)) -> tuple:
    try:
        tw, th = (float(x) for x in str(trim).lower().split("x"))
        return tw, th
    except Exception:
        return default


def safe_pct(trim: str) -> tuple:
    """(top/bottom floor as share of height, side floor as share of width)."""
    tw, th = _dims(trim)
    return SAFE_INCHES / th, SAFE_INCHES / tw


def safe_zone_line(trim: str) -> str:
    """The prevention half: one plain sentence in the brief."""
    pretty = str(trim).replace("x", "″ × ") + "″"
    return (f"IMPORTANT LAYOUT RULE: the picture will be trimmed to the book's "
            f"{pretty} proportions. Keep the title, every word of text and "
            f"every important element completely inside the picture with a "
            f"generous clear margin from all four edges — at least "
            f"{int(BRIEF_TOP_BOTTOM * 100)}% of the height away from the top and "
            f"bottom edges and {int(BRIEF_SIDES * 100)}% of the width away from "
            f"the sides. No letter may touch, overlap or run off any edge. The "
            f"whole title must be readable in full and spelled exactly as given. "
            f"The author name must appear on the cover, in full, well inside the "
            f"bottom margin.")


def crop_to_ratio(im, target_w_over_h: float):
    """Centre-crop to a width/height ratio (the install step's own rule)."""
    w, h = im.size
    cur = w / h
    if abs(cur - target_w_over_h) < 0.005:
        return im
    if cur > target_w_over_h:
        new_w = int(h * target_w_over_h)
        x = (w - new_w) // 2
        return im.crop((x, 0, x + new_w, h))
    new_h = int(w / target_w_over_h)
    y = (h - new_h) // 2
    return im.crop((0, y, w, y + new_h))


def _to_png(im, max_side: int) -> bytes:
    from PIL import Image
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, format="PNG"); return buf.getvalue()


def trim_view(png: bytes, trim: str, max_side: int = 1024) -> bytes:
    """What the install step keeps of this canvas."""
    from PIL import Image
    tw, th = _dims(trim)
    im = Image.open(io.BytesIO(png)).convert("RGB")
    return _to_png(crop_to_ratio(im, tw / th), max_side)


def ebook_view(png: bytes, max_side: int = 1024) -> bytes:
    """Amazon's 1600x2560 ebook crop — narrower than most trims."""
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    return _to_png(crop_to_ratio(im, 1600 / 2560), max_side)


# ── 3. MEASURE: on-device text boxes ─────────────────────────────────

def text_boxes(png: bytes) -> Optional[list]:
    """Every recognised piece of text as (text, left, top, right, bottom) in
    0..1 image fractions, top-left origin. None when the Vision framework
    is not available (then the model's estimate is the fallback)."""
    try:
        import Vision
        import Quartz
        from Foundation import NSData
    except ImportError:
        return None
    data = NSData.dataWithBytes_length_(png, len(png))
    src = Quartz.CGImageSourceCreateWithData(data, None)
    if src is None:
        return None
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(0)          # accurate
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    ok, _err = handler.performRequests_error_([req], None)
    if not ok:
        return None
    out = []
    for o in (req.results() or []):
        cands = o.topCandidates_(1)
        if not cands:
            continue
        b = o.boundingBox()          # normalised, origin bottom-left
        left = float(b.origin.x); width = float(b.size.width)
        bottom_from_bottom = float(b.origin.y); height = float(b.size.height)
        top = 1.0 - (bottom_from_bottom + height)
        out.append((str(cands[0].string()), left, top, left + width, top + height))
    return out


def edge_gaps(boxes: list) -> dict:
    """Smallest gap between any text and each edge, as image fractions.
    Negative means text crosses the edge."""
    if not boxes:
        return {}
    return {"top": min(b[2] for b in boxes),
            "bottom": min(1.0 - b[4] for b in boxes),
            "left": min(b[1] for b in boxes),
            "right": min(1.0 - b[3] for b in boxes)}


# ── 4. READ: the model's eyes ────────────────────────────────────────

_SYSTEM = ("You are a print production checker at a publishing house. You "
           "inspect finished front-cover artwork for one thing only: whether "
           "all the text is complete, inside the cover, and spelled right. "
           "You are strict and literal. Answer in JSON only.")


def _question(title: str, author: str, view_name: str) -> str:
    return (
        f"This image is the {view_name} of a book cover exactly as it will be "
        f"printed or displayed — the picture edges ARE the cover edges.\n"
        f"The book's title is: \"{title}\"" + (f"\nThe author is: \"{author}\"" if author else "") +
        "\n\nInspect every piece of text on the cover and answer:\n"
        "1. title_read: the title text exactly as it is lettered in the image, "
        "letter by letter, including any misspelling (only the letters actually "
        "visible).\n"
        "2. title_complete: true only if EVERY letter of every word of the title "
        "is fully visible — nothing cut off by the picture edge, nothing "
        "partially outside the image.\n"
        "3. any_text_clipped: true if ANY text (title, subtitle, author, series "
        "line) is cut off by an edge or partly outside the image.\n"
        "4. gap_top_pct, gap_bottom_pct, gap_left_pct, gap_right_pct: for the "
        "piece of text nearest each edge, the empty gap between that text and "
        "that edge, as a percentage of the image height (top/bottom) or width "
        "(left/right). 0 means the letters touch or cross the edge.\n"
        "5. author_read: the author name exactly as lettered on the cover, or an "
        "empty string if there is no author name anywhere on the cover.\n"
        "6. issues: a short list of plain-English problems (a misspelled word, "
        "a clipped word, a missing author name, text on the edge), empty if none.\n\n"
        "Reply with ONLY a JSON object with keys title_read, title_complete, "
        "any_text_clipped, gap_top_pct, gap_bottom_pct, gap_left_pct, "
        "gap_right_pct, author_read, issues."
    )


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"error": "no JSON in vision reply", "raw": text[:300]}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {"error": "bad JSON in vision reply", "raw": text[:300]}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _pct(v) -> Optional[float]:
    try:
        return max(0.0, float(v)) / 100.0
    except (TypeError, ValueError):
        return None


def _title_mismatch(read: str, title: str) -> Optional[str]:
    """The title as lettered must be the title as given. A subtitle after a
    colon may be missing from the read; a wrong letter may not."""
    r, w = _norm(read), _norm(title)
    if not r or not w:
        return None
    if w in r or r in w:
        return None
    head = _norm(title.split(":")[0])
    if head and head in r:
        return None
    return f"title is lettered \"{read}\", not \"{title}\""


async def check_cover_fit(png: bytes, book: dict) -> dict:
    """Returns {"ok": bool, "issues": [...], "measured": {...}, "views": {...}}.
    Looks at the trimmed view AND the ebook view: the ebook crop is narrower
    and can clip side text the trim keeps."""
    from ..writing.client import complete_vision
    from .front_cover import trim_of
    title = str(book.get("title") or "").strip()
    author = str((book.get("data") or {}).get("author_name") or "").strip()
    trim = trim_of(book)
    floor_tb, floor_lr = safe_pct(trim)
    views = {"trim": trim_view(png, trim), "ebook": ebook_view(png)}
    # a print-only book (workbooks, picture books first printed) has no
    # ebook crop to judge — a 2:3 view of an 8.5x11 cover clips by design
    _bd = book.get("data") or {}
    if _bd.get("print_only") or (_bd.get("book_type") or "") == "workbook" or (_bd.get("workbook") or {}).get("done"):
        views = {"trim": views["trim"]}
    result = {"ok": True, "issues": [], "views": {}, "measured": {}, "trim": trim,
              "floor_pct": {"top_bottom": round(floor_tb * 100, 1),
                            "sides": round(floor_lr * 100, 1)},
              "checked_at": _dt.datetime.now().isoformat(timespec="seconds")}

    def fail(msg):
        result["ok"] = False
        result["issues"].append(msg)

    for name, img in views.items():
        # ── measured boxes (primary) ──
        boxes = text_boxes(img)
        measured = None
        if boxes is not None:
            gaps = edge_gaps(boxes)
            measured = {"text": [b[0] for b in boxes],
                        "gaps_pct": {k: round(v * 100, 1) for k, v in gaps.items()}}
            result["measured"][name] = measured
            if not boxes:
                fail(f"{name}: no text found on the cover at all")
            for edge, gap in gaps.items():
                if name == "trim":
                    floor = floor_tb if edge in ("top", "bottom") else floor_lr
                else:
                    floor = 0.01        # a screen image only has to stay inside
                if gap < floor:
                    where = "crosses" if gap < 0 else "sits only " + f"{gap * 100:.1f}% from"
                    fail(f"{name}: text {where} the {edge} edge "
                         f"(floor {floor * 100:.1f}%)")
        # ── the model's read (title complete, spelled right) ──
        try:
            raw = await complete_vision(_SYSTEM, _question(title, author, name + " view"),
                                        img, max_tokens=600)
        except Exception as e:
            # no eyes = no verdict = not ok. A gate that passes when it
            # cannot look is not a gate.
            fail(f"{name}: vision read unavailable ({str(e)[:120]})")
            result["views"][name] = {"error": str(e)[:200]}
            continue
        v = _parse(raw)
        result["views"][name] = v
        if v.get("error"):
            fail(f"{name}: {v['error']}")
            continue
        if not v.get("title_complete"):
            fail(f"{name}: title not completely visible")
        if v.get("any_text_clipped"):
            fail(f"{name}: text clipped by an edge")
        mm = _title_mismatch(v.get("title_read") or "", title)
        if mm:
            fail(f"{name}: {mm}")
        # REQUIRED TEXT IS PRESENT (found 2026-09-10: a redraw "passed" with
        # no author name at all — uncut is not the same as there). The
        # author name must be found by the measurement or read by the model.
        if author and name == "trim":
            ocr_join = _norm(" ".join(measured["text"])) if measured else ""
            read_a = _norm(v.get("author_read") or "")
            want_a = _norm(author)
            surname = _norm(author.split()[-1]) if author.split() else want_a
            present = (want_a and want_a in ocr_join) or (surname and len(surname) > 3 and surname in ocr_join) \
                or (read_a and (want_a in read_a or read_a in want_a))
            if not present:
                fail(f"{name}: author name \"{author}\" is missing from the cover"
                     + (f" (lettered as \"{v.get('author_read')}\")" if read_a else ""))
        if measured is None:
            # no on-device measurement: hold the model's own estimate to the
            # floor instead, so the rule still exists
            for edge in ("top", "bottom", "left", "right"):
                gap = _pct(v.get(f"gap_{edge}_pct"))
                floor = (floor_tb if edge in ("top", "bottom") else floor_lr) if name == "trim" else 0.01
                if gap is None:
                    fail(f"{name}: no {edge} margin estimate")
                elif gap < floor:
                    fail(f"{name}: text only {gap * 100:.0f}% from the {edge} edge (estimated)")
        for extra in (v.get("issues") or [])[:3]:
            if isinstance(extra, str) and re.search(r"misspel|spelled|typo|wrong letter|cut off|clipped|missing", extra, re.I):
                fail(f"{name}: {extra.strip()[:140]}")
    return result


def retry_note(fit: dict) -> str:
    """What to tell the image engine when a draw failed the check."""
    why = "; ".join(fit.get("issues") or [])[:400]
    return ("The previous attempt FAILED the print check: " + why +
            ". Redraw with the title and all text noticeably smaller and "
            "placed well inside the picture, far from every edge, spelled "
            "exactly as given, and leave empty margin around the outside of "
            "the whole composition.")


def summary_line(fit: Optional[dict]) -> str:
    if not fit:
        return "not checked"
    if fit.get("ok"):
        return f"passed {fit.get('checked_at', '')[:16]}"
    return "; ".join(fit.get("issues") or ["failed"])[:160]


def edge_gap_shortfall(fit: dict) -> float:
    """How far (in % of the short side) the text must move in from the
    nearest edge to satisfy the floor, 0.0 when the only issues are not
    edge gaps. Read off the issue lines the checker writes."""
    import re as _re
    worst = 0.0; hit = False
    for iss in fit.get("issues") or []:
        m = _re.search(r"only ([\d.]+)% from the \w+ edge \(floor ([\d.]+)%\)", str(iss))
        if not m:
            return 0.0                    # some other fault — a redraw is needed
        hit = True
        worst = max(worst, float(m.group(2)) - float(m.group(1)))
    # a gap sitting exactly on the floor is still a refusal (2026-09-11: nine
    # covers were redrawn for "2.7% (floor 2.7%)" because the shortfall was 0)
    return max(worst, 0.6) if hit else 0.0


def inset_cover(png: bytes, pct: float) -> bytes:
    """Shrink the whole cover picture by `pct` percent inside a border made
    of its own reflected, softened edges — the text moves in from the edge,
    nothing is redrawn, and the band (mostly inside the bleed) is invisible
    in print. Star Map and Rex Count, Colour & Play, 2026-09-11: three draws
    each were spent on a 1-2% shortfall this fixes for free."""
    import io
    from PIL import Image, ImageFilter, ImageOps
    im = Image.open(io.BytesIO(png)).convert("RGB"); W, H = im.size
    pad = max(2, int(round(pct / 100.0 * H))); padw = max(2, int(round(pct / 100.0 * W)))
    big = Image.new("RGB", (W + 2 * padw, H + 2 * pad)); big.paste(im, (padw, pad))
    big.paste(ImageOps.flip(im.crop((0, 0, W, pad))), (padw, 0))
    big.paste(ImageOps.flip(im.crop((0, H - pad, W, H))), (padw, H + pad))
    big.paste(ImageOps.mirror(big.crop((padw, 0, 2 * padw, H + 2 * pad))), (0, 0))
    big.paste(ImageOps.mirror(big.crop((W, 0, W + padw, H + 2 * pad))), (W + padw, 0))
    blur = big.filter(ImageFilter.GaussianBlur(6)); mask = Image.new("L", big.size, 255)
    mask.paste(0, (padw, pad, W + padw, H + pad)); big = Image.composite(blur, big, mask)
    out = io.BytesIO(); big.resize((W, H), Image.LANCZOS).save(out, format="PNG"); return out.getvalue()


async def fit_or_inset(png: bytes, book: dict, fit: dict):
    """After a failed check: if the only faults are edge gaps, inset the
    picture and check again. Returns (png, fit) — fit ok when it worked."""
    short = edge_gap_shortfall(fit)
    if not short:
        return png, fit
    fixed = inset_cover(png, short + 1.0)
    fit2 = await check_cover_fit(fixed, book)
    fit2["inset_pct"] = round(short + 1.0, 2)
    return (fixed, fit2) if fit2.get("ok") else (png, fit)
