"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useBooks } from "@/hooks/useBooks";
import { BOOK_TYPE_LABELS, BOOK_TYPE_SHORT } from "@/lib/types";
import type { BookType } from "@/lib/types";
import {
  searchBestsellerCovers,
  generateDesignFromReference,
} from "@/lib/api";
import type { CoverSearchResult } from "@/lib/api";

const TRIM_SIZES = [
  { value: "5x8", label: "5\" x 8\"" },
  { value: "5.5x8.5", label: "5.5\" x 8.5\"" },
  { value: "6x9", label: "6\" x 9\"" },
  { value: "7x10", label: "7\" x 10\"" },
  { value: "8x10", label: "8\" x 10\"" },
  { value: "8.5x8.5", label: "8.5\" x 8.5\" (Square)" },
  { value: "8.5x11", label: "8.5\" x 11\" (US Letter)" },
];

const PAPER_TYPES = [
  { value: "white_bw", label: "White (B&W)" },
  { value: "cream_bw", label: "Cream (B&W)" },
  { value: "standard_color", label: "Standard Color" },
  { value: "premium_color", label: "Premium Color" },
];

const BOOK_TYPE_DEFAULTS: Record<string, { trim: string; pages: number; price: number; paper: string }> = {
  word_search: { trim: "8.5x11", pages: 120, price: 12.97, paper: "white_bw" },
  coloring_book: { trim: "8.5x8.5", pages: 50, price: 9.99, paper: "white_bw" },
  cryptogram: { trim: "8.5x11", pages: 120, price: 11.97, paper: "white_bw" },
  kids_activity: { trim: "8.5x11", pages: 100, price: 9.99, paper: "white_bw" },
  password_log: { trim: "6x9", pages: 120, price: 7.99, paper: "white_bw" },
  color_by_number: { trim: "8.5x11", pages: 80, price: 11.97, paper: "white_bw" },
  sudoku: { trim: "8.5x11", pages: 120, price: 9.97, paper: "white_bw" },
  maze: { trim: "8.5x11", pages: 100, price: 9.97, paper: "white_bw" },
  math_workbook: { trim: "8.5x11", pages: 100, price: 12.97, paper: "white_bw" },
  journal: { trim: "6x9", pages: 200, price: 9.99, paper: "cream_bw" },
};

export default function CreateBookPage() {
  const router = useRouter();
  const { createBook } = useBooks();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    title: "",
    book_type: "word_search",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    author_name: "",
    list_price: 12.97,
  });

  // Cover design picker state
  type DesignStep = "idle" | "searching" | "results" | "generating" | "done";
  const [designStep, setDesignStep] = useState<DesignStep>("idle");
  const [searchKeyword, setSearchKeyword] = useState("Word Search puzzle books");
  const [searchResults, setSearchResults] = useState<CoverSearchResult[]>([]);
  const [selectedCover, setSelectedCover] = useState<CoverSearchResult | null>(null);
  const [generatedVariant, setGeneratedVariant] = useState<string | null>(null);
  const [designNotes, setDesignNotes] = useState<string | null>(null);
  const [designError, setDesignError] = useState<string | null>(null);

  const handleTypeChange = (bookType: string) => {
    const defaults = BOOK_TYPE_DEFAULTS[bookType] || BOOK_TYPE_DEFAULTS.word_search;
    setForm({
      ...form,
      book_type: bookType,
      trim_size: defaults.trim,
      page_count: defaults.pages,
      list_price: defaults.price,
      paper_type: defaults.paper,
    });
    // Reset design state when book type changes
    setDesignStep("idle");
    setSearchResults([]);
    setSelectedCover(null);
    setGeneratedVariant(null);
    setDesignNotes(null);
    setDesignError(null);
    // Pre-fill search keyword from the book type label
    const label = BOOK_TYPE_LABELS[bookType as BookType] || bookType;
    setSearchKeyword(`${label} puzzle books`);
  };

  const handleSearchCovers = async () => {
    if (!searchKeyword.trim()) return;
    setDesignStep("searching");
    setDesignError(null);
    setSelectedCover(null);
    setGeneratedVariant(null);
    setDesignNotes(null);
    try {
      const response = await searchBestsellerCovers(searchKeyword.trim(), 6);
      setSearchResults(response.results);
      setDesignStep("results");
      if (response.results.length === 0) {
        setDesignError("No results found. Try a different keyword.");
      }
    } catch (e) {
      setDesignError((e as Error).message);
      setDesignStep("idle");
    }
  };

  const handleGenerateDesign = async () => {
    if (!selectedCover) return;
    setDesignStep("generating");
    setDesignError(null);
    try {
      const response = await generateDesignFromReference({
        reference_image_url: selectedCover.cover_image_url,
        reference_asin: selectedCover.asin,
        book_type: form.book_type,
        niche_keyword: searchKeyword.trim() || undefined,
      });
      if (response.success && response.variant_id) {
        setGeneratedVariant(response.variant_id);
        setDesignNotes(response.design_notes || null);
        setDesignStep("done");
      } else {
        setDesignError(response.error || "Design generation failed");
        setDesignStep("results");
      }
    } catch (e) {
      setDesignError((e as Error).message);
      setDesignStep("results");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) {
      setError("Title is required");
      return;
    }
    if (form.page_count < 24 || form.page_count > 828) {
      setError("Page count must be between 24 and 828");
      return;
    }
    if (form.page_count % 2 !== 0) {
      setError("Page count must be even");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const bookInput: Parameters<typeof createBook>[0] = {
        ...form,
        ...(generatedVariant
          ? { generator_config: { cover_variant_id: generatedVariant } }
          : {}),
      };
      await createBook(bookInput);
      router.push("/catalog");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-8 max-w-3xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900">Create Book</h1>
        <p className="text-sm text-slate-500 mt-1">
          Set up a new book project for Amazon KDP
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Book Type Selector */}
        <div>
          <label className="block text-sm font-semibold text-slate-900 mb-3">Book Type</label>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {Object.entries(BOOK_TYPE_LABELS).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => handleTypeChange(value)}
                className={`flex flex-col items-center gap-1.5 rounded-lg border p-3 text-center transition-colors ${
                  form.book_type === value
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                }`}
              >
                <span
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-[11px] font-mono font-semibold ${
                    form.book_type === value
                      ? "bg-white/20 text-white"
                      : "bg-slate-100 text-slate-500"
                  }`}
                >
                  {BOOK_TYPE_SHORT[value as BookType]}
                </span>
                <span className="text-xs font-medium">{label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Title */}
        <div>
          <label className="block text-sm font-semibold text-slate-900 mb-1.5">Title</label>
          <input
            type="text"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="e.g., Ultimate Word Search for Seniors"
            className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* Author Name */}
        <div>
          <label className="block text-sm font-semibold text-slate-900 mb-1.5">
            Author / Publisher Name
          </label>
          <input
            type="text"
            value={form.author_name}
            onChange={(e) => setForm({ ...form, author_name: e.target.value })}
            placeholder="e.g., Creative Puzzles Press"
            className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* Specifications Grid */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-semibold text-slate-900 mb-1.5">
              Trim Size
            </label>
            <select
              value={form.trim_size}
              onChange={(e) => setForm({ ...form, trim_size: e.target.value })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm bg-white focus:border-blue-500 focus:outline-none"
            >
              {TRIM_SIZES.map((ts) => (
                <option key={ts.value} value={ts.value}>
                  {ts.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-900 mb-1.5">
              Paper Type
            </label>
            <select
              value={form.paper_type}
              onChange={(e) => setForm({ ...form, paper_type: e.target.value })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm bg-white focus:border-blue-500 focus:outline-none"
            >
              {PAPER_TYPES.map((pt) => (
                <option key={pt.value} value={pt.value}>
                  {pt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-900 mb-1.5">
              Page Count
            </label>
            <input
              type="number"
              value={form.page_count}
              onChange={(e) =>
                setForm({ ...form, page_count: parseInt(e.target.value) || 24 })
              }
              min={24}
              max={828}
              step={2}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none"
            />
            <p className="text-xs text-slate-400 mt-1">Must be even, 24-828</p>
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-900 mb-1.5">
              List Price ($)
            </label>
            <input
              type="number"
              value={form.list_price}
              onChange={(e) =>
                setForm({
                  ...form,
                  list_price: parseFloat(e.target.value) || 9.99,
                })
              }
              min={0.99}
              max={250}
              step={0.01}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none"
            />
            <p className="text-xs text-slate-400 mt-1">
              {form.list_price >= 9.98 ? "60% royalty" : "50% royalty"} — above
              $9.98 recommended
            </p>
          </div>
        </div>

        {/* ── Cover Design Picker ────────────────────────────── */}
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-slate-900 mb-1">
              Cover Design
            </label>
            <p className="text-xs text-slate-500 mb-3">
              Search Amazon for bestselling covers, pick a reference, and generate an AI-powered design.
            </p>
          </div>

          {/* Search bar */}
          <div className="flex gap-2">
            <input
              type="text"
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleSearchCovers();
                }
              }}
              placeholder="e.g., large print word search puzzle books"
              className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <button
              type="button"
              onClick={handleSearchCovers}
              disabled={designStep === "searching" || !searchKeyword.trim()}
              className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 transition-colors whitespace-nowrap"
            >
              {designStep === "searching" ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Searching...
                </span>
              ) : (
                "Search Bestsellers"
              )}
            </button>
          </div>

          {/* Design error */}
          {designError && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">
              {designError}
            </div>
          )}

          {/* Search results */}
          {searchResults.length > 0 && designStep !== "idle" && (
            <div className="space-y-3">
              <p className="text-xs font-medium text-slate-600">
                {searchResults.length} bestseller{searchResults.length !== 1 ? "s" : ""} found — click to select a reference:
              </p>
              <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-3">
                {searchResults.map((cover) => (
                  <button
                    key={cover.asin}
                    type="button"
                    onClick={() => {
                      setSelectedCover(
                        selectedCover?.asin === cover.asin ? null : cover
                      );
                      // Reset generated state when picking a different cover
                      if (selectedCover?.asin !== cover.asin) {
                        setGeneratedVariant(null);
                        setDesignNotes(null);
                        setDesignStep("results");
                      }
                    }}
                    disabled={designStep === "generating"}
                    className={`relative group rounded-lg overflow-hidden border-2 transition-all ${
                      selectedCover?.asin === cover.asin
                        ? "border-blue-500 ring-2 ring-blue-200 scale-[1.02]"
                        : "border-slate-200 hover:border-slate-300"
                    } ${designStep === "generating" ? "opacity-60 cursor-not-allowed" : ""}`}
                  >
                    {/* Cover image */}
                    <div className="aspect-[2/3] bg-slate-100 relative">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={cover.cover_image_url}
                        alt={cover.title}
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                      {/* Selection checkmark */}
                      {selectedCover?.asin === cover.asin && (
                        <div className="absolute top-1.5 right-1.5 h-5 w-5 rounded-full bg-blue-500 flex items-center justify-center">
                          <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        </div>
                      )}
                    </div>
                    {/* Info bar */}
                    <div className="p-1.5 bg-white">
                      <p className="text-[10px] text-slate-600 truncate leading-tight" title={cover.title}>
                        {cover.title}
                      </p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {cover.price != null && (
                          <span className="text-[10px] font-semibold text-slate-800">
                            ${cover.price.toFixed(2)}
                          </span>
                        )}
                        {cover.rating != null && (
                          <span className="text-[10px] text-amber-600">
                            {"★".repeat(Math.round(cover.rating))}
                          </span>
                        )}
                        {cover.reviews != null && (
                          <span className="text-[10px] text-slate-400">
                            ({cover.reviews.toLocaleString()})
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                ))}
              </div>

              {/* Generate button */}
              {selectedCover && designStep !== "done" && (
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={handleGenerateDesign}
                    disabled={designStep === "generating"}
                    className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                  >
                    {designStep === "generating" ? (
                      <span className="flex items-center gap-2">
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Generating Design...
                      </span>
                    ) : (
                      "Generate AI Design"
                    )}
                  </button>
                  {designStep === "generating" && (
                    <p className="text-xs text-slate-500">
                      Analyzing reference and generating CSS/HTML... (~15s)
                    </p>
                  )}
                </div>
              )}

              {/* Design success */}
              {designStep === "done" && generatedVariant && (
                <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3">
                  <div className="flex items-start gap-2">
                    <svg className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div>
                      <p className="text-sm font-medium text-green-800">
                        Cover design generated!
                      </p>
                      {designNotes && (
                        <p className="text-xs text-green-700 mt-1">{designNotes}</p>
                      )}
                      <p className="text-xs text-green-600 mt-1">
                        Variant: <code className="bg-green-100 px-1 rounded">{generatedVariant}</code>
                        {" · "}Based on: {selectedCover?.title ? `"${selectedCover.title.slice(0, 50)}${selectedCover.title.length > 50 ? "..." : ""}"` : "selected reference"}
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          setDesignStep("results");
                          setGeneratedVariant(null);
                          setDesignNotes(null);
                        }}
                        className="text-xs text-green-600 underline mt-2 hover:text-green-800"
                      >
                        Pick a different reference
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Skip link */}
          {designStep === "idle" && (
            <p className="text-xs text-slate-400">
              Optional — if you skip this, the default template will be used when generating the cover.
            </p>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Submit */}
        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {saving ? "Creating..." : "Create Book"}
          </button>
          <button
            type="button"
            onClick={() => router.push("/catalog")}
            className="rounded-lg border border-slate-200 px-6 py-2.5 text-sm font-medium hover:bg-slate-50 transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
