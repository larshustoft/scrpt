"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useBooks } from "@/hooks/useBooks";
import { BOOK_TYPE_LABELS, BOOK_TYPE_SHORT } from "@/lib/types";
import type { BookType } from "@/lib/types";

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
      await createBook(form);
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
