"""
SCRPT API Server
=================
FastAPI backend powering the SCRPT book publishing engine.
Handles all CRUD operations, generation requests, and pipeline orchestration.

Run: uvicorn engine.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from .config import (
    API_PORT,
    CORS_ORIGINS,
    BOOK_TYPES,
    TRIM_SIZE_OPTIONS,
    PAPER_TYPE_OPTIONS,
    BOOK_STATUSES,
    OUTPUT_DIR,
)
from .database import (
    init_database,
    create_book,
    get_book,
    get_book_by_catalog,
    list_books,
    update_book,
    delete_book,
    create_niche,
    get_niche,
    list_niches,
    update_niche,
    delete_niche,
    get_all_settings,
    update_settings,
    get_dashboard_stats,
)
from .models import (
    BookCreate,
    BookUpdate,
    BookResponse,
    BookListResponse,
    NicheCreate,
    NicheResponse,
    NicheListResponse,
    DashboardStats,
    SettingsUpdate,
    SuccessResponse,
    ErrorResponse,
    GenerateInteriorRequest,
    GenerateCoverRequest,
    GenerateDesignRequest,
    CoverPreviewRequest,
    QualityCheckRequest,
    UploadRequest,
)


# ── App Lifecycle ────────────────────────────────────────────────

def _cleanup_preview_dirs():
    """Remove cover preview directories older than 1 hour."""
    import time
    preview_root = OUTPUT_DIR / "_preview"
    if not preview_root.exists():
        return
    cutoff = time.time() - 3600  # 1 hour
    for d in preview_root.iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff:
            import shutil
            shutil.rmtree(d, ignore_errors=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_database()
    from .jobs import init_jobs_table
    from .reports.importer import init_reports_table
    init_jobs_table()
    init_reports_table()
    _cleanup_preview_dirs()
    print("━" * 60)
    print("  SCRPT Engine v1.0")
    print("  Amazon KDP Book Publishing Automation")
    print(f"  API running on http://localhost:{API_PORT}")
    print("━" * 60)

    # The production line survives restarts: any book that was mid-draft when
    # the engine last stopped (crash, reboot, upgrade) resumes automatically.
    # Chapters already written are on disk; drafting picks up at the next one.
    async def _resume_interrupted():
        import asyncio as _aio
        await _aio.sleep(5)  # let the server settle first
        try:
            from . import database as _db
            from .jobs import list_jobs, start_job
            from .writing import pipeline as _wp
            for b in _db.list_books(per_page=500)["books"]:
                if (b.get("data") or {}).get("authorship") == "author":
                    continue  # the human's book — never auto-resume a machine draft
                ms = (b.get("data") or {}).get("manuscript") or {}
                if ms.get("status") != "drafting":
                    continue
                if (b.get("data") or {}).get("draft_paused"):
                    continue  # explicitly parked (e.g. awaiting a model decision)
                catalog = b["catalog_number"]
                if any(j["kind"] == "full_draft"
                       for j in list_jobs(catalog, active_only=True)):
                    continue
                chosen = ms.get("chosen_plot") or 0
                start_job("full_draft",
                          lambda h, c=catalog, p=chosen: _wp.full_draft_job(h, c, p),
                          book_catalog=catalog)
                print(f"  ↻ resuming interrupted draft: {catalog} — {b['title'][:50]}")
        except Exception as e:
            print(f"  draft auto-resume skipped: {e}")

    import asyncio as _aio
    _aio.get_event_loop().create_task(_resume_interrupted())

    # the growth engine runs the business on a daily cycle when enabled
    from .market.autopilot import scheduler as _autopilot
    _aio.get_event_loop().create_task(_autopilot())
    yield


app = FastAPI(
    title="SCRPT Engine",
    description="Automated Amazon KDP book publishing — research, create, validate, upload.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── SCRPT prose-book API ────────────────────────────────────────
from .routers.scrpt import router as scrpt_router  # noqa: E402
from .routers.assistant import router as assistant_router  # noqa: E402
from .routers.auth_local import router as auth_local_router
from .routers.market import router as market_router  # noqa: E402
app.include_router(scrpt_router)
app.include_router(assistant_router)
app.include_router(auth_local_router)
app.include_router(market_router)

# ── CORS ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HEALTH + DASHBOARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "scrpt-engine", "version": "1.0.0"}


@app.get("/api/dashboard", response_model=DashboardStats)
async def get_dashboard():
    """Get dashboard summary statistics."""
    return get_dashboard_stats()


@app.get("/api/config")
async def get_config():
    """Get app configuration constants (book types, trim sizes, etc.)."""
    return {
        "book_types": BOOK_TYPES,
        "trim_sizes": TRIM_SIZE_OPTIONS,
        "paper_types": PAPER_TYPE_OPTIONS,
        "statuses": BOOK_STATUSES,
    }


@app.get("/api/generators")
async def get_generators():
    """Get status of available interior generators."""
    from .generators.interior_builder import get_available_generators
    return get_available_generators()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOOKS CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/api/books", response_model=BookResponse, status_code=201)
async def create_book_endpoint(book: BookCreate):
    """Create a new book project."""
    # Validate book type
    if book.book_type not in BOOK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid book type: {book.book_type}. Options: {list(BOOK_TYPES.keys())}"
        )

    # Build metadata
    data = {
        "book_type": book.book_type,
        "trim_size": book.trim_size,
        "paper_type": book.paper_type,
        "page_count": book.page_count,
        "subtitle": book.subtitle,
        "author_name": book.author_name,
        "list_price": book.list_price,
        "niche_keyword": book.niche_keyword,
        "generator_config": book.generator_config,
        "keywords": [],
        "categories": [],
        "description": "",
    }

    result = create_book(title=book.title, data=data)
    return result


@app.get("/api/books", response_model=BookListResponse)
async def list_books_endpoint(
    status: Optional[str] = Query(None, description="Filter by status"),
    book_type: Optional[str] = Query(None, description="Filter by book type"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
):
    """List all books with optional filtering."""
    return list_books(status=status, book_type=book_type, page=page, per_page=per_page)


@app.get("/api/books/{book_id}", response_model=BookResponse)
async def get_book_endpoint(book_id: str):
    """Get a single book by ID."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@app.get("/api/books/catalog/{catalog_number}", response_model=BookResponse)
async def get_book_by_catalog_endpoint(catalog_number: str):
    """Get a single book by catalog number (e.g., BB-001)."""
    book = get_book_by_catalog(catalog_number)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@app.patch("/api/books/{book_id}", response_model=BookResponse)
async def update_book_endpoint(book_id: str, updates: BookUpdate):
    """Update a book's fields."""
    # Convert to dict, excluding None values
    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Convert status enum to string if present
    if "status" in update_data:
        update_data["status"] = update_data["status"].value if hasattr(update_data["status"], "value") else update_data["status"]

    result = update_book(book_id, update_data)
    if not result:
        raise HTTPException(status_code=404, detail="Book not found")
    return result


@app.delete("/api/books/{book_id}", response_model=SuccessResponse)
async def delete_book_endpoint(book_id: str):
    """Delete a book by ID."""
    if not delete_book(book_id):
        raise HTTPException(status_code=404, detail="Book not found")
    return {"success": True, "message": "Book deleted"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NICHES CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/api/niches", response_model=NicheResponse, status_code=201)
async def create_niche_endpoint(niche: NicheCreate):
    """Create a new niche research entry."""
    result = create_niche(keyword=niche.keyword, data=niche.data.model_dump())
    return result


@app.get("/api/niches", response_model=NicheListResponse)
async def list_niches_endpoint(
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """List all researched niches."""
    return list_niches(status=status)


@app.get("/api/niches/{niche_id}", response_model=NicheResponse)
async def get_niche_endpoint(niche_id: str):
    """Get a single niche by ID."""
    niche = get_niche(niche_id)
    if not niche:
        raise HTTPException(status_code=404, detail="Niche not found")
    return niche


@app.patch("/api/niches/{niche_id}", response_model=NicheResponse)
async def update_niche_endpoint(niche_id: str, updates: dict):
    """Update a niche entry."""
    result = update_niche(niche_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Niche not found")
    return result


@app.delete("/api/niches/{niche_id}", response_model=SuccessResponse)
async def delete_niche_endpoint(niche_id: str):
    """Delete a niche by ID."""
    if not delete_niche(niche_id):
        raise HTTPException(status_code=404, detail="Niche not found")
    return {"success": True, "message": "Niche deleted"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SETTINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/settings")
async def get_settings_endpoint():
    """Get all application settings."""
    return get_all_settings()


@app.patch("/api/settings", response_model=SuccessResponse)
async def update_settings_endpoint(settings: SettingsUpdate):
    """Update application settings."""
    updates = {k: v for k, v in settings.model_dump().items() if v is not None}
    if updates:
        update_settings(updates)
    return {"success": True, "message": "Settings updated"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GENERATION ENDPOINTS (stubs — implemented in later phases)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _resolve_book_data(request, required_fields=None):
    """Resolve book data from companion mode (inline) or legacy mode (SQLite lookup).
    Returns (book_data, catalog_number, book_id_or_none).
    """
    # Companion mode: inline data from Supabase
    if request.catalog_number and request.title:
        book_data = {
            "title": request.title,
            "book_type": getattr(request, "book_type", None) or "word_search",
            "trim_size": request.trim_size,
            "paper_type": request.paper_type,
            "page_count": request.page_count,
            "generator_config": request.generator_config,
        }
        # Cover-specific fields
        if hasattr(request, "subtitle"):
            book_data["subtitle"] = request.subtitle or ""
        if hasattr(request, "author_name"):
            book_data["author_name"] = request.author_name or ""
        return book_data, request.catalog_number, None

    # Legacy mode: look up from local SQLite
    if request.book_id:
        book = get_book(request.book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        book_data = {**book["data"], "title": book["title"]}
        return book_data, book["catalog_number"], request.book_id

    raise HTTPException(
        status_code=400,
        detail="Provide either (catalog_number + title) or book_id"
    )


def _resolve_catalog_number(identifier: str) -> str:
    """Resolve a path identifier to a catalog number.
    Accepts a catalog number directly (SC-XXX) or a book UUID (legacy).
    """
    # If it looks like a catalog number, use directly
    if identifier.upper().startswith("SC-"):
        return identifier.upper()

    # Legacy: try DB lookup by UUID
    try:
        book = get_book(identifier)
        if book:
            return book["catalog_number"]
    except Exception:
        pass

    # Fall back to using the identifier as-is (e.g., catalog number without SC- prefix)
    return identifier


@app.post("/api/generate/interior")
async def generate_interior(request: GenerateInteriorRequest):
    """Generate the book interior PDF.
    Companion mode: send catalog_number + title + book data inline.
    Legacy mode: send book_id to look up from local SQLite.
    """
    book_data, catalog_number, book_id = _resolve_book_data(request)

    # Check if already generated (unless force)
    output_dir = OUTPUT_DIR / catalog_number
    interior_path = output_dir / "interior.pdf"
    if interior_path.exists() and not request.force_regenerate:
        return {"success": True, "message": "Interior already generated", "path": str(interior_path)}

    # Update status in local DB if available
    if book_id:
        update_book(book_id, {"status": "generating"})

    try:
        from .generators.interior_builder import build_interior

        result = build_interior(book_data, output_dir)

        if result.get("error"):
            if book_id:
                update_book(book_id, {"status": "draft"})
            return {"success": False, "message": result["error"]}

        # Update local DB if available
        if book_id:
            update_book(book_id, {
                "status": "draft",
                "interior_pdf": result["path"],
                "page_count": result["page_count"],
            })

        return {
            "success": True,
            "message": f"Interior generated: {result['page_count']} pages",
            "path": result["path"],
            "page_count": result["page_count"],
        }

    except Exception as e:
        if book_id:
            update_book(book_id, {"status": "draft"})
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@app.post("/api/generate/cover")
async def generate_cover(request: GenerateCoverRequest):
    """Generate the book cover PDF.
    Companion mode: send catalog_number + title + book data inline.
    Legacy mode: send book_id to look up from local SQLite.
    """
    book_data, catalog_number, book_id = _resolve_book_data(request)

    # Check if already generated (unless force)
    output_dir = OUTPUT_DIR / catalog_number
    cover_path = output_dir / "cover.pdf"
    if cover_path.exists() and not request.force_regenerate:
        return {"success": True, "message": "Cover already generated", "path": str(cover_path)}

    if book_id:
        update_book(book_id, {"status": "generating"})

    try:
        from .cover.renderer import render_cover

        page_count = book_data.get("page_count", 120)
        trim_size = book_data.get("trim_size", "8.5x11")
        paper_type = book_data.get("paper_type", "white_bw")
        gen_config = book_data.get("generator_config", {})

        output_dir.mkdir(parents=True, exist_ok=True)

        result = await render_cover(
            page_count=page_count,
            trim_size=trim_size,
            paper_type=paper_type,
            title=book_data.get("title", "Untitled"),
            subtitle=book_data.get("subtitle", ""),
            author=book_data.get("author_name", "Creative Puzzles Press"),
            book_type=book_data.get("book_type", "default"),
            output_dir=output_dir,
            puzzle_count=gen_config.get("num_puzzles", 55),
            variant_id=gen_config.get("cover_variant_id"),
        )

        if not result.get("success", False):
            if book_id:
                update_book(book_id, {"status": "draft"})
            return {"success": False, "message": result.get("error", "Cover generation failed")}

        # Update local DB if available
        if book_id:
            update_data = {"status": "draft"}
            if result.get("cover_pdf"):
                update_data["cover_pdf"] = result["cover_pdf"]
            if result.get("cover_png"):
                update_data["cover_front_png"] = result["cover_png"]
            update_book(book_id, update_data)

        return {
            "success": True,
            "message": "Cover generated successfully",
            "note": result.get("note", ""),
            "dimensions": result.get("dimensions", {}),
        }

    except Exception as e:
        if book_id:
            update_book(book_id, {"status": "draft"})
        raise HTTPException(status_code=500, detail=f"Cover generation failed: {str(e)}")


@app.post("/api/quality/validate", response_model=SuccessResponse)
async def run_quality_check(request: QualityCheckRequest):
    """Run the 5-gate quality validation pipeline. (Phase 5)"""
    # TODO: Phase 5 — run quality pipeline
    return {"success": True, "message": "Quality check queued (not yet implemented)"}


@app.post("/api/research/scan", response_model=SuccessResponse)
async def research_scan():
    """Run autonomous niche research. (Phase 6)"""
    # TODO: Phase 6 — BSR scanning + validation
    return {"success": True, "message": "Research scan queued (not yet implemented)"}


@app.post("/api/listing/optimize", response_model=SuccessResponse)
async def optimize_listing(book_id: str):
    """Generate optimized title, description, keywords. (Phase 7)"""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # TODO: Phase 7 — AI listing optimization
    return {"success": True, "message": "Listing optimization queued (not yet implemented)"}


@app.post("/api/upload/submit", response_model=SuccessResponse)
async def submit_to_kdp(request: UploadRequest):
    """Upload a book to Amazon KDP. (Phase 8)"""
    # TODO: Phase 8 — Playwright KDP upload
    return {"success": True, "message": "Upload queued (not yet implemented)"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILE SERVING (generated PDFs and images)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/files/{identifier}/{filename:path}")
async def serve_file(identifier: str, filename: str, download: int = 0, name: str = ""):
    """Serve generated files (PDFs, images, media) for a book — including
    one level of sub-folder (audio-preview/ready-00.mp3).
    Identifier can be a catalog_number (SC-001) or legacy book_id (UUID).
    """
    catalog_number = _resolve_catalog_number(identifier)

    # Files are stored in output/{catalog_number}/
    base = (OUTPUT_DIR / catalog_number).resolve()
    file_path = (base / filename).resolve()
    if base not in file_path.parents or ".." in filename:
        raise HTTPException(status_code=404, detail="File not found")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type
    content_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".json": "application/json",
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".epub": "application/epub+zip",
    }
    suffix = file_path.suffix.lower()
    content_type = content_types.get(suffix, "application/octet-stream")

    # media plays inline in the app's players; only documents download —
    # unless ?download=1 asks for a save, optionally under a titled name
    inline = suffix in (".mp4", ".mp3", ".jpg", ".jpeg", ".png") and not download
    safe_name = "".join(ch for ch in (name or "") if ch.isalnum() or ch in "-_. ").strip() or filename
    if not safe_name.lower().endswith(suffix):
        safe_name += suffix
    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        filename=safe_name,
        content_disposition_type="inline" if inline else "attachment",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PREVIEW SYSTEM — Interior + Cover Quality Preview
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Page image cache: {(file_path, page_num, width): png_bytes}
_page_cache: dict[tuple, bytes] = {}


def _render_pdf_page(pdf_path: str, page_num: int, width: int = 800) -> bytes:
    """Render a single PDF page to PNG bytes using PyMuPDF."""
    cache_key = (pdf_path, page_num, width)
    if cache_key in _page_cache:
        return _page_cache[cache_key]

    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    total = len(doc)
    if page_num < 0 or page_num >= total:
        doc.close()
        raise ValueError(f"Page {page_num} out of range (0-{total - 1})")

    page = doc[page_num]
    # Scale to target width while maintaining aspect ratio
    zoom = width / page.rect.width
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    png_bytes = pix.tobytes("png")
    doc.close()

    # Cache (limit to 200 entries)
    if len(_page_cache) > 200:
        _page_cache.clear()
    _page_cache[cache_key] = png_bytes
    return png_bytes


@app.get("/api/preview/{identifier}/files")
async def get_book_files(identifier: str):
    """List all generated files for a book.
    Identifier can be a catalog_number (SC-001) or legacy book_id (UUID).
    """
    catalog_number = _resolve_catalog_number(identifier)

    output_path = OUTPUT_DIR / catalog_number
    files = {}

    if output_path.exists():
        for f in output_path.iterdir():
            if f.is_file():
                files[f.name] = {
                    "name": f.name,
                    "size": f.stat().st_size,
                    "url": f"/api/files/{catalog_number}/{f.name}",
                }

    # Check for interior PDF page count
    interior_path = output_path / "interior.pdf"
    interior_pages = 0
    if interior_path.exists():
        try:
            import fitz
            doc = fitz.open(str(interior_path))
            interior_pages = len(doc)
            doc.close()
        except Exception:
            pass

    # Check for cover
    cover_path = output_path / "cover.pdf"
    cover_front_path = output_path / "cover-front.png"

    return {
        "catalog_number": catalog_number,
        "files": files,
        "has_interior": interior_path.exists(),
        "interior_pages": interior_pages,
        "has_cover": cover_path.exists(),
        "has_cover_front": cover_front_path.exists(),
    }


@app.get("/api/preview/{identifier}/interior/{page_num}")
async def preview_interior_page(
    identifier: str,
    page_num: int,
    width: int = Query(800, ge=200, le=2400, description="Render width in pixels"),
):
    """Render a single interior PDF page as PNG image.
    Identifier can be a catalog_number (SC-001) or legacy book_id (UUID).
    """
    catalog_number = _resolve_catalog_number(identifier)

    pdf_path = OUTPUT_DIR / catalog_number / "interior.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Interior PDF not found. Generate the interior first.")

    try:
        png_bytes = _render_pdf_page(str(pdf_path), page_num, width)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {str(e)}")

    return Response(content=png_bytes, media_type="image/png")


@app.get("/api/preview/{identifier}/cover")
async def preview_cover(
    identifier: str,
    width: int = Query(800, ge=200, le=2400, description="Render width in pixels"),
):
    """Get the front cover preview image.
    Identifier can be a catalog_number (SC-001) or legacy book_id (UUID).
    """
    catalog_number = _resolve_catalog_number(identifier)
    output_path = OUTPUT_DIR / catalog_number

    no_cache_headers = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}

    # First try the pre-rendered PNG
    cover_front = output_path / "cover-front.png"
    if cover_front.exists():
        return FileResponse(str(cover_front), media_type="image/png", headers=no_cache_headers)

    # Fall back to rendering from cover PDF
    cover_pdf = output_path / "cover.pdf"
    if cover_pdf.exists():
        try:
            png_bytes = _render_pdf_page(str(cover_pdf), 0, width)
            return Response(content=png_bytes, media_type="image/png", headers=no_cache_headers)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cover render failed: {str(e)}")

    raise HTTPException(status_code=404, detail="No cover found. Generate the cover first.")


@app.get("/api/preview/{identifier}/cover/full")
async def preview_cover_full(
    identifier: str,
    width: int = Query(1600, ge=200, le=4800, description="Render width in pixels"),
):
    """Get the full cover (front + spine + back) preview image.
    Identifier can be a catalog_number (SC-001) or legacy book_id (UUID).
    """
    catalog_number = _resolve_catalog_number(identifier)

    cover_pdf = OUTPUT_DIR / catalog_number / "cover.pdf"
    if not cover_pdf.exists():
        raise HTTPException(status_code=404, detail="Cover PDF not found.")

    try:
        png_bytes = _render_pdf_page(str(cover_pdf), 0, width)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cover render failed: {str(e)}")

    no_cache_headers = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
    return Response(content=png_bytes, media_type="image/png", headers=no_cache_headers)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COVER DIMENSIONS (immediate utility)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/cover/dimensions")
async def get_cover_dimensions(
    page_count: int = Query(..., ge=24, le=828, description="Number of pages (must be even)"),
    trim_size: str = Query("8.5x11", description="Trim size (e.g., 8.5x11, 6x9)"),
    paper_type: str = Query("white_bw", description="Paper type"),
):
    """Calculate cover dimensions for given book parameters."""
    if page_count % 2 != 0:
        raise HTTPException(status_code=400, detail="Page count must be even")

    try:
        from .cover.dimensions import calculate_cover
        dims = calculate_cover(page_count, trim_size, paper_type)
        return {
            "page_count": dims.page_count,
            "trim_size": dims.trim_size,
            "paper_type": dims.paper_type,
            "trim_width": dims.trim_width,
            "trim_height": dims.trim_height,
            "spine_width": round(dims.spine_width, 4),
            "spine_has_text": dims.spine_has_text,
            "total_width": round(dims.total_width, 4),
            "total_height": round(dims.total_height, 4),
            "total_width_px": dims.total_width_px,
            "total_height_px": dims.total_height_px,
            "spine_width_px": dims.spine_width_px,
            "bleed_px": dims.bleed_px,
            "safe_zone_px": dims.safe_zone_px,
            "zones": {
                "back_cover": {"start_px": dims.back_cover_start_px, "end_px": dims.back_cover_end_px},
                "spine": {"start_px": dims.spine_start_px, "end_px": dims.spine_end_px},
                "front_cover": {"start_px": dims.front_cover_start_px, "end_px": dims.front_cover_end_px},
                "barcode": {"x_px": dims.barcode_x_px, "y_px": dims.barcode_y_px},
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Cover Template & Reference API ─────────────────────────────

@app.get("/api/cover/templates")
async def list_cover_templates():
    """List all available cover templates with their status (file/inline, has spec, reference count)."""
    from .cover.template_loader import get_template_loader
    loader = get_template_loader()
    return {"templates": loader.list_niches()}


@app.get("/api/cover/references/{niche}")
async def get_cover_references(niche: str):
    """Get reference images and design specification for a niche."""
    from .cover.template_loader import get_template_loader
    loader = get_template_loader()
    spec = loader.load_spec(niche)
    if not spec:
        raise HTTPException(status_code=404, detail=f"No design spec found for niche: {niche}")

    references = []
    for img_path in spec.reference_images:
        source_info = next(
            (s for s in spec.data.get("references", [])
             if s.get("filename") == img_path.name),
            {},
        )
        references.append({
            "filename": img_path.name,
            "url": f"/api/cover/references/{niche}/{img_path.name}",
            **source_info,
        })

    return {
        "niche": niche,
        "display_name": spec.display_name,
        "references": references,
        "design_decisions": spec.data.get("design_decisions", {}),
        "typography": spec.data.get("typography", {}),
        "colors": spec.data.get("colors", {}),
        "layout": spec.data.get("layout", {}),
    }


@app.get("/api/cover/references/{niche}/{filename}")
async def get_reference_image(niche: str, filename: str):
    """Serve a reference image file."""
    from .config import TEMPLATES_DIR
    ref_path = TEMPLATES_DIR / niche / "references" / filename
    if not ref_path.exists():
        raise HTTPException(status_code=404, detail=f"Reference image not found: {filename}")
    suffix = ref_path.suffix.lower()
    media_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(suffix, "image/png")
    return FileResponse(str(ref_path), media_type=media_type)


@app.get("/api/cover/variants/{niche}")
async def get_cover_variants(niche: str):
    """List available design variants for a niche with reference image URLs."""
    from .cover.template_loader import get_template_loader
    loader = get_template_loader()
    variants = loader.list_variants(niche)
    return {
        "niche": niche,
        "variants": [
            {
                "variant_id": v.variant_id,
                "name": v.name,
                "description": v.description,
                "inspired_by": v.inspired_by,
                "reference_image_url": f"/api/cover/references/{niche}/{v.reference_filename}" if v.reference_filename else None,
            }
            for v in variants
        ],
    }


@app.get("/api/cover/archetypes/{book_type}")
async def list_cover_archetypes(book_type: str):
    """List available cover archetypes with their themes for the design gallery."""
    from .cover.template_loader import get_template_loader
    loader = get_template_loader()
    archetypes = loader.list_archetypes(book_type)
    return {"book_type": book_type, "archetypes": archetypes}


@app.post("/api/cover/upload-artwork")
async def upload_cover_artwork(request: dict):
    """
    Upload front cover artwork (base64 PNG/JPG). The engine stores it and returns
    a variant_id that can be used with the preview endpoint.

    The uploaded image is placed as the front cover background. The archetype's
    typography overlays it, and the back cover + spine use the archetype's
    CSS-only design.

    Request body:
    {
        "book_type": "word_search",
        "archetype_id": "bold-stack",
        "theme": "dark",
        "image_data": "base64-encoded image data",
        "image_format": "png" | "jpg"
    }
    """
    import base64
    from .config import TEMPLATES_DIR

    book_type = request.get("book_type", "word_search")
    archetype_id = request.get("archetype_id", "bold-stack")
    theme = request.get("theme", "dark")
    image_data = request.get("image_data", "")
    image_format = request.get("image_format", "png")

    if not image_data:
        raise HTTPException(status_code=400, detail="image_data is required")

    # Decode image
    try:
        img_bytes = base64.b64decode(image_data)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    # Create a custom variant directory for this upload
    import uuid
    upload_id = f"upload_{uuid.uuid4().hex[:8]}"
    variant_dir = TEMPLATES_DIR / book_type / "variants" / upload_id
    variant_dir.mkdir(parents=True, exist_ok=True)

    # Save the uploaded artwork
    artwork_ext = "png" if image_format == "png" else "jpg"
    artwork_path = variant_dir / f"artwork.{artwork_ext}"
    artwork_path.write_bytes(img_bytes)

    # Copy archetype template files but add artwork as background
    from .cover.template_loader import get_template_loader
    loader = get_template_loader()

    arch_dir = TEMPLATES_DIR / book_type / "archetypes" / archetype_id
    if not arch_dir.exists():
        raise HTTPException(status_code=404, detail=f"Archetype not found: {archetype_id}")

    import json as _json
    arch_meta = _json.loads((arch_dir / "archetype.json").read_text(encoding="utf-8"))
    themes = arch_meta.get("themes", {})
    theme_vars = themes.get(theme, themes.get("dark", {}))

    # Read archetype CSS and inject artwork background on front cover
    arch_css = (arch_dir / "style.css").read_text(encoding="utf-8")
    artwork_bg_css = f"""
/* ── Uploaded artwork background ── */
.front-cover {{
    background-image: url('artwork.{artwork_ext}');
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
}}
/* Darken overlay for text readability */
.front-cover::after {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: linear-gradient(180deg,
        rgba(0,0,0,0.45) 0%,
        rgba(0,0,0,0.15) 40%,
        rgba(0,0,0,0.15) 60%,
        rgba(0,0,0,0.55) 100%
    );
    z-index: 0;
}}
"""
    full_css = arch_css + "\n" + artwork_bg_css

    # Write variant files
    (variant_dir / "style.css").write_text(full_css, encoding="utf-8")

    # Copy HTML files from archetype
    for f in ["front.html", "back.html", "spine.html"]:
        src = arch_dir / f
        if src.exists():
            (variant_dir / f).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    # Write variant.json
    (variant_dir / "variant.json").write_text(_json.dumps({
        "name": f"Custom Artwork ({archetype_id})",
        "description": f"Uploaded artwork with {archetype_id} typography",
        "archetype_id": archetype_id,
        "theme": theme,
        "uploaded": True,
        "has_artwork": True,
    }, indent=2), encoding="utf-8")

    # Clear cache
    loader.invalidate_cache(book_type)

    return {
        "success": True,
        "variant_id": f"arch_{archetype_id}_{theme}",
        "upload_variant_id": upload_id,
        "message": "Artwork uploaded successfully",
    }


@app.get("/api/cover/compare/{identifier}")
async def compare_cover(identifier: str, width: int = Query(800)):
    """
    Get comparison data for a book: reference images + generated cover URLs.
    Frontend renders these side-by-side for visual quality benchmarking.
    """
    from .cover.template_loader import get_template_loader

    catalog_number = identifier
    output_path = OUTPUT_DIR / catalog_number

    # Determine book type
    book = get_book_by_catalog(catalog_number)
    niche = book["data"].get("book_type", "default") if book else "default"

    loader = get_template_loader()
    spec = loader.load_spec(niche)
    template = loader.load_template(niche)

    cover_front = output_path / "cover-front.png"

    return {
        "catalog_number": catalog_number,
        "niche": niche,
        "template_source": template.source,
        "generated_cover_url": f"/api/preview/{catalog_number}/cover?width={width}" if cover_front.exists() else None,
        "generated_full_url": f"/api/preview/{catalog_number}/cover/full?width={width * 2}",
        "references": [
            {
                "filename": img.name,
                "url": f"/api/cover/references/{niche}/{img.name}",
            }
            for img in (spec.reference_images if spec else [])
        ],
        "spec": spec.data if spec else None,
    }


@app.post("/api/cover/templates/{niche}/reload")
async def reload_template(niche: str):
    """Invalidate cache for a niche template. Picks up file changes without server restart."""
    from .cover.template_loader import get_template_loader
    loader = get_template_loader()
    loader.invalidate_cache(niche)
    return {"success": True, "message": f"Template cache cleared for '{niche}'"}


# ── Cover Design Search & AI Generation ───────────────────────

@app.get("/api/cover/search")
async def search_covers(
    keyword: str = Query(..., description="Niche keyword to search for"),
    max_results: int = Query(5, ge=1, le=10),
):
    """Search Amazon for bestselling book covers in a niche using Playwright."""
    from .cover.amazon_search import search_bestseller_covers

    try:
        results = await search_bestseller_covers(keyword, max_results)
        return {
            "keyword": keyword,
            "results": [
                {
                    "title": r.title,
                    "asin": r.asin,
                    "cover_image_url": r.cover_image_url,
                    "price": r.price,
                    "reviews": r.reviews,
                    "rating": r.rating,
                }
                for r in results
            ],
            "count": len(results),
        }
    except Exception as e:
        return {
            "keyword": keyword,
            "results": [],
            "count": 0,
            "error": str(e),
        }


@app.post("/api/cover/generate-design")
async def generate_design(request: GenerateDesignRequest):
    """
    Generate a cover design from a reference image using Claude Vision.
    Fetches the reference image, sends to Claude for analysis, and saves
    the generated CSS/HTML as a variant template.
    """
    from .cover.amazon_search import fetch_cover_image
    from .cover.design_generator import (
        generate_design_from_reference,
        save_generated_design,
    )
    from .cover.template_loader import get_template_loader
    from .config import TEMPLATES_DIR
    import json as _json

    # Check if variant already exists for this ASIN (reuse instead of re-generating)
    variant_id = f"ai_{request.reference_asin}" if request.reference_asin else "ai_custom"
    existing_variant_dir = TEMPLATES_DIR / request.book_type / "variants" / variant_id
    existing_variant_json = existing_variant_dir / "variant.json"
    if existing_variant_json.exists():
        try:
            meta = _json.loads(existing_variant_json.read_text(encoding="utf-8"))
            return {
                "success": True,
                "variant_id": variant_id,
                "niche": request.book_type,
                "design_notes": meta.get("description", ""),
                "has_artwork": meta.get("has_artwork", False),
                "image_prompt": meta.get("image_prompt", ""),
            }
        except Exception:
            pass  # Fall through to regenerate

    # Fetch the reference image
    try:
        image_bytes = await fetch_cover_image(request.reference_image_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch reference image: {e}")

    # Generate design via Claude Vision
    design = await generate_design_from_reference(
        reference_image_bytes=image_bytes,
        book_type=request.book_type,
        niche_keyword=request.niche_keyword or request.book_type.replace("_", " "),
        reference_asin=request.reference_asin or "",
    )

    if not design.success:
        return {
            "success": False,
            "error": design.error,
            "fallback": "default",
        }

    # Save as a variant
    variant_id = f"ai_{request.reference_asin}" if request.reference_asin else "ai_custom"

    await save_generated_design(
        design=design,
        niche=request.book_type,
        variant_id=variant_id,
        reference_asin=request.reference_asin or "",
    )

    # Invalidate template cache so the new variant is immediately available
    get_template_loader().invalidate_cache(request.book_type)

    return {
        "success": True,
        "variant_id": variant_id,
        "niche": request.book_type,
        "design_notes": design.design_notes,
        "has_artwork": design.artwork_path is not None,
        "image_prompt": design.image_prompt or "",
    }


# ── Cover Preview (render before book creation) ───────────────

@app.post("/api/cover/preview")
async def preview_cover_design(request: CoverPreviewRequest):
    """
    Render a cover preview before the book exists.
    For AI-generated variants with artwork, runs a quality control loop
    (Claude Vision review → fix CSS/HTML → re-render) on first preview.
    Returns a session_id that can be used to fetch the rendered image.
    """
    import json as _json
    import uuid
    from .cover.renderer import render_cover
    from .config import TEMPLATES_DIR

    # Check if this AI variant needs quality control
    needs_qc = False
    variant_dir = None

    if request.variant_id and not getattr(request, 'skip_quality_check', False):
        variant_dir = TEMPLATES_DIR / request.book_type / "variants" / request.variant_id
        variant_json = variant_dir / "variant.json"
        if variant_json.exists():
            try:
                meta = _json.loads(variant_json.read_text(encoding="utf-8"))
                if (meta.get("generated")
                        and meta.get("has_artwork")
                        and not meta.get("quality_checked")):
                    needs_qc = True
            except Exception:
                pass

    # Run quality control loop for AI variants (first preview only)
    if needs_qc and variant_dir:
        try:
            from .cover.design_controller import quality_control_loop

            preview_dir, review = await quality_control_loop(
                variant_dir=variant_dir,
                title=request.title,
                subtitle=request.subtitle or "",
                author=request.author_name or "Creative Puzzles Press",
                book_type=request.book_type,
                trim_size=request.trim_size,
                paper_type=request.paper_type,
                page_count=request.page_count,
                puzzle_count=request.puzzle_count,
            )

            session_id = preview_dir.name
            return {
                "success": True,
                "session_id": session_id,
                "preview_url": f"/api/cover/preview/{session_id}",
                "quality_score": review.overall_score,
                "quality_issues": len(review.issues),
                "quality_passed": review.passed,
                "quality_notes": review.review_notes,
            }
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Quality control failed: {e}")
            # Fall through to normal preview on QC failure

    # Standard preview (non-AI variants, already QC'd, or QC failure fallback)
    session_id = str(uuid.uuid4())[:8]
    preview_dir = OUTPUT_DIR / "_preview" / session_id
    preview_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = await render_cover(
            page_count=request.page_count,
            trim_size=request.trim_size,
            paper_type=request.paper_type,
            title=request.title,
            subtitle=request.subtitle,
            author=request.author_name or "Creative Puzzles Press",
            book_type=request.book_type,
            output_dir=preview_dir,
            puzzle_count=request.puzzle_count,
            variant_id=request.variant_id,
        )

        if not result.get("success", False):
            return {
                "success": False,
                "error": result.get("error", "Cover preview rendering failed"),
            }

        return {
            "success": True,
            "session_id": session_id,
            "preview_url": f"/api/cover/preview/{session_id}",
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Cover preview failed: {str(e)}",
        }


@app.get("/api/cover/preview/{session_id}")
async def serve_cover_preview(
    session_id: str,
    width: int = Query(800, ge=200, le=2400),
):
    """Serve a cover preview image by session_id."""
    preview_dir = OUTPUT_DIR / "_preview" / session_id

    if not preview_dir.exists():
        raise HTTPException(status_code=404, detail="Preview not found or expired")

    no_cache = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    # Try front cover PNG first
    front_png = preview_dir / "cover-front.png"
    if front_png.exists():
        return FileResponse(str(front_png), media_type="image/png", headers=no_cache)

    # Fall back to rendering from PDF
    cover_pdf = preview_dir / "cover.pdf"
    if cover_pdf.exists():
        try:
            png_bytes = _render_pdf_page(str(cover_pdf), 0, width)
            return Response(content=png_bytes, media_type="image/png", headers=no_cache)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Preview render failed: {str(e)}")

    raise HTTPException(status_code=404, detail="No preview image found")
