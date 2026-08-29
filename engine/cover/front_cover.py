"""
Automatic front-cover generation.

House doctrine: SCRPT gives NO art direction — the image engine is the
designer. Every cover request is a fact sheet (title, genre, a 3-5 sentence
summary, subtitle, author, series membership) and nothing else. Series
consistency comes from a persistent design conversation that sees Book 1's
cover and every chosen cover since.

Output files per book (output/<catalog>/):
  cover-art.png       raw generation (1024x1536)
  ebook-cover.jpg     1600x2560 upscale — meets Amazon's ebook cover spec
  cover-front.png     800px preview used by the Bookshelf and Front Office

Print note: 1536px tall is ebook-grade. The print wrap still goes through the
designer package; this artwork doubles as the designer's reference.
"""

import asyncio
import base64
import json
from pathlib import Path

import httpx

from ..config import OPENAI_API_KEY, OUTPUT_DIR
from ..database import get_book_by_catalog, list_books, update_book
from ..prose.models import GENRE_PRESETS, Manuscript
from ..writing.client import complete, extract_json

IMAGE_MODEL_FALLBACK = "gpt-image-1"
IMAGE_SIZE = "1024x1536"

# The engine offers three canvases. Generating a square picture book on the
# tall one and cropping to fit throws a third of the art away — and the
# composition was designed for the wrong frame, so titles and characters end
# up clipped. Draw on the canvas closest to the book's real trim instead.
GEN_SIZES = {"1024x1024": 1.0, "1536x1024": 1.5, "1024x1536": 1024 / 1536}


def size_for_trim(trim: str) -> str:
    try:
        tw, th = (float(x) for x in str(trim).lower().split("x"))
        want = tw / th
    except Exception:
        return IMAGE_SIZE
    return min(GEN_SIZES, key=lambda k: abs(GEN_SIZES[k] - want))


def trim_of(book: dict) -> str:
    d = book.get("data") or {}
    return ((d.get("format") or {}).get("trim_size")
            or d.get("trim_size") or "5.5x8.5")
_best_image_model_cache: dict = {}


async def _best_image_model(client: httpx.AsyncClient) -> str:
    """Always create with OpenAI's newest, best image engine: ask the live
    model list and pick the highest gpt-image version (never a -mini). Auto-
    upgrades the day a better engine ships; falls back to gpt-image-1."""
    if _best_image_model_cache.get("id"):
        return _best_image_model_cache["id"]
    best = IMAGE_MODEL_FALLBACK
    try:
        r = await client.get("https://api.openai.com/v1/models",
                             headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                             timeout=20)
        if r.status_code == 200:
            ids = [m.get("id", "") for m in r.json().get("data", [])]
            best = pick_image_model(ids) or best
    except httpx.HTTPError:
        pass
    _best_image_model_cache["id"] = best
    return best


def pick_image_model(ids: list) -> str:
    """The newest full-size gpt-image engine.

    Compared on parsed VERSION NUMBER, not as a string — a plain sort would
    rank "gpt-image-10" below "gpt-image-2". Where a version exists both as a
    rolling alias and a dated snapshot, the alias wins: it keeps picking up
    improvements the day OpenAI ships them, which is the whole point.
    """
    import re as _re
    best_id, best_key = "", None
    for i in ids:
        m = _re.match(r"^gpt-image-(\d+)(?:\.(\d+))?(-\d{4}-\d{2}-\d{2})?$", i or "")
        if not m or "mini" in (i or ""):
            continue
        major, minor, dated = int(m.group(1)), int(m.group(2) or 0), bool(m.group(3))
        key = (major, minor, 0 if dated else 1)      # alias beats snapshot
        if best_key is None or key > best_key:
            best_id, best_key = i, key
    return best_id

def _merged_direction(book: dict, extra_direction: str) -> str:
    """Only direction the publisher types for THIS run reaches the engine.
    The acquisitions-research `cover_direction` is deliberately NOT used:
    it reads as an art brief (palettes, motifs, "painterly") and produced
    identical AI-cliche covers. House rule: the image engine is the designer;
    we hand it facts, never direction."""
    return extra_direction.strip()


def _publisher_cover_png(book: dict):
    """The publisher's own approved cover, if they supplied one — the
    standard every alternative must meet."""
    cov = book["data"].get("cover") or {}
    if (cov.get("art_brief") or "").lower().startswith("publisher-supplied"):
        from ..config import OUTPUT_DIR
        for name in (cov.get("cover_front_png"), "cover-front.png", "cover-art.png"):
            if not name:
                continue
            path = Path(name) if str(name).startswith("/") else OUTPUT_DIR / book["catalog_number"] / name
            if path.exists():
                return path.read_bytes()
    return None


def _series_line(book: dict) -> str:
    """The small line publishers set on an installment's cover,
    e.g. 'The Larkspur Season · Book 2'."""
    series = book["data"].get("series") or {}
    if series.get("series_id") and series.get("series_title") and series.get("book_number"):
        return f"{series['series_title']} · Book {series['book_number']}"
    return ""


RESPONSES_MODELS = ["gpt-5", "gpt-4.1", "gpt-4o"]  # first available wins


async def _thread_generate(client: httpx.AsyncClient, prompt: str,
                           previous_response_id: str = None,
                           seed_png: bytes = None,
                           want_image: bool = True,
                           gen_size: str = IMAGE_SIZE):
    """One turn in a persistent cover-design conversation (the API's version
    of designing every series cover in the same ChatGPT chat): the model sees
    every earlier turn — Book 1's cover, each chosen installment — and the
    image tool renders in that context. Returns (png_or_None, response_id)."""
    content = []
    if seed_png:
        content.append({"type": "input_image",
                        "image_url": "data:image/png;base64,"
                        + base64.b64encode(seed_png).decode()})
    content.append({"type": "input_text", "text": prompt})
    body = {
        "input": [{"role": "user", "content": content}],
    }
    if previous_response_id:
        body["previous_response_id"] = previous_response_id
    if want_image:
        tool = {"type": "image_generation", "size": gen_size, "quality": "high"}
        best = await _best_image_model(client)
        if best != IMAGE_MODEL_FALLBACK:
            tool["model"] = best  # newer engine available: request it
        body["tools"] = [tool]
        body["tool_choice"] = "required"
    last_err = None
    for model in RESPONSES_MODELS:
        body["model"] = model
        for attempt in range(2):
            try:
                r = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json=body, timeout=300)
            except httpx.HTTPError as e:
                last_err = e
                await asyncio.sleep(3)
                continue
            if r.status_code == 200:
                data = r.json()
                png = None
                for item in data.get("output", []):
                    if item.get("type") == "image_generation_call" and item.get("result"):
                        png = base64.b64decode(item["result"])
                if want_image and png is None:
                    last_err = RuntimeError("no image in thread response")
                    continue
                return png, data.get("id")
            last_err = RuntimeError(f"thread turn failed ({r.status_code}): {r.text[:200]}")
            if (r.status_code == 400 and body.get("tools")
                    and "model" in r.text.lower() and "model" in body["tools"][0]):
                body["tools"][0].pop("model", None)  # tool rejected the pin
                continue
            if r.status_code in (400, 404) and "model" in r.text.lower():
                break  # try the next text model in the list
            if r.status_code < 500:
                break
            await asyncio.sleep(3)
    raise RuntimeError(f"series thread generation failed: {last_err}")


async def _ensure_series_thread(client: httpx.AsyncClient, book: dict) -> str:
    """Open (or resume) the series' design conversation, seeded with Book 1's
    final cover. The thread id is stored on every member and advanced each
    time a cover is chosen, so the conversation accumulates the series."""
    series = book["data"].get("series") or {}
    if not series.get("series_id") or (series.get("book_number") or 1) <= 1:
        return ""
    if series.get("cover_thread_id"):
        return series["cover_thread_id"]
    reference, ref_series = _series_reference_cover(book)
    if not reference:
        return ""
    _, rid = await _thread_generate(
        client,
        f'This image is the final, approved cover of Book 1 of the series '
        f'"{ref_series}". We will design the covers of the later installments '
        "here in this same conversation so the series look stays consistent - "
        "same art style, fonts and text placement, new scene and new text per "
        "book. Reply OK.",
        seed_png=reference, want_image=False)
    if rid:
        _store_series_thread(book, rid)
    return rid or ""


def _store_series_thread(book: dict, response_id: str):
    series = book["data"].get("series") or {}
    for member in list_books(per_page=300)["books"]:
        s = member["data"].get("series") or {}
        if s.get("series_id") == series.get("series_id"):
            d = dict(get_book_by_catalog(member["catalog_number"])["data"])
            ds = dict(d.get("series") or {})
            ds["cover_thread_id"] = response_id
            d["series"] = ds
            update_book(member["id"], d, sections=["series"])


def _series_reference_cover(book: dict):
    """For Book 2+ of a series: Book 1's cover art (bytes) as the design
    reference, so every installment keeps the same style, fonts and text
    placement. Returns (png_bytes, series_title) or (None, "")."""
    series = book["data"].get("series") or {}
    if not series.get("series_id") or (series.get("book_number") or 1) <= 1:
        return None, ""
    for member in list_books(per_page=300)["books"]:
        ms = member["data"].get("series") or {}
        if (ms.get("series_id") == series["series_id"]
                and (ms.get("book_number") or 0) == 1):
            art = Path(OUTPUT_DIR) / member["catalog_number"] / "cover-art.png"
            if art.exists():
                return art.read_bytes(), series.get("series_title", "")
    return None, ""


def _ensure_real_title(book: dict) -> str:
    """The title is baked into the art — refuse to render a placeholder."""
    t = (book["title"] or "").strip()
    if not t or t.lower().startswith("untitled") or len(t) > 120 or "\n" in t:
        raise ValueError(
            "This book doesn't have its real title yet — the title is rendered "
            "into the artwork, so covers would say the placeholder. Title the "
            "book first (drafting sets it at the bible stage), then generate "
            "covers.")
    return t


async def _cover_summary(book: dict, ms: Manuscript) -> str:
    """The 3-5 sentence 'about the book' for the cover fact sheet, cached
    on the cover record so the facts stay stable across regenerations."""
    cover = book["data"].get("cover") or {}
    if cover.get("summary"):
        return cover["summary"]
    if ms.story_bible:
        b = ms.story_bible
        src = f"Logline: {b.logline}\nSetting: {b.setting} ({b.time_period})\nTone: {b.tone}"
    elif ms.concept_bible:
        c = ms.concept_bible
        src = f"Thesis: {c.thesis}\nFramework: {c.framework_name}\nAudience: {c.audience}"
    else:
        src = f"Concept: {ms.idea[:900]}"
    raw = await complete(
        "You distill books into vivid, concrete summaries.",
        src + "\n" + (f"BLURB: {ms.blurb[:600]}\n" if ms.blurb else "")
        + "Give the cover designer the book's hook in ONE or TWO short "
        "sentences - the shape of \"It's an action filled thriller based in "
        "the political rings of Washington.\" Setting and stakes, nothing "
        'more. Return JSON only: {"summary": "..."}',
        max_tokens=800, mechanical=True)
    summary = str(extract_json(raw)["summary"]).strip()
    fresh = get_book_by_catalog(book["catalog_number"])
    data = dict(fresh["data"])
    cov = dict(data.get("cover") or {})
    cov["summary"] = summary
    data["cover"] = cov
    update_book(fresh["id"], data, sections=["cover"])
    return summary


def _fact_brief(book: dict, ms: Manuscript, summary: str, notes: str = "") -> str:
    """The publisher's proven prompt shape (A/B validated 2026-08-18):
    'front' cover (never a 3D mockup), a one-two sentence hook, author, book
    size — short. NO art direction: the image engine is the designer."""
    preset = GENRE_PRESETS.get(ms.genre_preset, {})
    label = preset.get("label", "book")
    series = book["data"].get("series") or {}
    trim = (book["data"].get("format") or {}).get("trim_size") \
        or book["data"].get("trim_size") or "5.5x8.5"
    author = (book["data"].get("author_name") or "").strip()
    # The summary was passed as a bare line and the engine did the obvious
    # thing: it SET IT ON THE COVER. A front cover carries a title, an author,
    # and at most a short subtitle — the blurb belongs on the back.
    lines = [
        f"Create a paperback front book cover for a {label.lower()} called: {book['title']}",
        f"What the story is about (for the ARTWORK only — do not write any of "
        f"this on the cover): {summary.strip()}",
    ]
    only = f'the title "{book["title"]}"'
    if author:
        only += f' and the author name "{author}"'
    if ms.tagline:
        only += f' and the short subtitle "{ms.tagline}"'
    lines.append(f"The ONLY text anywhere on the cover is {only}. "
                 "No blurb, no description, no review quotes, no sentences.")
    # the docstring has always claimed 'never a 3D mockup' but never said so
    # to the model, and it duly returned a photo of a book standing on a desk
    lines.append("Output the FLAT COVER ARTWORK ITSELF — one flat rectangle "
                 "filled edge to edge, exactly as it would be printed. Not a "
                 "photograph of a book, not a 3D mockup or render, no book "
                 "thickness or edges, no spine, no visible pages, no drop "
                 "shadow, no desk or table, no hands, no background around it.")
    if author:
        lines.append(f"Author: {author}")
    lines.append("Book size: " + trim.replace("x", "″ × ") + "″")
    if ms.tagline:
        lines.append(f'Subtitle: "{ms.tagline}"')
    if series.get("series_id") and series.get("series_title"):
        lines.append(f'Series: {series["series_title"]} — Book {series.get("book_number")}')
    if notes:
        lines.append(f"Notes: {notes}")
    return "\n".join(lines)


async def generate_front_cover(catalog: str, extra_direction: str = "") -> dict:
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError(f"Book {catalog} not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured in the engine .env")

    _ensure_real_title(book)
    summary = await _cover_summary(book, ms)
    brief = _fact_brief(book, ms, summary,
                        notes=_merged_direction(book, extra_direction))

    gen_size = size_for_trim(trim_of(book))
    async with httpx.AsyncClient() as client:
        thread_id = await _ensure_series_thread(client, book)
        if thread_id:
            try:
                png, rid = await _thread_generate(
                    client, "Same series look as the covers above.\n" + brief,
                    gen_size=gen_size,
                    previous_response_id=thread_id)
                _store_series_thread(book, rid)
                return _install_cover(catalog, png, brief)
            except Exception:
                pass  # fall back to a plain generation
        raw_png = await _generate_one(client, brief, gen_size=gen_size)

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

    # `book` was read before minutes of image work — re-read so the cover
    # section merges onto the current record, and touch only that section
    fresh = get_book_by_catalog(catalog)
    data = dict(fresh["data"])
    cover = dict(data.get("cover") or {})
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
    update_book(fresh["id"], data, sections=["cover"])
    return {"artwork": str(art_path), "ebook_cover": str(ebook_path),
            "preview": str(preview_path), "brief": brief}


async def _generate_one(client: httpx.AsyncClient, brief: str,
                        reference_png: bytes = None,
                        gen_size: str = IMAGE_SIZE) -> bytes:
    import asyncio
    last_err = None
    for attempt in range(3):   # DNS blips / resets must not kill a cover run
        try:
            if reference_png:
                # series installment: Book 1's cover rides along as the design
                # reference (image + prompt via the edits endpoint)
                r = await client.post(
                    "https://api.openai.com/v1/images/edits",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files={"image[]": ("book1-cover.png", reference_png, "image/png")},
                    data={"model": await _best_image_model(client),
                          "prompt": brief, "size": gen_size,
                          "quality": "high", "n": "1"},
                    timeout=300,
                )
            else:
                r = await client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json={"model": await _best_image_model(client),
                          "prompt": brief, "size": gen_size,
                          "quality": "high", "n": 1},
                    timeout=300,
                )
        except httpx.HTTPError as e:
            last_err = e
            await asyncio.sleep(3 * (attempt + 1))
            continue
        if r.status_code >= 500:
            last_err = RuntimeError(f"Image generation failed ({r.status_code}): {r.text[:200]}")
            await asyncio.sleep(3 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise RuntimeError(f"Image generation failed ({r.status_code}): {r.text[:200]}")
        return base64.b64decode(r.json()["data"][0]["b64_json"])
    raise RuntimeError(f"Image generation failed after 3 attempts: {last_err}")


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
    if on_progress:
        on_progress(0.1, "Preparing the fact sheet")
    summary = await _cover_summary(book, ms)
    brief = _fact_brief(book, ms, summary,
                        notes=_merged_direction(book, extra_direction))
    reference_png = _publisher_cover_png(book)
    if reference_png:
        # the publisher's own cover sets the bar: same standard, same visual
        # language, a different composition — never a drift back to cliche
        brief = ("The attached image is the approved cover for this book. "
                 "Create another front cover for the same book at the same "
                 "standard — a sibling, not a copy.\n\n" + brief)
    # the engine is the designer: every option gets the SAME facts and
    # designs freely — variety comes from the model, not from our direction
    briefs = [{"concept": f"Option {i + 1}", "prompt": brief,
               "seed_png": reference_png}
              for i in range(count)]
    if on_progress:
        on_progress(0.3, f"Creating {len(briefs)} covers")

    gen_size = size_for_trim(trim_of(book))
    async with httpx.AsyncClient() as client:
        # series installments render inside the series' design conversation
        # (Book 1's cover and every chosen cover are the model's context);
        # a variant falls back to a plain generation if its thread turn fails
        thread_id = await _ensure_series_thread(client, book)
        response_ids = [None] * len(briefs)

        async def render(i, brief_prompt, seed_png=None):
            if seed_png:
                # the publisher's cover in the conversation: the model SEES the
                # standard it must match before it designs
                try:
                    png, rid = await _thread_generate(client, brief_prompt,
                                                     seed_png=seed_png,
                                                     gen_size=gen_size)
                    response_ids[i] = rid
                    return png
                except Exception:
                    pass
            if thread_id:
                try:
                    png, rid = await _thread_generate(
                        client,
                        "Same series look as the covers above.\n" + brief_prompt,
                        previous_response_id=thread_id)
                    response_ids[i] = rid
                    return png
                except Exception:
                    pass
            return await _generate_one(client, brief_prompt, gen_size=gen_size)

        # The bar sat at 30% until every cover was finished, which for four
        # high-quality generations is minutes of looking broken. Report each
        # one as it lands instead.
        done_n = [0]

        async def render_reporting(i, prompt, seed):
            try:
                return await render(i, prompt, seed)
            finally:
                done_n[0] += 1
                if on_progress:
                    on_progress(0.3 + 0.65 * done_n[0] / len(briefs),
                                f"Cover {done_n[0]} of {len(briefs)} ready")

        results = await asyncio.gather(
            *[render_reporting(i, b["prompt"], b.get("seed_png"))
              for i, b in enumerate(briefs)],
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
        # The preview is what the picker actually shows. Hard-coding it to
        # 400x640 squashed a square picture-book cover into a portrait, so the
        # thumbnails misrepresented the very thing being chosen. Preview at the
        # book's own trim.
        try:
            _tw, _th = (float(x) for x in trim_of(book).split("x"))
        except Exception:
            _tw, _th = 5.5, 8.5
        _pw = 400
        img.resize((_pw, max(1, int(round(_pw * _th / _tw)))), Image.LANCZOS).save(
            out_dir / f"cover-variant-{i + 1}-preview.png", optimize=True)
        variants.append({"index": i + 1,
                         "preview": f"cover-variant-{i + 1}-preview.png",
                         "concept": briefs[i].get("concept", ""),
                         "brief": briefs[i]["prompt"],
                         "response_id": response_ids[i]})
    if not variants:
        first_err = next((r for r in results if isinstance(r, Exception)), None)
        raise RuntimeError(f"All variants failed: {first_err}")

    data = dict(get_book_by_catalog(catalog)["data"])
    cover = dict(data.get("cover") or {})
    cover["variants"] = variants
    data["cover"] = cover
    update_book(book["id"], data, sections=["cover"])
    return {"variants": variants}


async def generate_series_suite(catalog: str, on_progress=None) -> dict:
    """All missing series covers in one go, in one design conversation.

    The publisher's insight: batch-creating the whole shelf row in a single
    chat gives the strongest consistency — but every book needs its title,
    tagline and summary BEFORE the batch. The suite gathers those, opens the
    series thread seeded with every already-final cover, then creates the
    missing covers oldest-first, each turn seeing all the covers before it."""
    book = get_book_by_catalog(catalog)
    series = (book["data"].get("series") or {})
    sid = series.get("series_id")
    if not sid:
        raise ValueError("This book is not part of a series")
    members = sorted(
        [m for m in list_books(per_page=300)["books"]
         if (m["data"].get("series") or {}).get("series_id") == sid],
        key=lambda m: (m["data"]["series"].get("book_number") or 0))
    if not members or (members[0]["data"].get("cover") or {}).get("cover_front_png") is None:
        raise ValueError("Book 1 needs a finished cover before the suite can run")

    todo = []
    for m in members[1:]:
        cover = m["data"].get("cover") or {}
        has_final = bool(cover.get("selected_variant")) or cover.get("mode") == "upload"
        title_ok = m["title"] and not m["title"].startswith("Untitled")
        if not has_final and title_ok:
            todo.append(m)
    if not todo:
        raise ValueError("Every book in the series already has a chosen cover "
                         "(or is still untitled)")

    async with httpx.AsyncClient() as client:
        thread_id = await _ensure_series_thread(client, members[1])
        # bring every already-chosen later cover into the conversation too
        for m in members[1:]:
            cover = m["data"].get("cover") or {}
            if bool(cover.get("selected_variant")) or cover.get("mode") == "upload":
                art = Path(OUTPUT_DIR) / m["catalog_number"] / "cover-art.png"
                if art.exists():
                    _, thread_id = await _thread_generate(
                        client,
                        f'This is the final cover of Book '
                        f'{m["data"]["series"].get("book_number")}, "{m["title"]}". '
                        "Reply OK.",
                        previous_response_id=thread_id,
                        seed_png=art.read_bytes(), want_image=False)

        done = []
        for k, m in enumerate(todo):
            ms_m = Manuscript.model_validate(m["data"].get("manuscript", {}))
            n = m["data"]["series"].get("book_number")
            if on_progress:
                on_progress(0.15 + 0.8 * k / len(todo),
                            f'Cover {k + 1} of {len(todo)}: "{m["title"]}"')
            summary = await _cover_summary(m, ms_m)
            prompt = ("Same series look as the covers above, a new scene for "
                      "this installment.\n"
                      + _fact_brief(m, ms_m, summary))
            png, rid = await _thread_generate(
                client, prompt, previous_response_id=thread_id)
            thread_id = rid  # the new cover joins the conversation
            _install_cover(m["catalog_number"], png,
                           brief=prompt, mode="ai")
            done.append({"catalog": m["catalog_number"], "title": m["title"]})

    _store_series_thread(book, thread_id)
    if on_progress:
        on_progress(1.0, "Series covers complete")
    return {"covers": done, "thread": thread_id}


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
    data["cover"] = dict(data.get("cover") or {})
    data["cover"]["selected_variant"] = index
    update_book(book["id"], data, sections=["cover"])
    # a chosen series cover becomes part of the series' design conversation:
    # advance the thread head so the next installment is designed with this
    # cover (and every one before it) in context
    rid = next((v.get("response_id") for v in stored
                if v.get("index") == index and v.get("response_id")), None)
    if rid and (book["data"].get("series") or {}).get("series_id"):
        _store_series_thread(book, rid)
    return result
