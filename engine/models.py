"""
SCRPT Data Models
==================
Pydantic models for API request/response validation.
These are the contracts between the frontend and backend.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────

class BookStatus(str, Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    QUALITY_CHECK = "quality_check"
    READY = "ready"
    UPLOADING = "uploading"
    IN_REVIEW = "in_review"
    LIVE = "live"
    REJECTED = "rejected"
    PAUSED = "paused"


class PaperType(str, Enum):
    WHITE_BW = "white_bw"
    CREAM_BW = "cream_bw"
    STANDARD_COLOR = "standard_color"
    PREMIUM_COLOR = "premium_color"


class BookType(str, Enum):
    WORD_SEARCH = "word_search"
    COLORING_BOOK = "coloring_book"
    CRYPTOGRAM = "cryptogram"
    KIDS_ACTIVITY = "kids_activity"
    PASSWORD_LOG = "password_log"
    COLOR_BY_NUMBER = "color_by_number"
    SUDOKU = "sudoku"
    MAZE = "maze"
    MATH_WORKBOOK = "math_workbook"
    JOURNAL = "journal"


# ── Book Models ──────────────────────────────────────────────────

class BookMetadata(BaseModel):
    """All book metadata stored as JSON in the database."""
    book_type: str
    trim_size: str = "8.5x11"
    paper_type: str = "white_bw"
    page_count: int = 120

    # Listing info
    subtitle: str = ""
    author_name: str = ""
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)

    # Pricing
    list_price: float = 9.99
    currency: str = "USD"

    # Production
    interior_pdf: Optional[str] = None      # Path to generated interior PDF
    cover_pdf: Optional[str] = None         # Path to generated cover PDF
    cover_front_png: Optional[str] = None   # Front cover preview image

    # Quality results
    quality_score: Optional[float] = None
    quality_report: Optional[dict] = None
    ai_vision_score: Optional[float] = None
    dimension_check_passed: Optional[bool] = None

    # Amazon KDP
    asin: Optional[str] = None              # Amazon Standard ID (after publish)
    kdp_id: Optional[str] = None            # KDP internal book ID
    bsr: Optional[int] = None               # Best Sellers Rank

    # Niche reference
    niche_keyword: Optional[str] = None
    niche_id: Optional[str] = None

    # Generation settings (varies by book type)
    generator_config: dict = Field(default_factory=dict)


class BookCreate(BaseModel):
    """Request body for creating a new book."""
    title: str
    subtitle: str = ""
    book_type: str
    trim_size: str = "8.5x11"
    paper_type: str = "white_bw"
    page_count: int = 120
    author_name: str = ""
    list_price: float = 9.99
    niche_keyword: Optional[str] = None
    generator_config: dict = Field(default_factory=dict)


class BookUpdate(BaseModel):
    """Request body for updating an existing book."""
    title: Optional[str] = None
    subtitle: Optional[str] = None
    status: Optional[BookStatus] = None
    trim_size: Optional[str] = None
    paper_type: Optional[str] = None
    page_count: Optional[int] = None
    author_name: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[list[str]] = None
    categories: Optional[list[str]] = None
    list_price: Optional[float] = None
    generator_config: Optional[dict] = None


class BookResponse(BaseModel):
    """Response model for a single book."""
    id: str
    catalog_number: str
    title: str
    status: str
    data: BookMetadata
    created_at: str
    updated_at: str


class BookListResponse(BaseModel):
    """Response model for listing books."""
    books: list[BookResponse]
    total: int
    page: int
    per_page: int


# ── Niche Models ─────────────────────────────────────────────────

class NicheData(BaseModel):
    """Niche analysis data stored as JSON."""
    keyword: str
    bsr_range: Optional[str] = None
    estimated_monthly_sales: Optional[int] = None
    competition_level: Optional[str] = None
    opportunity_score: Optional[float] = None
    demand_level: Optional[str] = None

    # BSR validation
    top_bsr: Optional[int] = None           # Best BSR found
    avg_bsr: Optional[int] = None           # Average BSR of top 10
    sample_books: list[dict] = Field(default_factory=list)

    # Recommendations
    recommended_book_types: list[str] = Field(default_factory=list)
    recommended_trim: Optional[str] = None
    recommended_pages: Optional[int] = None
    recommended_price: Optional[float] = None

    # Analysis
    analysis_notes: str = ""
    rejection_reason: Optional[str] = None


class NicheCreate(BaseModel):
    """Request body for creating a niche entry."""
    keyword: str
    data: NicheData


class NicheResponse(BaseModel):
    """Response model for a niche."""
    id: str
    keyword: str
    status: str
    data: NicheData
    created_at: str


class NicheListResponse(BaseModel):
    """Response model for listing niches."""
    niches: list[NicheResponse]
    total: int


# ── Dashboard Models ─────────────────────────────────────────────

class DashboardStats(BaseModel):
    """Dashboard summary statistics."""
    total_books: int = 0
    books_by_status: dict[str, int] = Field(default_factory=dict)
    books_live: int = 0
    books_in_progress: int = 0
    total_niches: int = 0
    validated_niches: int = 0

    # Revenue estimates
    estimated_monthly_revenue: float = 0.0
    average_bsr: Optional[int] = None

    # Recent activity
    recent_books: list[BookResponse] = Field(default_factory=list)
    recent_niches: list[NicheResponse] = Field(default_factory=list)


# ── Generation Models ────────────────────────────────────────────
# Companion mode: frontend sends full book data inline (no local DB lookup).
# Legacy mode: send book_id to look up from local SQLite.

class GenerateInteriorRequest(BaseModel):
    """Request to generate a book interior."""
    # Companion mode — inline data from Supabase
    catalog_number: Optional[str] = None
    title: Optional[str] = None
    book_type: Optional[str] = None
    trim_size: str = "8.5x11"
    paper_type: str = "white_bw"
    page_count: int = 120
    generator_config: dict = Field(default_factory=dict)
    # Legacy mode — look up from local SQLite
    book_id: Optional[str] = None
    force_regenerate: bool = False


class GenerateCoverRequest(BaseModel):
    """Request to generate a book cover."""
    # Companion mode — inline data from Supabase
    catalog_number: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = ""
    author_name: Optional[str] = ""
    book_type: Optional[str] = None
    trim_size: str = "8.5x11"
    paper_type: str = "white_bw"
    page_count: int = 120
    generator_config: dict = Field(default_factory=dict)
    # Legacy mode — look up from local SQLite
    book_id: Optional[str] = None
    force_regenerate: bool = False


class GenerateDesignRequest(BaseModel):
    """Request to generate a cover design from a reference image."""
    reference_image_url: str
    reference_asin: Optional[str] = None
    book_type: str
    niche_keyword: Optional[str] = None


class QualityCheckRequest(BaseModel):
    """Request to run quality checks on a book."""
    book_id: Optional[str] = None
    catalog_number: Optional[str] = None
    skip_ai_review: bool = False


class UploadRequest(BaseModel):
    """Request to upload a book to KDP."""
    book_id: Optional[str] = None
    catalog_number: Optional[str] = None


# ── Settings Model ───────────────────────────────────────────────

class AuthorPenName(BaseModel):
    """A pen name associated with specific book genres."""
    name: str
    genres: list[str] = []  # Book type keys, e.g. ["word_search", "maze"]


class SettingsUpdate(BaseModel):
    """Partial settings update."""
    # Publisher identity
    publisher_name: Optional[str] = None
    author_name: Optional[str] = None          # legacy / default fallback
    copyright_holder: Optional[str] = None
    website: Optional[str] = None
    kdp_email: Optional[str] = None

    # Standard book defaults
    default_trim_size: Optional[str] = None
    default_paper_type: Optional[str] = None
    default_description_template: Optional[str] = None
    default_keywords: Optional[list[str]] = None
    default_categories: Optional[list[str]] = None

    # Author pen names (list of name + genres)
    author_pen_names: Optional[list[AuthorPenName]] = None

    # Upload / automation
    comfyui_url: Optional[str] = None
    auto_upload: Optional[bool] = None
    daily_upload_limit: Optional[int] = None


# ── API Response Wrappers ────────────────────────────────────────

class SuccessResponse(BaseModel):
    """Generic success response."""
    success: bool = True
    message: str = "OK"


class ErrorResponse(BaseModel):
    """Generic error response."""
    success: bool = False
    error: str
    detail: Optional[str] = None
