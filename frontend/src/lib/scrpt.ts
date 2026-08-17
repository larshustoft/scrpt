/**
 * SCRPT engine client — the /api/scrpt prose-book API on the local companion.
 * Mirrors the Pydantic contracts in engine/prose/models.py.
 */

const ENGINE_URL =
  process.env.NEXT_PUBLIC_ENGINE_URL || "http://127.0.0.1:8000";

// ── types ────────────────────────────────────────────────────────

export type BookKind = "fiction" | "nonfiction";

export type BlockType =
  | "paragraph" | "heading" | "scene_break" | "blockquote"
  | "bullet_list" | "numbered_list" | "callout" | "exercise";

export interface Block {
  id: string;
  type: BlockType;
  text: string;
  level?: number;
  items?: string[];
  title?: string;
}

export interface Chapter {
  id: string;
  index: number;
  title: string;
  subtitle?: string;
  epigraph?: string;
  epigraph_source?: string;
  blocks: Block[];
  status: "outlined" | "drafting" | "drafted" | "revised" | "final";
  outline_summary: string;
  beats: string[];
  rolling_summary: string;
  word_count: number;
  quality_score?: number | null;
  quality_notes?: string;
  hook_type?: string;
  revised?: boolean;
}

export interface Manuscript {
  kind: BookKind;
  genre_preset: string;
  idea: string;
  plot_options: { title: string; logline: string; synopsis: string }[];
  chosen_plot: number | null;
  story_bible: Record<string, unknown> | null;
  concept_bible: Record<string, unknown> | null;
  target_words: number;
  status: "idea" | "plotting" | "bible" | "outlined" | "drafting" | "drafted" | "editing" | "locked";
  chapters: Chapter[];
  front_matter: FrontMatterConfig;
  back_matter: BackMatterConfig;
  blurb: string;
  tagline: string;
  ai_disclosure: boolean;
  word_count: number;
}

export interface FrontMatterConfig {
  half_title: boolean;
  also_by: string[];
  title_page: boolean;
  copyright_page: boolean;
  copyright_text: string;
  dedication: string;
  epigraph: string;
  epigraph_source: string;
  toc: boolean | null;
  introduction_title: string;
}

export interface BackMatterConfig {
  acknowledgments: string;
  about_the_author: string;
  next_in_series_cta: string;
  also_by: string[];
}

export interface FormatConfig {
  trim_size: string;
  paper_type: string;
  bleed: boolean;
  font_preset: string;
  font_size_pt: number | null;
  leading: number | null;
  justify: boolean;
  paragraph_style: "indent" | "spaced";
  chapter_sink: number;
  drop_caps: boolean;
  running_header_verso: "author" | "title" | "none";
  running_header_recto: "title" | "chapter" | "none";
  scene_break_glyph: string;
  margin_top: number;
  margin_bottom: number;
  margin_outside: number;
  gutter_extra: number;
}

export interface ScrptBook {
  id: string;
  catalog_number: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  data: {
    kind?: BookKind;
    genre_preset?: string;
    author_name?: string;
    trim_size?: string;
    paper_type?: string;
    page_count?: number;
    list_price?: number;
    description?: string;
    keywords?: string[];
    categories?: string[];
    manuscript?: Manuscript;
    format?: FormatConfig;
    interior?: {
      page_count?: number;
      locked?: boolean;
      pdf_path?: string;
      exported_at?: string;
      validation?: ValidationReport;
    };
    cover?: {
      mode?: "ai" | "upload";
      status?: string;
      spec?: CoverSpec;
      spec_page_count?: number;
      uploaded_path?: string;
      cover_pdf?: string;
      cover_front_png?: string;
      variants?: { index: number; preview: string; concept?: string; brief?: string }[];
      selected_variant?: number;
      validation?: ValidationReport;
    };
    audio?: {
      status?: string;
      voice_name?: string;
      chapters?: { index: number; title: string; audio_path: string; duration_s: number }[];
      sample_path?: string;
      total_duration_s?: number;
    };
    series?: {
      series_id?: string;
      series_title?: string;
      book_number?: number;
      total_planned?: number;
      series_bible?: string;
    };
    acceptance?: {
      verdict?: "accept" | "revise";
      score?: number;
      length?: { total_words: number; target_words: number; floor: number;
        ceiling: number; ok: boolean };
      length_repairs?: number[];
      revision_orders?: { chapter: number; order: string }[];
      review?: { strengths?: string[]; editor_letter?: string;
        issues?: { chapter: number; order: string }[] };
    };
    [key: string]: unknown;
  };
}

export interface ValidationReport {
  passed: boolean;
  checks: { name: string; ok: boolean; detail: string }[];
}

export interface CoverSpec {
  page_count: number;
  trim_size: string;
  paper_type: string;
  spine_width_in: number;
  spine_has_text: boolean;
  total_width_in: number;
  total_height_in: number;
  total_width_px: number;
  total_height_px: number;
  bleed_in: number;
  safe_zone_in: number;
  dpi: number;
}

export interface Job {
  id: string;
  kind: string;
  book_catalog: string | null;
  status: "queued" | "running" | "done" | "error" | "cancelled" | "interrupted";
  progress: number;
  stage: string;
  detail: string;
  result?: Record<string, unknown>;
  error?: string;
  created_at: string;
  updated_at: string;
}

export interface GenrePreset {
  kind: BookKind;
  label: string;
  comps: string;
  trim: string;
  paper: string;
  target_words: number;
  chapter_words: number;
  pov: string;
  font: string;
}

export interface WorkOrderPayload {
  kind: BookKind;
  genre_preset: string;
  idea: string;
  title?: string;
  pen_name?: string;
  series_title?: string;
  series_books?: number;
  target_words?: number | null;
  trim_size?: string | null;
  paper_type?: string | null;
  font_preset?: string | null;
  cover_direction?: string;
  book_titles?: string[];
  generate_plot_options?: boolean;
  auto_draft?: boolean;
}

// ── fetch helpers ────────────────────────────────────────────────

class EngineOffline extends Error {
  constructor() {
    super("SCRPT engine is not running on this machine");
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${ENGINE_URL}${path}`, {
      ...init,
      signal: init?.signal ?? AbortSignal.timeout(600_000),
    });
  } catch {
    throw new EngineOffline();
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch { /* keep statusText */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// ── API surface ──────────────────────────────────────────────────

export const scrpt = {
  engineUrl: ENGINE_URL,

  async health(): Promise<boolean> {
    try {
      const res = await fetch(`${ENGINE_URL}/api/health`, {
        signal: AbortSignal.timeout(3000),
      });
      return res.ok;
    } catch {
      return false;
    }
  },

  presets: () =>
    call<{ genres: Record<string, GenrePreset>; fonts: Record<string, { label: string; family: string; size_pt: number; leading: number }> }>(
      "/api/scrpt/presets"),

  createWorkOrder: (payload: WorkOrderPayload) =>
    call<{ books: ScrptBook[]; job_id: string | null }>("/api/scrpt/workorder", json(payload)),

  getBook: (catalog: string) => call<ScrptBook>(`/api/scrpt/books/${catalog}`),

  listBooks: () =>
    call<{ books: ScrptBook[]; total: number }>("/api/scrpt/books"),

  regeneratePlots: (catalog: string) =>
    call<{ job_id: string }>(`/api/scrpt/plot-options/${catalog}`, { method: "POST" }),

  choosePlot: (catalog: string, chosen: number, edits = "") =>
    call<{ job_id: string }>("/api/scrpt/choose-plot",
      json({ catalog_number: catalog, chosen_plot: chosen, edits })),

  resumeDraft: (catalog: string) =>
    call<{ job_id: string }>(`/api/scrpt/draft/${catalog}`, { method: "POST" }),

  saveChapter: (catalog: string, chapterId: string, blocks: Block[]) =>
    call<{ success: boolean; chapter_words: number; book_words: number }>(
      "/api/scrpt/chapter",
      { ...json({ catalog_number: catalog, chapter_id: chapterId, blocks }), method: "PUT" }),

  regenerateBlurb: (catalog: string) =>
    call<{ job_id: string }>(`/api/scrpt/blurb/${catalog}`, { method: "POST" }),

  job: (id: string) => call<Job>(`/api/scrpt/jobs/${id}`),
  jobs: (catalog?: string, active = false) =>
    call<{ jobs: Job[] }>(
      `/api/scrpt/jobs?${catalog ? `catalog=${catalog}&` : ""}active=${active}`),
  cancelJob: (id: string) =>
    call<{ cancelled: boolean }>(`/api/scrpt/jobs/${id}/cancel`, { method: "POST" }),

  exportInterior: (catalog: string) =>
    call<{ job_id: string }>(`/api/scrpt/interior/export/${catalog}`, { method: "POST" }),
  interiorPdfUrl: (catalog: string) =>
    `${ENGINE_URL}/api/scrpt/interior/pdf/${catalog}`,

  coverSpec: (catalog: string) => call<CoverSpec>(`/api/scrpt/cover/spec/${catalog}`),
  designerPackage: (catalog: string) =>
    call<{ spec_sheet: string; template_pdf: string; spec: CoverSpec }>(
      `/api/scrpt/cover/designer-package/${catalog}`, { method: "POST" }),
  designerFileUrl: (catalog: string, file: "spec" | "template") =>
    `${ENGINE_URL}/api/scrpt/cover/designer-package/${catalog}/${file}`,

  uploadCover: async (catalog: string, file: File): Promise<ValidationReport & { expected?: CoverSpec }> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${ENGINE_URL}/api/scrpt/cover/upload/${catalog}`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || res.statusText);
    }
    return res.json();
  },

  startAudiobook: (catalog: string) =>
    call<{ job_id: string }>(`/api/scrpt/audio/${catalog}`, { method: "POST" }),
  audioFileUrl: (catalog: string, path: string) => {
    const name = path.split("/").pop() || "";
    return `${ENGINE_URL}/api/scrpt/audio/file/${catalog}/${name}`;
  },

  importReport: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${ENGINE_URL}/api/scrpt/reports/import`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || res.statusText);
    }
    return res.json() as Promise<{ file: string; total_added: number; sheets: Record<string, { added: number; rows: number }> }>;
  },

  reportsSummary: () =>
    call<{
      by_month: { month: string; format: string; units: number; kenp_pages: number; royalty: number; currency: string }[];
      by_marketplace: { marketplace: string; units: number; royalty: number; currency: string }[];
      totals: { titles: number; units: number; kenp_pages: number; royalty: number };
    }>("/api/scrpt/reports/summary"),

  reportsSeries: () =>
    call<{
      series: {
        series_id: string; series_title: string; proven: boolean;
        books: { catalog_number: string; title: string; book_number: number; units: number; kenp_pages: number; royalty: number }[];
        readthrough: (number | null)[];
        value_per_first_sale: number | null;
        royalty_total: number; royalty_recent_60d: number;
        suggested_ad_share: number;
      }[];
      notes: { min_units_proven: number; explore_pool: number };
    }>("/api/scrpt/reports/series"),

  reportsByBook: () =>
    call<{ books: { title: string; asin: string; format: string; units: number; kenp_pages: number; royalty: number; currency: string; catalog_number: string | null }[] }>(
      "/api/scrpt/reports/books"),
};

/** Poll a job until it settles. onTick fires on every poll. */
export async function pollJob(
  jobId: string,
  onTick?: (job: Job) => void,
  intervalMs = 2500,
): Promise<Job> {
  for (;;) {
    const job = await scrpt.job(jobId);
    onTick?.(job);
    if (["done", "error", "cancelled", "interrupted"].includes(job.status)) {
      return job;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
