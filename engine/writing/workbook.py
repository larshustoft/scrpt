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

PAGE_SIZE = "1024x1536"
PAGES_DEFAULT = 48
PARALLEL = 3
PAGE_COST_USD = 0.25          # gpt-image-2 high, 1024x1536 — for the ledger

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
}


def _universe(d: dict) -> dict:
    return UNIVERSE_CAST.get((d.get("workbook") or {}).get("universe") or d.get("universe") or "", {})


def _plate_png(slug: str, rel: str) -> bytes | None:
    p = PROJECT_ROOT / "universe" / slug / rel
    return p.read_bytes() if p.is_file() else None


async def plan_workbook(catalog: str) -> list[dict]:
    from .client import complete, extract_json
    book = get_book_by_catalog(catalog); d = book["data"]; wb = dict(d.get("workbook") or {})
    if wb.get("pages"):
        return wb["pages"]
    n = int(wb.get("pages_target") or PAGES_DEFAULT)
    uni = _universe(d)
    prompt = (
        f"BOOK: {book['title']}\nAGES: {wb.get('ages') or '3-5'}\nWHAT IT IS: {wb.get('pitch') or d.get('description') or ''}\n"
        + (f"CHARACTER: {uni.get('look')}\n" if uni else "")
        + f"\nPlan exactly {n} interior exercise pages for this printable activity book (US Letter, black-and-white line art, "
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
    pages = [p for p in (pages or []) if isinstance(p, dict) and p.get("brief")][:n]
    if len(pages) < 12:
        raise RuntimeError(f"the plan came back with {len(pages)} pages")
    for i, p in enumerate(pages, 1):
        p["n"] = i
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


async def _draw_page(client: httpx.AsyncClient, book: dict, page: dict, uni: dict, slug: str, out: Path) -> str:
    from ..cover.front_cover import _best_text_models
    content = []
    for name, rel in ((uni.get("plates") or {}).items() if uni else []):
        png = _plate_png(slug, rel)
        if png:
            content.append({"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode()})
    content.append({"type": "input_text", "text": _page_prompt(book, page, uni)})
    body = {"input": [{"role": "user", "content": content}],
            "tools": [{"type": "image_generation", "size": PAGE_SIZE, "quality": "high"}], "tool_choice": "required"}
    last = None
    for model in await _best_text_models(client):
        body["model"] = model
        for attempt in range(2):
            try:
                r = await client.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                                      json=body, timeout=420)
            except httpx.HTTPError as e:
                last = e; await asyncio.sleep(3); continue
            if r.status_code == 200:
                for item in r.json().get("output", []):
                    if item.get("type") == "image_generation_call" and item.get("result"):
                        out.write_bytes(base64.b64decode(item["result"]))
                        return model
                last = RuntimeError("no image in the response"); continue
            last = RuntimeError(f"{r.status_code}: {r.text[:160]}")
            if r.status_code in (400, 404) and "model" in r.text.lower():
                break
            if r.status_code < 500:
                break
            await asyncio.sleep(3)
    raise RuntimeError(f"page {page['n']} failed: {last}")


def _ledger(catalog: str, n: int, model: str):
    try:
        import sqlite3
        from ..config import DATABASE_PATH
        c = sqlite3.connect(str(DATABASE_PATH))
        c.execute("INSERT INTO token_usage (at, catalog, job_id, kind, model, input_tokens, output_tokens, cache_read, cache_write, usd) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (datetime.now().isoformat(timespec="seconds"), catalog, "workbook", f"workbook page {n}", model, 0, 0, 0, 0, PAGE_COST_USD))
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
                    _ledger(catalog, p["n"], model); done.append(p["n"])
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
    pdf = out_dir / "interior.pdf"
    c = rl_canvas.Canvas(str(pdf), pagesize=(W, H)); c.setTitle(book["title"]); c.setAuthor(d.get("author_name") or "")
    # 1. title page
    c.setFont("Helvetica-Bold", 30); c.drawCentredString(W / 2, H * 0.62, book["title"][:60])
    c.setFont("Helvetica", 16); c.drawCentredString(W / 2, H * 0.55, d.get("author_name") or "")
    c.setFont("Helvetica", 11); c.drawCentredString(W / 2, H * 0.12, "OLIVE TREE SCRIPTS")
    c.showPage()
    # 2. belongs-to + copyright
    c.setFont("Helvetica-Bold", 22); c.drawCentredString(W / 2, H * 0.7, "This book belongs to")
    c.setLineWidth(1.2); c.line(W * 0.2, H * 0.62, W * 0.8, H * 0.62)
    c.setFont("Helvetica", 9)
    c.drawCentredString(W / 2, H * 0.1, f"© {datetime.now().year} {d.get('author_name') or ''} · Olive Tree Scripts · All rights reserved.")
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
    if n_pages % 2:
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
    b = get_book_by_catalog(catalog); data = dict(b["data"])
    data["workbook"] = {**(data.get("workbook") or {}), "done": ok, "drawn_at": datetime.now().isoformat(timespec="minutes")}
    data["acceptance"] = {"verdict": "accept" if ok else "revise", "accepted_by": "workbook line", "score": None,
                          "readability": {"meets_target": True, "house_target": "activity pages"}, "length": {"ok": True}, "continuity": []}
    data["manuscript"] = {**(data.get("manuscript") or {}), "status": "complete", "word_count": 0}
    update_book(b["id"], data)
    return {"ok": ok, "pages": len(pages), **res}


async def design_cover(catalog: str) -> dict:
    """The front cover, with the universe's character plate as the identity
    reference, installed the house way (cover-art, ebook, preview files)."""
    from ..cover.front_cover import _generate_one, _install_cover
    book = get_book_by_catalog(catalog); d = book["data"]; wb = d.get("workbook") or {}
    slug = wb.get("universe") or ""; uni = UNIVERSE_CAST.get(slug, {})
    plates = [png for png in (_plate_png(slug, rel) for rel in (uni.get("plates") or {}).values()) if png] if uni else []
    author = d.get("author_name") or ""
    brief = (f"Create a paperback front book cover for a children's activity book called: {book['title']}\n"
             f"What the book is about (for the ARTWORK only — do not write any of this on the cover): {wb.get('pitch') or d.get('description') or ''}\n"
             + (f"The characters: {uni.get('look')} {uni.get('cast', '')} The attached pictures are the references, in this order: "
                "Princess, Glitter, Pip, Moss. Draw them in a friendly full-colour cartoon style, happy and inviting.\n" if uni else "")
             + f'The ONLY text anywhere on the cover is the title "{book["title"]}"' + (f' and the author name "{author}"' if author else "") + ".\n"
             "Output the FLAT COVER ARTWORK ITSELF, one flat rectangle filled edge to edge; not a mockup, no spine, no shadow.\n"
             "Bright, clean, child-safe; big readable title; it must look like a bestselling activity book on Amazon.\n"
             + (f"Author: {author}\n" if author else "") + "Book size: 8.5″ × 11″")
    async with httpx.AsyncClient() as client:
        png = await _generate_one(client, brief, reference_png=plates or None, gen_size="1024x1536")
    return _install_cover(catalog, png, brief)
