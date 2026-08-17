"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useBooks } from "@/hooks/useBooks";
import { getIdeaById, CATEGORY_META, formatTrim } from "@/lib/book-ideas";
import type { BookIdea } from "@/lib/book-ideas";
import { BOOK_TYPE_LABELS, BOOK_TYPE_SHORT } from "@/lib/types";
import {
  previewCoverDesign,
  getCoverPreviewImageUrl,
  generateInterior,
  generateCover,
  getArchetypes,
  uploadCoverArtwork,
} from "@/lib/companion";
import type { Archetype } from "@/lib/companion";
import { IconArrowLeft, IconLoader, IconCheck, IconRefresh } from "@/components/icons";

// ── Types ───────────────────────────────────────────────────────

type DesignStage =
  | "loading"
  | "gallery"
  | "rendering"
  | "preview"
  | "creating";

// ── Book Type Colors ────────────────────────────────────────────

const BOOK_TYPE_COLORS: Record<string, string> = {
  word_search: "bg-blue-100 text-blue-700",
  sudoku: "bg-purple-100 text-purple-700",
  math_workbook: "bg-amber-100 text-amber-700",
  cryptogram: "bg-emerald-100 text-emerald-700",
  maze: "bg-rose-100 text-rose-700",
  password_log: "bg-slate-200 text-slate-700",
  journal: "bg-teal-100 text-teal-700",
};

const PAPER_LABELS: Record<string, string> = {
  white_bw: "White B&W",
  cream_bw: "Cream B&W",
  standard_color: "Standard Color",
  premium_color: "Premium Color",
};

const DEMAND_META: Record<
  string,
  { label: string; color: string; dotColor: string }
> = {
  very_strong: { label: "Very Strong", color: "text-emerald-700", dotColor: "bg-emerald-500" },
  strong: { label: "Strong", color: "text-blue-700", dotColor: "bg-blue-500" },
  moderate: { label: "Moderate", color: "text-amber-700", dotColor: "bg-amber-500" },
  weak: { label: "Weak", color: "text-red-600", dotColor: "bg-red-400" },
};

const THEME_LABELS: Record<string, string> = {
  dark: "Dark",
  cool: "Cool",
  warm: "Warm",
  muted: "Muted",
};

// ── Idea Detail Panel ───────────────────────────────────────────

function IdeaDetailPanel({ idea }: { idea: BookIdea }) {
  const typeColor = BOOK_TYPE_COLORS[idea.book_type] || "bg-gray-100 text-gray-700";
  const catMeta = CATEGORY_META[idea.category];

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="p-5 border-b border-slate-100">
        <div className="flex items-center gap-1.5 flex-wrap mb-2">
          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${typeColor}`}>
            {BOOK_TYPE_SHORT[idea.book_type]}
          </span>
          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${catMeta.color}`}>
            {catMeta.label}
          </span>
        </div>
        <h2 className="text-base font-semibold text-slate-900 leading-tight">
          {idea.title}
        </h2>
        {idea.subtitle && (
          <p className="text-xs text-slate-400 mt-0.5">{idea.subtitle}</p>
        )}
      </div>

      {/* Description */}
      <div className="p-5 border-b border-slate-100">
        <p className="text-xs text-slate-600 leading-relaxed">{idea.description}</p>
      </div>

      {/* Specs Grid */}
      <div className="p-5 border-b border-slate-100">
        <p className="text-[10px] font-medium text-slate-400 uppercase tracking-wider mb-3">
          Specifications
        </p>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2.5">
          <div>
            <p className="text-[10px] text-slate-400">Type</p>
            <p className="text-[13px] font-medium text-slate-700">
              {BOOK_TYPE_LABELS[idea.book_type]}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-slate-400">Trim Size</p>
            <p className="text-[13px] font-medium text-slate-700">
              {formatTrim(idea.trim_size)}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-slate-400">Pages</p>
            <p className="text-[13px] font-medium text-slate-700">{idea.page_count}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-400">Paper</p>
            <p className="text-[13px] font-medium text-slate-700">
              {PAPER_LABELS[idea.paper_type] || idea.paper_type}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-slate-400">Price</p>
            <p className="text-[13px] font-medium text-slate-700">
              ${idea.list_price.toFixed(2)}
              <span className="text-[10px] text-slate-400 ml-1">
                ({idea.list_price >= 9.98 ? "60%" : "50%"} royalty)
              </span>
            </p>
          </div>
          <div>
            <p className="text-[10px] text-slate-400">Audience</p>
            <p className="text-[13px] font-medium text-slate-700">{idea.target_audience}</p>
          </div>
        </div>
      </div>

      {/* Market Data */}
      {idea.market_data && (
        <div className="p-5 border-b border-slate-100">
          <p className="text-[10px] font-medium text-slate-400 uppercase tracking-wider mb-3">
            Market Signal
          </p>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className={`inline-block w-2 h-2 rounded-full ${DEMAND_META[idea.market_data.demand].dotColor}`} />
              <span className={`text-xs font-semibold ${DEMAND_META[idea.market_data.demand].color}`}>
                {DEMAND_META[idea.market_data.demand].label} Demand
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-lg bg-slate-50 px-2.5 py-2 text-center">
                <p className="text-[10px] text-slate-400">BSR</p>
                <p className="text-xs font-semibold text-slate-700">#{idea.market_data.bsr.toLocaleString()}</p>
              </div>
              <div className="rounded-lg bg-slate-50 px-2.5 py-2 text-center">
                <p className="text-[10px] text-slate-400">Results</p>
                <p className="text-xs font-semibold text-slate-700">{idea.market_data.search_results}</p>
              </div>
              <div className="rounded-lg bg-slate-50 px-2.5 py-2 text-center">
                <p className="text-[10px] text-slate-400">Reviews</p>
                <p className="text-xs font-semibold text-slate-700">{idea.market_data.reviews.toLocaleString()}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Revenue Estimate */}
      <div className="p-5">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500">Est. Monthly Revenue</span>
          <span className="text-sm font-semibold text-emerald-600">{idea.est_monthly_revenue}</span>
        </div>
      </div>
    </div>
  );
}

// ── Theme Swatch ────────────────────────────────────────────────

function ThemeSwatch({
  themeId,
  themeVars,
  selected,
  onClick,
}: {
  themeId: string;
  themeVars: Record<string, string>;
  selected: boolean;
  onClick: () => void;
}) {
  const bgPrimary = themeVars["--bg-primary"] || themeVars["--grad-start"] || "#333";
  const accent = themeVars["--accent"] || "#fff";
  const textPrimary = themeVars["--text-primary"] || "#fff";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex flex-col items-center gap-1.5 p-2 rounded-lg transition-all ${
        selected
          ? "ring-2 ring-blue-500 bg-blue-50"
          : "hover:bg-slate-50"
      }`}
    >
      <div className="flex gap-0.5">
        <div className="w-6 h-6 rounded-l-md" style={{ background: bgPrimary }} />
        <div className="w-6 h-6" style={{ background: accent }} />
        <div className="w-6 h-6 rounded-r-md" style={{ background: textPrimary }} />
      </div>
      <span className="text-[10px] text-slate-500 font-medium">
        {THEME_LABELS[themeId] || themeId}
      </span>
    </button>
  );
}

// ── Archetype Card ──────────────────────────────────────────────

function ArchetypeCard({
  archetype,
  selected,
  onClick,
}: {
  archetype: Archetype;
  selected: boolean;
  onClick: () => void;
}) {
  // Use the "dark" theme colors for the preview card
  const theme = archetype.themes.dark || Object.values(archetype.themes)[0] || {};
  const bgPrimary = theme["--bg-primary"] || theme["--grad-start"] || "#1a1a1a";
  const accent = theme["--accent"] || "#ff6b35";
  const textPrimary = theme["--text-primary"] || "#ffffff";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`group text-left rounded-xl border-2 overflow-hidden transition-all ${
        selected
          ? "border-blue-500 ring-2 ring-blue-200 scale-[1.02]"
          : "border-slate-200 hover:border-slate-300 hover:shadow-md"
      }`}
    >
      {/* Mini cover preview */}
      <div
        className="aspect-[2/3] flex flex-col items-center justify-center p-4 relative"
        style={{ background: bgPrimary }}
      >
        <div
          className="text-center font-bold text-sm leading-tight mb-1"
          style={{ color: textPrimary }}
        >
          WORD
        </div>
        <div
          className="text-center font-bold text-sm leading-tight mb-2"
          style={{ color: accent }}
        >
          SEARCH
        </div>
        <div
          className="w-8 h-[2px] mb-2"
          style={{ background: accent, opacity: 0.5 }}
        />
        <div
          className="text-[8px] opacity-60"
          style={{ color: textPrimary }}
        >
          55 Puzzles
        </div>
        {selected && (
          <div className="absolute top-2 right-2 h-5 w-5 rounded-full bg-blue-500 flex items-center justify-center">
            <IconCheck className="w-3 h-3 text-white" />
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-3 bg-white">
        <p className="text-xs font-semibold text-slate-800">{archetype.name}</p>
        <p className="text-[10px] text-slate-500 mt-0.5 line-clamp-2">{archetype.description}</p>
      </div>
    </button>
  );
}

// ── Main Design Studio Page ─────────────────────────────────────

export default function DesignStudioPage() {
  const params = useParams();
  const router = useRouter();
  const ideaId = params.ideaId as string;
  const idea = getIdeaById(ideaId);
  const { createBook } = useBooks();

  // Design state
  const [stage, setStage] = useState<DesignStage>("loading");
  const [archetypes, setArchetypes] = useState<Archetype[]>([]);
  const [selectedArchetype, setSelectedArchetype] = useState<Archetype | null>(null);
  const [selectedTheme, setSelectedTheme] = useState<string>("dark");
  const [variantId, setVariantId] = useState<string | null>(null);
  const [previewSessionId, setPreviewSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadMode, setUploadMode] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const loadedRef = useRef(false);

  // Load archetypes on mount
  useEffect(() => {
    if (!idea || loadedRef.current) return;
    loadedRef.current = true;

    (async () => {
      try {
        const res = await getArchetypes(idea.book_type);
        if (res.ok && res.data?.archetypes) {
          setArchetypes(res.data.archetypes);
        } else {
          setError(res.error || "Failed to load cover templates");
        }
      } catch (e) {
        setError((e as Error).message);
      }
      setStage("gallery");
    })();
  }, [idea]);

  // Preview when archetype + theme are selected
  const handlePreview = useCallback(async (archetype: Archetype, theme: string) => {
    if (!idea) return;

    const vid = `arch_${archetype.archetype_id}_${theme}`;
    setVariantId(vid);
    setStage("rendering");
    setError(null);

    try {
      const previewResult = await previewCoverDesign({
        title: idea.title,
        subtitle: idea.subtitle,
        author_name: "",
        book_type: idea.book_type,
        trim_size: idea.trim_size,
        paper_type: idea.paper_type,
        page_count: idea.page_count,
        variant_id: vid,
        puzzle_count: (idea.generator_config.num_puzzles as number) || 55,
      });

      if (previewResult.ok && previewResult.data?.success && previewResult.data.session_id) {
        setPreviewSessionId(previewResult.data.session_id);
        setStage("preview");
      } else {
        setError(previewResult.data?.error || previewResult.error || "Cover preview rendering failed");
        setStage("preview");
      }
    } catch (e) {
      setError((e as Error).message);
      setStage("gallery");
    }
  }, [idea]);

  const handleSelectArchetype = useCallback((archetype: Archetype) => {
    setSelectedArchetype(archetype);
    setSelectedTheme("dark");
    setPreviewSessionId(null);
    handlePreview(archetype, "dark");
  }, [handlePreview]);

  const handleSelectTheme = useCallback((theme: string) => {
    if (!selectedArchetype) return;
    setSelectedTheme(theme);
    setPreviewSessionId(null);
    handlePreview(selectedArchetype, theme);
  }, [selectedArchetype, handlePreview]);

  const handleBackToGallery = useCallback(() => {
    setStage("gallery");
    setSelectedArchetype(null);
    setVariantId(null);
    setPreviewSessionId(null);
    setError(null);
    setUploadMode(false);
  }, []);

  // Manual artwork upload
  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !idea || !selectedArchetype) return;

    setUploading(true);
    setError(null);

    try {
      // Read file as base64
      const reader = new FileReader();
      const base64 = await new Promise<string>((resolve, reject) => {
        reader.onload = () => {
          const result = reader.result as string;
          // Strip data URL prefix
          const base64Data = result.split(",")[1];
          resolve(base64Data);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });

      const format = file.type.includes("png") ? "png" : "jpg";

      const uploadResult = await uploadCoverArtwork({
        book_type: idea.book_type,
        archetype_id: selectedArchetype.archetype_id,
        theme: selectedTheme,
        image_data: base64,
        image_format: format,
      });

      if (uploadResult.ok && uploadResult.data?.success) {
        // Preview with the uploaded variant
        const vid = uploadResult.data.upload_variant_id;
        setVariantId(vid);
        setStage("rendering");

        const previewResult = await previewCoverDesign({
          title: idea.title,
          subtitle: idea.subtitle,
          author_name: "",
          book_type: idea.book_type,
          trim_size: idea.trim_size,
          paper_type: idea.paper_type,
          page_count: idea.page_count,
          variant_id: vid,
          puzzle_count: (idea.generator_config.num_puzzles as number) || 55,
        });

        if (previewResult.ok && previewResult.data?.success && previewResult.data.session_id) {
          setPreviewSessionId(previewResult.data.session_id);
          setStage("preview");
        } else {
          setError(previewResult.data?.error || previewResult.error || "Preview rendering failed");
          setStage("preview");
        }
      } else {
        setError(uploadResult.error || "Upload failed");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUploading(false);
      // Reset file input
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [idea, selectedArchetype, selectedTheme]);

  const handleCreateBook = useCallback(async () => {
    if (!idea) return;

    setStage("creating");
    setError(null);

    try {
      const generatorConfig = {
        ...idea.generator_config,
        ...(variantId ? { cover_variant_id: variantId } : {}),
      };

      const newBook = await createBook({
        title: idea.title,
        book_type: idea.book_type,
        subtitle: idea.subtitle,
        trim_size: idea.trim_size,
        paper_type: idea.paper_type,
        page_count: idea.page_count,
        list_price: idea.list_price,
        niche_keyword: idea.niche_keyword,
        generator_config: generatorConfig,
      });

      if (newBook) {
        // Fire-and-forget: trigger interior + cover generation
        generateInterior({
          catalog_number: newBook.catalog_number,
          title: newBook.title,
          book_type: idea.book_type,
          trim_size: idea.trim_size,
          paper_type: idea.paper_type,
          page_count: idea.page_count,
          generator_config: generatorConfig,
        }).catch(() => {});

        generateCover({
          catalog_number: newBook.catalog_number,
          title: newBook.title,
          subtitle: idea.subtitle,
          author_name: "",
          book_type: idea.book_type,
          trim_size: idea.trim_size,
          paper_type: idea.paper_type,
          page_count: idea.page_count,
          generator_config: generatorConfig,
          force_regenerate: true,
        }).catch(() => {});

        router.push(`/catalog/${newBook.id}`);
      } else {
        setError("Failed to create book");
        setStage("preview");
      }
    } catch (e) {
      setError((e as Error).message);
      setStage("preview");
    }
  }, [idea, variantId, createBook, router]);

  // ── Not found ──────────────────────────────────────────────────
  if (!idea) {
    return (
      <div className="p-8">
        <div className="text-center py-20">
          <h2 className="text-sm font-semibold text-slate-700">Book idea not found</h2>
          <p className="text-xs text-slate-400 mt-1">
            The idea &ldquo;{ideaId}&rdquo; doesn&apos;t exist in the curated list.
          </p>
          <Link
            href="/research"
            className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-700"
          >
            <IconArrowLeft className="w-3 h-3" />
            Back to Research
          </Link>
        </div>
      </div>
    );
  }

  // ── Main Render ────────────────────────────────────────────────
  return (
    <div className="p-8 max-w-[1400px]">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-5">
        <Link href="/research" className="hover:text-slate-600 transition-colors">
          Research
        </Link>
        <span className="text-slate-300">/</span>
        <span className="text-slate-600 font-medium">Design Studio</span>
      </div>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Design Studio</h1>
        <p className="text-sm text-slate-500 mt-1">
          Choose a cover design for &ldquo;{idea.title}&rdquo;
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6">
        {/* Left: Idea Details */}
        <div>
          <IdeaDetailPanel idea={idea} />
        </div>

        {/* Right: Cover Design Studio */}
        <div className="space-y-5">
          {/* Loading State */}
          {stage === "loading" && (
            <div className="rounded-xl border border-slate-200 bg-white p-8 flex items-center justify-center">
              <div className="flex items-center gap-3">
                <IconLoader className="w-5 h-5 text-slate-400" />
                <span className="text-sm text-slate-500">Loading cover templates...</span>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-xs text-amber-700">
              {error}
            </div>
          )}

          {/* Archetype Gallery */}
          {stage === "gallery" && (
            <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-4">
              <div>
                <p className="text-sm font-semibold text-slate-900">Choose a Cover Style</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  Select a professional template. Each has 4 color themes.
                </p>
              </div>

              {archetypes.length > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                  {archetypes.map((arch) => (
                    <ArchetypeCard
                      key={arch.archetype_id}
                      archetype={arch}
                      selected={selectedArchetype?.archetype_id === arch.archetype_id}
                      onClick={() => handleSelectArchetype(arch)}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-center py-10">
                  <p className="text-xs text-slate-400">No cover templates available for this book type yet.</p>
                </div>
              )}
            </div>
          )}

          {/* Rendering State */}
          {stage === "rendering" && (
            <div className="rounded-xl border border-violet-200 bg-violet-50 p-6">
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-full bg-violet-100 flex items-center justify-center">
                  <IconLoader className="w-4 h-4 text-violet-600" />
                </div>
                <div>
                  <p className="text-sm font-medium text-violet-800">Rendering Cover Preview...</p>
                  <p className="text-xs text-violet-600 mt-0.5">
                    Generating 300 DPI print-ready cover
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Preview */}
          {(stage === "preview" || stage === "creating") && selectedArchetype && (
            <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
              {/* Header */}
              <div className="p-5 border-b border-slate-100">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="h-6 w-6 rounded-full bg-green-100 flex items-center justify-center">
                      <IconCheck className="w-3.5 h-3.5 text-green-600" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-900">{selectedArchetype.name}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{selectedArchetype.description}</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Theme Selector */}
              <div className="px-5 py-3 border-b border-slate-100 bg-slate-50/50">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-medium text-slate-400 uppercase tracking-wider mr-2">Theme</span>
                  {Object.entries(selectedArchetype.themes).map(([themeId, themeVars]) => (
                    <ThemeSwatch
                      key={themeId}
                      themeId={themeId}
                      themeVars={themeVars}
                      selected={selectedTheme === themeId}
                      onClick={() => handleSelectTheme(themeId)}
                    />
                  ))}
                </div>
              </div>

              {/* Cover Preview Image */}
              {previewSessionId ? (
                <div className="bg-slate-100 flex items-center justify-center min-h-[500px] p-6">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={getCoverPreviewImageUrl(previewSessionId, 1200)}
                    alt="Cover preview"
                    className="max-w-full max-h-[70vh] shadow-xl rounded-sm"
                    style={{ background: "white" }}
                  />
                </div>
              ) : (
                <div className="bg-slate-50 flex flex-col items-center justify-center py-16 gap-3">
                  <p className="text-xs text-slate-400">
                    Preview didn&apos;t load. Try a different theme or retry.
                  </p>
                  <button
                    type="button"
                    onClick={() => selectedArchetype && handlePreview(selectedArchetype, selectedTheme)}
                    disabled={stage === "creating"}
                    className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center gap-2"
                  >
                    <IconRefresh className="w-3.5 h-3.5" />
                    Retry Preview
                  </button>
                </div>
              )}

              {/* Upload Custom Artwork */}
              <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/50">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => setUploadMode(!uploadMode)}
                      className="text-xs text-slate-500 hover:text-blue-600 transition-colors underline underline-offset-2"
                    >
                      {uploadMode ? "Hide upload" : "Upload custom artwork"}
                    </button>
                  </div>
                </div>

                {uploadMode && (
                  <div className="mt-3 p-4 rounded-lg border border-dashed border-slate-300 bg-white">
                    <p className="text-xs text-slate-500 mb-3">
                      Upload a front cover image. The engine will composite it with the correct KDP dimensions
                      (back cover + spine + front cover) based on your book&apos;s page count and trim size.
                    </p>
                    <div className="flex items-center gap-3">
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/png,image/jpeg"
                        onChange={handleFileUpload}
                        disabled={uploading || stage === "creating"}
                        className="text-xs text-slate-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-blue-50 file:text-blue-600 hover:file:bg-blue-100 disabled:opacity-50"
                      />
                      {uploading && (
                        <span className="flex items-center gap-1.5 text-xs text-blue-600">
                          <IconLoader className="w-3.5 h-3.5" />
                          Uploading...
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="p-5 border-t border-slate-100 flex items-center justify-between">
                <button
                  type="button"
                  onClick={handleBackToGallery}
                  disabled={stage === "creating"}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-50 flex items-center gap-2"
                >
                  <IconArrowLeft className="w-3.5 h-3.5" />
                  Change Style
                </button>

                <button
                  type="button"
                  onClick={handleCreateBook}
                  disabled={stage === "creating" || !previewSessionId}
                  className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center gap-2"
                >
                  {stage === "creating" ? (
                    <>
                      <IconLoader className="w-4 h-4" />
                      Creating Book...
                    </>
                  ) : (
                    "Create Book"
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
