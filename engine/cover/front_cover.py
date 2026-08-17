"""
Automatic front-cover generation.

Claude turns the book's bible into professional cover art direction — scene,
composition, palette, and typography — including the EXACT title, author name,
and tagline to render into the artwork (modern image models set display type
well, and baked-in type can interact with the art in ways an overlay cannot).

Output files per book (output/<catalog>/):
  cover-art.png       raw generation (1024x1536)
  ebook-cover.jpg     1600x2560 upscale — meets Amazon's ebook cover spec
  cover-front.png     800px preview used by the Bookshelf and Front Office

Print note: 1536px tall is ebook-grade. The print wrap still goes through the
designer package; this artwork doubles as the designer's reference.
"""

import base64
import json
from pathlib import Path

import httpx

from ..config import OPENAI_API_KEY, OUTPUT_DIR
from ..database import get_book_by_catalog, update_book
from ..prose.models import GENRE_PRESETS, Manuscript
from ..writing.client import complete, extract_json

IMAGE_MODEL = "gpt-image-1"
IMAGE_SIZE = "1024x1536"

GENRE_COVER_STYLE = {
    "action_thriller": "high-contrast cinematic action-thriller cover: bold distressed "
        "condensed sans-serif title, dramatic landscape or urban scene, cold palette "
        "with one hot accent color, small human figure against vast danger",
    "legal_thriller": "sleek legal-thriller cover: strong serif or slab title, "
        "courthouse/city symbolism, desaturated blues and steel greys, ominous "
        "geometric composition",
    "conspiracy_thriller": "conspiracy-thriller cover: monumental typography over "
        "historic architecture or symbols, gold and deep shadow palette, hidden-detail "
        "composition that rewards a second look",
    "romance": "contemporary romance cover: warm inviting palette, elegant serif or "
        "script title, evocative couple or symbolic scene, soft light",
    "historical_romance": "historical romance cover, the smart-collectible register: "
        "heroine seen from behind or in profile in period dress (never a front-facing "
        "photoreal face), holding a story-object that carries the plot; layered depth — "
        "figure foreground, gardens midground, estate and light in the distance; soft "
        "painterly florals framing the composition and a delicate ornamental border as "
        "the series' collectible device; title mixing refined script with elegant serif, "
        "small tagline top, discreet category line, author in clean small caps",
    "self_help": "modern self-help cover: clean bold typography as the hero on a "
        "confident flat or gradient background, one striking graphic symbol, generous "
        "white space",
    "business": "business bestseller cover: massive confident title type, minimal "
        "background, one memorable visual metaphor, two-color discipline",
    "mindfulness": "mindful/spiritual cover: serene minimal scene, soft natural "
        "palette, graceful serif, feeling of stillness and depth",
}


def _merged_direction(book: dict, extra_direction: str) -> str:
    """Publisher direction = acquisitions research direction + ad-hoc extra."""
    stored = (book["data"].get("cover_direction") or "").strip()
    extra = extra_direction.strip()
    return " ".join(p for p in (stored, extra) if p)


def _ensure_real_title(book: dict) -> str:
    """The title is baked into the art — refuse to paint a placeholder."""
    t = (book["title"] or "").strip()
    if not t or t.lower().startswith("untitled") or len(t) > 120 or "\n" in t:
        raise ValueError(
            "This book doesn't have its real title yet — the title is painted "
            "into the artwork, so covers would say the placeholder. Title the "
            "book first (drafting sets it at the bible stage), then generate "
            "covers.")
    return t


async def build_cover_brief(book: dict, ms: Manuscript) -> str:
    """Claude writes the image-generation prompt from the book's own bible."""
    preset = GENRE_PRESETS.get(ms.genre_preset, {})
    style = GENRE_COVER_STYLE.get(ms.genre_preset, "commercial bestseller cover")
    author = (book["data"].get("author_name") or "").strip()
    bible = ""
    if ms.story_bible:
        b = ms.story_bible
        bible = f"Logline: {b.logline}\nSetting: {b.setting} ({b.time_period})\nTone: {b.tone}"
    elif ms.concept_bible:
        c = ms.concept_bible
        bible = f"Thesis: {c.thesis}\nFramework: {c.framework_name}\nAudience: {c.audience}"
    else:
        # pre-bible: the commissioning brief is the premise source
        bible = f"Concept: {ms.idea[:900]}"

    # Premise-first briefing (Lars-validated): tell the model the story and the
    # names, then let it do its own cover-design thinking. Over-specified art
    # direction produces flatter covers than a vivid premise does.
    prompt = (
        f"Summarize this book's premise in 2-4 vivid sentences for a cover "
        f"designer — concrete stakes, setting, and hook, no spoilers past the "
        f"setup:\n{bible}\nBLURB: {ms.blurb[:600]}\n"
        'Return JSON only: {"premise": "..."}'
    )
    raw = await complete(
        "You distill books into vivid, concrete premises.", prompt, max_tokens=800)
    premise = str(extract_json(raw)["premise"])

    label = preset.get("label", "book").lower()
    trim = (book["data"].get("format") or {}).get("trim_size") \
        or book["data"].get("trim_size") or "5.5x8.5"
    trim_label = trim.replace("x", '\" × ') + '\"'
    parts = [
        f"I need a book cover for a {trim_label} paperback {label} called {book['title']}.",
        premise,
        f"The author is called {author}." if author else "",
        f'If a tagline fits the design, use exactly: "{ms.tagline}"' if ms.tagline else "",
        "Portrait book cover. No text other than the title"
        + (", author name" if author else "")
        + (" and tagline." if ms.tagline else "."),
    ]
    return " ".join(p for p in parts if p)


async def build_variant_briefs(book: dict, ms: Manuscript, count: int,
                               direction: str) -> list:
    """Claude art-directs N GENUINELY DIFFERENT covers for one book.

    One call: check what the genre's current bestselling covers look like
    (live web search), then return N distinct painter briefs — different
    compositions and moments, not the same image four times. Each brief is a
    complete prompt with the exact title/author/tagline baked in.
    """
    preset = GENRE_PRESETS.get(ms.genre_preset, {})
    style = GENRE_COVER_STYLE.get(ms.genre_preset, "commercial bestseller cover")
    author = (book["data"].get("author_name") or "").strip()
    title = _ensure_real_title(book)
    bible = ""
    if ms.story_bible:
        b = ms.story_bible
        bible = (f"Logline: {b.logline}\nSetting: {b.setting} ({b.time_period})\n"
                 f"Tone: {b.tone}")
    elif ms.concept_bible:
        c = ms.concept_bible
        bible = (f"Thesis: {c.thesis}\nFramework: {c.framework_name}\n"
                 f"Audience: {c.audience}")
    else:
        bible = f"Concept: {ms.idea[:900]}"
    trim = (book["data"].get("format") or {}).get("trim_size") \
        or book["data"].get("trim_size") or "5.5x8.5"
    trim_label = trim.replace("x", '\" × ') + '\"'

    prompt = (
        f"You are art-directing the cover of \"{title}\""
        + (f" by {author}" if author else "") + f", a {trim_label} paperback "
        f"{preset.get('label', 'book').lower()}.\n\nTHE BOOK:\n{bible}\n"
        + (f"BLURB: {ms.blurb[:500]}\n" if ms.blurb else "")
        + (f"TAGLINE (use exactly if it fits): \"{ms.tagline}\"\n" if ms.tagline else "")
        + (f"\nPUBLISHER'S DIRECTION (binding): {direction}\n" if direction else "")
        + f"\nGenre shelf convention: {style}.\n\n"
        "FIRST, glance at what the current bestselling covers in this exact "
        "genre look like on Amazon right now, so the shelf register is "
        "current.\n\n"
        f"THEN write {count} DISTINCT image-generation prompts — {count} "
        "different covers a top publisher would genuinely consider, not one "
        "idea repeated (e.g. an intimate character moment; a scene where the "
        "setting is the star; a symbolic/object composition; a type-led "
        "design).\n\n"
        "HOUSE RULE — the publisher's proven brief shape (do not exceed it): "
        "the essentials, ONE famous comp anchor, and at most one sentence of "
        "visual angle to make this variant distinct. The comp anchor does "
        "the heavy lifting — name one famous title or universe every shelf "
        "reader recognizes (the way 'a historical romance like Pride & "
        "Prejudice' hands the model an entire visual language); pick the "
        "strongest comp for THIS book. "
        "No typography direction, no palette lists, no constraint bullets. "
        "The image model is the designer; get out of its way.\n"
        "Each prompt is self-contained (the image model sees only that "
        "paragraph), names it a portrait book cover in the "
        f"{trim_label} format, and carries the exact title "
        f"\"{title}\"" + (f", the author name \"{author}\"" if author else "")
        + (f", and the tagline \"{ms.tagline}\"" if ms.tagline else "")
        + " as text in the artwork.\n\n"
        'Return JSON only: {"briefs": [{"concept": "2-4 word label", '
        '"prompt": "the paragraph"}]}'
    )
    raw = await complete(
        "You are a celebrated book-cover art director. Your covers win the "
        "shelf: instantly on-genre, but composed and lit like no one else's. "
        "You check the live market before you direct.",
        prompt, max_tokens=6000, web_search=3)
    briefs = extract_json(raw).get("briefs") or []
    briefs = [b for b in briefs if b.get("prompt")][:count]
    if not briefs:
        raise RuntimeError("Art direction returned no usable briefs")
    # fill to count by reusing the strongest (first) concepts
    while len(briefs) < count:
        briefs.append(briefs[len(briefs) % max(1, len(briefs))])
    return briefs


async def generate_front_cover(catalog: str, extra_direction: str = "") -> dict:
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError(f"Book {catalog} not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured in the engine .env")

    _ensure_real_title(book)
    brief = await build_cover_brief(book, ms)
    direction = _merged_direction(book, extra_direction)
    if direction:
        brief = f"{brief}\n\nAdditional direction from the publisher: {direction}"

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": IMAGE_MODEL, "prompt": brief, "size": IMAGE_SIZE,
                  "quality": "high", "n": 1},
            timeout=300,
        )
    if r.status_code != 200:
        raise RuntimeError(f"Image generation failed ({r.status_code}): {r.text[:300]}")
    b64 = r.json()["data"][0]["b64_json"]
    raw_png = base64.b64decode(b64)

    return _install_cover(catalog, raw_png, brief)


def _install_cover(catalog: str, raw_png: bytes, brief: str = "",
                   mode: str = "ai") -> dict:
    """Write cover-art/ebook/preview files and update the book record."""
    book = get_book_by_catalog(catalog)
    out_dir = Path(OUTPUT_DIR) / catalog
    out_dir.mkdir(parents=True, exist_ok=True)
    art_path = out_dir / "cover-art.png"
    art_path.write_bytes(raw_png)

    from PIL import Image
    import io

    def crop_to_ratio(im, target_w_over_h):
        w, h = im.size
        cur = w / h
        if abs(cur - target_w_over_h) < 0.005:
            return im
        if cur > target_w_over_h:   # too wide: trim sides
            new_w = int(h * target_w_over_h)
            x = (w - new_w) // 2
            return im.crop((x, 0, x + new_w, h))
        new_h = int(w / target_w_over_h)  # too tall: trim top/bottom evenly
        y = (h - new_h) // 2
        return im.crop((0, y, w, y + new_h))

    trim = (data_trim := (get_book_by_catalog(catalog)["data"])) and (
        (data_trim.get("format") or {}).get("trim_size")
        or data_trim.get("trim_size") or "5.5x8.5")
    try:
        tw, th = (float(x) for x in trim.split("x"))
    except ValueError:
        tw, th = 5.5, 8.5

    img = Image.open(io.BytesIO(raw_png)).convert("RGB")
    # ebook cover: Amazon's 1600x2560 (0.625) — crop, never stretch
    ebook = crop_to_ratio(img, 1600 / 2560).resize((1600, 2560), Image.LANCZOS)
    ebook_path = out_dir / "ebook-cover.jpg"
    ebook.save(ebook_path, quality=92, optimize=True)
    # audiobook cover: square 3000x3000 (Spotify/Google/Kobo/aggregator spec)
    side = min(img.size)
    sq = crop_to_ratio(img, 1.0)
    audio_size = min(3000, side * 2)  # upscale cap: 2x source
    sq.resize((audio_size, audio_size), Image.LANCZOS).save(
        out_dir / "audiobook-cover.jpg", quality=92, optimize=True)

    # preview / print reference: the book's actual trim proportions
    pv = crop_to_ratio(img, tw / th)
    pw = 800
    preview = pv.resize((pw, int(pw * th / tw)), Image.LANCZOS)
    preview_path = out_dir / "cover-front.png"
    preview.save(preview_path, optimize=True)

    data = dict(book["data"])
    cover = data.get("cover") or {}
    cover.update({
        "mode": mode,
        "status": "draft",
        "artwork_path": str(art_path),
        "ebook_cover_path": str(ebook_path),
        "cover_front_png": str(preview_path),
    })
    if brief:
        cover["art_brief"] = brief
    data["cover"] = cover
    update_book(book["id"], data)
    return {"artwork": str(art_path), "ebook_cover": str(ebook_path),
            "preview": str(preview_path), "brief": brief}


async def _generate_one(client: httpx.AsyncClient, brief: str) -> bytes:
    r = await client.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={"model": IMAGE_MODEL, "prompt": brief, "size": IMAGE_SIZE,
              "quality": "high", "n": 1},
        timeout=300,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Image generation failed ({r.status_code}): {r.text[:200]}")
    return base64.b64decode(r.json()["data"][0]["b64_json"])


async def generate_cover_variants(catalog: str, count: int = 4,
                                  extra_direction: str = "",
                                  on_progress=None) -> dict:
    """Generate N cover alternatives in parallel; user picks one to install."""
    import asyncio

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError(f"Book {catalog} not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured in the engine .env")
    _ensure_real_title(book)

    count = max(2, min(6, count))
    direction = _merged_direction(book, extra_direction)
    if on_progress:
        on_progress(0.1, "Art-directing against the live market")
    briefs = await build_variant_briefs(book, ms, count, direction)
    if on_progress:
        on_progress(0.3, f"Painting {len(briefs)} distinct covers in parallel")

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_generate_one(client, b["prompt"]) for b in briefs],
            return_exceptions=True)

    out_dir = Path(OUTPUT_DIR) / catalog
    out_dir.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    import io
    variants = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            continue
        vpath = out_dir / f"cover-variant-{i + 1}.png"
        vpath.write_bytes(res)
        img = Image.open(io.BytesIO(res)).convert("RGB")
        img.resize((400, 640), Image.LANCZOS).save(
            out_dir / f"cover-variant-{i + 1}-preview.png", optimize=True)
        variants.append({"index": i + 1,
                         "preview": f"cover-variant-{i + 1}-preview.png",
                         "concept": briefs[i].get("concept", ""),
                         "brief": briefs[i]["prompt"]})
    if not variants:
        first_err = next((r for r in results if isinstance(r, Exception)), None)
        raise RuntimeError(f"All variants failed: {first_err}")

    data = dict(get_book_by_catalog(catalog)["data"])
    cover = data.get("cover") or {}
    cover["variants"] = variants
    data["cover"] = cover
    update_book(book["id"], data)
    return {"variants": variants}


def select_cover_variant(catalog: str, index: int) -> dict:
    """Promote a generated variant to the book's official front cover."""
    vpath = Path(OUTPUT_DIR) / catalog / f"cover-variant-{index}.png"
    if not vpath.exists():
        raise ValueError(f"Variant {index} not found")
    book = get_book_by_catalog(catalog)
    stored = (book["data"].get("cover") or {}).get("variants") or []
    brief = next((v.get("brief", "") for v in stored if v.get("index") == index),
                 ((book["data"].get("cover") or {}).get("art_brief")) or "")
    result = _install_cover(catalog, vpath.read_bytes(), brief)
    data = dict(get_book_by_catalog(catalog)["data"])
    data["cover"]["selected_variant"] = index
    update_book(book["id"], data)
    return result
