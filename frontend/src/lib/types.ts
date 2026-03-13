// SCRPT TypeScript Types
// ======================
// Mirrors the Python Pydantic models exactly.

export type BookStatus =
  | "draft"
  | "generating"
  | "quality_check"
  | "ready"
  | "uploading"
  | "in_review"
  | "live"
  | "rejected"
  | "paused";

export type BookType =
  | "word_search"
  | "coloring_book"
  | "cryptogram"
  | "kids_activity"
  | "password_log"
  | "color_by_number"
  | "sudoku"
  | "maze"
  | "math_workbook"
  | "journal";

export type PaperType =
  | "white_bw"
  | "cream_bw"
  | "standard_color"
  | "premium_color";

export interface BookMetadata {
  book_type: BookType;
  trim_size: string;
  paper_type: PaperType;
  page_count: number;
  subtitle: string;
  author_name: string;
  description: string;
  keywords: string[];
  categories: string[];
  list_price: number;
  currency: string;
  interior_pdf: string | null;
  cover_pdf: string | null;
  cover_front_png: string | null;
  quality_score: number | null;
  quality_report: Record<string, unknown> | null;
  ai_vision_score: number | null;
  dimension_check_passed: boolean | null;
  asin: string | null;
  kdp_id: string | null;
  bsr: number | null;
  niche_keyword: string | null;
  niche_id: string | null;
  generator_config: Record<string, unknown>;
}

export interface Book {
  id: string;
  catalog_number: string;
  title: string;
  status: BookStatus;
  data: BookMetadata;
  created_at: string;
  updated_at: string;
}

export interface BookListResponse {
  books: Book[];
  total: number;
  page: number;
  per_page: number;
}

export interface NicheData {
  keyword: string;
  bsr_range: string | null;
  estimated_monthly_sales: number | null;
  competition_level: string | null;
  opportunity_score: number | null;
  demand_level: string | null;
  top_bsr: number | null;
  avg_bsr: number | null;
  sample_books: Record<string, unknown>[];
  recommended_book_types: string[];
  recommended_trim: string | null;
  recommended_pages: number | null;
  recommended_price: number | null;
  analysis_notes: string;
  rejection_reason: string | null;
}

export interface Niche {
  id: string;
  keyword: string;
  status: string;
  data: NicheData;
  created_at: string;
}

export interface NicheListResponse {
  niches: Niche[];
  total: number;
}

export interface DashboardStats {
  total_books: number;
  books_by_status: Record<string, number>;
  books_live: number;
  books_in_progress: number;
  total_niches: number;
  validated_niches: number;
  estimated_monthly_revenue: number;
  average_bsr: number | null;
  recent_books: Book[];
  recent_niches: Niche[];
}

export interface CoverDimensions {
  page_count: number;
  trim_size: string;
  paper_type: string;
  trim_width: number;
  trim_height: number;
  spine_width: number;
  spine_has_text: boolean;
  total_width: number;
  total_height: number;
  total_width_px: number;
  total_height_px: number;
  spine_width_px: number;
  bleed_px: number;
  safe_zone_px: number;
  zones: {
    back_cover: { start_px: number; end_px: number };
    spine: { start_px: number; end_px: number };
    front_cover: { start_px: number; end_px: number };
    barcode: { x_px: number; y_px: number };
  };
}

export interface AppConfig {
  book_types: Record<
    string,
    {
      name: string;
      default_trim: string;
      default_pages: number;
      default_paper: string;
      generator: string;
    }
  >;
  trim_sizes: {
    value: string;
    label: string;
    width: number;
    height: number;
  }[];
  paper_types: {
    value: string;
    label: string;
  }[];
  statuses: string[];
}

// Status display helpers
export const STATUS_LABELS: Record<BookStatus, string> = {
  draft: "Draft",
  generating: "Generating",
  quality_check: "Quality Check",
  ready: "Ready",
  uploading: "Uploading",
  in_review: "In Review",
  live: "Live",
  rejected: "Rejected",
  paused: "Paused",
};

export const STATUS_COLORS: Record<BookStatus, string> = {
  draft: "bg-gray-100 text-gray-700",
  generating: "bg-blue-100 text-blue-700",
  quality_check: "bg-yellow-100 text-yellow-700",
  ready: "bg-green-100 text-green-700",
  uploading: "bg-purple-100 text-purple-700",
  in_review: "bg-orange-100 text-orange-700",
  live: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  paused: "bg-gray-100 text-gray-500",
};

export const BOOK_TYPE_LABELS: Record<BookType, string> = {
  word_search: "Word Search",
  coloring_book: "Coloring Book",
  cryptogram: "Cryptogram",
  kids_activity: "Kids Activity",
  password_log: "Password Log",
  color_by_number: "Color by Number",
  sudoku: "Sudoku",
  maze: "Maze Book",
  math_workbook: "Math Workbook",
  journal: "Journal",
};

export const BOOK_TYPE_SHORT: Record<BookType, string> = {
  word_search: "WS",
  coloring_book: "CB",
  cryptogram: "CR",
  kids_activity: "KA",
  password_log: "PL",
  color_by_number: "CN",
  sudoku: "SU",
  maze: "MZ",
  math_workbook: "MW",
  journal: "JN",
};
