/**
 * SCRPT Companion Client
 * ======================
 * Client for the local Python companion server (localhost:8000).
 * Handles PDF generation, cover rendering, preview, and file serving.
 * Falls back gracefully when companion is offline.
 */

const COMPANION_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"

interface CompanionResponse<T = unknown> {
  ok: boolean
  data?: T
  error?: string
}

/**
 * Fetch with timeout and graceful fallback.
 * Returns { ok: false } when companion is offline.
 */
async function companionFetch<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 10_000
): Promise<CompanionResponse<T>> {
  const controller = new AbortController()
  const timer = setTimeout(
    () => controller.abort(new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`)),
    timeoutMs,
  )

  try {
    const res = await fetch(`${COMPANION_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    })

    clearTimeout(timer)

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      return { ok: false, error: err.detail || err.error || `Error ${res.status}` }
    }

    const data = await res.json()
    return { ok: true, data: data as T }
  } catch (e) {
    clearTimeout(timer)
    const msg = (e as Error).message
    // Replace cryptic abort message with something useful
    if (msg.includes("aborted") || msg.includes("abort")) {
      return { ok: false, error: `Request timed out after ${Math.round(timeoutMs / 1000)}s — the engine may still be processing` }
    }
    return { ok: false, error: msg }
  }
}

// ── Health ────────────────────────────────────────────────────────

export async function checkHealth(): Promise<boolean> {
  const res = await companionFetch("/api/health", {}, 3_000)
  return res.ok
}

// ── Config ────────────────────────────────────────────────────────

export async function getConfig() {
  return companionFetch<{
    book_types: Record<string, { name: string; default_trim: string; default_pages: number; default_paper: string; generator: string }>
    trim_sizes: { value: string; label: string; width: number; height: number }[]
    paper_types: { value: string; label: string }[]
    statuses: string[]
  }>("/api/config")
}

// ── Generation ────────────────────────────────────────────────────

export async function generateInterior(bookData: Record<string, unknown>) {
  return companionFetch<{ success: boolean; message: string }>(
    "/api/generate/interior",
    { method: "POST", body: JSON.stringify(bookData) }
  )
}

export async function generateCover(bookData: Record<string, unknown>) {
  return companionFetch<{ success: boolean; message: string }>(
    "/api/generate/cover",
    { method: "POST", body: JSON.stringify(bookData) }
  )
}

// ── Quality Check ─────────────────────────────────────────────────

export async function runQualityCheck(bookId: string, skipAi = false) {
  return companionFetch<{ success: boolean; message: string }>(
    "/api/quality/validate",
    {
      method: "POST",
      body: JSON.stringify({ book_id: bookId, skip_ai_review: skipAi }),
    }
  )
}

// ── Cover Dimensions ──────────────────────────────────────────────

export async function getCoverDimensions(params: {
  page_count: number
  trim_size: string
  paper_type: string
}) {
  const sp = new URLSearchParams({
    page_count: String(params.page_count),
    trim_size: params.trim_size,
    paper_type: params.paper_type,
  })
  return companionFetch<Record<string, unknown>>(
    `/api/cover/dimensions?${sp.toString()}`
  )
}

// ── File / Preview URLs ───────────────────────────────────────────
// All file/preview URLs use catalog_number (e.g. SC-001), not Supabase UUID.

export function getFileUrl(catalogNumber: string, filename: string) {
  return `${COMPANION_URL}/api/files/${catalogNumber}/${filename}`
}

export interface BookFiles {
  catalog_number: string
  files: Record<string, { name: string; size: number; url: string }>
  has_interior: boolean
  interior_pages: number
  has_cover: boolean
  has_cover_front: boolean
}

export async function getBookFiles(catalogNumber: string) {
  return companionFetch<BookFiles>(`/api/preview/${catalogNumber}/files`)
}

export function getInteriorPageUrl(
  catalogNumber: string,
  pageNum: number,
  width = 800
) {
  return `${COMPANION_URL}/api/preview/${catalogNumber}/interior/${pageNum}?width=${width}`
}

export function getCoverPreviewUrl(catalogNumber: string, width = 800) {
  const t = Date.now()
  return `${COMPANION_URL}/api/preview/${catalogNumber}/cover?width=${width}&t=${t}`
}

export function getCoverFullUrl(catalogNumber: string, width = 1600) {
  const t = Date.now()
  return `${COMPANION_URL}/api/preview/${catalogNumber}/cover/full?width=${width}&t=${t}`
}

// ── Cover Preview (render before book creation) ──────────────────

export interface CoverPreviewResponse {
  success: boolean
  session_id?: string
  preview_url?: string
  error?: string
}

export async function previewCoverDesign(data: {
  title: string
  subtitle?: string
  author_name?: string
  book_type: string
  trim_size: string
  paper_type: string
  page_count: number
  variant_id?: string
  puzzle_count?: number
}) {
  return companionFetch<CoverPreviewResponse>(
    "/api/cover/preview",
    { method: "POST", body: JSON.stringify(data) },
    180_000 // 180s timeout — QC loop (Claude Vision + re-renders) can take 60-120s
  )
}

export function getCoverPreviewImageUrl(sessionId: string, width = 800) {
  const t = Date.now()
  return `${COMPANION_URL}/api/cover/preview/${sessionId}?width=${width}&t=${t}`
}

// ── Archetypes ───────────────────────────────────────────────────

export interface ArchetypeTheme {
  [key: string]: string
}

export interface Archetype {
  archetype_id: string
  name: string
  description: string
  font_pair: string
  tags: string[]
  themes: Record<string, ArchetypeTheme>
}

export async function getArchetypes(bookType: string) {
  return companionFetch<{ book_type: string; archetypes: Archetype[] }>(
    `/api/cover/archetypes/${bookType}`
  )
}

export async function uploadCoverArtwork(data: {
  book_type: string
  archetype_id: string
  theme: string
  image_data: string
  image_format: string
}) {
  return companionFetch<{
    success: boolean
    variant_id: string
    upload_variant_id: string
    message: string
  }>("/api/cover/upload-artwork", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

// ── Upload ────────────────────────────────────────────────────────

export async function submitToKDP(bookId: string) {
  return companionFetch<{ success: boolean; message: string }>(
    "/api/upload/submit",
    { method: "POST", body: JSON.stringify({ book_id: bookId }) }
  )
}

export { COMPANION_URL }
