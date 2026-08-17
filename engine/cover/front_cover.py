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

    prompt = (
        f"Design the front cover art direction for this {preset.get('label', 'book')}:\n"
        f"TITLE: {book['title']}\nAUTHOR: {author}\nTAGLINE: {ms.tagline or '(none)'}\n"
        f"{bible}\nBLURB: {ms.blurb[:600]}\n\n"
        f"Genre cover convention: {style}.\n\n"
        "Write ONE image-generation prompt (150-220 words) for a professional book "
        "cover in portrait 2:3. It must:\n"
        "- describe the scene, composition, lighting and palette concretely\n"
        "- specify the title text rendered LARGE as the dominant element, with a "
        "treatment that interacts with the artwork (texture, weathering, or overlap)\n"
        "- specify the author name in smaller capitals near the bottom\n"
        "- include the tagline only if one was given\n"
        "- state the exact strings to spell, character for character\n"
        "- forbid any other text, logos or watermarks\n"
        'Return JSON only: {"image_prompt": "..."}'
    )
    raw = await complete(
        "You are an award-winning book cover art director for commercial bestsellers. "
        "You brief image models with precise, vivid, production-ready prompts.",
        prompt, max_tokens=1500)
    return str(extract_json(raw)["image_prompt"])


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

    out_dir = Path(OUTPUT_DIR) / catalog
    out_dir.mkdir(parents=True, exist_ok=True)
    art_path = out_dir / "cover-art.png"
    art_path.write_bytes(raw_png)

    # ebook cover (Amazon: 1600x2560 recommended) + shelf preview
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(raw_png)).convert("RGB")
    ebook = img.resize((1600, 2560), Image.LANCZOS)
    ebook_path = out_dir / "ebook-cover.jpg"
    ebook.save(ebook_path, quality=92, optimize=True)
    preview = img.resize((800, 1280), Image.LANCZOS)
    preview_path = out_dir / "cover-front.png"
    preview.save(preview_path, optimize=True)

    data = dict(book["data"])
    cover = data.get("cover") or {}
    cover.update({
        "mode": "ai",
        "status": "draft",
        "artwork_path": str(art_path),
        "ebook_cover_path": str(ebook_path),
        "cover_front_png": str(preview_path),
        "art_brief": brief,
    })
    data["cover"] = cover
    update_book(book["id"], data)
    return {"artwork": str(art_path), "ebook_cover": str(ebook_path),
            "preview": str(preview_path), "brief": brief}
