"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import type { Book } from "@/lib/types";
import {
  BOOK_TYPE_LABELS,
  BOOK_TYPE_SHORT,
  STATUS_COLORS,
  STATUS_LABELS,
} from "@/lib/types";
import type { BookType, BookStatus } from "@/lib/types";
import {
  getBook,
  getBookFiles,
  generateInterior,
  generateCover,
  getInteriorPageUrl,
  getCoverPreviewUrl,
  getCoverFullUrl,
  getFileUrl,
  type BookFiles,
} from "@/lib/api";
import {
  IconFileText,
  IconImage,
  IconPalette,
  IconFile,
  IconCode,
  IconCheck,
  IconLoader,
  IconRefresh,
  IconExternalLink,
  IconChevronLeft,
  IconChevronRight,
  IconAlertTriangle,
  IconArrowLeft,
} from "@/components/icons";

// ── Interior Preview ────────────────────────────────────────────

function InteriorPreview({
  bookId,
  files,
  onRefresh,
}: {
  bookId: string;
  files: BookFiles | null;
  onRefresh: () => void;
}) {
  const [currentPage, setCurrentPage] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imgKey, setImgKey] = useState(0);

  const totalPages = files?.interior_pages || 0;
  const hasInterior = files?.has_interior || false;

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const result = await generateInterior(bookId);
      if (!result.success) {
        setError(result.message);
      } else {
        setImgKey((k) => k + 1);
        onRefresh();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGenerating(false);
    }
  };

  if (!hasInterior) {
    return (
      <div className="flex flex-col items-center justify-center py-20 bg-slate-50 rounded-lg border border-dashed border-slate-200">
        <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mb-4">
          <IconFileText className="w-5 h-5 text-slate-400" />
        </div>
        <h3 className="text-sm font-semibold text-slate-700 mb-1">
          No Interior Generated
        </h3>
        <p className="text-xs text-slate-400 mb-5">
          Generate the interior PDF to preview pages
        </p>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="rounded-md bg-slate-900 px-5 py-2 text-xs font-medium text-white hover:bg-slate-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {generating ? (
            <span className="flex items-center gap-2">
              <IconLoader className="w-3.5 h-3.5" />
              Generating...
            </span>
          ) : (
            "Generate Interior"
          )}
        </button>
        {error && (
          <p className="text-xs text-red-500 mt-3 max-w-sm text-center">{error}</p>
        )}
      </div>
    );
  }

  return (
    <div>
      {/* Navigation Bar */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setCurrentPage(0)}
            disabled={currentPage === 0}
            className="rounded border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            First
          </button>
          <button
            onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
            disabled={currentPage === 0}
            className="rounded border border-slate-200 p-1 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <IconChevronLeft className="w-4 h-4 text-slate-500" />
          </button>
          <span className="text-xs text-slate-500 px-1.5">
            <input
              type="number"
              min={1}
              max={totalPages}
              value={currentPage + 1}
              onChange={(e) => {
                const val = parseInt(e.target.value);
                if (val >= 1 && val <= totalPages) {
                  setCurrentPage(val - 1);
                }
              }}
              className="w-14 rounded border border-slate-200 px-2 py-0.5 text-center text-xs tabular-nums"
            />
            <span className="ml-1 text-slate-400">of {totalPages}</span>
          </span>
          <button
            onClick={() =>
              setCurrentPage(Math.min(totalPages - 1, currentPage + 1))
            }
            disabled={currentPage >= totalPages - 1}
            className="rounded border border-slate-200 p-1 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <IconChevronRight className="w-4 h-4 text-slate-500" />
          </button>
          <button
            onClick={() => setCurrentPage(totalPages - 1)}
            disabled={currentPage >= totalPages - 1}
            className="rounded border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Last
          </button>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="rounded border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-500 hover:bg-slate-50 transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            <IconRefresh className="w-3 h-3" />
            {generating ? "Regenerating..." : "Regenerate"}
          </button>
          <a
            href={getFileUrl(bookId, "interior.pdf")}
            target="_blank"
            rel="noopener"
            className="rounded border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-blue-600 hover:bg-blue-50 transition-colors flex items-center gap-1.5"
          >
            Open PDF
            <IconExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>

      {/* Page Render */}
      <div className="relative bg-slate-100 rounded-lg overflow-hidden flex items-center justify-center min-h-[600px]">
        <img
          key={`${imgKey}-${currentPage}`}
          src={getInteriorPageUrl(bookId, currentPage, 1200)}
          alt={`Page ${currentPage + 1}`}
          className="max-w-full max-h-[80vh] shadow-xl"
          style={{ background: "white" }}
        />
      </div>

      {/* Scrubber */}
      <div className="mt-3">
        <input
          type="range"
          min={0}
          max={totalPages - 1}
          value={currentPage}
          onChange={(e) => setCurrentPage(parseInt(e.target.value))}
          className="w-full accent-slate-900 h-1"
        />
        <div className="flex justify-between text-[10px] text-slate-400 mt-1">
          <span>Page 1</span>
          <span>Page {totalPages}</span>
        </div>
      </div>

      {error && (
        <p className="text-xs text-red-500 mt-3">{error}</p>
      )}
    </div>
  );
}

// ── Cover Preview ───────────────────────────────────────────────

function CoverPreview({
  bookId,
  files,
  onRefresh,
}: {
  bookId: string;
  files: BookFiles | null;
  onRefresh: () => void;
}) {
  const [showFull, setShowFull] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imgKey, setImgKey] = useState(0);

  const hasCover = files?.has_cover || false;
  const hasCoverFront = files?.has_cover_front || false;

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const result = await generateCover(bookId);
      if (!result.success) {
        setError(result.message || "Cover generation failed");
        if (result.note) {
          setError(`${result.message || ""} ${result.note}`);
        }
      } else {
        setImgKey((k) => k + 1);
        onRefresh();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGenerating(false);
    }
  };

  if (!hasCover && !hasCoverFront) {
    return (
      <div className="flex flex-col items-center justify-center py-20 bg-slate-50 rounded-lg border border-dashed border-slate-200">
        <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mb-4">
          <IconPalette className="w-5 h-5 text-slate-400" />
        </div>
        <h3 className="text-sm font-semibold text-slate-700 mb-1">
          No Cover Generated
        </h3>
        <p className="text-xs text-slate-400 mb-5">
          Generate the cover to preview artwork
        </p>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="rounded-md bg-slate-900 px-5 py-2 text-xs font-medium text-white hover:bg-slate-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {generating ? (
            <span className="flex items-center gap-2">
              <IconLoader className="w-3.5 h-3.5" />
              Generating...
            </span>
          ) : (
            "Generate Cover"
          )}
        </button>
        {error && (
          <p className="text-xs text-red-500 mt-3 max-w-sm text-center">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <div>
      {/* View Toggle */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowFull(false)}
            className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
              !showFull
                ? "bg-slate-900 text-white"
                : "border border-slate-200 text-slate-500 hover:bg-slate-50"
            }`}
          >
            Front Cover
          </button>
          {hasCover && (
            <button
              onClick={() => setShowFull(true)}
              className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                showFull
                  ? "bg-slate-900 text-white"
                  : "border border-slate-200 text-slate-500 hover:bg-slate-50"
              }`}
            >
              Full Spread
            </button>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="rounded border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-500 hover:bg-slate-50 transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            <IconRefresh className="w-3 h-3" />
            {generating ? "Regenerating..." : "Regenerate"}
          </button>
          {hasCover && (
            <a
              href={getFileUrl(bookId, "cover.pdf")}
              target="_blank"
              rel="noopener"
              className="rounded border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-blue-600 hover:bg-blue-50 transition-colors flex items-center gap-1.5"
            >
              Open PDF
              <IconExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
      </div>

      {/* Cover Image */}
      <div className="relative bg-slate-100 rounded-lg overflow-hidden flex items-center justify-center min-h-[600px]">
        {showFull ? (
          <img
            key={`full-${imgKey}`}
            src={getCoverFullUrl(bookId, 2400)}
            alt="Full cover spread"
            className="max-w-full max-h-[80vh] shadow-xl"
          />
        ) : (
          <img
            key={`front-${imgKey}`}
            src={getCoverPreviewUrl(bookId, 1200)}
            alt="Front cover"
            className="max-w-full max-h-[80vh] shadow-xl"
          />
        )}
      </div>

      {error && (
        <p className="text-xs text-red-500 mt-3">{error}</p>
      )}
    </div>
  );
}

// ── Side Panel ──────────────────────────────────────────────────

function BookInfoPanel({
  book,
  files,
}: {
  book: Book;
  files: BookFiles | null;
}) {
  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const fileIcon = (name: string) => {
    if (name.endsWith(".pdf")) return <IconFileText className="w-3.5 h-3.5 text-slate-400" />;
    if (name.endsWith(".png") || name.endsWith(".jpg")) return <IconImage className="w-3.5 h-3.5 text-slate-400" />;
    if (name.endsWith(".html")) return <IconCode className="w-3.5 h-3.5 text-slate-400" />;
    return <IconFile className="w-3.5 h-3.5 text-slate-400" />;
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="p-5 border-b border-slate-100">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-[11px] font-mono text-slate-400">
            {book.catalog_number}
          </span>
          <span
            className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ${STATUS_COLORS[book.status as BookStatus] || "bg-slate-100 text-slate-600"}`}
          >
            {STATUS_LABELS[book.status as BookStatus] || book.status}
          </span>
        </div>
        <h2 className="text-base font-semibold text-slate-900 leading-tight">
          {book.title}
        </h2>
        {book.data.subtitle && (
          <p className="text-xs text-slate-400 mt-0.5">
            {book.data.subtitle}
          </p>
        )}
      </div>

      {/* Details Grid */}
      <div className="p-5">
        <div className="grid grid-cols-2 gap-x-4 gap-y-3">
          <DetailItem label="Type" value={BOOK_TYPE_LABELS[book.data.book_type as BookType] || book.data.book_type} />
          <DetailItem label="Pages" value={String(book.data.page_count)} />
          <DetailItem label="Trim Size" value={`${book.data.trim_size}"`} />
          <DetailItem label="Price" value={`$${book.data.list_price.toFixed(2)}`} />
          <DetailItem label="Author" value={book.data.author_name} />
          <DetailItem label="Paper" value={book.data.paper_type.replace(/_/g, " ")} />
        </div>
      </div>

      {/* Files */}
      {files && Object.keys(files.files).length > 0 && (
        <div className="px-5 pb-5 pt-0">
          <div className="border-t border-slate-100 pt-4">
            <p className="text-[10px] font-medium text-slate-400 uppercase tracking-wider mb-2.5">
              Generated Files
            </p>
            <div className="space-y-1.5">
              {Object.values(files.files).map((file) => (
                <div
                  key={file.name}
                  className="flex items-center justify-between"
                >
                  <div className="flex items-center gap-2">
                    {fileIcon(file.name)}
                    <span className="font-mono text-[11px] text-slate-600">{file.name}</span>
                  </div>
                  <span className="text-[11px] text-slate-400 tabular-nums">
                    {formatBytes(file.size)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Timestamps */}
      <div className="px-5 py-3 border-t border-slate-100 text-[10px] text-slate-400">
        <p>Created {new Date(book.created_at).toLocaleString()}</p>
        <p>Updated {new Date(book.updated_at).toLocaleString()}</p>
      </div>
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] text-slate-400 uppercase tracking-wider">{label}</p>
      <p className="text-[13px] font-medium text-slate-700 mt-0.5">{value}</p>
    </div>
  );
}

// ── Pipeline ────────────────────────────────────────────────────

function PipelineStep({
  step,
  label,
  done,
  active,
}: {
  step: number;
  label: string;
  done: boolean;
  active: boolean;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <div
        className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-semibold ${
          done
            ? "bg-emerald-500 text-white"
            : active
              ? "bg-blue-500 text-white animate-pulse"
              : "bg-slate-100 text-slate-400"
        }`}
      >
        {done ? <IconCheck className="w-3 h-3" /> : step}
      </div>
      <span
        className={`text-xs ${
          done
            ? "text-emerald-700 font-medium"
            : active
              ? "text-blue-600 font-medium"
              : "text-slate-400"
        }`}
      >
        {label}
      </span>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────

export default function BookDetailPage() {
  const params = useParams();
  const bookId = params.id as string;

  const [book, setBook] = useState<Book | null>(null);
  const [files, setFiles] = useState<BookFiles | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"interior" | "cover">(
    "interior"
  );

  const fetchData = useCallback(async () => {
    try {
      const [bookData, filesData] = await Promise.all([
        getBook(bookId),
        getBookFiles(bookId),
      ]);
      setBook(bookData);
      setFiles(filesData);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [bookId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
      </div>
    );
  }

  if (error || !book) {
    return (
      <div className="p-8">
        <div className="text-center py-20">
          <div className="mx-auto w-10 h-10 rounded-full bg-red-50 flex items-center justify-center mb-4">
            <IconAlertTriangle className="w-5 h-5 text-red-400" />
          </div>
          <h2 className="text-sm font-semibold text-slate-700">
            {error || "Book not found"}
          </h2>
          <Link
            href="/catalog"
            className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-700"
          >
            <IconArrowLeft className="w-3 h-3" />
            Back to Catalog
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-[1400px]">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-5">
        <Link href="/catalog" className="hover:text-slate-600 transition-colors">
          Catalog
        </Link>
        <span className="text-slate-300">/</span>
        <span className="text-slate-600 font-medium">
          {book.catalog_number}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-6">
        {/* Preview Area */}
        <div>
          {/* Tabs */}
          <div className="flex items-center gap-1 mb-5 border-b border-slate-200 pb-px">
            <button
              onClick={() => setActiveTab("interior")}
              className={`rounded-t px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
                activeTab === "interior"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
            >
              <span className="flex items-center gap-2">
                Interior
                {files?.has_interior && (
                  <span className="text-[10px] tabular-nums text-slate-400 font-normal">
                    {files.interior_pages} pages
                  </span>
                )}
              </span>
            </button>
            <button
              onClick={() => setActiveTab("cover")}
              className={`rounded-t px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
                activeTab === "cover"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
            >
              <span className="flex items-center gap-2">
                Cover
                {(files?.has_cover || files?.has_cover_front) && (
                  <IconCheck className="w-3 h-3 text-emerald-500" />
                )}
              </span>
            </button>
          </div>

          {/* Content */}
          {activeTab === "interior" ? (
            <InteriorPreview
              bookId={bookId}
              files={files}
              onRefresh={fetchData}
            />
          ) : (
            <CoverPreview
              bookId={bookId}
              files={files}
              onRefresh={fetchData}
            />
          )}
        </div>

        {/* Side Panel */}
        <div className="space-y-4">
          <BookInfoPanel book={book} files={files} />

          {/* Pipeline */}
          <div className="rounded-lg border border-slate-200 bg-white p-5">
            <p className="text-[10px] font-medium text-slate-400 uppercase tracking-wider mb-3">
              Pipeline
            </p>
            <div className="space-y-2">
              <PipelineStep
                step={1}
                label="Interior"
                done={!!files?.has_interior}
                active={book.status === "generating"}
              />
              <PipelineStep
                step={2}
                label="Cover"
                done={!!files?.has_cover || !!files?.has_cover_front}
                active={false}
              />
              <PipelineStep
                step={3}
                label="Quality Check"
                done={book.status === "ready" || book.status === "live"}
                active={book.status === "quality_check"}
              />
              <PipelineStep
                step={4}
                label="Upload to KDP"
                done={book.status === "live"}
                active={
                  book.status === "uploading" ||
                  book.status === "in_review"
                }
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
