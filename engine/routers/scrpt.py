"""
SCRPT prose-book API.
Everything the Work Order page, Bookshelf, Formatting Studio, Cover tab,
Audiobook tab and Analytics pages talk to.
"""

import uuid

from pydantic import BaseModel
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
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
    """All three kinds the house writes: fiction, non-fiction, children's."""
    from ..prose.models import CHILDRENS_PRESETS
    return {"genres": {**GENRE_PRESETS, **CHILDRENS_PRESETS},
            "childrens": CHILDRENS_PRESETS,
            "kinds": [
                {"value": "fiction", "label": "Fiction",
                 "hint": "Novels — thrillers, romance, mystery, fantasy"},
                {"value": "nonfiction", "label": "Non-fiction",
                 "hint": "Self-help, business, health, personal finance"},
                {"value": "childrens", "label": "Children's book",
                 "hint": "Picture books, early readers and chapter books — illustrated"},
            ],
            "fonts": FONT_PRESETS}


def _assert_machine_writable(book: dict):
    """An author-mode manuscript is the HUMAN's. Every machine writing door
    checks here first and refuses — a hard gate like the retired trailer
    lines, not a convention ([[scrpt-dual-paths]], Lars 2026-08-29)."""
    if (book.get("data") or {}).get("authorship") == "author":
        raise HTTPException(status_code=423, detail=(
            "This is the author's manuscript — SCRPT does not write, rewrite "
            "or restructure it. AI help arrives only as suggestions the "
            "author explicitly accepts."))


# ── work orders ──────────────────────────────────────────────────

@router.post("/workorder")
async def create_workorder(req: WorkOrderRequest):
    from ..prose.models import CHILDRENS_PRESETS
    preset = GENRE_PRESETS.get(req.genre_preset) or CHILDRENS_PRESETS.get(req.genre_preset)
    if not preset:
        raise HTTPException(400, f"Unknown genre preset: {req.genre_preset}")
    if preset["kind"] != req.kind.value:
        raise HTTPException(400, "Genre preset does not match book kind")

    n_total = max(1, req.series_books if req.series_title else 1)
    # the series can be PLANNED at five but COMMISSIONED one at a time —
    # later books join via /series/{id}/extend (Lars)
    n_books = n_total if not req.commission_books else max(1, min(n_total, req.commission_books))
    series_id = uuid.uuid4().hex[:8] if req.series_title else ""
    created = []

    for book_no in range(1, n_books + 1):
        # the publisher can hand each book its own plot; the series idea
        # always rides along as context. An empty slot = SCRPT plots it.
        per_book = (req.book_ideas[book_no - 1].strip()
                    if book_no - 1 < len(req.book_ideas) else "")
        idea = (f"{req.idea}\n\nTHIS BOOK (#{book_no} of the series): {per_book}"
                if per_book else req.idea)
        ms = Manuscript(
            kind=req.kind,
            genre_preset=req.genre_preset,
            idea=idea,
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
            "authorship": "author" if req.authorship == "author" else "house",
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
                "total_planned": n_total,
                "planned_titles": req.book_titles,
                "planned_ideas": req.book_ideas,
                "series_bible": "",
            } if series_id else {},
        }
        created.append(db.create_book(title, data))

    first = created[0]
    job_id = None
    if req.authorship == "author":
        # the author's book: SCRPT starts NO writing. The manuscript belongs
        # to the human ([[scrpt-dual-paths]]); covers and everything
        # downstream still serve them.
        req.auto_draft = False
        req.generate_plot_options = False
    if req.auto_draft:
        catalog = first["catalog_number"]
        if req.kind == BookKind.CHILDRENS:
            from ..writing.childrens import write_childrens_book
            job_id = start_job("childrens_book",
                               lambda h, c=catalog: write_childrens_book(c, h),
                               book_catalog=catalog)
        else:
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

    # Covers start the moment the book is commissioned — created from the
    # researched commissioning brief + cover direction, in parallel with the
    # writing. Needs a real title (it is baked into the art); the research
    # flow always provides one.
    cover_job_id = None
    title_ok = (first["title"] and not first["title"].lower().startswith("untitled")
                and len(first["title"]) <= 120
                and 1 not in req.covers_uploaded)   # the publisher's own cover wins
    if title_ok:
        from ..cover.front_cover import generate_cover_variants
        catalog = first["catalog_number"]

        async def cover_job(handle, c=catalog):
            handle.progress(0.08, "brief", "Art-directing from the commissioning brief")
            return await generate_cover_variants(
                c, 4, "",
                on_progress=lambda f, d: handle.progress(f, "creating", d))

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
            # a pen name belongs to the kind it writes: a thriller author has
            # no business appearing on a picture book
            "kind": (b["data"].get("kind")
                     or (b["data"].get("manuscript") or {}).get("kind") or "fiction"),
            "status": b["status"],
            "series_title": (b["data"].get("series") or {}).get("series_title", ""),
            "words": (b["data"].get("manuscript") or {}).get("word_count", 0),
        })
    out = []
    for n, bs in sorted(authors.items(), key=lambda kv: -len(kv[1])):
        kinds = sorted({b["kind"] for b in bs if b.get("kind")})
        out.append({"name": n, "books": bs, "kinds": kinds})
    return {"authors": out}


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
    working_title: str = ""


@router.post("/workorder/develop")
async def develop_workorder_idea(req: DevelopIdeaRequest):
    """Research & extend a rough idea into a commissioning package."""
    from ..writing.develop import develop_idea
    if not req.idea.strip():
        raise HTTPException(400, "Write the rough idea first")

    async def job(handle):
        handle.progress(0.15, "research", "Researching the market and developing the concept")
        return await develop_idea(req.kind.value, req.genre_preset,
                                  req.idea.strip(), req.series_books,
                                  working_title=req.working_title.strip())

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
    try:
        from ..writing.ledger import all_costs
        costs = all_costs()
        for b in result["books"]:
            b["production_cost_usd"] = costs.get(b.get("catalog_number"))
    except Exception:
        pass
    return {"books": result["books"], "total": result["total"]}


@router.get("/books/{catalog}")
def get_book(catalog: str):
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    return book


@router.post("/books/{catalog}/draft")
async def draft_book(catalog: str):
    """Start the full draft directly — the write-immediately path for a book
    commissioned as part of a series (books 2+ have their plot already)."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    _assert_machine_writable(book)
    ms = (book["data"].get("manuscript") or {})
    if (ms.get("chapters") or []):
        raise HTTPException(400, "This book already has a draft")
    if [j for j in list_jobs(catalog, active_only=True) if j["kind"] == "full_draft"]:
        raise HTTPException(400, "A draft is already running for this book")
    job_id = start_job("full_draft",
                       lambda h, c=catalog: wp.full_draft_job(h, c),
                       book_catalog=catalog)
    return {"job_id": job_id}


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
    _assert_machine_writable(book)
    job_id = start_job(
        "full_draft",
        lambda h: wp.full_draft_job(h, req.catalog_number, req.chosen_plot, req.edits),
        book_catalog=req.catalog_number,
    )
    return {"job_id": job_id}


@router.post("/acceptance/rulings/{catalog}")
async def run_rulings(catalog: str, body: dict = Body(default={})):
    """Publisher's rulings enforced manuscript-wide, then the editor re-reads.
    body: {rulings: [{chapters: [..], ruling: "..."}]}"""
    rulings = [r for r in (body.get("rulings") or []) if r.get("chapters") and r.get("ruling")]
    if not rulings:
        raise HTTPException(status_code=400, detail="No rulings")
    async def job(handle):
        from ..writing.acceptance import rulings_job
        return await rulings_job(handle, catalog, rulings)
    return {"job_id": start_job("acceptance", job, book_catalog=catalog)}


@router.post("/acceptance/{catalog}")
async def run_acceptance(catalog: str):
    """The acceptance desk on demand: length gate + managing-editor read
    (with bounded automated repair). Re-run any time — e.g. after a model
    upgrade, the whole catalog can be re-checked to the new standard."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    _assert_machine_writable(book)

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
            "book: who returns, what changes per installment - every installment "
            "a self-contained story a newcomer can start with - the repeatable "
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
            "supporting cast, world rules and tone, the per-book formula (each "
            "book SELF-CONTAINED: complete arc, real ending, no required prior "
            "reading - film-adaptable on its own), the timeline rule (the "
            "series moves forward in time: each book takes place after the "
            "previous one), and "
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
    _assert_machine_writable(book)
    if [j for j in list_jobs(catalog, active_only=True) if j["kind"] == "full_draft"]:
        raise HTTPException(409, "This book is already being written")

    data = dict(book["data"])
    old_ms = data.get("manuscript") or {}
    preset = GENRE_PRESETS.get(old_ms.get("genre_preset"), {})
    # A rewrite is held to TODAY'S standard: the genre's researched target,
    # never the old book's (early test books carried tiny targets). The live
    # market check then verifies it per book as usual.
    fresh = Manuscript(
        kind=BookKind(old_ms.get("kind", data.get("kind", "fiction"))),
        genre_preset=old_ms.get("genre_preset", "action_thriller"),
        idea=old_ms.get("idea", ""),
        target_words=preset.get("target_words") or old_ms.get("target_words") or 90000,
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


def _snapshot_manuscript(book: dict, reason: str = "edit") -> str:
    """Append-only manuscript snapshot — NOTHING is ever overwritten. Every
    save banks the PREVIOUS state first; restores bank too, so even a
    restore cannot destroy anything ([[scrpt-dual-paths]])."""
    import datetime as _dt, json as _json
    d = book.get("data") or {}
    vdir = Path(OUTPUT_DIR) / book["catalog_number"] / "versions"
    vdir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    f = vdir / f"ms-{ts}-{reason[:24]}.json"
    ms = d.get("manuscript") or {}
    f.write_text(_json.dumps(
        {"saved_at": ts, "reason": reason, "title": book.get("title"),
         "word_count": ms.get("word_count"), "manuscript": ms},
        ensure_ascii=False))
    return f.name


@router.post("/books/{catalog}/import-docx")
async def import_docx(catalog: str, file: UploadFile = File(...)):
    """Bring a manuscript home from Word / Google Docs / Pages (.docx).
    Heading 1 starts a chapter; italics survive; everything else arrives as
    clean paragraphs. The previous manuscript state is snapshotted first —
    switching to SCRPT must be simple AND safe (Lars, 2026-08-29)."""
    import io as _io, uuid as _uuid
    from docx import Document
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    d = book["data"]
    ms0 = d.get("manuscript") or {}
    if (ms0.get("chapters") and d.get("authorship") != "author"):
        raise HTTPException(400, (
            "This house-written book already has a manuscript. Imports "
            "replace the text, so they are allowed only on author-mode "
            "books or empty ones."))
    content = await file.read()
    try:
        doc = Document(_io.BytesIO(content))
    except Exception:
        raise HTTPException(400, "That file does not read as a .docx")

    def _runs_to_text(para):
        out = []
        for r in para.runs:
            t = r.text
            if not t:
                continue
            out.append(f"*{t}*" if r.italic else t)
        return "".join(out).strip() or para.text.strip()

    chapters, cur = [], None
    def _new_chapter(title=""):
        return {"id": _uuid.uuid4().hex[:12], "index": len(chapters) + 1,
                "title": title, "blocks": [], "status": "drafted",
                "word_count": 0}
    for para in doc.paragraphs:
        style = (para.style.name or "").lower() if para.style else ""
        text = _runs_to_text(para)
        if style.startswith("heading 1") or style == "title":
            if cur and (cur["blocks"] or cur["title"]):
                chapters.append(cur)
            cur = _new_chapter(para.text.strip())
            continue
        if not text:
            continue
        if cur is None:
            cur = _new_chapter()
        if style.startswith("heading"):
            cur["blocks"].append({"id": _uuid.uuid4().hex[:12],
                                  "type": "heading", "text": text, "level": 2})
        else:
            cur["blocks"].append({"id": _uuid.uuid4().hex[:12],
                                  "type": "paragraph", "text": text})
    if cur and (cur["blocks"] or cur["title"]):
        chapters.append(cur)
    if not chapters:
        raise HTTPException(400, "No readable text found in the document")
    for i, c in enumerate(chapters, 1):
        c["index"] = i
        c["word_count"] = sum(len(b.get("text", "").split()) for b in c["blocks"])

    _snapshot_manuscript(book, reason="before-docx-import")
    data = dict(d)
    ms = dict(ms0)
    ms["chapters"] = chapters
    ms["word_count"] = sum(c["word_count"] for c in chapters)
    ms["status"] = "drafting"
    data["manuscript"] = ms
    data.setdefault("authorship", "author")
    db.update_book(book["id"], data)
    _snapshot_manuscript(db.get_book_by_catalog(catalog), reason="docx-imported")
    return {"chapters": len(chapters), "words": ms["word_count"],
            "titles": [c["title"] or f"Chapter {c['index']}" for c in chapters][:30]}


@router.get("/books/{catalog}/versions")
def list_versions(catalog: str):
    """The version ledger — newest first."""
    import json as _json
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    vdir = Path(OUTPUT_DIR) / catalog / "versions"
    out = []
    for f in sorted(vdir.glob("ms-*.json"), reverse=True)[:200]:
        try:
            head = _json.loads(f.read_text())
            out.append({"file": f.name, "saved_at": head.get("saved_at"),
                        "reason": head.get("reason"),
                        "word_count": head.get("word_count")})
        except Exception:
            continue
    return {"versions": out}


@router.post("/books/{catalog}/versions/restore")
def restore_version(catalog: str, body: dict = Body(default={})):
    """Restore a snapshot — which itself snapshots the current state first."""
    import json as _json
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    name = str(body.get("file") or "")
    f = Path(OUTPUT_DIR) / catalog / "versions" / name
    if not (name.startswith("ms-") and name.endswith(".json") and f.exists()):
        raise HTTPException(404, "Version not found")
    snap = _json.loads(f.read_text())
    _snapshot_manuscript(book, reason="before-restore")
    data = dict(book["data"])
    data["manuscript"] = snap.get("manuscript") or {}
    db.update_book(book["id"], data)
    return {"restored": name}


@router.put("/chapter")
def save_chapter(req: ChapterEditRequest):
    """Persist studio edits to one chapter (full block replacement)."""
    book = db.get_book_by_catalog(req.catalog_number)
    if not book:
        raise HTTPException(404, "Book not found")
    _snapshot_manuscript(book, reason=f"chapter-{req.chapter_id[:8]}")
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
            "series_note": (
                f"Register in KDP Series Manager: series \"{series.get('series_title')}\", "
                f"book {series.get('book_number')}. Same series name on every installment - "
                "Amazon then builds the series page, shows 'Book "
                f"{series.get('book_number')} of {series.get('total_planned')}' on the "
                "listing, and cross-links all books with a whole-series buy option."
            ) if series.get("series_id") else "",
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
        handle.progress(0.75, "validate", "Validating against KDP rules")

        # The print wrap depends on the final page count, so it is built here,
        # automatically, in the house style: type matched to the front cover,
        # then the full back+spine+front wrap. Never leaves a book with a
        # stale spine width.
        try:
            from ..cover.typography import match_fonts
            handle.progress(0.85, "cover", "Matching cover typography")
            await match_fonts(catalog)
        except Exception as e:
            result["font_match_error"] = str(e)[:200]
        try:
            handle.progress(0.92, "cover", "Composing the print wrap")
            result["print_wrap"] = build_print_wrap(catalog)
        except Exception as e:
            result["wrap_error"] = str(e)[:200]
        # titled delivery copies: "<Title>-interior.pdf", "<Title>-cover.pdf"
        try:
            from ..config import write_delivery_copies
            bk = db.get_book_by_catalog(catalog)
            result["delivery_files"] = write_delivery_copies(catalog, bk["title"] if bk else catalog)
        except Exception as e:
            result["delivery_error"] = str(e)[:200]
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


@router.post("/cover/print-wrap/{catalog}")
def build_print_wrap(catalog: str):
    """Compose the final KDP print file: back + spine + front with bleed."""
    from ..cover.designer_package import compose_print_wrap
    from ..cover.front_cover import _series_line
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    d = book["data"]
    ms = d.get("manuscript") or {}
    rec = d.get("childrens") or {}
    words = sum(c.get("word_count", 0) for c in ms.get("chapters") or [])
    # A picture book has no chapters, so the words-per-page estimate produced
    # a ten-page book and a spine to match. Its extent is fixed by the format.
    if rec.get("spreads"):
        from ..prose.models import CHILDRENS_PRESETS
        cp = CHILDRENS_PRESETS.get(rec.get("preset") or "") or CHILDRENS_PRESETS["picture_book"]
        pages = (d.get("interior") or {}).get("page_count") or int(cp.get("pages") or 32)
    else:
        pages = (d.get("interior") or {}).get("page_count") or int(words / 280) + 10
    if pages % 2 == 1:
        # an odd export: add the final blank verso to the PDF itself, then carry on
        from ..interior.print_service import _pad_even
        pdf = OUTPUT_DIR / catalog / "interior.pdf"
        if pdf.exists():
            pages = _pad_even(str(pdf))
            interior = dict(d.get("interior") or {})
            interior["page_count"] = pages
            d["interior"] = interior
            db.update_book(book["id"], {**d})
        else:
            pages += 1
    label = GENRE_PRESETS.get(d.get("genre_preset", ""), {}).get("label", "")
    try:
        res = compose_print_wrap(
            catalog, book["title"], d.get("author_name") or "",
            d.get("back_cover_blurb") or d.get("description") or ms.get("blurb") or "",
            ms.get("tagline") or "", _series_line(book),
            (("An " if label[:1].upper() in "AEIOU" else "A ") + label)
            if label else "", pages,
            (d.get("format") or {}).get("trim_size") or d.get("trim_size") or "5.5x8.5",
            ((d.get("format") or {}).get("paper_type") or d.get("paper_type")
             or (((__import__("engine.prose.models", fromlist=["CHILDRENS_PRESETS"])
                   .CHILDRENS_PRESETS.get(rec.get("preset") or "")
                   or {}).get("paper")) if rec.get("spreads") else None)
             or "cream_bw"),
            genre_preset=d.get("genre_preset") or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    data = dict(db.get_book_by_catalog(catalog)["data"])
    cover = data.get("cover") or {}
    cover["print_wrap"] = {"path": res["path"], "pages_used": pages,
                           "estimated_pages": not bool((d.get("interior") or {}).get("page_count")),
                           "spec": res["spec"], "validation": res["validation"]}
    data["cover"] = cover
    db.update_book(book["id"], data)
    return cover["print_wrap"]


@router.post("/cover/print-wrap-preview/{catalog}")
def build_print_wrap_preview(catalog: str):
    """A proof copy of the wrap WITH a sample barcode drawn in, so the back
    can be judged as a real object. Written to cover-wrap-preview.pdf — the
    upload file (cover-wrap.pdf) is never touched, because Amazon prints its
    own barcode and a baked-in one would be rejected."""
    from ..cover.designer_package import compose_print_wrap
    from ..cover.front_cover import _series_line
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    d = book["data"]
    ms = d.get("manuscript") or {}
    words = sum(c.get("word_count", 0) for c in ms.get("chapters") or [])
    pages = (d.get("interior") or {}).get("page_count") or int(words / 280) + 10
    try:
        res = compose_print_wrap(
            catalog, book["title"], d.get("author_name") or "",
            d.get("back_cover_blurb") or d.get("description") or ms.get("blurb") or "",
            ms.get("tagline") or "", _series_line(book), "", pages,
            (d.get("format") or {}).get("trim_size") or d.get("trim_size") or "5.5x8.5",
            (d.get("format") or {}).get("paper_type") or d.get("paper_type") or "cream_bw",
            genre_preset=d.get("genre_preset") or "", preview_barcode=True,
            list_price=float(d.get("list_price") or 0),
            isbn=str((d.get("publishing") or {}).get("isbn") or ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"file": "cover-wrap-preview.pdf",
            "url": f"/api/files/{catalog}/cover-wrap-preview.pdf",
            "spec": res["spec"], "validation": res["validation"],
            "note": "Preview only — the upload file has no barcode."}


@router.get("/cover/wrap-image/{catalog}")
def cover_wrap_image(catalog: str, dpi: int = 220):
    """A PNG of the FULL wrap (with the preview barcode) for on-screen review.
    Rebuilt whenever the wrap PDF is newer than the cached image."""
    import fitz
    base = Path(OUTPUT_DIR) / catalog
    src = base / "cover-wrap-preview.pdf"
    if not src.exists():
        # fall back to building the preview, so the card always has something
        try:
            build_print_wrap_preview(catalog)
        except Exception:
            src = base / "cover-wrap.pdf"
    if not src.exists():
        raise HTTPException(404, "No print wrap yet")
    # render at the requested resolution; the viewer asks for a high dpi so the
    # full-size view is sharp, and each dpi is cached separately
    dpi = max(72, min(400, int(dpi)))
    png = base / f"cover-wrap-preview-{dpi}.png"
    if not png.exists() or png.stat().st_mtime < src.stat().st_mtime:
        doc = fitz.open(str(src))
        doc[0].get_pixmap(dpi=dpi).save(str(png))
        doc.close()
    return FileResponse(str(png), media_type="image/png")


@router.get("/cover/fact-sheet/{catalog}")
async def cover_fact_sheet(catalog: str):
    """The exact cover prompt — the six facts, nothing else — ready to paste
    into the publisher's own ChatGPT conversation."""
    from ..cover.front_cover import _cover_summary, _fact_brief
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    summary = await _cover_summary(book, ms)
    return {"prompt": _fact_brief(book, ms, summary)}


@router.post("/cover/install-art/{catalog}")
async def install_cover_art(catalog: str, file: UploadFile = File(...)):
    """Install a finished cover image (publisher-created, e.g. in ChatGPT)
    as the book's official front cover. Keeps the previous art on disk."""
    from ..cover.front_cover import _install_cover
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    content = await file.read()
    if not content or len(content) < 10_000:
        raise HTTPException(400, "That file does not look like a cover image")
    prev = Path(OUTPUT_DIR) / catalog / "cover-art.png"
    if prev.exists():
        (Path(OUTPUT_DIR) / catalog / "cover-art-previous.png").write_bytes(prev.read_bytes())
    result = _install_cover(catalog, content,
                            brief="Publisher-supplied artwork", mode="upload")
    return {"installed": True, "preview": result["preview"]}


@router.post("/cover/install-full/{catalog}")
async def install_full_cover(catalog: str, file: UploadFile = File(...)):
    """Install a finished FULL cover (back + spine + front), publisher-made or
    from the print-wrap composer, validated against KDP's computed spec.

    Kept as a separate file from the front cover: the front feeds ads and the
    ebook listing, the full wrap is what KDP's paperback upload needs.
    """
    from ..cover.designer_package import validate_uploaded_cover
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    content = await file.read()
    if not content or len(content) < 20_000:
        raise HTTPException(400, "That file does not look like a full cover")
    d = book["data"]
    ms = d.get("manuscript") or {}
    words = sum(c.get("word_count", 0) for c in ms.get("chapters") or [])
    pages = (d.get("interior") or {}).get("page_count") or int(words / 280) + 10
    trim = (d.get("format") or {}).get("trim_size") or d.get("trim_size") or "5.5x8.5"
    paper = (d.get("format") or {}).get("paper_type") or d.get("paper_type") or "cream_bw"
    fname = (file.filename or "cover-full.pdf").lower()
    ext = ".pdf" if fname.endswith(".pdf") else (".png" if fname.endswith(".png") else ".jpg")
    report = validate_uploaded_cover(content, fname, pages, trim, paper)
    dest = Path(OUTPUT_DIR) / catalog / f"cover-full{ext}"
    dest.write_bytes(content)
    data = dict(d)
    cover = dict(data.get("cover") or {})
    cover["full_cover"] = {"path": str(dest), "file": dest.name,
                           "mode": "upload", "validation": report,
                           "spec_pages": pages}
    data["cover"] = cover
    db.update_book(book["id"], data)
    return {"installed": True, "file": dest.name, "validation": report}


@router.get("/cover/files/{catalog}")
def cover_files(catalog: str):
    """The two cover deliverables a book carries: the front (ebook + ads) and
    the full wrap (KDP paperback)."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    base = Path(OUTPUT_DIR) / catalog
    cover = book["data"].get("cover") or {}

    def present(name):
        return (base / name).exists()

    front = None
    for n in ("cover-front.png", "cover-art.png"):
        if present(n):
            front = n
            break
    ebook = "ebook-cover.jpg" if present("ebook-cover.jpg") else None
    full = None
    fc = cover.get("full_cover") or {}
    if fc.get("file") and present(fc["file"]):
        full = fc["file"]
    elif present("cover-wrap.pdf"):
        full = "cover-wrap.pdf"
    return {
        "front": {"file": front, "ebook_jpg": ebook,
                  "url": f"/api/files/{catalog}/{front}" if front else None,
                  "ebook_url": f"/api/files/{catalog}/{ebook}" if ebook else None},
        "full": {"file": full,
                 "url": f"/api/files/{catalog}/{full}" if full else None,
                 "validation": fc.get("validation"),
                 "source": fc.get("mode") or ("composed" if full == "cover-wrap.pdf" else None)},
    }


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
            on_progress=lambda f, d: handle.progress(f, "creating", d))

    job_id = start_job("cover_variants", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/cover/series-suite/{catalog}")
async def series_cover_suite(catalog: str):
    """Create every missing cover in this book's series in one go — one
    design conversation, oldest first, each cover seeing all before it."""
    from ..cover.front_cover import generate_series_suite
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    if not (book["data"].get("series") or {}).get("series_id"):
        raise HTTPException(400, "This book is not part of a series")
    active = [j for j in list_jobs(active_only=True) if j["kind"] == "series_covers"]
    if active:
        return {"job_id": active[0]["id"], "already_running": True}

    async def job(handle):
        return await generate_series_suite(
            catalog, on_progress=lambda f, d: handle.progress(f, "creating", d))

    return {"job_id": start_job("series_covers", job, book_catalog=catalog)}


class SelectVariantRequest(BaseModel):
    index: int


@router.post("/cover/select-variant/{catalog}")
def select_variant(catalog: str, req: SelectVariantRequest):
    from ..cover.front_cover import select_cover_variant
    try:
        result = select_cover_variant(catalog, req.index)
    except ValueError as e:
        raise HTTPException(404, str(e))
    # a children's book with unillustrated spreads starts drawing the moment
    # the cover is picked — the cover sets the look, so nothing blocks the
    # interior any more and the publisher should not need a second click (Lars)
    book = db.get_book_by_catalog(catalog)
    d = (book or {}).get("data", {})
    kind = d.get("kind") or d.get("book_type")
    spreads = ((d.get("childrens") or {}).get("spreads")
               or d.get("spreads") or [])
    undrawn = [sp for sp in spreads
               if not ((sp.get("illustration") or {}).get("path") or sp.get("illustrated"))]
    if kind == "childrens" and spreads and undrawn:
        from ..writing.childrens import illustrate
        from ..writing.childrens_bible import build_bible

        async def _bible_then_draw(h, c=catalog):
            # the pipeline's own order: the bible reads the approved cover,
            # then every spread is drawn against the bible
            await build_bible(c, h)
            return await illustrate(c, None, h)

        result["illustrate_job_id"] = start_job(
            "childrens_art", _bible_then_draw, book_catalog=catalog)
    return result


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
    """Cast the narrator for this book (optionally as the house default).

    A series shares a narrator: one voice across the whole run is what makes
    it sound like one series, so casting a book casts every other book in it
    too. Books whose audiobook is already recorded keep their audio until
    they are re-recorded — only the casting changes."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")

    def _cast(b) -> None:
        d = dict(b["data"])
        audio = dict(d.get("audio") or {})
        audio["voice_id"] = req.voice_id
        audio["voice_name"] = req.voice_name
        d["audio"] = audio
        db.update_book(b["id"], d)

    _cast(book)

    siblings = []
    series = (book["data"].get("series") or {})
    sid = series.get("series_id")
    if sid:
        for other in db.list_books(per_page=500)["books"]:
            if other["catalog_number"] == catalog:
                continue
            if ((other["data"].get("series") or {}).get("series_id")) != sid:
                continue
            _cast(other)
            siblings.append(other["catalog_number"])

    if req.set_as_default:
        db.set_setting("elevenlabs_voice_id", req.voice_id)
        db.set_setting("elevenlabs_voice_name", req.voice_name)
    return {"success": True, "series": series.get("series_title") or "",
            "also_cast": siblings}


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


@router.get("/reports/overview")
def reports_overview(months: int = 24):
    from ..reports.importer import overview
    return overview(months)


@router.post("/reports/link")
def reports_link(body: dict = Body(default={})):
    """Tie a sold title/ASIN to a catalogue book by hand (or untie with catalog=null)."""
    from ..reports.importer import link_sale
    key = (body.get("key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key (title or ASIN) is required")
    return link_sale(key, body.get("catalog") or None)


@router.post("/reports/fx")
def reports_fx(body: dict = Body(default={})):
    """Base currency and the rates table (units per 1 USD)."""
    from ..reports.importer import set_fx
    return set_fx(body.get("base"), body.get("rates"))


@router.get("/reports/sync")
def reports_sync_status():
    from ..reports.sync import settings as sync_settings
    return sync_settings()


@router.post("/reports/sync")
async def reports_sync_run(body: dict = Body(default={})):
    """Run the KDP report sync now (never signs in). body: {backfill?: bool}"""
    from ..reports.sync import run_sync
    async def job(handle):
        handle.progress(0.1, "sync", "opening the KDP reports in your signed-in session")
        return await run_sync(body.get("backfill"))
    return {"job_id": start_job("kdp_sync", job)}


@router.post("/reports/sync/settings")
def reports_sync_configure(body: dict = Body(default={})):
    from ..reports.sync import configure
    return configure(body)


@router.post("/reports/sync/login")
async def reports_sync_login():
    """Open a visible browser at KDP so the publisher signs in by hand."""
    from ..market.kdp import open_login
    return await open_login()


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


@router.post("/simplify/{catalog}")
async def simplify_book_endpoint(catalog: str):
    """Book-wide readability pass — every dense chapter rewritten for an
    effortless read, story untouched."""
    from ..writing.quality import simplify_book
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")

    async def job(handle):
        handle.progress(0.02, "simplify", "Measuring every chapter")
        return await simplify_book(catalog, handle)

    return {"job_id": start_job("simplify", job, book_catalog=catalog)}


# ── book trailers ────────────────────────────────────────────────
# Two productions: "full" (veo3.1_fast, native audio) and "voiceover"
# (gen4_turbo silent shots carried by the trailer voice + score). Both end
# on the cover card with the call to action.

@router.get("/trailer/{catalog}")
async def trailer_status(catalog: str):
    from ..trailer import runway as _runway
    from ..trailer.producer import MODES, OUTPUT_DIR as _OUT
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    t = book["data"].get("trailer") or {}
    out = _OUT / catalog
    conn = await _runway.check_connection()
    tr_ = t.get("treatment") or {}
    shots = tr_.get("plates") or tr_.get("shots") or []
    n_pl = len(shots) or 6
    n_ins = len(tr_.get("inserts") or []) or 6
    cuts_ = tr_.get("cuts") or []
    secs = sum(float(c.get("seconds") or 2.5) for c in cuts_) or 30
    total_secs = int(secs) + 6                # the edit + end card
    estimates = {
        # master: 8 s veo3.1 plates w/ audio (40 cr/s), ~2 inspected stills each, cheap inserts,
        # two portrait plates, two cues — plus one reshoot round on average
        "full": int(n_pl * (8 * 40 + 16) * 1.25 + n_ins * 12 + 60),
        "draft": int(n_pl * (8 * 10 + 10) * 1.25 + n_ins * 12 + 40),   # silent veo_fast 720p
        "voiceover": int(secs * 5 + 20),
        "finish_4k": int(total_secs * 24 * 0.012 / 0.01) + 2,   # per-frame lab bill
    }
    prod = t.get("production") or {}
    latest_file = prod.get("file") or "trailer.mp4"
    latest_poster = prod.get("poster") or "trailer-poster.jpg"
    versions = []
    for v in (t.get("versions") or []):
        f = out / f"trailer-v{v['n']}.mp4"
        if f.exists():
            versions.append({**v,
                "url": f"/api/files/{catalog}/trailer-v{v['n']}.mp4",
                "poster_url": f"/api/files/{catalog}/trailer-v{v['n']}.jpg"
                              if (out / f"trailer-v{v['n']}.jpg").exists() else None})
    return {
        "treatment": t.get("treatment"),
        "world_style": t.get("world_style"),
        "production": t.get("production"),
        "approved": bool(t.get("approved")),
        "finish": t.get("finish"),
        "direction": t.get("direction"),
        "review": t.get("review"),
        "workorder_prompt": t.get("workorder_prompt"),
        "voice": t.get("voice"),
        "reference": ({k: v for k, v in (t.get("reference") or {}).items() if k != "transcript"}
                      if t.get("reference") else None),
        "storyboard_pending": ({"panels": len((t.get("storyboard_pending") or {}).get("panels") or []),
                                "source": t.get("storyboard_pending_source") or ""}
                               if t.get("storyboard_pending") else None),
        # The cast sheet and the board, in full — the publisher should be able
        # to SEE what the trailer was built from, and judge it, without going
        # to the database. Pictures are addressed through /api/files.
        "bibles": {
            kind: {
                "source": (b or {}).get("source") or "",
                "style": (b or {}).get("style") or "",
                "characters": [
                    {**c,
                     "plate_url": (f"/api/files/{catalog}/trailer/{c['plate']}"
                                   if c.get("plate") else None),
                     "locked": bool(c.get("locked")),
                     "variant_urls": [f"/api/files/{catalog}/trailer/{v}"
                                      for v in (c.get("variants") or [])]}
                    for c in ((b or {}).get("characters") or [])
                ],
                "locations": (b or {}).get("locations") or [],
            } if b else None
            for kind, b in ((k, (book["data"].get("bibles") or {}).get(k))
                            for k in ("main", "supporting"))
        },
        "storyboard": ({
            "panels": [
                # the URL carries the file's own mtime, so a redrawn frame can
                # NEVER display stale from the browser cache (Lars, 2026-08-29:
                # three "failed" redraws were all cache)
                {**p, "frame_url": ((lambda fp: f"/api/files/{catalog}/trailer/{p['frame']}?v="
                                    + str(int(fp.stat().st_mtime)) if fp.exists()
                                    else None)(Path(OUTPUT_DIR) / catalog / "trailer" / p["frame"])
                                    if p.get("frame") else None)}
                for p in ((t.get("storyboard") or {}).get("panels") or [])
            ],
            "music": (t.get("storyboard") or {}).get("music") or "",
            "count": len((t.get("storyboard") or {}).get("panels") or []),
        } if t.get("storyboard") else None),
        "versions": versions,
        "has_video": (out / latest_file).exists(),
        # the latest reel is a mutable file: stamp its address with the
        # cut's mtime so a browser can never replay a stale cached copy
        "video_url": (f"/api/files/{catalog}/{latest_file}"
                      f"?v={int((out / latest_file).stat().st_mtime)}")
                     if (out / latest_file).exists() else None,
        "poster_url": (f"/api/files/{catalog}/{latest_poster}"
                       f"?v={int((out / latest_poster).stat().st_mtime)}")
                      if (out / latest_poster).exists() else None,
        "runway": {"connected": conn.get("connected"),
                   "credits": conn.get("credits")},
        "estimates": estimates,
        "modes": list(MODES.keys()),
    }


@router.post("/trailer/script/{catalog}")
async def trailer_script(catalog: str, body: dict = Body(default={})):
    """Rewrite the storyboard's WORDS (vo, lines, sounds, music) from the
    book — shots stay locked. The storyboard-first meaning of 'rewrite
    full script'."""
    from ..trailer.bible import rewrite_board_script
    if not db.get_book_by_catalog(catalog):
        raise HTTPException(404, "Book not found")
    brief = str(body.get("brief") or "")
    return {"job_id": start_job("trailer_script",
                                lambda h: rewrite_board_script(catalog, brief, h),
                                book_catalog=catalog)}


@router.post("/trailer/treatment/{catalog}")
async def trailer_treatment(catalog: str, body: dict = Body(default={})):
    raise HTTPException(status_code=410, detail=(
        "Retired. Trailers have ONE production line: character bible from "
        "plot + cover, then the storyboard, then the shoot from board + "
        "bible, closing on the cover."))
    """(Re)write the treatment — reviewable before any credits are spent.
    An optional `brief` is the publisher's own description of the trailer
    they want; the director follows it over everything else."""
    from ..trailer.director import write_treatment
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    brief = (body.get("brief") or "").strip()

    async def job(handle):
        result = await write_treatment(catalog, brief=brief)
        fresh = db.get_book_by_catalog(catalog)
        data = dict(fresh["data"])
        tr = dict(data.get("trailer") or {})
        tr["approved"] = False          # new words need a new okay
        if brief:
            tr["brief"] = brief
        data["trailer"] = tr
        db.update_book(fresh["id"], data)
        return result

    job_id = start_job("trailer_treatment", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/trailer/edit/{catalog}")
async def trailer_edit(catalog: str, body: dict = Body(default={})):
    """Save the publisher's edits to the screenplay: voice-over lines and
    the tagline. `approved: true` marks the script okayed for production;
    any content change clears a previous approval unless it is re-given
    in the same call."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    data = dict(book["data"])
    tr = dict(data.get("trailer") or {})
    treatment = dict(tr.get("treatment") or {})
    if not treatment:
        raise HTTPException(status_code=400, detail="No treatment to edit")

    changed = False
    if isinstance(body.get("shots"), list):
        by_n = {s.get("n"): s for s in body["shots"] if isinstance(s, dict)}
        shots = [dict(s) for s in (treatment.get("shots") or [])]
        for shot in shots:
            edit = by_n.get(shot.get("n"))
            if not edit:
                continue
            for f in ("voiceover", "prompt", "sound", "camera"):
                if f in edit and edit[f] != shot.get(f):
                    shot[f] = edit[f]
                    changed = True
        treatment["shots"] = shots
    for field in ("end_card_text", "concept", "music"):
        if field in body and body[field] != treatment.get(field):
            treatment[field] = body[field]
            changed = True

    tr["treatment"] = treatment
    tr["approved"] = bool(body.get("approved")) if ("approved" in body or changed)         else tr.get("approved", False)
    data["trailer"] = tr
    db.update_book(book["id"], data)
    return {"saved": True, "approved": tr["approved"]}


@router.post("/trailer/produce/{catalog}")
async def trailer_produce(catalog: str, body: dict = Body(default={})):
    """Shoot, record and cut the trailer. Long job; polls like any other."""
    from ..trailer import runway as _runway
    from ..trailer.producer import produce, MODES, FORMATS
    mode = (body.get("mode") or "full").strip()
    fmt = (body.get("format") or "wide").strip()
    if mode not in MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {list(MODES)}")
    if fmt not in FORMATS:
        raise HTTPException(status_code=400, detail=f"format must be one of {list(FORMATS)}")
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not _runway.configured():
        raise HTTPException(status_code=400, detail="Runway is not connected")
    tr = book["data"].get("trailer") or {}
    # ── RETIRED LINE (Lars, 2026-08-29): this endpoint fed the treatment
    # production line, which invents its own script. Closed, no override.
    raise HTTPException(status_code=410, detail=(
        "The treatment production line is retired. Trailers are built ONLY "
        "from the book's storyboard — use the trailer work-order / "
        "storyboard path."))
    if tr.get("treatment") and not tr.get("approved") and not body.get("force"):
        raise HTTPException(status_code=400,
                            detail="The script is not approved yet — okay the "
                                   "voice-over and tagline in the screenplay "
                                   "first (or pass force).")

    fresh = bool(body.get("fresh"))

    async def job(handle):
        return await produce(catalog, mode, format_name=fmt, fresh=fresh,
                             handle=handle)

    job_id = start_job("trailer_produce", job, book_catalog=catalog)
    return {"job_id": job_id, "mode": mode, "format": fmt}


# ── the automatic trailer ────────────────────────────────────────
# The publisher's order, run end to end: book + cover -> character bibles ->
# storyboard -> trailer. Each stage is skipped if the house already has it, so
# a re-run costs nothing for work already done and an edited board is never
# overwritten.

@router.post("/trailer/auto/{catalog}")
async def trailer_auto(catalog: str, body: dict = Body(default={})):
    """One button: bibles, board, trailer. body: {format?, rebuild_board?, panels?}"""
    from ..trailer.bible import auto_storyboard, ensure_bibles
    from ..trailer.producer import produce_storyboard
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    fmt = (body.get("format") or "wide").strip()
    rebuild = bool(body.get("rebuild_board"))
    panels = int(body.get("panels") or 9)

    async def job(handle):
        class _Sub:
            """Scale a stage's own progress into a slice of the whole run."""
            def __init__(self, lo, hi): self.lo, self.hi = lo, hi
            def progress(self, f, stage="", detail=""):
                handle.progress(self.lo + (self.hi - self.lo) * min(1.0, max(0.0, f)), stage, detail)
            def cancelled(self): return handle.cancelled()

        from ..trailer.plates import draw_board_plates, draw_cast_plates

        handle.progress(0.02, "bible", "checking the cast sheet")
        await ensure_bibles(catalog, _Sub(0.02, 0.12))

        # Draw the cast. A written description cannot hold a face: every shot
        # reads the same words and invents a different person, which is how a
        # nine-shot trailer came back with nine different leads. These
        # portraits are handed to the camera as references so the same man
        # walks through the whole film.
        handle.progress(0.12, "cast", "drawing the cast sheet")
        cast_plates = (await draw_cast_plates(catalog, _Sub(0.12, 0.26))).get("plates") or {}

        fresh = db.get_book_by_catalog(catalog)
        board = ((fresh["data"].get("trailer") or {}).get("storyboard"))
        if rebuild or not board:
            board = await auto_storyboard(catalog, panels=panels, handle=_Sub(0.26, 0.36))
        else:
            handle.progress(0.36, "board", "using the storyboard already on the book")

        # The shoot looks up references here, by character name.
        board["characters"] = {**(board.get("characters") or {}), **cast_plates}

        handle.progress(0.38, "board", "drawing the storyboard")
        try:
            await draw_board_plates(catalog, board, _Sub(0.38, 0.50))
        except Exception as e:                    # a board picture is for us to
            handle.progress(0.50, "board", f"board art skipped: {str(e)[:70]}")  # look at, not to shoot

        data = dict(db.get_book_by_catalog(catalog)["data"])
        data["trailer"] = {**(data.get("trailer") or {}), "storyboard": board}
        db.update_book(db.get_book_by_catalog(catalog)["id"], data)

        return await produce_storyboard(catalog, board, format_name=fmt, handle=_Sub(0.50, 1.0))

    return {"job_id": start_job("trailer_produce", job, book_catalog=catalog)}


@router.post("/trailer/storyboard/auto/{catalog}")
async def trailer_board_auto(catalog: str, body: dict = Body(default={})):
    """Write (or rewrite) just the storyboard, so it can be read and edited
    before a single credit is spent on filming it."""
    from ..trailer.bible import auto_storyboard, ensure_bibles
    if not db.get_book_by_catalog(catalog):
        raise HTTPException(404, "Book not found")
    panels = int(body.get("panels") or 9)

    async def job(handle):
        await ensure_bibles(catalog, handle)
        return await auto_storyboard(catalog, panels=panels, handle=handle)

    return {"job_id": start_job("trailer_board", job, book_catalog=catalog)}


# ── children's books ─────────────────────────────────────────────

@router.get("/childrens/{catalog}")
def childrens_get(catalog: str):
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    return book["data"].get("childrens") or {}


@router.post("/childrens/{catalog}")
async def childrens_write(catalog: str):
    """Write (or rewrite) the whole picture book — spreads, text and art briefs."""
    from ..writing.childrens import write_childrens_book
    if not db.get_book_by_catalog(catalog):
        raise HTTPException(404, "Book not found")
    return {"job_id": start_job("childrens_book",
                                lambda h: write_childrens_book(catalog, h),
                                book_catalog=catalog)}


@router.get("/childrens/{catalog}/layout/{n}")
def childrens_layout_options(catalog: str, n: int):
    """The placements available for this spread, best first."""
    from pathlib import Path as _P
    from PIL import Image
    from ..interior.childrens_interior import zone_candidates, _spec
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    rec = book["data"].get("childrens") or {}
    art = (rec.get("art") or {}).get(str(n))
    if not art:
        raise HTTPException(400, "That spread is not drawn yet")
    img = _P(OUTPUT_DIR) / catalog / art
    if not img.exists():
        raise HTTPException(404, "Artwork missing")
    sp = _spec(rec, book)
    dpi = 300
    safe_px = int((sp["bleed"] + sp["safe"]) * dpi)
    spread = next((x for x in (rec.get("spreads") or []) if x["n"] == n), None)
    words = len((spread or {}).get("text", "").split())
    est_lines = max(1, int(words / 7) + 1)
    im = Image.open(img).convert("RGB")
    cands = zone_candidates(im, safe_px, est_lines, 60,
                            rec.get("layout_prefs") or {})
    # one per position, not every width variant — the editor picks a place
    seen, top = set(), []
    for c in cands:
        pos = f"{c['band']}-{c['column']}"
        if pos in seen:
            continue
        seen.add(pos); top.append(c)
        if len(top) >= 8:
            break
    return {"spread": n, "chosen": (rec.get("layout") or {}).get(str(n)),
            "auto": (rec.get("layout_used") or {}).get(str(n)),
            "options": top}


@router.post("/childrens/{catalog}/layout/{n}")
def childrens_set_layout(catalog: str, n: int, body: dict = Body(default={})):
    """Pin a placement for one spread — and learn from the correction.

    Every manual move is a signal about house taste: the position the editor
    moved TO gains weight for future books, the one they moved AWAY from
    loses a little. That is how the layout gets better as we make books."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    d = dict(book["data"]); rec = dict(d.get("childrens") or {})
    key = (body.get("key") or "").strip()
    page = (body.get("page") or "").strip() or None
    layout = dict(rec.get("layout") or {})
    prefs = dict(rec.get("layout_prefs") or {})

    if not key:                                  # back to the automatic choice
        layout.pop(str(n), None)
    else:
        was = ((rec.get("layout_used") or {}).get(str(n)) or {}).get("key")
        layout[str(n)] = {"key": key, "page": page}
        prefs[key] = round(float(prefs.get(key, 0.0)) + 0.25, 3)
        if was and was != key:
            prefs[was] = round(float(prefs.get(was, 0.0)) - 0.15, 3)

    rec["layout"] = layout
    rec["layout_prefs"] = prefs
    d["childrens"] = rec
    db.update_book(book["id"], d)
    # taste carries across books, not just this one
    house = db.get_setting("childrens_layout_prefs", {}) or {}
    for k, v in prefs.items():
        house[k] = round(float(house.get(k, 0.0)) * 0.9 + v * 0.1, 3)
    db.set_setting("childrens_layout_prefs", house)
    return {"layout": layout.get(str(n)), "prefs": prefs}


@router.get("/childrens/{catalog}/pages")
def childrens_pages(catalog: str):
    """How many pages the built interior actually has."""
    import fitz
    pdf = OUTPUT_DIR / catalog / "interior.pdf"
    if not pdf.exists():
        return {"pages": 0, "built": False}
    with fitz.open(str(pdf)) as d:
        n = d.page_count
    return {"pages": n, "built": True, "divisible_by_8": n % 8 == 0}


@router.get("/childrens/{catalog}/page/{n}.png")
def childrens_page_image(catalog: str, n: int, dpi: int = 90):
    """One page of the built interior, rendered.

    The read-through used to reassemble the book from the spread artwork,
    which meant it showed a book that did not exist — no front matter, no
    blanks, no real pagination. This serves the PRINT FILE itself, so what
    is on screen is exactly what goes to KDP."""
    import fitz
    from fastapi.responses import Response
    pdf = OUTPUT_DIR / catalog / "interior.pdf"
    if not pdf.exists():
        raise HTTPException(404, "Interior not built yet")
    with fitz.open(str(pdf)) as d:
        if n < 1 or n > d.page_count:
            raise HTTPException(404, "No such page")
        pix = d[n - 1].get_pixmap(dpi=max(40, min(200, dpi)))
        png = pix.tobytes("png")
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.post("/childrens/{catalog}/interior")
async def childrens_interior(catalog: str):
    """Build the print-ready interior PDF for a picture book.

    Full-bleed art at trim + bleed, words inside the safe margin and clear of
    the gutter, padded to a page count the binder accepts."""
    from ..interior.childrens_interior import build_interior
    if not db.get_book_by_catalog(catalog):
        raise HTTPException(404, "Book not found")
    return {"job_id": start_job("childrens_interior",
                                lambda h: build_interior(catalog, h),
                                book_catalog=catalog)}


@router.get("/childrens/{catalog}/bible")
def childrens_bible_get(catalog: str):
    """The character bible and the scenery bible for this book."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    rec = book["data"].get("childrens") or {}
    bible = rec.get("bible") or {}
    return {"bible": bible, "plates": rec.get("plates") or [],
            "has": bool(bible.get("characters") or bible.get("settings"))}


@router.post("/childrens/{catalog}/bible")
async def childrens_bible_build(catalog: str, body: dict = Body(default={})):
    """Write the bibles — or extend the series bible this book inherits."""
    from ..writing.childrens_bible import build_bible
    if not db.get_book_by_catalog(catalog):
        raise HTTPException(404, "Book not found")
    rebuild = bool(body.get("rebuild"))
    return {"job_id": start_job("childrens_bible",
                                lambda h: build_bible(catalog, h, rebuild),
                                book_catalog=catalog)}


@router.post("/childrens/{catalog}/bible/plates")
async def childrens_bible_plates(catalog: str, body: dict = Body(default={})):
    """Draw the character turnaround sheets and the location plates."""
    from ..writing.childrens_bible import draw_plates
    if not db.get_book_by_catalog(catalog):
        raise HTTPException(404, "Book not found")
    only = (body.get("name") or "").strip() or None
    return {"job_id": start_job("childrens_plates",
                                lambda h: draw_plates(catalog, only, h),
                                book_catalog=catalog)}


@router.post("/childrens/{catalog}/illustrate")
async def childrens_illustrate(catalog: str, body: dict = Body(default={})):
    """Draw the spreads with gpt-image-1. Spread 1 sets the look and every
    later spread is drawn as an edit against it, so the characters hold."""
    from ..writing.childrens import illustrate
    if not db.get_book_by_catalog(catalog):
        raise HTTPException(404, "Book not found")
    only = body.get("spread")
    only = int(only) if only else None
    return {"job_id": start_job("childrens_art",
                                lambda h: illustrate(catalog, only, h),
                                book_catalog=catalog)}


# ── character bibles ─────────────────────────────────────────────
# The cast, held as canon. Uploaded as a sheet, transcribed once, then every
# trailer panel (and later every film scene) that names a character gets that
# character's exact wording — the only reliable cure for drift.

@router.get("/bible/{catalog}")
def bible_status(catalog: str):
    from ..trailer.bible import cast_of, world_of, KINDS
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    bibles = (book["data"].get("bibles") or {})
    out = {}
    for k in KINDS:
        b = bibles.get(k)
        out[k] = ({"characters": b.get("characters") or [],
                   "locations": b.get("locations") or [],
                   "style": b.get("style") or "", "tone": b.get("tone") or "",
                   "source": b.get("source") or ""} if b else None)
    return {"bibles": out, "cast": cast_of(book), "world": world_of(book)}


@router.post("/bible/{catalog}")
async def bible_upload(catalog: str, kind: str = "main", file: UploadFile = File(...)):
    """Upload a character-bible sheet. kind=main|supporting."""
    from ..trailer.bible import KINDS, parse_bible, save_bible
    if kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {KINDS}")
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    if not (file.content_type or "").lower().startswith("image/"):
        raise HTTPException(400, "Upload an image of the character bible (PNG or JPG)")
    blob = await file.read()
    if len(blob) > 20 * 1024 * 1024:
        raise HTTPException(400, "That image is too large (20MB max)")

    async def job(handle):
        handle.progress(0.2, "reading", f"reading the {kind} character bible")
        fresh = db.get_book_by_catalog(catalog)
        rec = await parse_bible(blob, fresh, kind)
        save_bible(catalog, kind, rec, file.filename or "bible.png")
        return {"characters": len(rec["characters"]), "locations": len(rec["locations"])}

    return {"job_id": start_job("character_bible", job, book_catalog=catalog)}


@router.delete("/bible/{catalog}")
def bible_delete(catalog: str, kind: str = "main"):
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    data = dict(book["data"]); bibles = dict(data.get("bibles") or {})
    bibles.pop(kind, None)
    data["bibles"] = bibles
    db.update_book(book["id"], data)
    return {"ok": True}


# ── the model bench ──────────────────────────────────────────────
# Asked live of Anthropic, so a model published tomorrow appears in the
# dropdown tomorrow without SCRPT being touched.

@router.get("/models")
async def writing_models():
    from ..writing.client import client as _client, DEFAULT_MODEL
    current = db.get_setting("writing_model", "") or DEFAULT_MODEL
    models, error = [], ""
    try:
        listed = await _client().models.list(limit=50)
        for m in listed.data:
            models.append({"id": m.id,
                           "name": getattr(m, "display_name", "") or m.id})
    except Exception as e:
        error = str(e)[:200]
    # whatever is configured must always be selectable, even if the account
    # cannot list models right now
    if current and not any(m["id"] == current for m in models):
        models.insert(0, {"id": current, "name": current})
    return {"models": models, "current": current,
            "mechanical": db.get_setting("mechanical_model", "") or current,
            "assistant": db.get_setting("assistant_model", "") or "claude-haiku-4-5",
            "error": error}


# ── the house ident ──────────────────────────────────────────────
# The short audio logo every audiobook opens on. Named after the Copyright
# holder in Settings, so a brand-new SCRPT install gets its own automatically.

@router.get("/audiobook/ident")
def audiobook_ident_status():
    from ..audio import ident as _id
    exists = _id.IDENT.exists() and _id.IDENT.stat().st_size > 10_000
    vid, vname = _id.ident_voice()
    return {
        "house": _id.house_name(),
        "line": _id.ident_line(),
        "voice_id": vid, "voice_name": vname,
        "exists": exists,
        "current": _id.is_current(),
        "seconds": round(_id._seconds(_id.IDENT), 2) if exists else None,
        "url": f"/api/scrpt/audiobook/ident/audio?v={int(_id.IDENT.stat().st_mtime)}" if exists else None,
        "voices": _id.IDENT_VOICES,
    }


@router.get("/audiobook/ident/audio")
def audiobook_ident_audio():
    from ..audio import ident as _id
    if not _id.IDENT.exists():
        raise HTTPException(404, "No ident yet")
    return FileResponse(str(_id.IDENT), media_type="audio/mpeg", filename="audiobook-intro.mp3")


@router.post("/audiobook/ident")
async def audiobook_ident_build(body: dict = Body(default={})):
    """Make (or remake) the house ident. body: {line?, voice_id?, force?}"""
    from ..audio import ident as _id
    line = (body.get("line") or "").strip()
    voice_id = (body.get("voice_id") or "").strip()
    if line:
        db.set_setting("audiobook_ident_line", line)
    if voice_id:
        db.set_setting("audiobook_ident_voice_id", voice_id)
        for v in _id.IDENT_VOICES:
            if v["id"] == voice_id:
                db.set_setting("audiobook_ident_voice_name", v["name"])
    try:
        return await _id.build_ident(force=bool(body.get("force", True)))
    except Exception as e:
        raise HTTPException(400, str(e)[:300])


# ── audiobook opening preview ────────────────────────────────────
# A few minutes of chapter one read by the house narrator voice: hear the
# audiobook AND quality-check the opening by ear before anything ships.

@router.get("/audiobook/preview/{catalog}")
async def audiobook_preview_status(catalog: str):
    from .. import audiobook as ab
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    rec = ((book["data"].get("audiobook") or {}).get("preview"))
    ch_rec = ((book["data"].get("audiobook") or {}).get("chapter1"))
    mp3 = OUTPUT_DIR / catalog / "audiobook-preview.mp3"
    ch_mp3 = OUTPUT_DIR / catalog / "audiobook-chapter1.mp3"
    chapter_chars = None
    try:
        chapter_chars = ab.chapter_text(catalog)["chars"]
    except Exception:
        pass
    voice_id, voice_name = ab.narrator_voice(book)
    # the cast voice's own audition clip, so the bench can be heard here
    voice_preview = None
    try:
        import httpx
        key = db.get_setting("elevenlabs_api_key", "")
        if key:
            async with httpx.AsyncClient(timeout=15) as c:
                rv = await c.get(f"https://api.elevenlabs.io/v1/voices/{voice_id}", headers={"xi-api-key": key})
            if rv.status_code == 200:
                voice_preview = rv.json().get("preview_url")
    except Exception:
        pass
    def stamped(p):
        return f"/api/files/{catalog}/{p.name}?v={int(p.stat().st_mtime)}" if p.exists() else None
    live = None
    live_file = OUTPUT_DIR / catalog / "audio-preview" / "live.json"
    if live_file.exists():
        try:
            import json as _json
            lj = _json.loads(live_file.read_text())
            live = {**lj, "urls": [f"/api/files/{catalog}/audio-preview/{n}?v={int((live_file.parent / n).stat().st_mtime)}"
                                   for n in lj.get("parts", []) if (live_file.parent / n).exists()]}
        except Exception:
            live = None
    return {
        "preview": rec, "chapter1": ch_rec, "live": live,
        "has_audio": mp3.exists(), "audio_url": stamped(mp3),
        "chapter_url": stamped(ch_mp3),
        "voice": voice_name, "voice_id": voice_id, "voice_preview_url": voice_preview,
        "chapter_chars": chapter_chars,
        "chapter_minutes": round(chapter_chars / 900, 1) if chapter_chars else None,   # ~900 chars/min read
    }


@router.post("/audiobook/preview/{catalog}")
async def audiobook_preview_generate(catalog: str, body: dict = Body(default={})):
    from .. import audiobook as ab
    from ..trailer import runway as _runway
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not _runway.configured():
        raise HTTPException(status_code=400, detail="Runway is not connected")

    scope = (body.get("scope") or "opening").strip()

    async def job(handle):
        if scope == "chapter":
            return await ab.record_chapter(catalog, handle=handle)
        return await ab.preview(catalog, handle=handle)

    job_id = start_job("audiobook_preview", job, book_catalog=catalog)
    return {"job_id": job_id, "scope": scope}


@router.post("/trailer/finish/{catalog}")
async def trailer_finish(catalog: str, body: dict = Body(default={})):
    """Finish the approved master in 4K (or 2K) via the upscale lab."""
    from ..trailer import runway as _runway
    from ..trailer.producer import finish_4k
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not _runway.configured():
        raise HTTPException(status_code=400, detail="Runway is not connected")
    resolution = (body.get("resolution") or "4k").strip()
    if resolution not in ("2k", "4k"):
        raise HTTPException(status_code=400, detail="resolution must be 2k or 4k")

    async def job(handle):
        return await finish_4k(catalog, resolution=resolution, handle=handle)

    job_id = start_job("trailer_finish", job, book_catalog=catalog)
    return {"job_id": job_id, "resolution": resolution}


@router.post("/trailer/line/{catalog}")
async def trailer_rewrite_line(catalog: str, body: dict = Body(default={})):
    """Punch-up desk: four alternative reads for one VO line or the tagline."""
    from ..trailer.director import rewrite_line
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        suggestions = await rewrite_line(
            catalog, shot_n=int(body.get("n") or 0),
            tagline=bool(body.get("tagline")),
            field=(body.get("field") or "voiceover"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"suggestions": suggestions}


# ── trailer voice casting ────────────────────────────────────────

@router.get("/trailer/voices/{catalog}")
async def trailer_voices(catalog: str):
    """The trailer voice bench: the publisher's ElevenLabs bank with
    audition clips, plus which voice is currently cast for this book."""
    import httpx
    from ..trailer.producer import trailer_voice
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    api_key = db.get_setting("elevenlabs_api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="ElevenLabs is not configured")
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.get("https://api.elevenlabs.io/v1/voices",
                           headers={"xi-api-key": api_key})
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Could not reach the voice bank")
    voices = [{"id": v["voice_id"], "name": v["name"],
               "category": v.get("category"),
               "preview_url": v.get("preview_url")}
              for v in resp.json().get("voices", [])]
    cur_id, cur_name = trailer_voice(book["data"].get("genre_preset") or "", catalog)
    return {"voices": voices, "current": {"id": cur_id, "name": cur_name}}


@router.post("/trailer/voice/{catalog}")
async def trailer_cast_voice(catalog: str, body: dict = Body(default={})):
    """Cast the trailer narrator for this book. The take ledger keys voice
    into every recording, so a recast re-records all the lines — nothing
    else — on the next production."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    voice_id = (body.get("voice_id") or "").strip()
    if not voice_id:
        raise HTTPException(status_code=400, detail="voice_id is required")
    body["auto"] = False          # a hand-cast narrator is never overruled by the director
    data = dict(book["data"])
    tr = dict(data.get("trailer") or {})
    tr["voice"] = {"id": voice_id, "name": (body.get("name") or "").strip(), "auto": False}
    data["trailer"] = tr
    db.update_book(book["id"], data)
    return {"cast": tr["voice"]}


@router.post("/trailer/shot/insert/{catalog}")
async def trailer_insert_shot(catalog: str, body: dict = Body(default={})):
    """Insert a new AI-drafted scene after shot `after` (0 = new opening).
    The scene bridges its neighbours, comes from the book, and arrives
    fully editable. Clears approval — new words need a new okay."""
    from ..trailer.director import write_shot
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    async def job(handle):
        return await write_shot(catalog, after_n=int(body.get("after") or 0))

    job_id = start_job("trailer_shot", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/trailer/shot/delete/{catalog}")
async def trailer_delete_shot(catalog: str, body: dict = Body(default={})):
    """Cut a scene from the running order. Footage takes are content-keyed,
    so nothing else is affected; approval is cleared."""
    n = int(body.get("n") or 0)
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    data = dict(book["data"])
    tr = dict(data.get("trailer") or {})
    treatment = dict(tr.get("treatment") or {})
    shots = [dict(s) for s in (treatment.get("shots") or []) if s.get("n") != n]
    if len(shots) == len(treatment.get("shots") or []):
        raise HTTPException(status_code=400, detail=f"No shot {n}")
    if len(shots) < 2:
        raise HTTPException(status_code=400, detail="A trailer needs at least two shots")
    for i, s2 in enumerate(shots, 1):
        s2["n"] = i
    treatment["shots"] = shots
    tr["treatment"] = treatment
    tr["approved"] = False
    data["trailer"] = tr
    db.update_book(book["id"], data)
    return {"count": len(shots)}


# ── the score bench ──────────────────────────────────────────────

@router.post("/trailer/score/options/{catalog}")
async def trailer_score_options(catalog: str, body: dict = Body(default={})):
    """Compose 3 candidate scores from an energy description (~15 credits)."""
    from ..trailer.producer import compose_score_options
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    brief = (body.get("brief") or "").strip()
    if not brief:
        raise HTTPException(status_code=400, detail="Describe the music you want")

    async def job(handle):
        return await compose_score_options(catalog, brief, handle=handle)

    job_id = start_job("score_options", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/trailer/score/pick/{catalog}")
async def trailer_score_pick(catalog: str, body: dict = Body(default={})):
    from ..trailer.producer import pin_score
    try:
        return {"pinned": pin_score(catalog, int(body.get("n") or 0))}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/trailer/score/{catalog}")
async def trailer_score_status(catalog: str):
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    tr = book["data"].get("trailer") or {}
    out = OUTPUT_DIR / catalog
    options = [{**o, "url": f"/api/files/{catalog}/{o['file']}"}
               for o in (tr.get("score_options") or [])
               if (out / o.get("file", "")).exists()]
    pinned = tr.get("score") or None
    if pinned and not (out / pinned.get("file", "")).exists():
        pinned = None
    return {"options": options,
            "pinned": {**pinned, "url": f"/api/files/{catalog}/{pinned['file']}"} if pinned else None}


# ── voice search (the whole ElevenLabs library) ──────────────────

@router.get("/voice-library/search")
async def trailer_voice_search(q: str = "", gender: str = "", accent: str = ""):
    """Search the full ElevenLabs voice library — free text ("Disney",
    "warm storyteller") plus real filters: gender and accent."""
    import httpx
    api_key = db.get_setting("elevenlabs_api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="ElevenLabs is not configured")
    # search EVERY available voice: the full shared library (biggest page the
    # API allows), plus the account's own bank matched locally
    params = {"search": q, "page_size": 100, "language": "en"}
    if gender in ("female", "male"):
        params["gender"] = gender
    if accent in ("american", "british"):
        params["accent"] = accent
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.get("https://api.elevenlabs.io/v1/shared-voices",
                           params=params,
                           headers={"xi-api-key": api_key})
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Voice library unreachable")
    out = [{
        "id": v["voice_id"], "name": v["name"],
        "description": (v.get("description") or "")[:140],
        "preview_url": v.get("preview_url"),
        "owner_id": v.get("public_owner_id"),
    } for v in resp.json().get("voices", [])]
    # the publisher's own bank + ElevenLabs premades, matched on the same terms
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            mine = await c.get("https://api.elevenlabs.io/v1/voices",
                               headers={"xi-api-key": api_key})
        needle = (q or "").lower()
        for v in (mine.json().get("voices") or []):
            labels = " ".join(str(x) for x in (v.get("labels") or {}).values()).lower()
            hay = f"{v.get('name','')} {v.get('description') or ''} {labels}".lower()
            if gender and gender not in labels:
                continue
            if accent and accent not in labels:
                continue
            if needle and needle not in hay:
                continue
            out.insert(0, {"id": v["voice_id"], "name": f"{v['name']} (your bank)",
                           "description": (v.get("description") or labels)[:140],
                           "preview_url": v.get("preview_url"), "owner_id": None})
    except Exception:
        pass
    return {"voices": out[:40]}


@router.post("/trailer/voice/hire/{catalog}")
async def trailer_voice_hire(catalog: str, body: dict = Body(default={})):
    """Add a library voice to the bank and cast it for this book."""
    import httpx
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    api_key = db.get_setting("elevenlabs_api_key", "")
    voice_id = (body.get("voice_id") or "").strip()
    owner_id = (body.get("owner_id") or "").strip()
    name = (body.get("name") or "").strip()
    if not (voice_id and owner_id):
        raise HTTPException(status_code=400, detail="voice_id and owner_id are required")
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.post(
            f"https://api.elevenlabs.io/v1/voices/add/{owner_id}/{voice_id}",
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={"new_name": name or "Trailer voice"})
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=502,
                            detail=f"Could not hire the voice: {resp.text[:150]}")
    data = dict(book["data"])
    tr = dict(data.get("trailer") or {})
    tr["voice"] = {"id": voice_id, "name": name}
    data["trailer"] = tr
    db.update_book(book["id"], data)
    return {"cast": tr["voice"]}


# ── release calendar ─────────────────────────────────────────────
# Every title carries a release plan: a date and a mode. The shelf shows it
# under each cover; the calendar shows the whole slate. Spacing is the
# strategy — each launch gets its own 30-day new-release window.

def _release_of(book: dict) -> dict:
    d = book.get("data") or {}
    rel = dict(d.get("release") or {})
    pub = d.get("publishing") or {}
    if pub.get("released_at") or pub.get("asin") or d.get("external"):
        rel.setdefault("status", "released")
        rel.setdefault("date", (pub.get("released_at") or "")[:10] or rel.get("date"))
    elif pub.get("uploaded_at"):
        rel.setdefault("status", "submitted")
    elif rel.get("date"):
        rel.setdefault("status", "planned")
    else:
        rel.setdefault("status", "unplanned")
    return rel


@router.get("/release-calendar")
def release_calendar():
    """Every title with its release plan, sorted by date (unplanned last)."""
    rows = []
    for b in db.list_books(per_page=500).get("books", []):
        rel = _release_of(b)
        d = b.get("data") or {}
        series = d.get("series") or {}
        rows.append({
            "catalog": b["catalog_number"], "title": b["title"],
            "author": d.get("author_name"), "genre": d.get("genre_preset"),
            "series": series.get("series_title"), "book_number": series.get("book_number"),
            "date": rel.get("date"), "mode": rel.get("mode") or "immediate",
            "status": rel.get("status"), "note": rel.get("note"),
        })
    rows.sort(key=lambda r: (r["date"] is None, r["date"] or "", r["catalog"]))
    return {"releases": rows}


@router.post("/release/{catalog}")
def set_release(catalog: str, body: dict = Body(default={})):
    """Set the planned release date and mode for a title."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    data = dict(book["data"])
    rel = dict(data.get("release") or {})
    date = (body.get("date") or "").strip()
    if date:
        import datetime
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        rel["date"] = date
    elif "date" in body:
        rel.pop("date", None)
    mode = (body.get("mode") or "").strip()
    if mode:
        if mode not in ("immediate", "scheduled"):
            raise HTTPException(status_code=400, detail="mode must be immediate or scheduled")
        rel["mode"] = mode
    if "note" in body:
        rel["note"] = (body.get("note") or "").strip()
    if "status" in body and body["status"] in ("planned", "submitted", "released", "unplanned"):
        rel["status"] = body["status"]
    data["release"] = rel
    db.update_book(book["id"], data)
    return {"release": _release_of({"data": data})}


@router.get("/release-calendar/suggest")
def release_suggest():
    """The slate planner's proposal for every open title, with reasons."""
    from ..market.scheduler import suggest_schedule
    return suggest_schedule()


@router.post("/release-calendar/apply")
def release_apply(body: dict = Body(default={})):
    """Accept proposals: [{catalog, date}] — writes each release plan."""
    applied = []
    for item in body.get("items") or []:
        book = db.get_book_by_catalog(item.get("catalog") or "")
        if not book or not item.get("date"):
            continue
        data = dict(book["data"])
        rel = dict(data.get("release") or {})
        rel["date"] = item["date"]
        rel.setdefault("mode", "immediate")
        rel["status"] = "planned"
        rel["planned_by"] = "slate-planner"
        data["release"] = rel
        db.update_book(book["id"], data)
        applied.append(item["catalog"])
    return {"applied": applied}


# ── the launch gate / factory line ───────────────────────────────

@router.get("/launch-gate/{catalog}")
def launch_gate_one(catalog: str):
    from ..market.launch_gate import launch_gate
    try:
        return launch_gate(catalog)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/factory-line")
def factory_line():
    from ..market.launch_gate import line_status
    return line_status()


@router.get("/cost/{catalog}")
def book_cost(catalog: str):
    from ..writing.ledger import book_cost as _bc
    return _bc(catalog)


@router.post("/line/run")
async def line_run(body: dict = Body(default={})):
    """Run the factory line for one or more books, all the way to KDP.
    body: {catalogs: [...], publish?: true}"""
    from ..market.line import run_many
    catalogs = [c for c in (body.get("catalogs") or []) if db.get_book_by_catalog(c)]
    if not catalogs:
        raise HTTPException(status_code=400, detail="No known catalog numbers")
    publish = body.get("publish", True)

    async def job(handle):
        return await run_many(catalogs, handle, publish=publish)

    return {"job_id": start_job("factory_line", job, book_catalog=catalogs[0]), "catalogs": catalogs}


@router.post("/kdp/stage-kindle/{catalog}")
async def kdp_stage_kindle(catalog: str, body: dict = Body(default={})):
    """Stage the Kindle eBook from the paperback (visible browser, persistent
    session). publish=true presses Publish — only past a clear launch gate
    and with confirm:true."""
    from ..market.kdp_ebook import stage_kindle
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    publish = bool(body.get("publish"))
    if publish and (db.get_setting("kdp_auto_publish", "0") or "0") != "1" and not body.get("confirm"):
        raise HTTPException(status_code=400, detail="Publishing needs confirm:true")

    async def job(handle):
        handle.progress(0.05, "kdp", "opening KDP for the Kindle edition")
        return await stage_kindle(catalog, publish=publish)

    return {"job_id": start_job("kdp_stage_kindle", job, book_catalog=catalog)}


@router.post("/bible/{catalog}/lock")
def bible_lock(catalog: str, body: dict = Body(default={})):
    """Lock or unlock a character's face. body: {name, locked}

    A locked face is the series' canon and nothing redraws it. Unlocking is
    the only way to ask for alternatives — which is the point: a recurring
    lead should not quietly change between books because a job ran twice.
    """
    from ..trailer.plates import set_lock
    try:
        return set_lock(catalog, str(body.get("name") or ""), bool(body.get("locked")))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))


@router.post("/bible/{catalog}/variants")
async def bible_variants(catalog: str, body: dict = Body(default={})):
    """Draw alternative looks for one unlocked character. body: {name, n?}"""
    from ..trailer.plates import draw_variants
    name = str(body.get("name") or "")
    n = max(1, min(4, int(body.get("n") or 3)))

    async def job(handle):
        return await draw_variants(catalog, name, n=n, handle=handle)

    return {"job_id": start_job("bible_variants", job, book_catalog=catalog)}


@router.post("/bible/{catalog}/choose")
def bible_choose(catalog: str, body: dict = Body(default={})):
    """Pick a look and lock it across the series. body: {name, variant, lock?}"""
    from ..trailer.plates import choose_variant
    try:
        return choose_variant(catalog, str(body.get("name") or ""),
                              str(body.get("variant") or ""),
                              lock=bool(body.get("lock", True)))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))


# ── the film desk ────────────────────────────────────────────────
# Book → treatment → screenplay (scene by scene) → shot scenes → assembly.
# Same canon as the trailers: the bible casts, frames stage, the cover
# stays off the camera. Every stage is reviewable before the next spends.

@router.post("/film/adapt/{catalog}")
async def film_adapt(catalog: str):
    """Write the treatment: three acts, beat sheet, full scene list."""
    from ..film.screenplay import adapt
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")

    async def job(handle):
        return await adapt(catalog, handle)

    return {"job_id": start_job("film_adapt", job, book_catalog=catalog)}


@router.post("/film/screenplay/{catalog}")
async def film_screenplay(catalog: str, body: dict = Body(default={})):
    """Write scenes. body: {scene?: n} for one, {opening: true} for the first reel."""
    from ..film.screenplay import write_opening, write_scene
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    n = body.get("scene")

    async def job(handle):
        if n is not None:
            return await write_scene(catalog, int(n), handle)
        return await write_opening(catalog, handle)

    return {"job_id": start_job("film_screenplay", job, book_catalog=catalog)}


@router.post("/film/shoot/{catalog}/{scene_n}")
async def film_shoot(catalog: str, scene_n: int):
    """Shoot one written scene. Re-shooting a scene touches only that scene."""
    from ..film.scenes import produce_scene
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")

    async def job(handle):
        return await produce_scene(catalog, scene_n, handle)

    return {"job_id": start_job("film_scene", job, book_catalog=catalog)}


@router.get("/film/{catalog}")
def film_status(catalog: str):
    """The whole film desk: treatment, written scenes, produced scenes."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    film = (book["data"].get("film")) or {}
    t = film.get("treatment") or {}
    scenes = film.get("scenes") or {}
    return {
        "treatment": t or None,
        "written": sorted(int(k) for k in scenes),
        "produced": [
            {**(s.get("produced") or {}),
             "url": f"/api/files/{catalog}/{(s.get('produced') or {}).get('file','')}"}
            for s in scenes.values() if s.get("produced")
        ],
    }


@router.post("/series-logo/{catalog}")
async def series_logo(catalog: str, body: dict = Body(default={})):
    """Draw wordmark options for this book's series. body: {n?}"""
    from ..trailer.plates import draw_series_logo
    n = max(1, min(4, int(body.get("n") or 3)))

    async def job(handle):
        return await draw_series_logo(catalog, n=n, handle=handle)

    return {"job_id": start_job("series_logo", job, book_catalog=catalog)}


@router.post("/series-logo/{catalog}/choose")
def series_logo_choose(catalog: str, body: dict = Body(default={})):
    """Adopt one option as the series mark. body: {option}"""
    from ..trailer.plates import choose_series_logo
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    sid = ((book["data"].get("series") or {}).get("series_id") or "").strip()
    if not sid:
        raise HTTPException(400, "This book is not part of a series")
    try:
        return choose_series_logo(sid, str(body.get("option") or ""))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/kdp/quota")
def kdp_quota():
    """How many new titles KDP will still let us create this week.

    Amazon caps title CREATION at 10 per format per week, not publishing —
    and an abandoned draft spends a slot just as a finished book does. Editing
    or publishing a title we already created costs nothing.
    """
    from ..market.kdp_quota import usage
    return usage()


@router.post("/kdp/stage/{catalog}")
async def kdp_stage(catalog: str, body: dict = Body(default={})):
    """Stage the paperback on KDP from the book's record (visible browser,
    persistent session). publish=true presses Publish — only past a clear
    launch gate."""
    from ..market.kdp_paperback import stage_paperback
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    publish = bool(body.get("publish"))
    if publish and (db.get_setting("kdp_auto_publish", "0") or "0") != "1" and not body.get("confirm"):
        raise HTTPException(status_code=400, detail="Publishing needs confirm:true (or the kdp_auto_publish setting)")

    async def job(handle):
        handle.progress(0.05, "kdp", "opening KDP")
        return await stage_paperback(catalog, publish=publish,
                                     force=bool(body.get("force")))

    job_id = start_job("kdp_stage", job, book_catalog=catalog)
    return {"job_id": job_id}


# ── keyword plan (live Amazon search data) ───────────────────────

@router.get("/keywords/{catalog}")
def keywords_status(catalog: str):
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"current": book["data"].get("keywords") or [],
            "research": book["data"].get("keyword_research")}


@router.post("/keywords/research/{catalog}")
async def keywords_research(catalog: str, body: dict = Body(default={})):
    """Research the seven KDP slots from Amazon autosuggest + competition,
    scrubbed for compliance and truth. apply=true writes them to the book."""
    from ..market.keyword_plan import keyword_plan
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    apply = bool(body.get("apply", True))

    async def job(handle):
        handle.progress(0.1, "keywords", "asking Amazon what readers type")
        return await keyword_plan(catalog, apply=apply)

    job_id = start_job("keyword_research", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/trailer/reference/{catalog}")
async def trailer_reference(catalog: str, body: dict = Body(default={})):
    """Learn the craft of a reference trailer (YouTube link): rhythm, voice,
    music, look. The director then matches its feel for this book."""
    from ..trailer.reference import analyze_reference
    url = (body.get("url") or "").strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Paste a YouTube link")
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    async def job(handle):
        handle.progress(0.1, "reference", "studying the reference trailer")
        return await analyze_reference(catalog, url)

    job_id = start_job("trailer_reference", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/trailer/board-frame/{catalog}")
async def redraw_board_frame(catalog: str, body: dict = Body(default={})):
    """Redraw ONE storyboard frame — optionally from the publisher's own
    prompt. Only the image changes; the board's shot text stays unless the
    publisher edits it separately (Lars, 2026-08-29)."""
    from ..trailer.plates import _draw, _panel_prompt, _dir
    from ..trailer.bible import cast_of
    from ..cover.front_cover import _best_image_model
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    tr = book["data"].get("trailer") or {}
    sb = tr.get("storyboard") or {}
    panels = (sb.get("panels") if isinstance(sb, dict) else sb) or []
    n = str(body.get("panel") or "")
    pn = next((p for p in panels if str(p.get("n")) == n), None)
    if not pn:
        raise HTTPException(404, f"Panel {n} not found on the storyboard")
    custom = str(body.get("prompt") or "").strip()

    async def job(handle):
        import httpx, shutil as _sh
        style = (sb.get("style") if isinstance(sb, dict) else "") or ""
        cast = cast_of(book)
        out = _dir(catalog, "board")
        dest = out / f"panel-{n}.png"
        if dest.exists():   # the old frame is banked, never destroyed
            _sh.copy2(dest, out / f"panel-{n}-prev.png")
        draw_pn = {**pn, "shot": custom} if custom else pn
        # the image API gives no progress signal — advance the ring on the
        # clock so the wait reads as motion, not a hang (typical draw ~60s)
        import asyncio as _aio
        done_flag = {"v": False}

        async def _tick():
            t = 0.0
            while not done_flag["v"]:
                await _aio.sleep(3)
                t += 3
                if handle:
                    handle.progress(min(0.92, 0.15 + t / 75.0), "board",
                                    f"redrawing panel {n}")

        ticker = _aio.create_task(_tick())
        try:
            async with httpx.AsyncClient(timeout=260) as client:
                model = await _best_image_model(client)
                got = await _draw(client, model,
                                  _panel_prompt(draw_pn, style, cast, book["title"]),
                                  dest, size="1536x1024", quality="medium",
                                  on_stage=lambda f: handle and handle.progress(
                                      f, "board", f"painting panel {n}"))
        finally:
            done_flag["v"] = True
            ticker.cancel()
        if not got:
            raise RuntimeError("The frame refused to draw — try rewording the prompt")
        return {"panel": n, "frame": f"board/panel-{n}.png"}

    return {"job_id": start_job("board_frame", job, book_catalog=catalog)}


@router.post("/trailer/reshoot-scene/{catalog}")
async def reshoot_scene(catalog: str, body: dict = Body(default={})):
    """Re-shoot ONE storyboard scene and re-cut the trailer. Everything else
    — takes, voice, music — is reused from cache. Without confirm:true this
    only QUOTES the estimate; nothing spends until the publisher approves
    (the money contract, as product)."""
    from ..trailer.producer import produce_storyboard
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    tr = book["data"].get("trailer") or {}
    sb = tr.get("storyboard") or {}
    panels = (sb.get("panels") if isinstance(sb, dict) else sb) or []
    n = str(body.get("panel") or "")
    pn = next((p for p in panels if str(p.get("n")) == n), None)
    if not pn:
        raise HTTPException(404, f"Panel {n} not found on the storyboard")
    try:
        secs = max(3.0, min(8.0, float(pn.get("dur") or 4)))
    except (TypeError, ValueError):
        secs = 4.0
    # conservative ceiling: Seedance ~60 cr/s at 1080p; the draft ratio is
    # cheaper, so the real bill usually lands under this number
    estimate = int(secs * 60)
    if not body.get("confirm"):
        return {"estimate_credits_max": estimate, "seconds": secs,
                "note": "One scene re-shoots; every other take, the voice and "
                        "the music are reused. Re-cut is free. Pass "
                        "confirm:true to roll."}
    board = sb if isinstance(sb, dict) else {"panels": panels}

    async def job(handle):
        return await produce_storyboard(catalog, board, format_name="wide",
                                        handle=handle, reshoot=[n])

    return {"job_id": start_job("trailer_produce", job, book_catalog=catalog),
            "estimate_credits_max": estimate}


@router.post("/trailer/storyboard/upload/{catalog}")
async def trailer_storyboard_upload(catalog: str, file: UploadFile = File(...)):
    """Upload a storyboard sheet (an image of numbered panels with shot
    notes and captions). SCRPT reads it and transcribes it into a shootable
    board — one clip per panel, narrated, scored, closed on the real cover.
    Works the same way as the reference-trailer field, just for a director's
    own storyboard instead of a YouTube link."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    ctype = (file.content_type or "").lower()
    if not ctype.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload an image of the storyboard (PNG or JPG)")
    image_bytes = await file.read()
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="That image is too large (20MB max)")

    async def job(handle):
        from ..trailer.producer import parse_storyboard_image
        handle.progress(0.2, "reading", "reading the storyboard panel by panel")
        fresh = db.get_book_by_catalog(catalog)
        board = await parse_storyboard_image(image_bytes, fresh)
        data = dict(fresh["data"])
        tr = dict(data.get("trailer") or {})
        tr["storyboard_pending"] = board
        tr["storyboard_pending_source"] = file.filename or "storyboard.png"
        data["trailer"] = tr
        db.update_book(fresh["id"], data)
        return {"panels": len(board["panels"])}

    job_id = start_job("trailer_storyboard_upload", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/trailer/storyboard/shoot/{catalog}")
async def trailer_storyboard_shoot(catalog: str, body: dict = Body(default={})):
    """Shoot the uploaded (or directly supplied) storyboard: one clip per
    panel on Seedance 2.5, narrated, scored, closed on the real cover.
    body: {board?: {...}, format?: wide|vertical|ad} — board defaults to
    the last uploaded storyboard for this book."""
    from ..trailer.producer import produce_storyboard
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    board = body.get("board") or (book["data"].get("trailer") or {}).get("storyboard_pending")
    if not board or not board.get("panels"):
        raise HTTPException(status_code=400, detail="Upload a storyboard first")
    fmt = (body.get("format") or "wide").strip()

    async def job(handle):
        result = await produce_storyboard(catalog, board, format_name=fmt, handle=handle)
        fresh = db.get_book_by_catalog(catalog)
        data = dict(fresh["data"])
        tr = dict(data.get("trailer") or {})
        tr.pop("storyboard_pending", None)
        tr.pop("storyboard_pending_source", None)
        data["trailer"] = tr
        db.update_book(fresh["id"], data)
        return result

    job_id = start_job("trailer_produce", job, book_catalog=catalog)
    return {"job_id": job_id}


@router.post("/trailer/workorder/{catalog}")
async def trailer_workorder(catalog: str, body: dict = Body(default={})):
    """The work order: title + cover + blurb + end screen, one Seedance take.
    body: {quality: draft|master, format: wide|vertical|ad, seconds?: 30}"""
    from ..trailer.producer import produce_workorder
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    quality = (body.get("quality") or "draft").strip()
    fmt = (body.get("format") or "wide").strip()
    seconds = int(body.get("seconds") or 30)
    finish = "4k" if quality in ("4k", "master") else ""     # "master" of a work-order cut = this cut in 4K

    async def job(handle):
        return await produce_workorder(catalog, quality="draft", format_name=fmt, seconds=seconds,
                                       handle=handle, finish=finish)

    return {"job_id": start_job("trailer_produce", job, book_catalog=catalog)}


@router.post("/trailer/reset/{catalog}")
def trailer_reset(catalog: str):
    """Start over: drop the script, the direction, the review, the take
    ledger and every generated file — keep the archived versions and a
    narrator the publisher cast by hand."""
    from ..trailer.producer import OUTPUT_DIR as _OUT
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    data = dict(book["data"])
    tr = dict(data.get("trailer") or {})
    keep = {k: tr[k] for k in ("versions", "reference") if k in tr}
    voice = tr.get("voice") or {}
    if voice.get("id") and voice.get("auto") is False:
        keep["voice"] = voice
    data["trailer"] = keep
    db.update_book(book["id"], data)
    tdir = _OUT / catalog / "trailer"
    removed = 0
    if tdir.exists():
        for f in tdir.iterdir():
            if f.name in ("world-plate.png",):
                continue
            if f.suffix in (".mp4", ".mp3", ".png", ".jpg", ".txt"):
                f.unlink(missing_ok=True); removed += 1
    for name in ("trailer.mp4", "trailer-poster.jpg"):
        f = _OUT / catalog / name
        if f.exists():
            f.unlink(missing_ok=True)
    return {"reset": True, "removed_files": removed, "kept": list(keep)}


@router.post("/trailer/like-this/{catalog}")
async def trailer_like_this(catalog: str, body: dict = Body(default={})):
    raise HTTPException(status_code=410, detail=(
        "Retired. Trailers have ONE production line: character bible from "
        "plot + cover, then the storyboard, then the shoot from board + "
        "bible, closing on the cover."))
    """One click: study a reference trailer, write this book's script in its
    rhythm and register, and shoot it (draft by default)."""
    from ..trailer.reference import analyze_reference
    from ..trailer.director import write_treatment
    from ..trailer.producer import produce, MODES, FORMATS
    url = (body.get("url") or "").strip()
    mode = (body.get("mode") or "draft").strip()
    fmt = (body.get("format") or "wide").strip()
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if mode not in MODES or fmt not in FORMATS:
        raise HTTPException(status_code=400, detail="bad mode/format")
    stored = ((book["data"].get("trailer") or {}).get("reference") or {}).get("url")
    # no link and no reference: the director works from the book alone —
    # the one-button "create the trailer"

    async def job(handle):
        if url and url != stored:
            handle.progress(0.05, "reference", "studying the reference trailer")
            await analyze_reference(catalog, url)
        from ..trailer.direction import write_direction, cast_narrator
        handle.progress(0.12, "directing", "making the directorial choices — look, rhythm, voice, score")
        direction = await write_direction(catalog)
        handle.progress(0.18, "casting", "casting the narrator")
        try:
            await cast_narrator(catalog, direction)
        except Exception:
            pass
        handle.progress(0.25, "directing",
                        "writing the script in the reference's rhythm" if (url or stored)
                        else "writing the script from the book")
        await write_treatment(catalog)
        fresh = db.get_book_by_catalog(catalog)
        data = dict(fresh["data"]); tr = dict(data.get("trailer") or {})
        tr["approved"] = True          # the publisher asked for the film in one click
        data["trailer"] = tr
        db.update_book(fresh["id"], data)
        handle.progress(0.30, "shooting", "rolling")

        class _Scaled:
            """The shoot owns the last 70% of the bar — it never runs backwards."""
            def progress(self, p, stage="", detail=""):
                handle.progress(0.30 + 0.70 * max(0.0, min(1.0, float(p or 0))), stage, detail)
            def __getattr__(self, name):
                return getattr(handle, name)

        return await produce(catalog, mode, format_name=fmt, handle=_Scaled())

    job_id = start_job("trailer_produce", job, book_catalog=catalog)
    return {"job_id": job_id}


# ── series builder: group existing standalone books into a series ───

@router.post("/series/group")
def series_group(body: dict = Body(default={})):
    """Make a series out of existing, unreleased books.
    body: {series_title, catalogs: [in reading order], bible?}
    Stamps series data + numbering on each book, keeps one series_id, and
    rebuilds the print wrap so the back cover carries 'Series · Book N'."""
    import uuid
    title = (body.get("series_title") or "").strip()
    catalogs = [c for c in (body.get("catalogs") or []) if c]
    if not title or len(catalogs) < 2:
        raise HTTPException(status_code=400, detail="A series needs a title and at least two books")
    books = []
    for c in catalogs:
        b = db.get_book_by_catalog(c)
        if not b:
            raise HTTPException(status_code=404, detail=f"{c} not found")
        pub = (b.get("data") or {}).get("publishing") or {}
        if pub.get("asin") or (b.get("data") or {}).get("external"):
            raise HTTPException(status_code=400, detail=f"{c} is already released — series membership is set on KDP for live titles")
        books.append(b)
    # reuse an existing id if any member already belongs to a series of this name
    sid = next(((b["data"].get("series") or {}).get("series_id") for b in books
                if (b["data"].get("series") or {}).get("series_title") == title
                and (b["data"].get("series") or {}).get("series_id")), None) or uuid.uuid4().hex[:8]
    bible = (body.get("bible") or "").strip()
    wraps = []
    for i, b in enumerate(books, 1):
        data = dict(b["data"])
        prev = dict(data.get("series") or {})
        data["series"] = {**prev, "series_id": sid, "series_title": title,
                          "book_number": i, "total_planned": len(books),
                          "series_bible": bible or prev.get("series_bible") or "",
                          "grouped_from_standalone": True}
        db.update_book(b["id"], data)
        if data.get("interior", {}).get("page_count"):
            try:
                build_print_wrap(b["catalog_number"])
                wraps.append(b["catalog_number"])
            except Exception:
                pass
    return {"series_id": sid, "series_title": title,
            "books": [{"catalog": b["catalog_number"], "title": b["title"], "book_number": i}
                      for i, b in enumerate(books, 1)],
            "wraps_rebuilt": wraps}


@router.get("/series/candidates")
def series_candidates():
    """Unreleased books that could join a series (standalones first)."""
    rows = []
    for b in db.list_books(per_page=500).get("books", []):
        d = b.get("data") or {}
        pub = d.get("publishing") or {}
        if pub.get("asin") or d.get("external"):
            continue
        s = d.get("series") or {}
        rows.append({"catalog": b["catalog_number"], "title": b["title"],
                     "author": d.get("author_name"), "genre": d.get("genre_preset"),
                     "series": s.get("series_title"), "book_number": s.get("book_number")})
    rows.sort(key=lambda r: (r["series"] is not None, r["catalog"]))
    return {"books": rows}
