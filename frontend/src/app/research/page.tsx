"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useBooks } from "@/hooks/useBooks";
import { BOOK_TYPE_LABELS, BOOK_TYPE_SHORT } from "@/lib/types";
import type { BookType } from "@/lib/types";
import { IconTarget, IconCheck, IconLoader } from "@/components/icons";
import {
  BOOK_IDEAS,
  CATEGORY_META,
  ALL_CATEGORIES,
  formatTrim,
} from "@/lib/book-ideas";
import type { IdeaCategory, BookIdea } from "@/lib/book-ideas";

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
  very_strong: {
    label: "Very Strong",
    color: "text-emerald-700",
    dotColor: "bg-emerald-500",
  },
  strong: {
    label: "Strong",
    color: "text-blue-700",
    dotColor: "bg-blue-500",
  },
  moderate: {
    label: "Moderate",
    color: "text-amber-700",
    dotColor: "bg-amber-500",
  },
  weak: {
    label: "Weak",
    color: "text-red-600",
    dotColor: "bg-red-400",
  },
};

// ── Page Component ──────────────────────────────────────────────

export default function ResearchPage() {
  const router = useRouter();
  const { books, createBook } = useBooks();

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [createProgress, setCreateProgress] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<
    "all" | IdeaCategory
  >("all");
  const [typeFilter, setTypeFilter] = useState<"all" | BookType>("all");

  const filteredIdeas = BOOK_IDEAS.filter((idea) => {
    if (activeCategory !== "all" && idea.category !== activeCategory)
      return false;
    if (typeFilter !== "all" && idea.book_type !== typeFilter) return false;
    return true;
  });

  const selectedCount = selectedIds.size;

  const toggleSelect = (id: string) => {
    if (creating) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllVisible = () => {
    if (creating) return;
    const visibleIds = new Set(filteredIdeas.map((i) => i.id));
    const allSelected = filteredIdeas.every((i) => selectedIds.has(i.id));
    if (allSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        visibleIds.forEach((id) => next.delete(id));
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        visibleIds.forEach((id) => next.add(id));
        return next;
      });
    }
  };

  const isInCatalog = (idea: BookIdea) =>
    books.some((b) => b.title === idea.title);

  const handleCreate = async () => {
    setCreating(true);
    setError(null);

    const ideas = BOOK_IDEAS.filter((idea) => selectedIds.has(idea.id));

    try {
      for (let i = 0; i < ideas.length; i++) {
        const idea = ideas[i];
        setCreateProgress(`Creating ${i + 1} of ${ideas.length}...`);
        await createBook({
          title: idea.title,
          book_type: idea.book_type,
          subtitle: idea.subtitle,
          trim_size: idea.trim_size,
          paper_type: idea.paper_type,
          page_count: idea.page_count,
          list_price: idea.list_price,
          niche_keyword: idea.niche_keyword,
          generator_config: idea.generator_config,
        });
      }
      router.push("/catalog");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create books");
    } finally {
      setCreating(false);
      setCreateProgress("");
    }
  };

  // Count per category for badges
  const categoryCounts = ALL_CATEGORIES.reduce(
    (acc, cat) => {
      acc[cat] = BOOK_IDEAS.filter((i) => i.category === cat).length;
      return acc;
    },
    {} as Record<IdeaCategory, number>
  );

  // Unique book types present in ideas
  const availableTypes = Array.from(
    new Set(BOOK_IDEAS.map((i) => i.book_type))
  ).sort();

  return (
    <div className="p-8 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Book Ideas</h1>
          <p className="text-sm text-slate-500 mt-1">
            {BOOK_IDEAS.length} curated concepts ready for one-click creation
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={selectAllVisible}
            disabled={creating}
            className="text-sm text-slate-500 hover:text-slate-900 transition-colors disabled:opacity-50"
          >
            {filteredIdeas.every((i) => selectedIds.has(i.id)) &&
            filteredIdeas.length > 0
              ? "Deselect all"
              : "Select all"}
          </button>
          <button
            onClick={handleCreate}
            disabled={selectedCount === 0 || creating}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {creating ? (
              <>
                <IconLoader className="w-4 h-4" />
                {createProgress}
              </>
            ) : selectedCount > 0 ? (
              `Create ${selectedCount} ${selectedCount === 1 ? "Book" : "Books"}`
            ) : (
              "Select ideas to create"
            )}
          </button>
        </div>
      </div>

      {/* Info Banner */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 mb-6">
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100">
            <IconTarget className="w-4 h-4 text-blue-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-blue-800">
              One-Click Book Creation
            </h3>
            <p className="text-xs text-blue-600 mt-1">
              Each idea is pre-configured with optimal format, pricing, and
              generator settings. Ideas with a demand signal are backed by real
              Amazon BSR data. Select one or more and create production-ready
              book projects instantly.
            </p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        {/* Category pills */}
        <button
          onClick={() => setActiveCategory("all")}
          className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
            activeCategory === "all"
              ? "bg-slate-900 text-white border-slate-900"
              : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
          }`}
        >
          All ({BOOK_IDEAS.length})
        </button>
        {ALL_CATEGORIES.map((cat) => {
          const meta = CATEGORY_META[cat];
          const isActive = activeCategory === cat;
          return (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                isActive ? meta.activeColor : `${meta.color} hover:opacity-80`
              }`}
            >
              {meta.label} ({categoryCounts[cat]})
            </button>
          );
        })}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Book type filter */}
        <select
          value={typeFilter}
          onChange={(e) =>
            setTypeFilter(e.target.value as "all" | BookType)
          }
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="all">All types</option>
          {availableTypes.map((bt) => (
            <option key={bt} value={bt}>
              {BOOK_TYPE_LABELS[bt]}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 mb-6">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Empty state */}
      {filteredIdeas.length === 0 && (
        <div className="text-center py-16">
          <p className="text-sm text-slate-500">
            No ideas match the current filters.
          </p>
          <button
            onClick={() => {
              setActiveCategory("all");
              setTypeFilter("all");
            }}
            className="mt-2 text-sm text-blue-600 hover:text-blue-500"
          >
            Clear filters
          </button>
        </div>
      )}

      {/* Card Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredIdeas.map((idea) => {
          const selected = selectedIds.has(idea.id);
          const inCatalog = isInCatalog(idea);
          const typeColor =
            BOOK_TYPE_COLORS[idea.book_type] || "bg-gray-100 text-gray-700";
          const catMeta = CATEGORY_META[idea.category];

          return (
            <div
              key={idea.id}
              onClick={() => toggleSelect(idea.id)}
              className={`rounded-xl border p-5 cursor-pointer transition-all duration-150 ${
                selected
                  ? "border-blue-500 bg-blue-50/40 ring-1 ring-blue-500/20"
                  : "border-slate-200 bg-white hover:border-slate-300"
              } ${creating ? "opacity-60 cursor-not-allowed" : ""}`}
            >
              {/* Top Row: Checkbox + Badges + Title */}
              <div className="flex items-start gap-3">
                {/* Checkbox */}
                <div
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition-colors ${
                    selected
                      ? "border-blue-600 bg-blue-600"
                      : "border-slate-300 bg-white"
                  }`}
                >
                  {selected && <IconCheck className="w-3 h-3 text-white" />}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${typeColor}`}
                    >
                      {BOOK_TYPE_SHORT[idea.book_type]}
                    </span>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${catMeta.color}`}
                    >
                      {catMeta.label}
                    </span>
                    {inCatalog && (
                      <span className="inline-flex items-center gap-0.5 rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-medium text-green-700">
                        <IconCheck className="w-2.5 h-2.5" />
                        In catalog
                      </span>
                    )}
                  </div>
                  <h3 className="text-sm font-semibold text-slate-900 leading-tight mt-1.5">
                    {idea.title}
                  </h3>

                  {/* Description */}
                  <p className="text-xs text-slate-500 mt-2 line-clamp-2">
                    {idea.description}
                  </p>

                  {/* Specs Row */}
                  <div className="flex items-center gap-1.5 mt-3 flex-wrap">
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      {formatTrim(idea.trim_size)}
                    </span>
                    <span className="text-slate-300 text-[10px]">
                      &middot;
                    </span>
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      {idea.page_count} pages
                    </span>
                    <span className="text-slate-300 text-[10px]">
                      &middot;
                    </span>
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      ${idea.list_price.toFixed(2)}
                    </span>
                    <span className="text-slate-300 text-[10px]">
                      &middot;
                    </span>
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      {PAPER_LABELS[idea.paper_type] || idea.paper_type}
                    </span>
                  </div>

                  {/* Market Data Row */}
                  {idea.market_data && (
                    <div className="flex items-center gap-2 mt-3 py-2 px-2.5 rounded-lg bg-slate-50 border border-slate-100">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`inline-block w-2 h-2 rounded-full ${DEMAND_META[idea.market_data.demand].dotColor}`}
                        />
                        <span
                          className={`text-[10px] font-semibold ${DEMAND_META[idea.market_data.demand].color}`}
                        >
                          {DEMAND_META[idea.market_data.demand].label}
                        </span>
                      </div>
                      <span className="text-slate-300 text-[10px]">
                        &middot;
                      </span>
                      <span className="text-[10px] text-slate-500">
                        BSR #{idea.market_data.bsr.toLocaleString()}
                      </span>
                      <span className="text-slate-300 text-[10px]">
                        &middot;
                      </span>
                      <span className="text-[10px] text-slate-500">
                        {idea.market_data.search_results} results
                      </span>
                      <span className="text-slate-300 text-[10px]">
                        &middot;
                      </span>
                      <span className="text-[10px] text-slate-500">
                        {idea.market_data.reviews.toLocaleString()} reviews
                      </span>
                    </div>
                  )}

                  {/* Bottom Row */}
                  <div className="flex items-center justify-between mt-3">
                    <div className="flex items-center gap-3">
                      <span className="text-[11px] font-medium text-emerald-600">
                        Est. {idea.est_monthly_revenue}/mo
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {idea.target_audience}
                      </span>
                    </div>
                    <Link
                      href={`/design/${idea.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-slate-700 transition-colors"
                    >
                      Design &amp; Create
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Floating Action Bar */}
      {selectedCount > 0 && !creating && (
        <div className="fixed bottom-0 left-0 right-0 z-50">
          <div className="mx-auto max-w-4xl px-8 pb-6">
            <div className="rounded-xl border border-slate-200 bg-white shadow-lg px-6 py-4 flex items-center justify-between">
              <span className="text-sm text-slate-600">
                <span className="font-semibold text-slate-900">
                  {selectedCount}
                </span>{" "}
                {selectedCount === 1 ? "idea" : "ideas"} selected
              </span>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setSelectedIds(new Set())}
                  className="text-sm text-slate-500 hover:text-slate-900 transition-colors"
                >
                  Clear
                </button>
                <button
                  onClick={handleCreate}
                  className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
                >
                  Create {selectedCount}{" "}
                  {selectedCount === 1 ? "Book" : "Books"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
