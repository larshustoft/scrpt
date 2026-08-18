"""
SCRPT prose-book API.
Everything the Work Order page, Bookshelf, Formatting Studio, Cover tab,
Audiobook tab and Analytics pages talk to.
"""

import uuid

from pydantic import BaseModel
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import database as db
from ..config import OUTPUT_DIR
from ..jobs import cancel_job, get_job, list_jobs, start_job
from ..prose.models import (
    BookKind, FONT_PRESETS, FormatConfig, GENRE_PRESETS, Manuscript,
    ManuscriptStatus, PlotChoiceRequest, ChapterEditRequest, WorkOrderRequest,
)
from ..writing import pipeline as wp
from ..writing.parsing import count_words

router = APIRouter(prefix="/api/scrpt", tags=["scrpt"])


# ── presets ──────────────────────────────────────────────────────

@router.get("/presets")
def presets():
    return {"genres": GENRE_PRESETS, "fonts": FONT_PRESETS}


# ── work orders ──────────────────────────────────────────────────

@router.post("/workorder")
async def create_workorder(req: WorkOrderRequest):
    preset = GENRE_PRESETS.get(req.genre_preset)
    if not preset:
        raise HTTPException(400, f"Unknown genre preset: {req.genre_preset}")
    if preset["kind"] != req.kind.value:
        raise HTTPException(400, "Genre preset does not match book kind")

    n_books = max(1, req.series_books if req.series_title else 1)
    series_id = uuid.uuid4().hex[:8] if req.series_title else ""
    created = []

    for book_no in range(1, n_books + 1):
        ms = Manuscript(
            kind=req.kind,
            genre_preset=req.genre_preset,
            idea=req.idea,
            target_words=req.target_words or preset["target_words"],
            status=ManuscriptStatus.IDEA,
        )
        fmt = FormatConfig(
            trim_size=req.trim_size or preset["trim"],
            paper_type=req.paper_type or preset["paper"],
            font_preset=req.font_preset or preset["font"],
            paragraph_style="indent" if req.kind == BookKind.FICTION else "spaced",
        )
        researched = (req.book_titles[book_no - 1].strip()
                      if book_no - 1 < len(req.book_titles) else "")
        if book_no == 1 and req.title:
            title = req.title
        elif researched:
            title = researched
        elif req.series_title:
            title = f"Untitled ({req.series_title} #{book_no})"
        else:
            title = req.title or "Untitled"
        data = {
            "kind": req.kind.value,
            "book_type": req.kind.value,          # legacy field compatibility
            "genre_preset": req.genre_preset,
            "author_name": req.pen_name,
            "cover_direction": req.cover_direction,
            "trim_size": fmt.trim_size,
            "paper_type": fmt.paper_type,
            "page_count": 0,
            "list_price": 14.99 if req.kind == BookKind.NONFICTION else 12.99,
            "manuscript": ms.model_dump(mode="json"),
            "format": fmt.model_dump(mode="json"),
            "interior": {}, "cover": {}, "audio": {},
            "series": {
                "series_id": series_id,
                "series_title": req.series_title,
                "book_number": book_no,
                "total_planned": n_books,
                "series_bible": "",
            } if series_id else {},
        }
        created.append(db.create_book(title, data))

    first = created[0]
    job_id = None
    if req.auto_draft:
        catalog = first["catalog_number"]
        job_id = start_job("full_draft",
                           lambda h, c=catalog: wp.full_draft_job(h, c),
                           book_catalog=catalog)
    elif req.generate_plot_options:
        catalog = first["catalog_number"]
        job_id = start_job(
            "plot_options",
            lambda h, c=catalog: _plot_options_job(h, c),
            book_catalog=catalog,
        )

    # Covers start the moment the book is commissioned — painted from the
    # researched commissioning brief + cover direction, in parallel with the
    # writing. Needs a real title (it is baked into the art); the research
    # flow always provides one.
    cover_job_id = None
    title_ok = (first["title"] and not first["title"].lower().startswith("untitled")
                and len(first["title"]) <= 120)
    if title_ok:
        from ..cover.front_cover import generate_cover_variants
        catalog = first["catalog_number"]

        async def cover_job(handle, c=catalog):
            handle.progress(0.08, "brief", "Art-directing from the commissioning brief")
            return await generate_cover_variants(
                c, 4, "",
                on_progress=lambda f, d: handle.progress(f, "painting", d))

        cover_job_id = start_job("cover_variants", cover_job, book_catalog=catalog)

    return {"books": created, "job_id": job_id, "cover_job_id": cover_job_id}


async def _plot_options_job(handle, catalog: str) -> dict:
    handle.progress(0.1, "plotting", "Developing three directions")
    options = await wp.generate_plot_options(catalog)
    return {"options": options}


@router.get("/pen-names")
def pen_names():
    """Existing pen names with their catalogs, for the Work Order form."""
    books = db.list_books(per_page=200)["books"]
    authors: dict[str, list[dict]] = {}
    for b in books:
        if not b["data"].get("manuscript"):
            continue
        name = (b["data"].get("author_name") or "").strip()
        if not name:
            continue
        authors.setdefault(name, []).append({
            "catalog_number": b["catalog_number"],
            "title": b["title"],
            "genre_preset": b["data"].get("genre_preset", ""),
            "status": b["status"],
            "series_title": (b["data"].get("series") or {}).get("series_title", ""),
            "words": (b["data"].get("manuscript") or {}).get("word_count", 0),
        })
    return {"authors": [{"name": n, "books": bs} for n, bs in
                        sorted(authors.items(), key=lambda kv: -len(kv[1]))]}


class PenNameSuggestRequest(BaseModel):
    kind: BookKind
    genre_preset: str
    idea: str = ""


@router.post("/workorder/pen-names")
async def suggest_pen_names(req: PenNameSuggestRequest):
    """Genre-appropriate pen name suggestions (avoiding existing house names)."""
    from ..writing.client import complete, extract_json
    preset = GENRE_PRESETS.get(req.genre_preset, {})
    existing = [a["name"] for a in pen_names()["authors"]]
    prompt = (
        f"Suggest 5 pen names for a {preset.get('label', 'book')} author"
        f"{' writing: ' + req.idea[:300] if req.idea else ''}.\n"
        "Rules: names must sound native to the genre's bestseller shelf; "
        "believable, memorable, easy to say and spell; mix genders where the "
        "genre supports it; NEVER a real living author's name or anything "
        "confusable with one; avoid these existing house pen names: "
        f"{existing or 'none'}.\n"
        'Return JSON only: [{"name": "...", "rationale": "6-12 words"}]'
    )
    raw = await complete(
        "You name authors for a commercial publishing house. You know how "
        "bestseller shelves in each genre sound.",
        prompt, max_tokens=1200)
    return {"suggestions": extract_json(raw)}


class DevelopIdeaRequest(BaseModel):
    kind: BookKind
    genre_preset: str
    idea: str
    series_books: int = 0


@router.post("/workorder/develop")
async def develop_workorder_idea(req: DevelopIdeaRequest):
    """Research & extend a rough idea into a commissioning package."""
    from ..writing.develop import develop_idea
    if not req.idea.strip():
        raise HTTPException(400, "Write the rough idea first")

    async def job(handle):
        handle.progress(0.15, "research", "Researching the market and developing the concept")
        return await develop_idea(req.kind.value, req.genre_preset,
                                  req.idea.strip(), req.series_books)

    job_id = start_job("develop_idea", job)
    return {"job_id": job_id}


# ── series ───────────────────────────────────────────────────────

def _series_books(series_id: str) -> list[dict]:
    books = db.list_books(per_page=200)["books"]
    members = [b for b in books
               if (b["data"].get("series") or {}).get("series_id") == series_id]
    members.sort(key=lambda b: (b["data"]["series"].get("book_number") or 0))
    return members


@router.get("/series/{series_id}")
def get_series(series_id: str):
    members = _series_books(series_id)
    if not members:
        raise HTTPException(404, "Series not found")
    info = members[0]["data"]["series"]
    return {"series_id": series_id,
            "series_title": info.get("series_title", ""),
            "series_bible": info.get("series_bible", ""),
            "total_planned": max((b["data"]["series"].get("total_planned") or 1)
                                 for b in members),
            "books": members}


class ExtendSeriesRequest(BaseModel):
    count: int = 1
    idea: str = ""     # optional steer for the next book(s)


@router.post("/series/{series_id}/extend")
async def extend_series(series_id: str, req: ExtendSeriesRequest = None):
    members = _series_books(series_id)
    if not members:
        raise HTTPException(404, "Series not found")
    count = max(1, min(6, req.count if req else 1))
    steer = (req.idea if req else "") or ""

    template = members[-1]["data"]
    info = template["series"]
    max_no = max((b["data"]["series"].get("book_number") or 1) for b in members)
    new_total = max_no + count

    created = []
    for offset in range(1, count + 1):
        book_no = max_no + offset
        ms = Manuscript(
            kind=BookKind(template.get("kind", "fiction")),
            genre_preset=template.get("genre_preset", "action_thriller"),
            idea=steer or template.get("manuscript", {}).get("idea", ""),
            target_words=template.get("manuscript", {}).get("target_words", 95000),
            status=ManuscriptStatus.IDEA,
        )
        data = {
            "kind": template.get("kind", "fiction"),
            "book_type": template.get("kind", "fiction"),
            "genre_preset": template.get("genre_preset"),
            "author_name": template.get("author_name", ""),
            "trim_size": template.get("trim_size"),
            "paper_type": template.get("paper_type"),
            "page_count": 0,
            "list_price": template.get("list_price", 12.99),
            "manuscript": ms.model_dump(mode="json"),
            "format": template.get("format", {}),
            "interior": {}, "cover": {}, "audio": {},
            "series": {
                "series_id": series_id,
                "series_title": info.get("series_title", ""),
                "book_number": book_no,
                "total_planned": new_total,
                "series_bible": info.get("series_bible", ""),
            },
        }
        created.append(db.create_book(
            f"Untitled ({info.get('series_title', 'Series')} #{book_no})", data))

    # existing members learn the new series size
    for b in members:
        d = dict(b["data"])
        d["series"]["total_planned"] = new_total
        db.update_book(b["id"], d)

    catalog = created[0]["catalog_number"]
    job_id = start_job("plot_options",
                       lambda h, c=catalog: _plot_options_job(h, c),
                       book_catalog=catalog)
    return {"books": created, "job_id": job_id}


# ── manuscript flow ──────────────────────────────────────────────

@router.get("/books")
def list_prose_books():
    """All books with full (unfiltered) data — the legacy /api/books endpoint
    strips unknown keys through its response model."""
    result = db.list_books(per_page=500)
    return {"books": result["books"], "total": result["total"]}


@router.get("/books/{catalog}")
def get_book(catalog: str):
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    return book


@router.post("/plot-options/{catalog}")
async def regenerate_plot_options(catalog: str):
    job_id = start_job("plot_options",
                       lambda h: _plot_options_job(h, catalog),
                       book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/choose-plot")
async def choose_plot(req: PlotChoiceRequest):
    book = db.get_book_by_catalog(req.catalog_number)
    if not book:
        raise HTTPException(404, "Book not found")
    job_id = start_job(
        "full_draft",
        lambda h: wp.full_draft_job(h, req.catalog_number, req.chosen_plot, req.edits),
        book_catalog=req.catalog_number,
    )
    return {"job_id": job_id}


@router.post("/acceptance/{catalog}")
async def run_acceptance(catalog: str):
    """The acceptance desk on demand: length gate + managing-editor read
    (with bounded automated repair). Re-run any time — e.g. after a model
    upgrade, the whole catalog can be re-checked to the new standard."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")

    async def job(handle):
        from ..writing.acceptance import acceptance_job
        return await acceptance_job(handle, catalog)

    job_id = start_job("acceptance", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/series/create-from/{catalog}")
async def create_series_from(catalog: str):
    """Promote a standalone book into Book 1 of a new series — same
    characters, same universe. Titles the series, writes the series bible
    from the finished book, and opens the series for commissioning more."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    if (book["data"].get("series") or {}).get("series_id"):
        raise HTTPException(409, "This book is already part of a series")
    ms = book["data"].get("manuscript") or {}
    if not ms.get("story_bible"):
        raise HTTPException(409, "The book needs its story bible first — "
                                 "series grow from a finished world")

    async def job(handle):
        from ..writing.client import complete, extract_json
        from ..writing.pipeline import _bible_digest
        from ..prose.models import Manuscript as _M
        m = _M.model_validate(ms)
        digest = _bible_digest(m)

        handle.progress(0.2, "series", "Naming the series")
        raw = await complete(
            "You build commercial book franchises from standalone successes.",
            f"THE BOOK: \"{book['title']}\"\nBIBLE:\n{digest}\n\n"
            "This standalone becomes Book 1 of a series in the same universe "
            "with the same central character(s). Return JSON only:\n"
            '{"series_title": "short, ownable, brandable — the shelf name '
            'readers collect", "series_engine": "what generates every next '
            "book: who returns, what changes per installment, the repeatable "
            'shape (max 60 words)"}',
            max_tokens=2000)
        naming = extract_json(raw)

        handle.progress(0.6, "series", "Writing the series bible")
        sb_raw = await complete(
            "You write series bibles for commercial publishing houses.",
            f"STORY BIBLE OF BOOK 1 (\"{book['title']}\"):\n{digest}\n\n"
            f"SERIES ENGINE: {naming.get('series_engine', '')}\n\n"
            f"Write the SERIES BIBLE for \"{naming.get('series_title')}\" — "
            "the canon document every later book must honor. 250-350 words: "
            "the recurring protagonist(s) as the series brand, recurring "
            "supporting cast, world rules and tone, the per-book formula, and "
            "long arcs that grow across books. Plain text.",
            max_tokens=3000)

        sid = uuid.uuid4().hex[:8]
        data = dict(db.get_book_by_catalog(catalog)["data"])
        data["series"] = {
            "series_id": sid,
            "series_title": str(naming.get("series_title", book["title"]))[:120],
            "book_number": 1,
            "total_planned": 1,   # grows as books are commissioned
            "series_bible": sb_raw.strip()[:4000],
        }
        db.update_book(book["id"], data)
        return {"series_id": sid,
                "series_title": data["series"]["series_title"]}

    job_id = start_job("create_series", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/rewrite/{catalog}")
async def rewrite_book(catalog: str):
    """Rewrite the book from scratch through the CURRENT pipeline — keeps the
    identity (title, author, cover artwork, idea, series) and discards the old
    manuscript, then runs the full line: market check, architecture, chapters,
    gates, acceptance. The existing cover is never touched."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    if [j for j in list_jobs(catalog, active_only=True) if j["kind"] == "full_draft"]:
        raise HTTPException(409, "This book is already being written")

    data = dict(book["data"])
    old_ms = data.get("manuscript") or {}
    preset = GENRE_PRESETS.get(old_ms.get("genre_preset"), {})
    fresh = Manuscript(
        kind=BookKind(old_ms.get("kind", data.get("kind", "fiction"))),
        genre_preset=old_ms.get("genre_preset", "action_thriller"),
        idea=old_ms.get("idea", ""),
        target_words=old_ms.get("target_words") or preset.get("target_words", 90000),
        status=ManuscriptStatus.IDEA,
    )
    data["manuscript"] = fresh.model_dump(mode="json")
    # stale derivatives of the old text go; identity and artwork stay
    data["interior"] = {}
    data["audio"] = {}
    data.pop("acceptance", None)
    data.pop("market_check", None)
    db.update_book(book["id"], data)

    job_id = start_job("full_draft",
                       lambda h: wp.full_draft_job(h, catalog),
                       book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/draft/{catalog}")
async def resume_draft(catalog: str):
    """(Re)start drafting for whatever chapters aren't finished."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    active = [j for j in list_jobs(catalog, active_only=True) if j["kind"] == "full_draft"]
    if active:
        return {"job_id": active[0]["id"], "already_running": True}
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    chosen = ms.chosen_plot or 0
    job_id = start_job("full_draft",
                       lambda h: wp.full_draft_job(h, catalog, chosen),
                       book_catalog=catalog)
    return {"job_id": job_id}


@router.put("/chapter")
def save_chapter(req: ChapterEditRequest):
    """Persist studio edits to one chapter (full block replacement)."""
    book = db.get_book_by_catalog(req.catalog_number)
    if not book:
        raise HTTPException(404, "Book not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    ch = next((c for c in ms.chapters if c.id == req.chapter_id), None)
    if not ch:
        raise HTTPException(404, "Chapter not found")
    ch.blocks = req.blocks
    ch.word_count = count_words(ch.blocks)
    if ch.status.value in ("outlined", "drafting"):
        ch.status = "drafted"
    ms.word_count = sum(c.word_count for c in ms.chapters)
    data = dict(book["data"])
    data["manuscript"] = ms.model_dump(mode="json")
    db.update_book(book["id"], data)
    return {"success": True, "chapter_words": ch.word_count,
            "book_words": ms.word_count}


@router.post("/blurb/{catalog}")
async def regenerate_blurb(catalog: str):
    job_id = start_job("blurb",
                       lambda h: _blurb_job(h, catalog), book_catalog=catalog)
    return {"job_id": job_id}


async def _blurb_job(handle, catalog: str) -> dict:
    handle.progress(0.2, "blurb", "Writing listing copy")
    return await wp.generate_blurb(catalog)


# ── production & release operations ──────────────────────────────

class ScheduleRequest(BaseModel):
    upload_date: Optional[str] = None
    release_date: Optional[str] = None


@router.put("/schedule/{catalog}")
def set_schedule(catalog: str, req: ScheduleRequest):
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    data = dict(book["data"])
    if req.upload_date is not None:
        data["upload_date"] = req.upload_date
    if req.release_date is not None:
        data["release_date"] = req.release_date
    db.update_book(book["id"], data)
    return {"success": True}


def _asset_state(book: dict) -> dict:
    d = book["data"]
    ms = d.get("manuscript") or {}
    chapters = ms.get("chapters") or []
    drafted = bool(chapters) and all(c.get("blocks") for c in chapters)
    interior = d.get("interior") or {}
    audio = d.get("audio") or {}
    return {
        "manuscript": drafted,
        # quality = the acceptance desk said "accept" (falls back to the
        # per-chapter audit trail for books that predate the desk)
        "quality": (d.get("acceptance") or {}).get("verdict") == "accept"
                   or (not d.get("acceptance")
                       and bool(ms.get("quality_report", {}).get("chapters_audited"))),
        "interior_pdf": bool(interior.get("page_count"))
                        and bool((interior.get("validation") or {}).get("passed")),
        "epub": bool((d.get("ebook") or {}).get("epub_path")),
        "cover": bool((d.get("cover") or {}).get("cover_front_png")),
        "audiobook": audio.get("status") == "mastered",
    }


@router.get("/queue")
def production_queue():
    """Everything scheduled or in flight, with asset readiness."""
    from datetime import date
    today = date.today().isoformat()
    books = db.list_books(per_page=200)["books"]
    rows = []
    for b in books:
        if not b["data"].get("manuscript"):
            continue
        assets = _asset_state(b)
        core_ready = all(assets[k] for k in
                         ("manuscript", "interior_pdf", "epub", "cover"))
        rows.append({
            "catalog_number": b["catalog_number"],
            "title": b["title"],
            "status": b["status"],
            "author": b["data"].get("author_name", ""),
            "series_title": (b["data"].get("series") or {}).get("series_title", ""),
            "upload_date": b["data"].get("upload_date", ""),
            "release_date": b["data"].get("release_date", ""),
            "assets": assets,
            "ready": core_ready,
            "due": bool(b["data"].get("upload_date"))
                   and b["data"]["upload_date"] <= today
                   and b["status"] not in ("in_review", "live"),
        })
    rows.sort(key=lambda r: (r["upload_date"] or "9999", r["catalog_number"]))
    return {"queue": rows, "today": today}


@router.post("/prepare/{catalog}")
async def prepare_release(catalog: str):
    """Produce every missing asset: interior PDF, EPUB, audiobook. One job."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    active = [j for j in list_jobs(catalog, active_only=True) if j["kind"] == "prepare"]
    if active:
        return {"job_id": active[0]["id"], "already_running": True}

    async def job(handle):
        from ..interior.print_service import export_interior as run_export
        from ..interior.epub import build_epub
        from ..audio.pipeline import audiobook_job
        from ..routers.assistant import elevenlabs_key

        result = {}
        b = db.get_book_by_catalog(catalog)
        assets = _asset_state(b)

        if not assets["interior_pdf"]:
            handle.progress(0.1, "interior", "Exporting print interior")
            result["interior"] = await run_export(catalog)

        handle.progress(0.4, "epub", "Building the ebook (EPUB)")
        result["epub"] = build_epub(catalog)

        b = db.get_book_by_catalog(catalog)
        assets = _asset_state(b)
        if (not assets["audiobook"] and elevenlabs_key()
                and db.get_setting("elevenlabs_voice_id", "")):
            handle.progress(0.5, "audiobook", "Narrating the audiobook")
            result["audiobook"] = await audiobook_job(handle, catalog)

        # everything core present -> ready
        b = db.get_book_by_catalog(catalog)
        assets = _asset_state(b)
        if all(assets[k] for k in ("manuscript", "interior_pdf", "epub", "cover")):
            data = dict(b["data"])
            db.update_book(b["id"], {"status": "ready", **data})
        result["assets"] = assets
        return result

    job_id = start_job("prepare", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.get("/upload-package/{catalog}")
def upload_package(catalog: str):
    """Everything needed at the upload desks, staged for copy-paste."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    d = book["data"]
    ms = d.get("manuscript") or {}
    fmt = d.get("format") or {}
    series = d.get("series") or {}
    audio = d.get("audio") or {}
    price = d.get("list_price", 12.99)
    pages = (d.get("interior") or {}).get("page_count", 0)

    audio_files = [{"title": c.get("title", ""),
                    "file": (c.get("audio_path") or "").split("/")[-1]}
                   for c in (audio.get("chapters") or [])]

    return {
        "catalog_number": catalog,
        "metadata": {
            "title": book["title"],
            "subtitle": "",
            "series_title": series.get("series_title", ""),
            "series_number": series.get("book_number"),
            "author": d.get("author_name", ""),
            "description": d.get("description", ms.get("blurb", "")),
            "keywords": d.get("keywords", []),
            "categories": d.get("categories", []),
            "language": "English",
            "ai_disclosure": (
                "Answer YES to AI-generated content. Text: AI-generated with "
                "extensive human editing and review. Cover: AI-generated with "
                "human review."
            ),
        },
        "print": {
            "trim_size": fmt.get("trim_size", d.get("trim_size")),
            "paper": fmt.get("paper_type", d.get("paper_type")),
            "pages": pages,
            "price_usd": price,
            "interior_pdf": f"/api/scrpt/interior/pdf/{catalog}",
            "cover_note": "Print wrap via designer package (front art as reference)",
        },
        "ebook": {
            "epub": f"/api/files/{catalog}/ebook.epub",
            "cover_jpg": f"/api/files/{catalog}/ebook-cover.jpg",
            "price_usd": min(9.99, max(2.99, round(price * 0.5, 2))),
            "royalty_note": "Price 2.99-9.99 for the 70% tier",
        },
        "audiobook": {
            "mastered": audio.get("status") == "mastered",
            "cover_square": f"/api/files/{catalog}/audiobook-cover.jpg",
            "chapters": audio_files,
            "narrator_credit": "Digital voice (ElevenLabs) — use each "
                               "platform's synthesized-voice flag; never a "
                               "human pseudonym",
            "portals": {
                "spotify": "https://authors.spotify.com",
                "google_play": "https://play.google.com/books/publish",
                "kobo": "https://writinglife.kobobooks.com",
                "kdp_virtual_voice": "https://kdp.amazon.com",
                "inaudio": "https://www.inaudio.com",
            },
            "uploaded_to": audio.get("platforms", {}),
        },
        "kdp_portal": "https://kdp.amazon.com/en_US/title-setup/paperback",
    }


class MarkStatusRequest(BaseModel):
    status: str          # "in_review" (uploaded) | "live"
    platform: str = ""   # for audiobook platform tracking


@router.post("/mark/{catalog}")
def mark_status(catalog: str, req: MarkStatusRequest):
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    data = dict(book["data"])
    if req.platform:
        audio = data.get("audio") or {}
        platforms = audio.get("platforms") or {}
        from datetime import date
        platforms[req.platform] = date.today().isoformat()
        audio["platforms"] = platforms
        data["audio"] = audio
        db.update_book(book["id"], data)
        return {"success": True, "platforms": platforms}
    if req.status not in ("in_review", "live", "ready", "draft"):
        raise HTTPException(400, "Bad status")
    db.update_book(book["id"], {"status": req.status, **data})
    return {"success": True}


@router.post("/epub/{catalog}")
def make_epub(catalog: str):
    from ..interior.epub import build_epub
    try:
        return build_epub(catalog)
    except ValueError as e:
        raise HTTPException(409, str(e))


# ── jobs ─────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/jobs")
def jobs_for_book(catalog: Optional[str] = None, active: bool = False):
    return {"jobs": list_jobs(catalog, active_only=active)}


@router.post("/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    return {"cancelled": cancel_job(job_id)}


# ── interior export ──────────────────────────────────────────────

@router.post("/interior/export/{catalog}")
async def export_interior(catalog: str):
    from ..interior.print_service import export_interior as run_export

    async def job(handle):
        handle.progress(0.1, "render", "Rendering pages in print engine")
        result = await run_export(catalog)
        handle.progress(0.9, "validate", "Validating against KDP rules")
        return result

    job_id = start_job("interior_export", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.get("/interior/pdf/{catalog}")
def interior_pdf(catalog: str):
    path = Path(OUTPUT_DIR) / catalog / "interior.pdf"
    if not path.exists():
        raise HTTPException(404, "No interior PDF exported yet")
    return FileResponse(str(path), media_type="application/pdf",
                        filename=f"{catalog}-interior.pdf")


# ── cover ────────────────────────────────────────────────────────

def _book_cover_inputs(catalog: str):
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    interior = book["data"].get("interior") or {}
    page_count = interior.get("page_count") or 0
    if not page_count:
        raise HTTPException(
            409, "Interior not exported yet — the cover spine width depends on "
                 "the final page count. Export the interior first.")
    fmt = book["data"].get("format") or {}
    trim = fmt.get("trim_size") or book["data"].get("trim_size", "5.5x8.5")
    paper = fmt.get("paper_type") or book["data"].get("paper_type", "cream_bw")
    return book, page_count, trim, paper


@router.get("/cover/spec/{catalog}")
def cover_spec(catalog: str):
    from ..cover.designer_package import cover_spec_dict
    book, pages, trim, paper = _book_cover_inputs(catalog)
    return cover_spec_dict(pages, trim, paper)


@router.post("/cover/designer-package/{catalog}")
def designer_package(catalog: str):
    from ..cover.designer_package import write_designer_package
    book, pages, trim, paper = _book_cover_inputs(catalog)
    result = write_designer_package(catalog, book["title"], pages, trim, paper)
    data = dict(book["data"])
    cover = data.get("cover") or {}
    cover.update({"spec": result["spec"], "spec_page_count": pages})
    data["cover"] = cover
    db.update_book(book["id"], data)
    return result


@router.get("/cover/designer-package/{catalog}/{file}")
def designer_package_file(catalog: str, file: str):
    safe = {"spec": ("COVER_SPEC.txt", "text/plain"),
            "template": ("cover_template.pdf", "application/pdf")}
    if file not in safe:
        raise HTTPException(404, "Unknown file")
    name, mime = safe[file]
    path = Path(OUTPUT_DIR) / catalog / "designer_package" / name
    if not path.exists():
        raise HTTPException(404, "Package not generated yet")
    return FileResponse(str(path), media_type=mime, filename=f"{catalog}-{name}")


@router.post("/cover/upload/{catalog}")
async def upload_cover(catalog: str, file: UploadFile = File(...)):
    from ..cover.designer_package import validate_uploaded_cover
    book, pages, trim, paper = _book_cover_inputs(catalog)
    content = await file.read()
    report = validate_uploaded_cover(content, file.filename or "cover", pages, trim, paper)

    data = dict(book["data"])
    cover = data.get("cover") or {}
    if report["passed"]:
        dest_dir = Path(OUTPUT_DIR) / catalog
        dest_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(file.filename or "cover.pdf").suffix or ".pdf"
        dest = dest_dir / f"cover_uploaded{ext}"
        dest.write_bytes(content)
        cover.update({
            "mode": "upload", "status": "final", "uploaded_path": str(dest),
            "spec_page_count": pages, "validation": report,
        })
        if ext == ".pdf":
            cover["cover_pdf"] = str(dest)
    else:
        cover.update({"mode": "upload", "status": "draft", "validation": report})
    data["cover"] = cover
    db.update_book(book["id"], data)
    return report


class FrontCoverRequest(BaseModel):
    direction: str = ""


@router.post("/cover/generate-front/{catalog}")
async def generate_front(catalog: str, req: FrontCoverRequest = None):
    """AI front cover: Claude art direction -> image model -> ebook cover files."""
    from ..cover.front_cover import generate_front_cover
    direction = req.direction if req else ""
    active = [j for j in list_jobs(catalog, active_only=True) if j["kind"] == "front_cover"]
    if active:
        return {"job_id": active[0]["id"], "already_running": True}

    async def job(handle):
        handle.progress(0.1, "brief", "Art-directing the cover")
        result = await generate_front_cover(catalog, direction)
        handle.progress(0.95, "files", "Preparing ebook cover files")
        return result

    job_id = start_job("front_cover", job, book_catalog=catalog)
    return {"job_id": job_id}


class VariantsRequest(BaseModel):
    direction: str = ""
    count: int = 4


@router.post("/cover/generate-variants/{catalog}")
async def generate_variants(catalog: str, req: VariantsRequest = None):
    from ..cover.front_cover import generate_cover_variants
    direction = req.direction if req else ""
    count = req.count if req else 4
    active = [j for j in list_jobs(catalog, active_only=True)
              if j["kind"] in ("front_cover", "cover_variants")]
    if active:
        return {"job_id": active[0]["id"], "already_running": True}

    async def job(handle):
        handle.progress(0.08, "brief", "Art-directing from the bible")
        return await generate_cover_variants(
            catalog, count, direction,
            on_progress=lambda f, d: handle.progress(f, "painting", d))

    job_id = start_job("cover_variants", job, book_catalog=catalog)
    return {"job_id": job_id}


class SelectVariantRequest(BaseModel):
    index: int


@router.post("/cover/select-variant/{catalog}")
def select_variant(catalog: str, req: SelectVariantRequest):
    from ..cover.front_cover import select_cover_variant
    try:
        return select_cover_variant(catalog, req.index)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── audiobook ────────────────────────────────────────────────────

@router.get("/audio/voices")
async def casting_voices():
    """The casting board: every voice on the ElevenLabs account, with the
    stock preview URL and labels so the publisher can audition and cast."""
    import httpx as _httpx
    from ..routers.assistant import elevenlabs_key
    key = elevenlabs_key()
    if not key:
        return {"configured": False, "voices": [], "default_voice_id": ""}
    async with _httpx.AsyncClient() as client:
        r = await client.get("https://api.elevenlabs.io/v1/voices",
                             headers={"xi-api-key": key}, timeout=20)
    if r.status_code != 200:
        raise HTTPException(502, f"ElevenLabs voices failed ({r.status_code})")
    voices = [{
        "id": v["voice_id"],
        "name": v["name"],
        "category": v.get("category", ""),
        "preview_url": v.get("preview_url", ""),
        "labels": v.get("labels") or {},
        "description": (v.get("description") or "")[:200],
    } for v in r.json().get("voices", [])]
    return {"configured": True, "voices": voices,
            "default_voice_id": db.get_setting("elevenlabs_voice_id", "") or ""}


@router.get("/audio/library")
async def voice_library(search: str = "", gender: str = "", accent: str = "",
                        page: int = 0, narration: bool = True):
    """Search the FULL ElevenLabs Voice Library (thousands of voices).
    English always; narration-labeled by default, every English voice when
    narration=false — the real casting pool."""
    import httpx as _httpx
    from ..routers.assistant import elevenlabs_key
    key = elevenlabs_key()
    if not key:
        return {"configured": False, "voices": [], "has_more": False}
    params = {"page_size": 24, "page": page, "language": "en"}
    if narration:
        params["use_cases"] = "narrative_story"
    if search.strip():
        params["search"] = search.strip()
    if gender in ("male", "female"):
        params["gender"] = gender
    if accent.strip():
        params["accent"] = accent.strip()
    async with _httpx.AsyncClient() as client:
        r = await client.get("https://api.elevenlabs.io/v1/shared-voices",
                             headers={"xi-api-key": key}, params=params,
                             timeout=25)
    if r.status_code != 200:
        raise HTTPException(502, f"Voice library failed ({r.status_code}): {r.text[:200]}")
    data = r.json()
    voices = [{
        "id": v.get("voice_id"),
        "owner": v.get("public_owner_id"),
        "name": v.get("name"),
        "gender": v.get("gender") or "",
        "accent": v.get("accent") or "",
        "age": v.get("age") or "",
        "descriptive": v.get("descriptive") or "",
        "preview_url": v.get("preview_url") or "",
        "popularity": v.get("cloned_by_count") or 0,
        "free_ok": bool(v.get("free_users_allowed", True)),
    } for v in data.get("voices", [])
        if (v.get("language") or "en").lower().startswith("en")
        # house rule: American and British narrators only
        and any(a in (v.get("accent") or "").lower()
                for a in ("american", "british", "english"))]
    return {"configured": True, "voices": voices,
            "has_more": bool(data.get("has_more"))}


class LibraryAddRequest(BaseModel):
    owner: str
    voice_id: str
    name: str


@router.post("/audio/library/add")
async def add_library_voice(req: LibraryAddRequest):
    """Add a Voice Library narrator into the account so it can be cast."""
    import httpx as _httpx
    from ..routers.assistant import elevenlabs_key
    key = elevenlabs_key()
    if not key:
        raise HTTPException(400, "ElevenLabs is not configured")
    async with _httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.elevenlabs.io/v1/voices/add/{req.owner}/{req.voice_id}",
            headers={"xi-api-key": key},
            json={"new_name": req.name[:100]},
            timeout=25,
        )
    if r.status_code != 200:
        detail = r.text[:300]
        if "missing_permissions" in detail or "add_voice_from_voice_library" in detail:
            raise HTTPException(422,
                "Your ElevenLabs API key lacks the 'add voices from the Voice "
                "Library' permission. In ElevenLabs: Developers → API Keys → "
                "edit the key SCRPT uses → enable the Voices permission (or "
                "issue an unrestricted key), then try again.")
        if "voice_limit" in detail or "maximum" in detail.lower():
            raise HTTPException(422, "Your ElevenLabs voice slots are full — "
                                     "remove an unused voice in ElevenLabs or "
                                     "upgrade the plan, then add again.")
        raise HTTPException(502, f"Could not add the voice ({r.status_code}): {detail}")
    new_id = (r.json() or {}).get("voice_id") or req.voice_id
    return {"success": True, "voice_id": new_id}


class CastVoiceRequest(BaseModel):
    voice_id: str
    voice_name: str = ""
    set_as_default: bool = False


@router.put("/audio/voice/{catalog}")
def cast_voice(catalog: str, req: CastVoiceRequest):
    """Cast the narrator for this book (optionally as the house default)."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    data = dict(book["data"])
    audio = data.get("audio") or {}
    audio["voice_id"] = req.voice_id
    audio["voice_name"] = req.voice_name
    data["audio"] = audio
    db.update_book(book["id"], data)
    if req.set_as_default:
        db.set_setting("elevenlabs_voice_id", req.voice_id)
        db.set_setting("elevenlabs_voice_name", req.voice_name)
    return {"success": True}


@router.post("/audio/audition/{catalog}")
async def audition_voice(catalog: str, req: CastVoiceRequest):
    """Narrate the book's real opening in a candidate voice (~15s render)."""
    from ..audio.pipeline import audition_sample

    async def job(handle):
        handle.progress(0.3, "audition",
                        f"{req.voice_name or 'The candidate'} reads the opening")
        return await audition_sample(catalog, req.voice_id, req.voice_name)

    job_id = start_job("audition", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/audio/{catalog}")
async def start_audiobook(catalog: str):
    from ..audio.pipeline import audiobook_job
    active = [j for j in list_jobs(catalog, active_only=True) if j["kind"] == "audiobook"]
    if active:
        return {"job_id": active[0]["id"], "already_running": True}
    job_id = start_job("audiobook",
                       lambda h: audiobook_job(h, catalog), book_catalog=catalog)
    return {"job_id": job_id}


@router.get("/audio/file/{catalog}/{name}")
def audio_file(catalog: str, name: str):
    if "/" in name or ".." in name:
        raise HTTPException(400, "Bad file name")
    path = Path(OUTPUT_DIR) / catalog / "audiobook" / name
    if not path.exists():
        raise HTTPException(404, "Audio file not found")
    return FileResponse(str(path), media_type="audio/mpeg", filename=name)


# ── royalties / reports ──────────────────────────────────────────

@router.post("/reports/import")
async def import_report(file: UploadFile = File(...)):
    from ..reports.importer import import_report as run_import
    content = await file.read()
    try:
        return run_import(file.filename or "report.xlsx", content)
    except Exception as e:
        raise HTTPException(422, f"Could not parse report: {e}")


@router.get("/reports/summary")
def reports_summary():
    from ..reports.importer import summary
    return summary()


@router.get("/reports/books")
def reports_books():
    from ..reports.importer import by_book
    return {"books": by_book()}


@router.get("/reports/series")
def reports_series():
    from ..reports.importer import series_readthrough
    return series_readthrough()
