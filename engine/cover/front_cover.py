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


def standard_size_for_trim(trim: str) -> str:
    """The nearest of the engine's three fixed canvases (the fallback for an
    engine that refuses a custom size)."""
    try:
        tw, th = (float(x) for x in str(trim).lower().split("x"))
        want = tw / th
    except Exception:
        return IMAGE_SIZE
    return min(GEN_SIZES, key=lambda k: abs(GEN_SIZES[k] - want))


def size_for_trim(trim: str) -> str:
    """A canvas in the book's OWN proportions, so nothing is cropped on
    install. THE COVER FIT CONTROL (2026-09-10): every Maze Meadow redraw
    put the author name in the 14% the trim crop cuts off a 2:3 canvas —
    the model cannot see a crop it is only told about. gpt-image-2 accepts
    any size whose sides divide by 16 (tested 2026-09-10: 1040x1344 OK,
    1024x1325 refused), so the canvas is made to match the trim at about
    1.4 megapixels. The generators fall back to standard_size_for_trim when
    an engine refuses the size."""
    try:
        tw, th = (float(x) for x in str(trim).lower().split("x"))
        ratio = tw / th
    except Exception:
        return IMAGE_SIZE
    import math
    target_px = 1400_000
    w = int(round(math.sqrt(target_px * ratio) / 16)) * 16
    h = int(round((w / ratio) / 16)) * 16
    w, h = max(512, min(2048, w)), max(512, min(2048, h))
    return f"{w}x{h}"


def _is_size_rejection(status: int, text: str) -> bool:
    return status == 400 and "size" in (text or "").lower()


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


def _manuscript_of(book: dict) -> Manuscript:
    """The cover code only needs the genre preset and the tagline. A finished
    workbook writes manuscript status "complete", which the Manuscript enum
    does not know — that must not stop a cover redraw (found 2026-09-10 when
    Maze Meadow's cover was refused by the fit control and could not be
    redrawn). Validate strictly first; fall back to the fields we use."""
    raw = dict((book.get("data") or {}).get("manuscript") or {})
    try:
        return Manuscript.model_validate(raw)
    except Exception:
        raw.pop("status", None)
        try:
            return Manuscript.model_validate(raw)
        except Exception:
            return Manuscript.model_validate({k: raw[k] for k in ("genre_preset", "tagline", "kind") if k in raw})


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


RESPONSES_MODELS = ["gpt-5", "gpt-4.1", "gpt-4o"]  # the floor; the live list is asked first (see _best_text_models)

_best_text_cache: dict = {}


def pick_text_models(ids: list) -> list:
    """The newest general models first, from the live list — never a
    hardcoded ceiling (Lars, 2026-09-08: "SCRPT should not be limited by our
    old setup. AI models evolve."). Ranks gpt-6-* above gpt-5.x above gpt-5,
    skips codex/mini/nano/search/chat-latest/pro/dated variants."""
    import re as _re
    def key(i):
        m = _re.match(r"^gpt-(\d+)(?:\.(\d+))?(?:-([a-z]+))?$", i)
        if not m:
            return None
        major, minor, tag = int(m.group(1)), int(m.group(2) or 0), m.group(3) or ""
        if tag in ("mini", "nano", "codex", "search", "chat", "pro"):
            return None
        return (major, minor, 1 if tag else 0)
    ranked = sorted((k, i) for i in ids if (k := key(i)) is not None)
    return [i for _, i in reversed(ranked)][:3]


async def _best_text_models(client: httpx.AsyncClient) -> list:
    if _best_text_cache.get("ids"):
        return _best_text_cache["ids"]
    best = list(RESPONSES_MODELS)
    try:
        r = await client.get("https://api.openai.com/v1/models",
                             headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}, timeout=30)
        if r.status_code == 200:
            live = pick_text_models([m["id"] for m in r.json().get("data", [])])
            if live:
                best = live + [m for m in RESPONSES_MODELS if m not in live]
    except Exception:
        pass
    _best_text_cache["ids"] = best
    return best


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
    for model in await _best_text_models(client):
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
            if (body.get("tools") and _is_size_rejection(r.status_code, r.text)
                    and body["tools"][0].get("size") not in GEN_SIZES):
                # the image tool only knows the three fixed canvases
                body["tools"][0]["size"] = min(
                    GEN_SIZES, key=lambda k: abs(GEN_SIZES[k] - _ratio_of(body["tools"][0]["size"])))
                continue
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
        max_tokens=800, mechanical=True, model=__import__('engine.writing.client', fromlist=['utility_model']).utility_model())
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
    # THE COVER FIT CONTROL (2026-09-10): the canvas is trimmed on install;
    # the engine is told so, and told to keep every word well inside.
    from .cover_fit import safe_zone_line
    lines.append(safe_zone_line(trim))
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
    ms = _manuscript_of(book)
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured in the engine .env")

    _ensure_real_title(book)
    summary = await _cover_summary(book, ms)
    brief = _fact_brief(book, ms, summary,
                        notes=_merged_direction(book, extra_direction))

    gen_size = size_for_trim(trim_of(book))
    from .cover_fit import MAX_ATTEMPTS, check_cover_fit, retry_note

    async def _draw(client, prompt):
        thread_id = await _ensure_series_thread(client, book)
        if thread_id:
            try:
                png, rid = await _thread_generate(
                    client, "Same series look as the covers above.\n" + prompt,
                    gen_size=gen_size,
                    previous_response_id=thread_id)
                return png, rid
            except Exception:
                pass  # fall back to a plain generation
        return await _generate_one(client, prompt, gen_size=gen_size), None

    # THE COVER FIT CONTROL: draw, measure and read the trimmed picture
    # back, and only install a cover whose title sits fully inside the page
    # and is spelled right. A failed draw is redrawn with the reason; after
    # MAX_ATTEMPTS the line stops here rather than shipping a bad cover.
    prompt = brief
    fit = None
    async with httpx.AsyncClient() as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            raw_png, rid = await _draw(client, prompt)
            fit = await check_cover_fit(raw_png, book)
            if not fit["ok"]:
                from .cover_fit import fit_or_inset
                raw_png, fit = await fit_or_inset(raw_png, book, fit)   # an edge gap is fixed for free, never by a draw
            fit["attempt"] = attempt
            if fit["ok"]:
                if rid:
                    _store_series_thread(book, rid)
                return _install_cover(catalog, raw_png, brief, fit=fit)
            # keep the rejected draw for the record, never as the cover
            out_dir = Path(OUTPUT_DIR) / catalog
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"cover-rejected-{attempt}.png").write_bytes(raw_png)
            prompt = brief + "\n" + retry_note(fit)
    _record_fit_failure(catalog, fit)
    raise RuntimeError("Cover failed the fit check " + str(MAX_ATTEMPTS) +
                       " times (title clipped, on the edge or misspelled): " +
                       "; ".join(fit.get("issues") or []))


def _record_fit_failure(catalog: str, fit: dict) -> None:
    """A failed gate leaves its verdict on the record so the launch gate
    and the shelf can show why the book has no cover."""
    fresh = get_book_by_catalog(catalog)
    if not fresh:
        return
    data = dict(fresh["data"])
    cover = dict(data.get("cover") or {})
    cover["fit"] = fit
    data["cover"] = cover
    update_book(fresh["id"], data, sections=["cover"])


def _install_cover(catalog: str, raw_png: bytes, brief: str = "",
                   mode: str = "ai", fit: dict = None) -> dict:
    """Write cover-art/ebook/preview files and update the book record."""
    book = get_book_by_catalog(catalog)
    out_dir = Path(OUTPUT_DIR) / catalog
    out_dir.mkdir(parents=True, exist_ok=True)
    # A trim wider than the art (8.5x11, 8.5x8.5 against a 2:3 picture) is
    # framed by looking — the title kept whole, the sides extended when a
    # crop would crowd it — never centre-cropped blind (Freddie books lost
    # their titles that way, 2026-09-09). The model's image is kept as
    # cover-art-raw.png; cover-art.png is the framed print art.
    try:
        _d0 = book["data"]; _trim = (_d0.get("format") or {}).get("trim_size") or _d0.get("trim_size") or "5.5x8.5"
        _tw, _th = (float(x) for x in _trim.split("x"))
        from PIL import Image as _Im
        import io as _io
        _im = _Im.open(_io.BytesIO(raw_png)); _ar = _im.width / _im.height
        if (_tw / _th) - _ar > 0.03 and (_d0.get("kind") == "childrens" or _tw >= 8):
            (out_dir / "cover-art-raw.png").write_bytes(raw_png)
            from ..writing.workbook import frame_cover_for_trim
            raw_png, _rep = frame_cover_for_trim(raw_png, _trim, _d0.get("author_name") or "", out_dir)
    except Exception as _e:
        print(f"  cover framing skipped for {catalog}: {str(_e)[:80]}")
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
    # the fit verdict travels with the cover; an install without one is
    # visibly unchecked at the launch gate
    cover["fit"] = fit if fit else {"ok": False, "issues": ["installed without a fit check"]}
    data["cover"] = cover
    update_book(fresh["id"], data, sections=["cover"])
    return {"artwork": str(art_path), "ebook_cover": str(ebook_path),
            "preview": str(preview_path), "brief": brief, "fit": cover["fit"]}


async def _generate_one(client: httpx.AsyncClient, brief: str,
                        reference_png: bytes = None,
                        gen_size: str = IMAGE_SIZE) -> bytes:
    import asyncio
    last_err = None
    for attempt in range(3):   # DNS blips / resets must not kill a cover run
        try:
            if reference_png:
                # series installment: Book 1's cover rides along as the design
                # reference (image + prompt via the edits endpoint). A LIST of
                # references (2026-09-08: a universe's whole cast) goes as
                # several image[] parts.
                refs = reference_png if isinstance(reference_png, (list, tuple)) else [reference_png]
                files = [("image[]", (f"reference-{i + 1}.png", png, "image/png")) for i, png in enumerate(refs)]
                r = await client.post(
                    "https://api.openai.com/v1/images/edits",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files=files,
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
        if _is_size_rejection(r.status_code, r.text) and gen_size not in GEN_SIZES:
            # this engine only knows the three fixed canvases
            std = min(GEN_SIZES, key=lambda k: abs(GEN_SIZES[k] - _ratio_of(gen_size)))
            return await _generate_one(client, brief, reference_png=reference_png, gen_size=std)
        if r.status_code != 200:
            raise RuntimeError(f"Image generation failed ({r.status_code}): {r.text[:200]}")
        return base64.b64decode(r.json()["data"][0]["b64_json"])
    raise RuntimeError(f"Image generation failed after 3 attempts: {last_err}")


def _ratio_of(size: str) -> float:
    try:
        w, h = (int(x) for x in size.lower().split("x"))
        return w / h
    except Exception:
        return 1024 / 1536


async def generate_cover_variants(catalog: str, count: int = 4,
                                  extra_direction: str = "",
                                  on_progress=None) -> dict:
    """Generate N cover alternatives in parallel; user picks one to install."""
    import asyncio

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError(f"Book {catalog} not found")
    ms = _manuscript_of(book)
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured in the engine .env")
    _ensure_real_title(book)

    count = max(2, min(6, count))
    if on_progress:
        on_progress(0.1, "Preparing the fact sheet")
    summary = await _cover_summary(book, ms)
    # THE SERIES COVER RULE (Lars, 2026-09-09: "The books can't look as similar
    # as you have created them"): a series shares its look — the type treatment,
    # the author band, the shelf identity — but every book is ITS OWN PICTURE:
    # a different scene, season, time of day, moment and colour world from every
    # sibling. The siblings' covers are named so the designer can avoid them.
    series_note = ""
    sid = (book["data"].get("series") or {}).get("series_id")
    if sid:
        from ..database import list_books as _lb
        sibs = [b for b in _lb(per_page=1000).get("books", [])
                if (b.get("data") or {}).get("series", {}).get("series_id") == sid and b["catalog_number"] != catalog
                and b.get("status") not in ("cancelled", "deleted")]
        described = [f"{b['title']}: {((b.get('data') or {}).get('cover_direction') or '')[:160]}" for b in sibs if (b.get("data") or {}).get("cover_direction")]
        if sibs:
            series_note = ("SERIES COVER RULE: this book belongs to a series. Keep the series LOOK — the same title type treatment, "
                           "the author name in the same band, the same overall quality — but make this cover ITS OWN PICTURE: a different "
                           "scene, season, time of day, key object and colour world from every other book in the series. Never repeat a "
                           "sibling's composition. The other books' covers are:\n- " + "\n- ".join(described or [b["title"] for b in sibs]) + "\n")
    brief = _fact_brief(book, ms, summary,
                        notes=(series_note + _merged_direction(book, extra_direction)))
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
    from .cover_fit import check_cover_fit, crop_to_ratio
    variants = []
    rejected = []
    try:
        _tw, _th = (float(x) for x in trim_of(book).split("x"))
    except Exception:
        _tw, _th = 5.5, 8.5
    if on_progress:
        on_progress(0.95, "Checking every cover fits the page")
    fits = await asyncio.gather(
        *[check_cover_fit(res, book) if not isinstance(res, Exception) else asyncio.sleep(0)
          for res in results], return_exceptions=True)
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            continue
        fit = fits[i]
        if isinstance(fit, Exception) or not isinstance(fit, dict):
            fit = {"ok": False, "issues": [f"fit check failed: {str(fit)[:120]}"]}
        vpath = out_dir / f"cover-variant-{i + 1}.png"
        vpath.write_bytes(res)
        img = Image.open(io.BytesIO(res)).convert("RGB")
        # The preview is what the picker actually shows. It used to SQUASH
        # the whole canvas into the trim shape while the install CROPPED it,
        # so a title the crop would cut looked fine at the moment of
        # choosing. Preview exactly what the install keeps: crop, then scale.
        _pw = 400
        crop_to_ratio(img, _tw / _th).resize(
            (_pw, max(1, int(round(_pw * _th / _tw)))), Image.LANCZOS).save(
            out_dir / f"cover-variant-{i + 1}-preview.png", optimize=True)
        entry = {"index": i + 1,
                 "preview": f"cover-variant-{i + 1}-preview.png",
                 "concept": briefs[i].get("concept", ""),
                 "brief": briefs[i]["prompt"],
                 "response_id": response_ids[i],
                 "fit": fit}
        # THE COVER FIT CONTROL: a variant whose title is clipped, on the
        # edge or misspelled is never offered for choosing. It stays on
        # disk, marked, for the record.
        (variants if fit.get("ok") else rejected).append(entry)
    if not variants:
        first_err = next((r for r in results if isinstance(r, Exception)), None)
        if rejected:
            raise RuntimeError("Every cover option failed the fit check: " +
                               " | ".join("; ".join(r["fit"].get("issues") or [])
                                          for r in rejected)[:600])
        raise RuntimeError(f"All variants failed: {first_err}")

    data = dict(get_book_by_catalog(catalog)["data"])
    cover = dict(data.get("cover") or {})
    # a fresh set of variants never throws the original away (Lars, 2026-09-08)
    keep = [v for v in (cover.get("variants") or []) if v.get("index") == 0]
    cover["variants"] = keep + variants
    cover["variants_rejected"] = [{k: v for k, v in r.items() if k != "brief"} for r in rejected]
    data["cover"] = cover
    update_book(book["id"], data, sections=["cover"])
    return {"variants": cover["variants"], "rejected": len(rejected)}


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


def select_cover_variant(catalog: str, index: int, fit: dict = None) -> dict:
    """Promote a generated variant to the book's official front cover."""
    vpath = Path(OUTPUT_DIR) / catalog / f"cover-variant-{index}.png"
    if not vpath.exists():
        raise ValueError(f"Variant {index} not found")
    book = get_book_by_catalog(catalog)
    cov = book["data"].get("cover") or {}
    stored = list(cov.get("variants") or [])
    # THE ORIGINAL IS ALWAYS AN ALTERNATIVE (Lars, 2026-09-08, after the approved
    # Innkeeper cover vanished on one click): a cover that is not itself one of
    # the variants is kept as variant 0 before anything replaces it.
    out = Path(OUTPUT_DIR) / catalog
    cur = out / "cover-art.png"
    if cur.exists() and cov.get("selected_variant") in (None, 0) and not any(v.get("index") == 0 for v in stored):
        (out / "cover-variant-0.png").write_bytes(cur.read_bytes())
        try:
            from PIL import Image
            im = Image.open(cur); im.thumbnail((400, 600)); im.save(out / "cover-variant-0-preview.png")
        except Exception:
            (out / "cover-variant-0-preview.png").write_bytes(cur.read_bytes())
        stored.insert(0, {"index": 0, "preview": "cover-variant-0-preview.png", "concept": "The original",
                          "brief": cov.get("art_brief") or ""})
    brief = next((v.get("brief", "") for v in stored if v.get("index") == index),
                 (cov.get("art_brief")) or "")
    # the variant carries the fit verdict it earned when it was drawn; a
    # variant from before the control (or the original, index 0) arrives
    # with the verdict the route just measured
    fit = fit or next((v.get("fit") for v in stored if v.get("index") == index), None)
    result = _install_cover(catalog, vpath.read_bytes(), brief, fit=fit)
    data = dict(get_book_by_catalog(catalog)["data"])
    data["cover"] = dict(data.get("cover") or {})
    data["cover"]["variants"] = stored
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
