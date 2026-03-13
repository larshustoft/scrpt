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
    QualityCheckRequest,
    UploadRequest,
)


# ── App Lifecycle ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_database()
    print("━" * 60)
    print("  SCRPT Engine v1.0")
    print("  Amazon KDP Book Publishing Automation")
    print(f"  API running on http://localhost:{API_PORT}")
    print("━" * 60)
    yield


app = FastAPI(
    title="SCRPT Engine",
    description="Automated Amazon KDP book publishing — research, create, validate, upload.",
    version="1.0.0",
    lifespan=lifespan,
)

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

@app.post("/api/generate/interior")
async def generate_interior(request: GenerateInteriorRequest):
    """Generate the book interior PDF."""
    book = get_book(request.book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Check if already generated (unless force)
    if book["data"].get("interior_pdf") and not request.force_regenerate:
        return {"success": True, "message": "Interior already generated", "path": book["data"]["interior_pdf"]}

    # Update status
    update_book(request.book_id, {"status": "generating"})

    try:
        from .generators.interior_builder import build_interior

        # Build interior data from book record
        book_data = {
            **book["data"],
            "title": book["title"],
        }

        output_dir = OUTPUT_DIR / book["catalog_number"]
        result = build_interior(book_data, output_dir)

        if result.get("error"):
            update_book(request.book_id, {"status": "draft"})
            return {"success": False, "message": result["error"]}

        # Update book with generated file info
        update_book(request.book_id, {
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
        update_book(request.book_id, {"status": "draft"})
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@app.post("/api/generate/cover")
async def generate_cover(request: GenerateCoverRequest):
    """Generate the book cover PDF."""
    book = get_book(request.book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Check if already generated (unless force)
    if book["data"].get("cover_pdf") and not request.force_regenerate:
        return {"success": True, "message": "Cover already generated", "path": book["data"]["cover_pdf"]}

    update_book(request.book_id, {"status": "generating"})

    try:
        from .cover.renderer import render_cover

        data = book["data"]
        page_count = data.get("page_count", 120)
        trim_size = data.get("trim_size", "8.5x11")
        paper_type = data.get("paper_type", "white_bw")
        gen_config = data.get("generator_config", {})

        output_dir = OUTPUT_DIR / book["catalog_number"]
        output_dir.mkdir(parents=True, exist_ok=True)

        result = await render_cover(
            page_count=page_count,
            trim_size=trim_size,
            paper_type=paper_type,
            title=book["title"],
            subtitle=data.get("subtitle", ""),
            author=data.get("author_name", "Creative Puzzles Press"),
            book_type=data.get("book_type", "default"),
            output_dir=output_dir,
            puzzle_count=gen_config.get("num_puzzles", 55),
        )

        if not result.get("success", False):
            update_book(request.book_id, {"status": "draft"})
            return {"success": False, "message": result.get("error", "Cover generation failed")}

        # Update book with cover file paths
        update_data = {"status": "draft"}
        if result.get("cover_pdf"):
            update_data["cover_pdf"] = result["cover_pdf"]
        if result.get("cover_png"):
            update_data["cover_front_png"] = result["cover_png"]

        update_book(request.book_id, update_data)

        return {
            "success": True,
            "message": "Cover generated successfully",
            "note": result.get("note", ""),
            "dimensions": result.get("dimensions", {}),
        }

    except Exception as e:
        update_book(request.book_id, {"status": "draft"})
        raise HTTPException(status_code=500, detail=f"Cover generation failed: {str(e)}")


@app.post("/api/quality/validate", response_model=SuccessResponse)
async def run_quality_check(request: QualityCheckRequest):
    """Run the 5-gate quality validation pipeline. (Phase 5)"""
    book = get_book(request.book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

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
    book = get_book(request.book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book["status"] != "ready":
        raise HTTPException(
            status_code=400,
            detail=f"Book must be in 'ready' status to upload. Current: {book['status']}"
        )

    # TODO: Phase 8 — Playwright KDP upload
    return {"success": True, "message": "Upload queued (not yet implemented)"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILE SERVING (generated PDFs and images)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/files/{book_id}/{filename}")
async def serve_file(book_id: str, filename: str):
    """Serve generated files (PDFs, images) for a book."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Files are stored in output/{catalog_number}/
    file_path = OUTPUT_DIR / book["catalog_number"] / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type
    content_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".json": "application/json",
    }
    suffix = file_path.suffix.lower()
    content_type = content_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        filename=filename,
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


@app.get("/api/preview/{book_id}/files")
async def get_book_files(book_id: str):
    """List all generated files for a book."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    output_path = OUTPUT_DIR / book["catalog_number"]
    files = {}

    if output_path.exists():
        for f in output_path.iterdir():
            if f.is_file():
                files[f.name] = {
                    "name": f.name,
                    "size": f.stat().st_size,
                    "url": f"/api/files/{book_id}/{f.name}",
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
        "catalog_number": book["catalog_number"],
        "files": files,
        "has_interior": interior_path.exists(),
        "interior_pages": interior_pages,
        "has_cover": cover_path.exists(),
        "has_cover_front": cover_front_path.exists(),
    }


@app.get("/api/preview/{book_id}/interior/{page_num}")
async def preview_interior_page(
    book_id: str,
    page_num: int,
    width: int = Query(800, ge=200, le=2400, description="Render width in pixels"),
):
    """Render a single interior PDF page as PNG image."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    pdf_path = OUTPUT_DIR / book["catalog_number"] / "interior.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Interior PDF not found. Generate the interior first.")

    try:
        png_bytes = _render_pdf_page(str(pdf_path), page_num, width)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {str(e)}")

    return Response(content=png_bytes, media_type="image/png")


@app.get("/api/preview/{book_id}/cover")
async def preview_cover(
    book_id: str,
    width: int = Query(800, ge=200, le=2400, description="Render width in pixels"),
):
    """Get the front cover preview image."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    output_path = OUTPUT_DIR / book["catalog_number"]

    # First try the pre-rendered PNG
    cover_front = output_path / "cover-front.png"
    if cover_front.exists():
        return FileResponse(str(cover_front), media_type="image/png")

    # Fall back to rendering from cover PDF
    cover_pdf = output_path / "cover.pdf"
    if cover_pdf.exists():
        try:
            png_bytes = _render_pdf_page(str(cover_pdf), 0, width)
            return Response(content=png_bytes, media_type="image/png")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cover render failed: {str(e)}")

    raise HTTPException(status_code=404, detail="No cover found. Generate the cover first.")


@app.get("/api/preview/{book_id}/cover/full")
async def preview_cover_full(
    book_id: str,
    width: int = Query(1600, ge=200, le=4800, description="Render width in pixels"),
):
    """Get the full cover (front + spine + back) preview image."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    cover_pdf = OUTPUT_DIR / book["catalog_number"] / "cover.pdf"
    if not cover_pdf.exists():
        raise HTTPException(status_code=404, detail="Cover PDF not found.")

    try:
        png_bytes = _render_pdf_page(str(cover_pdf), 0, width)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cover render failed: {str(e)}")

    return Response(content=png_bytes, media_type="image/png")


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
