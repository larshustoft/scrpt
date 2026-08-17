// SCRPT API Client
// =================
// All communication with the Python backend goes through here.

import type {
  Book,
  BookListResponse,
  Niche,
  NicheListResponse,
  DashboardStats,
  CoverDimensions,
  AppConfig,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Base Fetch ──────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;

  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || error.error || `API error: ${res.status}`);
  }

  return res.json();
}

// ── Health & Config ─────────────────────────────────────────────

export async function healthCheck() {
  return apiFetch<{ status: string; service: string; version: string }>(
    "/api/health"
  );
}

export async function getConfig() {
  return apiFetch<AppConfig>("/api/config");
}

// ── Dashboard ───────────────────────────────────────────────────

export async function getDashboard() {
  return apiFetch<DashboardStats>("/api/dashboard");
}

// ── Books ───────────────────────────────────────────────────────

export async function getBooks(params?: {
  status?: string;
  book_type?: string;
  page?: number;
  per_page?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set("status", params.status);
  if (params?.book_type) searchParams.set("book_type", params.book_type);
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.per_page) searchParams.set("per_page", String(params.per_page));

  const query = searchParams.toString();
  return apiFetch<BookListResponse>(`/api/books${query ? `?${query}` : ""}`);
}

export async function getBook(id: string) {
  return apiFetch<Book>(`/api/books/${id}`);
}

export async function getBookByCatalog(catalogNumber: string) {
  return apiFetch<Book>(`/api/books/catalog/${catalogNumber}`);
}

export async function createBook(data: {
  title: string;
  book_type: string;
  subtitle?: string;
  trim_size?: string;
  paper_type?: string;
  page_count?: number;
  author_name?: string;
  list_price?: number;
  niche_keyword?: string;
  generator_config?: Record<string, unknown>;
}) {
  return apiFetch<Book>("/api/books", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateBook(
  id: string,
  data: Partial<{
    title: string;
    subtitle: string;
    status: string;
    trim_size: string;
    paper_type: string;
    page_count: number;
    author_name: string;
    description: string;
    keywords: string[];
    categories: string[];
    list_price: number;
    generator_config: Record<string, unknown>;
  }>
) {
  return apiFetch<Book>(`/api/books/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteBook(id: string) {
  return apiFetch<{ success: boolean; message: string }>(`/api/books/${id}`, {
    method: "DELETE",
  });
}

// ── Niches ──────────────────────────────────────────────────────

export async function getNiches(status?: string) {
  const query = status ? `?status=${status}` : "";
  return apiFetch<NicheListResponse>(`/api/niches${query}`);
}

export async function getNiche(id: string) {
  return apiFetch<Niche>(`/api/niches/${id}`);
}

export async function createNiche(data: {
  keyword: string;
  data: Record<string, unknown>;
}) {
  return apiFetch<Niche>("/api/niches", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteNiche(id: string) {
  return apiFetch<{ success: boolean; message: string }>(
    `/api/niches/${id}`,
    { method: "DELETE" }
  );
}

// ── Settings ────────────────────────────────────────────────────

export async function getSettings() {
  return apiFetch<Record<string, unknown>>("/api/settings");
}

export interface AuthorPenName {
  name: string;
  genres: string[];
}

export async function updateSettings(
  data: Partial<{
    publisher_name: string;
    author_name: string;
    copyright_holder: string;
    website: string;
    kdp_email: string;
    default_trim_size: string;
    default_paper_type: string;
    default_description_template: string;
    default_keywords: string[];
    default_categories: string[];
    author_pen_names: AuthorPenName[];
    comfyui_url: string;
    auto_upload: boolean;
    daily_upload_limit: number;
  }>
) {
  return apiFetch<{ success: boolean; message: string }>("/api/settings", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

// ── Cover Dimensions ────────────────────────────────────────────

export async function getCoverDimensions(params: {
  page_count: number;
  trim_size: string;
  paper_type: string;
}) {
  const searchParams = new URLSearchParams({
    page_count: String(params.page_count),
    trim_size: params.trim_size,
    paper_type: params.paper_type,
  });

  return apiFetch<CoverDimensions>(
    `/api/cover/dimensions?${searchParams.toString()}`
  );
}

// ── Generation (stubs for future phases) ────────────────────────

export async function generateInterior(bookId: string) {
  return apiFetch<{ success: boolean; message: string }>(
    "/api/generate/interior",
    {
      method: "POST",
      body: JSON.stringify({ book_id: bookId }),
    }
  );
}

export async function generateCover(bookId: string) {
  return apiFetch<{ success: boolean; message: string }>(
    "/api/generate/cover",
    {
      method: "POST",
      body: JSON.stringify({ book_id: bookId }),
    }
  );
}

export async function runQualityCheck(
  bookId: string,
  skipAiReview?: boolean
) {
  return apiFetch<{ success: boolean; message: string }>(
    "/api/quality/validate",
    {
      method: "POST",
      body: JSON.stringify({
        book_id: bookId,
        skip_ai_review: skipAiReview ?? false,
      }),
    }
  );
}

export async function submitToKDP(bookId: string) {
  return apiFetch<{ success: boolean; message: string }>(
    "/api/upload/submit",
    {
      method: "POST",
      body: JSON.stringify({ book_id: bookId }),
    }
  );
}

// ── File URLs ───────────────────────────────────────────────────

export function getFileUrl(bookId: string, filename: string) {
  return `${API_BASE}/api/files/${bookId}/${filename}`;
}

// ── Preview System ──────────────────────────────────────────────

export interface BookFiles {
  catalog_number: string;
  files: Record<
    string,
    { name: string; size: number; url: string }
  >;
  has_interior: boolean;
  interior_pages: number;
  has_cover: boolean;
  has_cover_front: boolean;
}

export async function getBookFiles(bookId: string) {
  return apiFetch<BookFiles>(`/api/preview/${bookId}/files`);
}

export function getInteriorPageUrl(
  bookId: string,
  pageNum: number,
  width: number = 800
) {
  return `${API_BASE}/api/preview/${bookId}/interior/${pageNum}?width=${width}`;
}

export function getCoverPreviewUrl(bookId: string, width: number = 800) {
  return `${API_BASE}/api/preview/${bookId}/cover?width=${width}`;
}

export function getCoverFullUrl(bookId: string, width: number = 1600) {
  return `${API_BASE}/api/preview/${bookId}/cover/full?width=${width}`;
}

// ── Cover Archetypes ─────────────────────────────────────────

export interface Archetype {
  archetype_id: string;
  name: string;
  description: string;
  font_pair: string;
  tags: string[];
  themes: Record<string, Record<string, string>>;
}

export async function getArchetypes(bookType: string) {
  return apiFetch<{ book_type: string; archetypes: Archetype[] }>(
    `/api/cover/archetypes/${bookType}`
  );
}

export async function uploadCoverArtwork(data: {
  book_type: string;
  archetype_id: string;
  theme: string;
  image_data: string;
  image_format: string;
}) {
  return apiFetch<{
    success: boolean;
    variant_id: string;
    upload_variant_id: string;
    message: string;
  }>("/api/cover/upload-artwork", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Cover Design Search & AI Generation ──────────────────────

export interface CoverSearchResult {
  title: string;
  asin: string;
  cover_image_url: string;
  price: number | null;
  reviews: number | null;
  rating: number | null;
}

export interface CoverSearchResponse {
  keyword: string;
  results: CoverSearchResult[];
  count: number;
  error?: string;
}

export async function searchBestsellerCovers(
  keyword: string,
  maxResults: number = 5
) {
  const params = new URLSearchParams({
    keyword,
    max_results: String(maxResults),
  });
  return apiFetch<CoverSearchResponse>(
    `/api/cover/search?${params.toString()}`
  );
}

export interface GenerateDesignResponse {
  success: boolean;
  variant_id?: string;
  niche?: string;
  design_notes?: string;
  error?: string;
  fallback?: string;
}

export async function generateDesignFromReference(data: {
  reference_image_url: string;
  reference_asin?: string;
  book_type: string;
  niche_keyword?: string;
}) {
  return apiFetch<GenerateDesignResponse>("/api/cover/generate-design", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Cover Preview (render before book creation) ──────────────

export interface CoverPreviewResponse {
  success: boolean;
  session_id?: string;
  preview_url?: string;
  error?: string;
}

export async function previewCoverDesign(data: {
  title: string;
  subtitle?: string;
  author_name?: string;
  book_type: string;
  trim_size: string;
  paper_type: string;
  page_count: number;
  variant_id?: string;
  puzzle_count?: number;
}) {
  return apiFetch<CoverPreviewResponse>("/api/cover/preview", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getCoverPreviewImageUrl(sessionId: string, width: number = 800) {
  const t = Date.now();
  return `${API_BASE}/api/cover/preview/${sessionId}?width=${width}&t=${t}`;
}
