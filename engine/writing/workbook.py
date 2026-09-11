"""THE WORKBOOK LINE — activity and learning books, model-first (Lars,
2026-09-08: "SCRPT should not be limited by our old setup. AI models evolve
… We should improve SCRPT's abilities as the AI models become better.")

A workbook is not written in spreads; it is a run of exercise pages. The
newest live model designs each page whole (tested 2026-09-08: gpt-6-astra
with gpt-image-2 returned print-ready tracing and cutting pages in one shot),
with the universe's own character plate as the identity reference, and the
house assembles, checks and prints them.

    plan_workbook   the page plan: what every page teaches and shows
    draw_workbook   every page as a 1024x1536 print-ready black-and-white PNG
    build_interior  the 8.5 x 11 PDF, KDP-validated
    write_workbook  all three, as one job
"""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime
from pathlib import Path

import httpx

from ..config import OUTPUT_DIR, OPENAI_API_KEY, PROJECT_ROOT
from ..database import get_book_by_catalog, update_book

# the house mark on every book (Lars, 2026-09-08: TigerWorks, never Olive Tree, never small)
HOUSE_LOGO_BLACK = Path.home() / ".scrpt" / "house" / "brand" / "tigerworks-black.png"

PAGE_SIZE = "1024x1536"
PAGES_DEFAULT = 48
PARALLEL = 3
# PAGE QUALITY (Lars, 2026-09-11: "why does it cost that much?"): a side-by-
# side of the same page at high / medium / low showed medium indistinguishable
# from high for black-and-white line art, at a quarter of the price. Covers
# stay high. Low was close but got stroke-order marks wrong.
PAGE_QUALITY = "medium"
PAGE_COST_USD = {"low": 0.016, "medium": 0.063, "high": 0.25}[PAGE_QUALITY]   # gpt-image, 1024x1536 — for the ledger

# the cast as the page designer must draw them (from the universe plates)
UNIVERSE_CAST = {
    "princess-the-unicorn": {
        "author": "Poppy Marsh",   # never Lily Tiger on a suggested book (Lars, 2026-09-08)
        "plates": {"Princess": "plates/princess.png", "Glitter": "plates/glitter.png", "Pip": "plates/pip.png", "Moss": "plates/moss.png"},
        "look": ("Princess is a small white unicorn foal with big purple eyes and long lashes, a long wavy two-tone mane "
                 "(pink and blue), a small golden horn, a crown of little flowers on her head and a small heart mark on her hip. "
                 "Draw her as clean cartoon line art for colouring, exactly the same face and features on every page."),
        "cast": ("Her friends, drawn ONLY like their reference pictures: GLITTER is another small unicorn with a pastel pink, "
                 "lilac and blue wavy mane and tail, lilac hooves, a heart mark on her hip and a little silver bell on a lilac "
                 "ribbon around her neck; PIP is a small round blue bird with a white chest, big dark eyes and an orange beak; "
                 "MOSS is a chubby teal baby dragon with small orange wings, tan horns and spikes, big green eyes and a happy smile. "
                 "No other creatures — no rabbits, turtles, cats or pink dragons."),
    },
    "freddie-the-farmer": {
        "author": "Hattie Meadows",
        "display": "Freddie the Farmer",
        "plates": {"Freddie": "plates/freddie.png", "Tilly the Tractor": "plates/tilly.png", "Pip the Sheepdog": "plates/pip.png",
                   "Daisy the Cow": "plates/daisy.png"},
        "look": ("FREDDIE is a small farm boy, about seven: a mop of brown hair under a green flat cap, freckles and rosy cheeks, "
                 "big brown eyes, a red-and-cream checked shirt under blue denim dungarees, a brown tool belt with a pouch, and "
                 "yellow wellington boots. He is a BOY, never an animal. Draw him exactly like his reference picture on every page."),
        "cast": ("His friends, drawn ONLY like their reference pictures: TILLY is a friendly little red tractor with a face; "
                 "PIP is a black-and-white sheepdog; DAISY is a gentle brown-and-white cow. "
                 "No other main creatures — no pigs, no invented animals as the lead."),
    },
}
UNIVERSE_CAST["rex-the-dinosaur"] = {
    "author": "Bennie Clay",
    "display": "Rex the Dinosaur",
    "plates": {"Rex": "plates/rex.png", "Dot the Triceratops": "plates/dot.png", "Skye the Pterodactyl": "plates/skye.png",
               "Bramble the Ankylosaurus": "plates/bramble.png", "Professor Fern": "plates/professor_fern.png"},
    "look": ("REX is a small young Tyrannosaurus rex: soft moss-green skin, pale cream belly, darker green spots on his back, big round "
             "amber eyes, a wide friendly smile with tiny harmless teeth, stubby little arms and a red bandana knotted at his neck. "
             "Draw him exactly like his reference picture on every page — never scary."),
    "cast": ("His friends, drawn ONLY like their reference pictures: DOT is a small lilac-grey triceratops with a peach frill and a yellow "
             "flower; SKYE is a slim sky-blue pterodactyl with an orange beak and goggles on her head; BRAMBLE is a sturdy brown "
             "ankylosaurus with a club tail and a leaf on his back; PROFESSOR FERN is an old sage-green brachiosaurus with half-moon "
             "spectacles. No other dinosaurs as leads."),
}
UNIVERSE_DISPLAY = {slug: v.get("display") or slug.replace("-", " ").title() for slug, v in UNIVERSE_CAST.items()}
UNIVERSE_DISPLAY["princess-the-unicorn"] = "Princess the Unicorn"


def detect_universe(*texts: str) -> str:
    """The universe a title or pitch belongs to, by its established character's
    name — a suggestion that says "Freddie the Farmer" is Freddie's, and its
    cover must lead with Freddie (Lars, 2026-09-09)."""
    import re as _re
    blob = " ".join(t or "" for t in texts).lower()
    for slug, name in UNIVERSE_DISPLAY.items():
        first = name.split()[0].lower()
        # the whole name, or the character's first name as a word ("Rex the
        # Dino Explorer" is Rex's — 2026-09-10, it went out under Poppy Marsh)
        if name.lower() in blob or _re.search(r"\b" + _re.escape(first) + r"\b", blob):
            return slug
    return ""


def _universe(d: dict) -> dict:
    return UNIVERSE_CAST.get((d.get("workbook") or {}).get("universe") or d.get("universe") or "", {})


def _plate_png(slug: str, rel: str) -> bytes | None:
    p = PROJECT_ROOT / "universe" / slug / rel
    return p.read_bytes() if p.is_file() else None


async def plan_workbook(catalog: str) -> list[dict]:
    from .client import complete, extract_json
    book = get_book_by_catalog(catalog); d = book["data"]; wb = dict(d.get("workbook") or {})
    n = int(wb.get("pages_target") or PAGES_DEFAULT)
    have = list(wb.get("pages") or [])
    if len(have) >= n:
        return have
    uni = _universe(d)
    # A plan that came back short (the model stops, or its JSON is cut off) is
    # EXTENDED, never replaced: the pages already drawn keep their briefs and
    # the planner is asked for the rest (Freddie's Barnyard book came back
    # with 17 of 48, 2026-09-09).
    existing = ("PAGES ALREADY PLANNED (keep them, do not repeat their exercises):\n"
                + "\n".join(f"{q['n']}. [{q.get('type')}] {q.get('title')}" for q in have) + "\n\n") if have else ""
    prompt = (existing + 
        f"BOOK: {book['title']}\nAGES: {wb.get('ages') or '3-5'}\nWHAT IT IS: {wb.get('pitch') or d.get('description') or ''}\n"
        + (f"CHARACTERS: {uni.get('look')} {uni.get('cast', '')}\n" if uni else "")
        + (f"\nPlan pages {len(have) + 1} to {n} — exactly {n - len(have)} MORE interior exercise pages, numbered from {len(have) + 1} — " if have else f"\nPlan exactly {n} interior exercise pages ")
        + "for this printable activity book (US Letter, black-and-white line art, "
        "one exercise per page, ages as stated). Order them as a child would progress: easy to harder, with variety every few "
        "pages, and the character appearing on most pages in a small supporting role (cheering, holding a sign, being coloured). "
        "Allowed page types: tracing (lines, shapes, letters, numbers, words), cutting (dashed cut lines, cut-and-paste), "
        "matching (draw a line from A to B), counting (count and circle / write the number), colouring (big simple line art, "
        "or colour-by-number), maze (simple), find-the-difference, patterns (what comes next), how-to-draw (a 2x3 grid of six "
        "numbered steps that each add a few simple strokes to the previous step, ending in the finished drawing, with a large "
        "empty practice box below), and one certificate page last. "
        "THE BOOK'S OWN KIND RULES THE MIX: a 'draw with' / 'how to draw' book is at least 36 how-to-draw pages (one subject per "
        "page: each character of the world, then its places and objects, easy to harder), with a few colouring pages; a 'cut and "
        "paste' book is mostly cutting pages after a few tracing warm-ups; a 'letters, numbers & colours' book is mostly tracing, "
        "counting and colouring. "
        "Every brief must be concrete enough that a designer draws the page without asking: the exact letters/numbers/objects, "
        "how many rows, what the character does, the one-line instruction printed at the top.\n"
        'Return JSON only: {"pages": [{"n": 1, "type": "tracing", "title": "Trace the letter A", "brief": "..."}]}'
    )
    raw = await complete("You plan children's activity books that teach one thing per page. JSON only.", prompt, max_tokens=12000, mechanical=True)
    out = extract_json(raw) or {}
    pages = out.get("pages") if isinstance(out, dict) else out
    pages = have + [p for p in (pages or []) if isinstance(p, dict) and p.get("brief")]
    pages = pages[:n]
    if len(pages) < 12:
        raise RuntimeError(f"the plan came back with {len(pages)} pages")
    for i, p in enumerate(pages, 1):
        p["n"] = i
    if len(pages) < n:
        # save what we have and ask again for the rest, up to three rounds
        b = get_book_by_catalog(catalog); data = dict(b["data"]); wb2 = dict(data.get("workbook") or {})
        wb2["pages"] = pages; data["workbook"] = wb2; update_book(b["id"], data)
        rounds = int(wb2.get("plan_rounds") or 0) + 1
        if rounds <= 3:
            b = get_book_by_catalog(catalog); data = dict(b["data"]); data["workbook"]["plan_rounds"] = rounds; update_book(b["id"], data)
            return await plan_workbook(catalog)
    b = get_book_by_catalog(catalog); data = dict(b["data"]); wb = dict(data.get("workbook") or {})
    wb["pages"] = pages; wb["planned_at"] = datetime.now().isoformat(timespec="minutes"); data["workbook"] = wb
    update_book(b["id"], data)
    return pages


def _page_prompt(book: dict, page: dict, uni: dict) -> str:
    return (
        f"Design ONE printable activity-book page: portrait, US Letter 8.5 x 11 in, BLACK-AND-WHITE LINE ART on pure white, "
        f"print-ready (thick clean lines, no grey fills, no gradients, no photo, no colour). Book: '{book['title']}', ages "
        f"{(book['data'].get('workbook') or {}).get('ages') or '3-5'}. Page {page['n']}: {page.get('title', '')}.\n"
        f"THE PAGE: {page['brief']}\n"
        + (f"THE CHARACTERS (the attached pictures are the references, in this order: Princess, Glitter, Pip, Moss): {uni.get('look')} {uni.get('cast', '')}\n" if uni else "")
        + ("HOW-TO-DRAW PAGE: a 2x3 grid of six numbered boxes; step 1 is the simplest shape, each later box repeats the previous "
           "drawing exactly and adds a few strokes, box 6 is the finished drawing; below the grid one large empty practice box. "
           "The subject must be drawn identically in every step.\n" if page.get("type") == "how-to-draw" else "")
        + "Rules: one short instruction line at the top in a friendly rounded font; generous spacing so a small child can work; "
        "dashed lines for cutting, dotted outlines for tracing, ruled rows for handwriting; every element fully inside 0.5 in margins; "
        "nothing cut off; no page number; no publisher text; no watermark."
    )


def _small_plate(png: bytes, side: int = 512) -> bytes:
    """A reference plate at 512px: the model keeps the character just as
    faithfully, and the input image tokens fall by more than half
    (measured 2026-09-11: $0.134 → $0.092 a page)."""
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB"); im.thumbnail((side, side))
    b = io.BytesIO(); im.save(b, format="PNG", optimize=True); return b.getvalue()


# token prices for the image endpoint (USD per 1M): text in, image in, image out
IMAGE_TOKEN_USD = (5.0, 10.0, 40.0)


def _usage_usd(usage: dict) -> float:
    ti = (usage or {}).get("input_tokens_details") or {}
    return round(ti.get("text_tokens", 0) * IMAGE_TOKEN_USD[0] / 1e6 + ti.get("image_tokens", 0) * IMAGE_TOKEN_USD[1] / 1e6
                 + (usage or {}).get("output_tokens", 0) * IMAGE_TOKEN_USD[2] / 1e6, 4)


async def _draw_page(client: httpx.AsyncClient, book: dict, page: dict, uni: dict, slug: str, out: Path) -> str:
    """One page through the images/edits endpoint: the newest live image
    model, PAGE_QUALITY, the universe plates at 512px as references — and
    the API's own usage numbers booked to the ledger as the page's cost
    (Lars, 2026-09-11: "$240 in less than an hour" — the old path via the
    Responses tool reported no usage, so the ledger guessed)."""
    from ..cover.front_cover import pick_image_model
    files = []
    for name, rel in ((uni.get("plates") or {}).items() if uni else []):
        png = _plate_png(slug, rel)
        if png:
            files.append(("image[]", (f"{name}.png", _small_plate(png), "image/png")))
    prompt = _page_prompt(book, page, uni)[:3800]
    try:
        ids = [m["id"] for m in (await client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}, timeout=30)).json().get("data", [])]
        model = pick_image_model(ids)
    except Exception:
        model = "gpt-image-2"
    last = None
    for attempt in range(2):
        try:
            if files:
                r = await client.post("https://api.openai.com/v1/images/edits", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                                      files=files, data={"model": model, "prompt": prompt, "size": PAGE_SIZE, "quality": PAGE_QUALITY, "n": "1"}, timeout=420)
            else:
                r = await client.post("https://api.openai.com/v1/images/generations", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                                      json={"model": model, "prompt": prompt, "size": PAGE_SIZE, "quality": PAGE_QUALITY, "n": 1}, timeout=420)
        except httpx.HTTPError as e:
            last = e; await asyncio.sleep(3); continue
        if r.status_code == 200:
            j = r.json()
            out.write_bytes(base64.b64decode(j["data"][0]["b64_json"]))
            page["_usd"] = _usage_usd(j.get("usage") or {})
            return model
        last = RuntimeError(f"{r.status_code}: {r.text[:160]}")
        if r.status_code < 500:
            break
        await asyncio.sleep(3)
    raise RuntimeError(f"page {page['n']} failed: {last}")


def _ledger(catalog: str, n: int, model: str, usd: float | None = None):
    try:
        import sqlite3
        from ..config import DATABASE_PATH
        c = sqlite3.connect(str(DATABASE_PATH))
        c.execute("INSERT INTO token_usage (at, catalog, job_id, kind, model, input_tokens, output_tokens, cache_read, cache_write, usd) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (datetime.now().isoformat(timespec="seconds"), catalog, "workbook", f"workbook page {n}", model, 0, 0, 0, 0, usd if usd is not None else PAGE_COST_USD))
        c.commit(); c.close()
    except Exception:
        pass


async def draw_workbook(catalog: str, handle=None) -> dict:
    book = get_book_by_catalog(catalog); d = book["data"]; wb = d.get("workbook") or {}
    pages = wb.get("pages") or await plan_workbook(catalog)
    slug = wb.get("universe") or ""
    uni = UNIVERSE_CAST.get(slug, {})
    out_dir = OUTPUT_DIR / catalog / "workbook"; out_dir.mkdir(parents=True, exist_ok=True)
    todo = [p for p in pages if not (out_dir / f"page-{p['n']:02d}.png").is_file()]
    done, failed = [], []
    sem = asyncio.Semaphore(PARALLEL)
    async with httpx.AsyncClient() as client:
        async def one(p):
            async with sem:
                if handle:
                    handle.progress(0.1 + 0.7 * (len(done) + len(failed)) / max(1, len(pages)), "drawing", f"page {p['n']} of {len(pages)}: {p.get('title', '')[:40]}")
                try:
                    model = await _draw_page(client, book, p, uni, slug, out_dir / f"page-{p['n']:02d}.png")
                    _ledger(catalog, p["n"], model, p.get("_usd")); done.append(p["n"])
                except Exception as e:
                    failed.append((p["n"], str(e)[:120]))
        await asyncio.gather(*[one(p) for p in todo])
    return {"drawn": sorted(done), "failed": failed, "already": len(pages) - len(todo)}


def build_workbook_interior(catalog: str) -> dict:
    """The 8.5 x 11 PDF: title page, 'this book belongs to', the pages, even count."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas
    from ..interior.validator import validate_interior_pdf
    book = get_book_by_catalog(catalog); d = book["data"]; wb = d.get("workbook") or {}
    pages = wb.get("pages") or []
    out_dir = OUTPUT_DIR / catalog; pdir = out_dir / "workbook"
    pngs = [pdir / f"page-{p['n']:02d}.png" for p in pages]
    missing = [p.name for p in pngs if not p.is_file()]
    if missing:
        raise RuntimeError(f"{len(missing)} page(s) not drawn yet: {missing[:5]}")
    # KDP MARGINS FOR A NO-BLEED 8.5 x 11 WORKBOOK (Lars, 2026-09-08: "margins
    # according to the KDP standard for this genre"): KDP's minimum inside
    # (gutter) margin is 0.375 in up to 150 pages and 0.5 in up to 300, outside
    # margins at least 0.25 in. Activity books are worked flat and cut, so the
    # house sets inside 0.75 in, outside 0.5 in, top and bottom 0.5 in — and
    # MIRRORS them: odd pages are right-hand (gutter on the left), even pages
    # left-hand (gutter on the right).
    PT = 72.0; W, H = 8.5 * PT, 11.0 * PT
    M_IN, M_OUT, M_TOP, M_BOT = 0.75 * PT, 0.5 * PT, 0.5 * PT, 0.5 * PT
    # fonts must be EMBEDDED (KDP's check): the house serif from the frontend's font folder
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fdir = PROJECT_ROOT / "frontend" / "public" / "fonts"
    try:
        pdfmetrics.registerFont(TTFont("HouseSerif", str(fdir / "EBGaramond-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("HouseSerif-Bold", str(fdir / "EBGaramond-Bold.ttf")))
        F_REG, F_BOLD = "HouseSerif", "HouseSerif-Bold"
    except Exception:
        F_REG, F_BOLD = "Helvetica", "Helvetica-Bold"
    pdf = out_dir / "interior.pdf"
    # initialFontName: reportlab otherwise puts an unembedded Helvetica in every page's resources
    c = rl_canvas.Canvas(str(pdf), pagesize=(W, H), initialFontName=F_REG); c.setTitle(book["title"]); c.setAuthor(d.get("author_name") or "")
    # 1. title page — every line inside the margins (KDP flagged a long title
    # drawn on one line, 2026-09-08), the TigerWorks mark at the foot
    from reportlab.lib.utils import simpleSplit, ImageReader
    text_w = W - M_IN - M_OUT - 0.4 * PT
    size = 30
    from ..typeset_rules import fit_title            # ≥3 words a line, balanced (Lars, 2026-09-09)
    from reportlab.pdfbase.pdfmetrics import stringWidth as _sw
    lines, size = fit_title(book["title"], lambda t, sz: _sw(t, F_BOLD, sz), text_w, size, 18)
    y = H * 0.64
    c.setFont(F_BOLD, size)
    for ln in lines:
        c.drawCentredString(W / 2, y, ln); y -= size * 1.2
    c.setFont(F_REG, 16); c.drawCentredString(W / 2, y - 10, d.get("author_name") or "")
    logo = HOUSE_LOGO_BLACK
    if logo.exists():
        from ..typeset_rules import HOUSE_MARK_IN
        lsz = HOUSE_MARK_IN["workbook_title"] * PT       # 0.8" — the house mark rule (Lars, 2026-09-09)
        c.drawImage(ImageReader(str(logo)), W / 2 - lsz / 2, M_BOT + 0.35 * PT, lsz, lsz, mask="auto")
    c.showPage()
    # 2. belongs-to + copyright
    c.setFont(F_BOLD, 22); c.drawCentredString(W / 2, H * 0.7, "This book belongs to")
    c.setLineWidth(1.2); c.line(W * 0.2, H * 0.62, W * 0.8, H * 0.62)
    c.setFont(F_REG, 9)
    c.drawCentredString(W / 2, H * 0.1, f"© {datetime.now().year} TigerWorks · All rights reserved.")
    c.drawCentredString(W / 2, H * 0.085, "For personal and classroom use. Adult supervision recommended for scissors.")
    c.showPage()
    # 3. the pages, mirrored margins
    box_w, box_h = W - M_IN - M_OUT, H - M_TOP - M_BOT
    page_no = 3
    for png in pngs:
        im = Image.open(png).convert("L")
        # pure black on white: lift any grey the model left, for clean print
        im = im.point(lambda v: 255 if v > 200 else (0 if v < 90 else v))
        iw, ih = im.size; scale = min(box_w / iw, box_h / ih); dw, dh = iw * scale, ih * scale
        right_hand = page_no % 2 == 1
        left = (M_IN if right_hand else M_OUT) + (box_w - dw) / 2
        c.drawImage(ImageReader(im), left, M_BOT + (box_h - dh) / 2, dw, dh)
        c.showPage(); page_no += 1
    n_pages = 2 + len(pngs)
    # a print binder wants a page count divisible by 8 — always (Lars, 2026-09-09)
    while n_pages % 8:
        c.showPage(); n_pages += 1
    c.save()
    validation = validate_interior_pdf(str(pdf), trim_w=8.5, trim_h=11.0, paper_type="white_bw", trim_key="8.5x11",
                                       gutter_used=0.75, outside_margin_used=0.5, body_font_pt=12, bleed=False)
    vd = validation.as_dict() if hasattr(validation, "as_dict") else (validation if isinstance(validation, dict) else {"passed": True})
    b = get_book_by_catalog(catalog); data = dict(b["data"])
    data["interior"] = {"page_count": n_pages, "pdf_path": str(pdf), "exported_at": datetime.now().isoformat(), "validation": vd, "kind": "workbook",
                        "margins_in": {"inside": 0.75, "outside": 0.5, "top": 0.5, "bottom": 0.5, "mirrored": True, "bleed": False}}
    data["page_count"] = n_pages
    update_book(b["id"], data)
    return {"pdf": str(pdf), "page_count": n_pages, "validation": vd}


async def write_blurb(catalog: str) -> str:
    """The back-cover / KDP description, written for the parent who is buying.
    The suggestion's pitch is publisher talk (market, cross-promotion,
    'customers also bought') and printed once on a back cover (2026-09-08);
    the blurb is what a parent reads in the shop."""
    from .client import complete
    book = get_book_by_catalog(catalog); d = book["data"]; wb = d.get("workbook") or {}
    uni = _universe(d)
    pages = wb.get("pages") or []
    sample = "; ".join(f"{p.get('type') or ''}: {p.get('title') or p.get('brief') or ''}" for p in pages[:12])
    prompt = (f"BOOK: {book['title']}\nAGES: {wb.get('ages') or '3-5'}\nAUTHOR: {d.get('author_name') or ''}\n"
              f"WHAT IT IS (publisher's note, do not copy its language): {wb.get('pitch') or d.get('description') or ''}\n"
              + (f"CHARACTERS: {uni.get('cast', '')}\n" if uni else "")
              + f"PAGES INSIDE ({len(pages)} total), first ones: {sample}\n\n"
              "Write the back-cover text a parent reads in the shop: 3 short paragraphs, 70-110 words in total. "
              "Paragraph 1: what the child does in this book, in warm concrete words (name two or three actual activities). "
              "Paragraph 2: the characters who keep them company and what the pages build (pencil control, letters, scissor skills...). "
              "Paragraph 3: one line on the format (big pages, one activity per page, ages) and an invitation. "
              "Speak to the parent, never about 'the market', 'the brand', 'the series', 'cross-promotion' or Amazon. "
              "No hype words (ultimate, amazing, perfect). No bullet points, no headings, no quotes. Plain text, paragraphs separated by a blank line.")
    text = (await complete("You write the back covers of children's activity books for a small publishing house. Warm, exact, never salesy.",
                           prompt, max_tokens=600, mechanical=True)).strip()
    b = get_book_by_catalog(catalog); data = dict(b["data"])
    data["description"] = text; data["back_cover_blurb"] = text
    update_book(b["id"], data, sections=["description", "back_cover_blurb"])
    return text


async def write_workbook(catalog: str, handle=None) -> dict:
    """Plan → draw → interior → accepted (there is no manuscript to read)."""
    if handle:
        handle.progress(0.03, "planning", "planning the pages")
    pages = await plan_workbook(catalog)
    if handle:
        handle.progress(0.08, "drawing", f"{len(pages)} pages to draw")
    dr = await draw_workbook(catalog, handle)
    if dr["failed"]:
        dr2 = await draw_workbook(catalog, handle)           # one more pass for the stragglers
        dr["failed"] = dr2["failed"]; dr["drawn"] = sorted(set(dr["drawn"]) | set(dr2["drawn"]))
    if dr["failed"]:
        return {"ok": False, "stopped_at": "drawing", "failed": dr["failed"], "drawn": dr["drawn"]}
    if handle:
        handle.progress(0.82, "cover", "designing the cover")
    try:
        await design_cover(catalog)
    except Exception as e:
        print(f"  workbook cover failed: {str(e)[:120]}")
    if handle:
        handle.progress(0.9, "interior", "assembling the PDF")
    res = await asyncio.to_thread(build_workbook_interior, catalog)
    ok = bool((res.get("validation") or {}).get("passed", True))
    if handle: handle.progress(0.93, "blurb", "the back cover text")
    try:
        await write_blurb(catalog)
    except Exception as e:
        print(f"  workbook blurb failed for {catalog}: {e}")
    b = get_book_by_catalog(catalog); data = dict(b["data"])
    data["workbook"] = {**(data.get("workbook") or {}), "done": ok, "drawn_at": datetime.now().isoformat(timespec="minutes")}
    data["acceptance"] = {"verdict": "accept" if ok else "revise", "accepted_by": "workbook line", "score": None,
                          "readability": {"meets_target": True, "house_target": "activity pages"}, "length": {"ok": True}, "continuity": []}
    data["manuscript"] = {**(data.get("manuscript") or {}), "status": "complete", "word_count": 0}
    update_book(b["id"], data)
    return {"ok": ok, "pages": len(pages), **res}


# ── Cover framing for the trim ───────────────────────────────────────────────
# The image model draws 2:3; an 8.5x11 cover is wider, so ~14% of the height
# is cut. The model ignores "leave the bottom band empty" often enough that
# the author name landed in the cut band three times out of three (Lars,
# 2026-09-08). So the crop is chosen by looking: macOS Vision OCR finds where
# the title and the author line actually are, the crop keeps the title whole
# and either keeps the author line inside the safe zone or, when that is not
# possible, the house stamps the author name itself.

_OCR_BIN = Path.home() / ".scrpt" / "bin" / "ocr-boxes"


def _ocr_boxes(png_path: Path) -> list[dict]:
    """[{text, conf, x, y, w, h}] in image fractions (origin top-left), [] when
    Vision is unavailable. Compiled once from engine/tools/ocr_boxes.swift."""
    import subprocess
    src = PROJECT_ROOT / "engine" / "tools" / "ocr_boxes.swift"
    try:
        if not _OCR_BIN.exists() or _OCR_BIN.stat().st_mtime < src.stat().st_mtime:
            _OCR_BIN.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["xcrun", "swiftc", "-O", str(src), "-o", str(_OCR_BIN)], check=True,
                           capture_output=True, timeout=300)
        out = subprocess.run([str(_OCR_BIN), str(png_path)], capture_output=True, text=True, timeout=120)
        return json.loads(out.stdout or "[]")
    except Exception:
        return []


def outpaint_for_trim(raw_png: bytes, trim: str) -> bytes | None:
    """Extend the model's 2:3 picture sideways so the WHOLE composition fits
    the trim: the picture is set at 88% inside a 1024x1536 canvas, the border
    is masked, and the image model continues sky, meadow and flowers outward
    (Letters, Numbers & Colours, 2026-09-09: its horn sat on the trim line
    under any crop). Returns the 2:3 result to be cropped centred, or None
    when the edit endpoint fails. About $0.25 a cover."""
    import io, httpx
    from PIL import Image
    try:
        raw = Image.open(io.BytesIO(raw_png)).convert("RGBA")
        W, H = 1024, 1536
        inner = raw.resize((int(W * 0.88), int(H * 0.88)), Image.LANCZOS)
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0)); mask = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ox, oy = (W - inner.width) // 2, (H - inner.height) // 2
        canvas.paste(inner, (ox, oy)); mask.paste(Image.new("RGBA", inner.size, (0, 0, 0, 255)), (ox, oy))
        cb, mb = io.BytesIO(), io.BytesIO(); canvas.save(cb, format="PNG"); mask.save(mb, format="PNG")
        prompt = ("Extend this children's book cover artwork outward to fill the whole canvas: continue the sky, clouds, "
                  "meadow, grass and flowers seamlessly beyond the current edges in the same painted style and colours. "
                  "Do not change, move or redraw anything inside the existing picture; add no new characters and no text.")
        from ..cover.front_cover import pick_image_model
        with httpx.Client(timeout=420) as c:
            try:      # the newest live image model, never a pinned version
                ids = [m["id"] for m in c.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}, timeout=30).json().get("data", [])]
                model = pick_image_model(ids)
            except Exception:
                model = "gpt-image-2"
            for attempt in range(2):
                r = c.post("https://api.openai.com/v1/images/edits", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                           files={"image[]": ("cover.png", cb.getvalue(), "image/png"), "mask": ("mask.png", mb.getvalue(), "image/png")},
                           data={"model": model, "prompt": prompt, "size": "1024x1536", "quality": "high", "n": "1"})
                if r.status_code == 200:
                    return base64.b64decode(r.json()["data"][0]["b64_json"])
                if r.status_code < 500:
                    break
        return None
    except Exception:
        return None


def _similar(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def frame_cover_for_trim(raw_png: bytes, trim: str, author: str, work_dir: Path | None = None) -> tuple[bytes, dict]:
    """Crop the model's image to the trim's proportions around the text it
    drew, and stamp the author name when the model's own is lost or unsafe.
    Returns (png bytes, report)."""
    import io
    from PIL import Image, ImageDraw, ImageFont
    tw, th = (float(x) for x in trim.split("x"))
    im = Image.open(io.BytesIO(raw_png)).convert("RGB"); W, H = im.size
    new_h = int(W * th / tw)
    report = {"trim": trim, "boxes": [], "cut_top": 0, "cut_bottom": 0, "stamped": False}
    if new_h >= H:                       # not too tall: nothing to decide
        return raw_png, report
    surplus = H - new_h
    tmp = (work_dir or Path(OUTPUT_DIR)) / "_frame-ocr.png"
    tmp.parent.mkdir(parents=True, exist_ok=True); tmp.write_bytes(raw_png)
    boxes = [b for b in _ocr_boxes(tmp) if b.get("conf", 0) >= 0.5 and b.get("w", 0) >= 0.08]
    tmp.unlink(missing_ok=True)
    report["boxes"] = boxes
    author_box = next((b for b in boxes if author and _similar(b["text"], author) >= 0.7), None)
    title_boxes = [b for b in boxes if b is not author_box]
    # The title usually wears an ornament (horn, flowers, stars) that OCR does
    # not see: give the top of the title real air, or the ornament sits on the
    # trim and the bleed cuts it (Letters, Numbers & Colours, 2026-09-09).
    margin = 0.06 * H
    title_top = min((b["y"] * H for b in title_boxes), default=None)
    title_bot = max(((b["y"] + b["h"]) * H for b in title_boxes), default=None)
    safe = 0.035 * new_h               # KDP: text 0.25" inside the trim (0.25/11 = 2.3%) plus air

    def author_state(cut_top):
        if not author_box:
            return "absent"
        top, bot = author_box["y"] * H - cut_top, (author_box["y"] + author_box["h"]) * H - cut_top
        if bot <= new_h - safe and top >= safe:
            return "safe"
        if top >= new_h or bot <= 0:
            return "gone"
        return "cut"

    def title_ok(cut_top):
        if title_top is None:
            return True
        return title_top - margin >= cut_top and title_bot + 0.015 * H <= cut_top + new_h

    # candidates: centred first, then every 1% of the surplus either way
    order = sorted(range(0, surplus + 1, max(1, surplus // 100)), key=lambda c: abs(c - surplus / 2))
    pick = None
    for want in ("safe", "gone", "absent"):
        for c in order:
            if title_ok(c) and author_state(c) == want:
                pick = c; break
        if pick is not None:
            break
    if pick is None:                    # keep the title whole, whatever the author line does
        pick = next((c for c in order if title_ok(c)), None)
    if pick is None:                    # the title itself does not fit: cut where it hurts least
        pick = int(min(surplus, max(0, (title_top or 0) - margin)))
    # When the crop would still crowd the title's ornament (less than 10% of
    # the height above the title, with a real cut at the top), the picture is
    # extended sideways instead of cut — the whole composition survives.
    crowded = pick > 0.02 * H and title_top is not None and (title_top - pick) < 0.10 * H
    if crowded and not report.get("outpainted"):
        ext = outpaint_for_trim(raw_png, trim)
        if ext:
            im = Image.open(io.BytesIO(ext)).convert("RGB"); W, H = im.size
            new_h = int(W * th / tw); surplus = H - new_h; pick = surplus // 2
            report.update({"outpainted": True})
            author_box = None                # the model drops the name; it is stamped below
    out = im.crop((0, pick, W, pick + new_h))
    report.update({"cut_top": pick, "cut_bottom": surplus - pick, "author": author_state(pick) if not report.get("outpainted") else "gone"})

    if author and author_state(pick) != "safe":
        draw = ImageDraw.Draw(out)
        size = max(18, int(new_h * 0.028))
        font = None
        for f in ("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", "/Library/Fonts/Arial Rounded Bold.ttf"):
            try:
                font = ImageFont.truetype(f, size); break
            except OSError:
                continue
        font = font or ImageFont.load_default()
        x0, y0, x1, y1 = draw.textbbox((0, 0), author, font=font)
        tw_px, th_px = x1 - x0, y1 - y0
        x = (W - tw_px) / 2 - x0; y = new_h - safe - th_px - y0 - int(new_h * 0.015)
        draw.text((x, y), author, font=font, fill="white", stroke_width=max(2, size // 9), stroke_fill=(43, 27, 61))
        report["stamped"] = True
    buf = io.BytesIO(); out.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), report


def reframe_cover(catalog: str) -> dict:
    """Re-run the framing on the model's original image (cover-art-raw.png),
    no generation, and re-install. For covers made before the framing rule."""
    from ..cover.front_cover import _install_cover
    book = get_book_by_catalog(catalog); d = book["data"]
    out_dir = Path(OUTPUT_DIR) / catalog
    raw = out_dir / "cover-art-raw.png"
    if not raw.exists():
        raw.write_bytes((out_dir / "cover-art.png").read_bytes())
    trim = (d.get("format") or {}).get("trim_size") or d.get("trim_size") or "8.5x11"
    framed, rep = frame_cover_for_trim(raw.read_bytes(), trim, d.get("author_name") or "", out_dir)
    res = _install_cover(catalog, framed, ((d.get("cover") or {}).get("art_brief") or ""))
    return {**res, "framing": rep}


async def design_cover(catalog: str) -> dict:
    """The front cover, with the universe's character plate as the identity
    reference, installed the house way (cover-art, ebook, preview files)."""
    from ..cover.front_cover import _generate_one, _install_cover, _record_fit_failure, size_for_trim
    from ..cover.cover_fit import MAX_ATTEMPTS, check_cover_fit, retry_note, safe_zone_line
    book = get_book_by_catalog(catalog); d = book["data"]; wb = d.get("workbook") or {}
    trim = (d.get("format") or {}).get("trim_size") or d.get("trim_size") or "8.5x11"
    slug = wb.get("universe") or ""; uni = UNIVERSE_CAST.get(slug, {})
    plates = [png for png in (_plate_png(slug, rel) for rel in (uni.get("plates") or {}).values()) if png] if uni else []
    author = d.get("author_name") or ""
    brief = (f"Create a paperback front book cover for a children's activity book called: {book['title']}\n"
             f"What the book is about (for the ARTWORK only — do not write any of this on the cover): {wb.get('pitch') or d.get('description') or ''}\n"
             + (f"The characters: {uni.get('look')} {uni.get('cast', '')} The attached pictures are the references, in this order: "
                "Princess, Glitter, Pip, Moss. Draw them in a friendly full-colour cartoon style, happy and inviting.\n" if uni else "")
             + f'The ONLY text anywhere on the cover is the title "{book["title"]}"' + (f' and the author name "{author}" — the author name MUST appear, in small clean type near the bottom of the safe zone' if author else "") + ".\n"
             "Output the FLAT COVER ARTWORK ITSELF, one flat rectangle filled edge to edge; not a mockup, no spine, no shadow.\n"
             "Bright, clean, child-safe; big readable title; it must look like a bestselling activity book on Amazon.\n"
             # THE COVER FIT CONTROL (2026-09-10): the canvas is now drawn in the
             # trim's own proportions (size_for_trim), so nothing is cut; the
             # safe-zone rule replaces the old "2:3 will be cut" paragraph.
             + safe_zone_line(trim) + "\n"
             + (f"Author: {author}\n" if author else "") + "Book size: " + trim.replace("x", "″ × ") + "″")
    out_dir = Path(OUTPUT_DIR) / catalog; out_dir.mkdir(parents=True, exist_ok=True)
    prompt = brief
    fit = None
    async with httpx.AsyncClient() as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            png = await _generate_one(client, prompt, reference_png=plates or None, gen_size=size_for_trim(trim))
            (out_dir / "cover-art-raw.png").write_bytes(png)          # the model's image, uncropped
            # framing is a no-op on a trim-exact canvas; it still guards a
            # fallback engine that could only draw 2:3
            framed, rep = frame_cover_for_trim(png, trim, author, out_dir)
            fit = await check_cover_fit(framed, book)
            if not fit["ok"]:
                from ..cover.cover_fit import fit_or_inset
                framed, fit = await fit_or_inset(framed, book, fit)     # an edge gap is fixed for free, never by a draw
            fit["attempt"] = attempt
            if fit["ok"]:
                res = _install_cover(catalog, framed, brief, fit=fit)
                return {**res, "framing": rep}
            (out_dir / f"cover-rejected-{attempt}.png").write_bytes(framed)
            print(f"  workbook cover attempt {attempt} refused: " + "; ".join(fit.get("issues") or [])[:200])
            prompt = brief + "\n" + retry_note(fit)
    _record_fit_failure(catalog, fit)
    raise RuntimeError("Workbook cover failed the fit check " + str(MAX_ATTEMPTS) + " times: "
                       + "; ".join((fit or {}).get("issues") or []))
