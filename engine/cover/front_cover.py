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
    "historical_romance": "historical romance cover: rich period palette, sweeping "
        "gown or landscape, ornate serif title with flourish",
    "self_help": "modern self-help cover: clean bold typography as the hero on a "
        "confident flat or gradient background, one striking graphic symbol, generous "
        "white space",
    "business": "business bestseller cover: massive confident title type, minimal "
        "background, one memorable visual metaphor, two-color discipline",
    "mindfulness": "mindful/spiritual cover: serene minimal scene, soft natural "
        "palette, graceful serif, feeling of stillness and depth",
}


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


async def generate_front_cover(catalog: str, extra_direction: str = "") -> dict:
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError(f"Book {catalog} not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured in the engine .env")

    brief = await build_cover_brief(book, ms)
    if extra_direction.strip():
        brief = f"{brief}\n\nAdditional direction from the publisher: {extra_direction.strip()}"

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

    brief = await build_cover_brief(book, ms)
    if extra_direction.strip():
        brief = f"{brief} Additional direction from the publisher: {extra_direction.strip()}"
    if on_progress:
        on_progress(0.15, f"Painting {count} covers in parallel")

    count = max(2, min(6, count))
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_generate_one(client, brief) for _ in range(count)],
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
                         "preview": f"cover-variant-{i + 1}-preview.png"})
    if not variants:
        first_err = next((r for r in results if isinstance(r, Exception)), None)
        raise RuntimeError(f"All variants failed: {first_err}")

    data = dict(get_book_by_catalog(catalog)["data"])
    cover = data.get("cover") or {}
    cover["variants"] = variants
    cover["art_brief"] = brief
    data["cover"] = cover
    update_book(book["id"], data)
    return {"variants": variants, "brief": brief}


def select_cover_variant(catalog: str, index: int) -> dict:
    """Promote a generated variant to the book's official front cover."""
    vpath = Path(OUTPUT_DIR) / catalog / f"cover-variant-{index}.png"
    if not vpath.exists():
        raise ValueError(f"Variant {index} not found")
    book = get_book_by_catalog(catalog)
    brief = ((book["data"].get("cover") or {}).get("art_brief")) or ""
    result = _install_cover(catalog, vpath.read_bytes(), brief)
    data = dict(get_book_by_catalog(catalog)["data"])
    data["cover"]["selected_variant"] = index
    update_book(book["id"], data)
    return result
