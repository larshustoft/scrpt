"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useBooks } from "@/hooks/useBooks";
import { BOOK_TYPE_LABELS, BOOK_TYPE_SHORT } from "@/lib/types";
import type { BookType, PaperType } from "@/lib/types";
import { IconTarget, IconCheck, IconLoader } from "@/components/icons";

// ── Book Idea Type ──────────────────────────────────────────────

interface BookIdea {
  id: string;
  title: string;
  book_type: BookType;
  subtitle: string;
  trim_size: string;
  paper_type: PaperType;
  page_count: number;
  list_price: number;
  niche_keyword: string;
  description: string;
  target_audience: string;
  est_monthly_revenue: string;
  generator_config: Record<string, unknown>;
}

// ── Badge Colors per Book Type ──────────────────────────────────

const BOOK_TYPE_COLORS: Record<string, string> = {
  word_search: "bg-blue-100 text-blue-700",
  sudoku: "bg-purple-100 text-purple-700",
  math_workbook: "bg-amber-100 text-amber-700",
  cryptogram: "bg-emerald-100 text-emerald-700",
  maze: "bg-rose-100 text-rose-700",
  password_log: "bg-slate-200 text-slate-700",
  journal: "bg-teal-100 text-teal-700",
};

// ── Paper Type Labels ───────────────────────────────────────────

const PAPER_LABELS: Record<string, string> = {
  white_bw: "White B&W",
  cream_bw: "Cream B&W",
  standard_color: "Standard Color",
  premium_color: "Premium Color",
};

// ── 10 Curated Book Ideas ───────────────────────────────────────

const BOOK_IDEAS: BookIdea[] = [
  {
    id: "ws-seniors-large-print",
    title: "Ultimate Large Print Word Search for Seniors",
    book_type: "word_search",
    subtitle: "Relaxing Themed Puzzles",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 12.97,
    niche_keyword: "large print word search seniors",
    description:
      "The highest-selling KDP activity book niche. Large print format targets the 65+ demographic with themed puzzles across nature, travel, food, and everyday life.",
    target_audience: "Seniors 65+",
    est_monthly_revenue: "$150 - $300",
    generator_config: {
      subtitle: "Relaxing Themed Puzzles",
      num_puzzles: 55,
      grid_size: 15,
      words_per_puzzle: 15,
      difficulty: "medium",
      large_print: true,
    },
  },
  {
    id: "su-beginners-easy",
    title: "Easy Sudoku for Beginners",
    book_type: "sudoku",
    subtitle: "Gentle Brain Training",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 9.97,
    niche_keyword: "easy sudoku large print beginners",
    description:
      "Beginner-friendly sudoku with 35-40 clue puzzles in large print. Targets new puzzle solvers and seniors looking for relaxing brain exercise without frustration.",
    target_audience: "New puzzlers / Seniors",
    est_monthly_revenue: "$80 - $180",
    generator_config: {
      subtitle: "Gentle Brain Training",
      num_puzzles: 55,
      difficulty: "easy",
      large_print: true,
    },
  },
  {
    id: "mw-multiplication-grade3",
    title: "Multiplication & Division Practice: Grades 3-4",
    book_type: "math_workbook",
    subtitle: "Multiplication & Division Practice",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 12.97,
    niche_keyword: "multiplication division practice grade 3 4",
    description:
      "Parents buy math workbooks year-round for supplemental practice. Multiplication and division focus for grades 3-4 is a perennial best-seller with strong back-to-school demand.",
    target_audience: "Parents / Kids 8-10",
    est_monthly_revenue: "$120 - $250",
    generator_config: {
      subtitle: "Multiplication & Division Practice",
      num_pages: 50,
      problems_per_page: 20,
      operation: "mixed",
      difficulty: "medium",
      large_print: true,
    },
  },
  {
    id: "cr-adults-quotes",
    title: "Cryptogram Puzzle Book for Adults",
    book_type: "cryptogram",
    subtitle: "Decode Famous Quotes",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 11.97,
    niche_keyword: "cryptogram puzzles adults",
    description:
      "Cryptograms are an underserved niche with strong demand from adult puzzle enthusiasts. Each puzzle decodes an inspirational quote, combining word play with motivation.",
    target_audience: "Adult puzzle fans",
    est_monthly_revenue: "$100 - $200",
    generator_config: {
      subtitle: "Decode Famous Quotes",
      num_puzzles: 55,
      large_print: true,
    },
  },
  {
    id: "mz-kids-6-8",
    title: "Amazing Mazes for Kids Ages 6-8",
    book_type: "maze",
    subtitle: "Fun Puzzles for Young Explorers",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 9.97,
    niche_keyword: "maze book kids ages 6 8",
    description:
      "Kids maze books sell strongly in the educational activity category. Easy-to-medium difficulty with large, clear paths designed for young solvers building spatial skills.",
    target_audience: "Kids 6-8 / Parents",
    est_monthly_revenue: "$80 - $160",
    generator_config: {
      subtitle: "Fun Puzzles for Young Explorers",
      num_puzzles: 50,
      difficulty: "easy",
      large_print: true,
    },
  },
  {
    id: "pl-password-organizer",
    title: "Internet Password Organizer",
    book_type: "password_log",
    subtitle: "Keep Your Passwords Safe & Organized",
    trim_size: "6x9",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 7.99,
    niche_keyword: "password organizer book alphabetical",
    description:
      "A top-10 KDP utility niche. Seniors and non-tech-savvy users buy physical password books for simple, secure offline storage. Alphabetical tabs for easy lookup.",
    target_audience: "Seniors / Non-tech users",
    est_monthly_revenue: "$60 - $150",
    generator_config: {
      subtitle: "Keep Your Passwords Safe & Organized",
      log_type: "password_organizer",
    },
  },
  {
    id: "jn-gratitude-6month",
    title: "Daily Gratitude Journal",
    book_type: "journal",
    subtitle: "Start Each Day with Gratitude",
    trim_size: "6x9",
    paper_type: "cream_bw",
    page_count: 200,
    list_price: 9.99,
    niche_keyword: "gratitude journal daily",
    description:
      "Gratitude journals are a proven evergreen niche in wellness. Cream paper gives a premium feel. Each page includes structured prompts for morning reflection.",
    target_audience: "Wellness / Self-help",
    est_monthly_revenue: "$80 - $200",
    generator_config: {
      subtitle: "Start Each Day with Gratitude",
      log_type: "gratitude_journal",
    },
  },
  {
    id: "su-expert-challenge",
    title: "Expert Sudoku Challenge: 200+ Puzzles",
    book_type: "sudoku",
    subtitle: "200+ Expert Puzzles",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 9.97,
    niche_keyword: "hard sudoku expert puzzles",
    description:
      "The complement to beginner sudoku. Expert-level puzzles with 17-21 clues for serious solvers looking for a genuine challenge. Compact print maximizes puzzles per page.",
    target_audience: "Experienced solvers",
    est_monthly_revenue: "$70 - $150",
    generator_config: {
      subtitle: "200+ Expert Puzzles",
      num_puzzles: 55,
      difficulty: "expert",
      large_print: false,
    },
  },
  {
    id: "mw-addition-grade1",
    title: "Addition & Subtraction Practice: Grades 1-2",
    book_type: "math_workbook",
    subtitle: "Addition & Subtraction Practice",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 12.97,
    niche_keyword: "addition subtraction workbook grade 1 2",
    description:
      "The foundational math workbook for early elementary. Easy difficulty with single and double-digit problems. Strong year-round demand from parents and teachers.",
    target_audience: "Parents / Kids 6-7",
    est_monthly_revenue: "$120 - $250",
    generator_config: {
      subtitle: "Addition & Subtraction Practice",
      num_pages: 50,
      problems_per_page: 20,
      operation: "mixed",
      difficulty: "easy",
      large_print: true,
    },
  },
  {
    id: "mz-adults-hard",
    title: "Challenging Mazes for Adults",
    book_type: "maze",
    subtitle: "Complex Brain Training Puzzles",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 9.97,
    niche_keyword: "hard maze book adults brain training",
    description:
      "Adult maze books with complex paths are an emerging niche. Targets the brain-training audience alongside crosswords and sudoku. Hard difficulty for a genuine challenge.",
    target_audience: "Adults / Brain training",
    est_monthly_revenue: "$60 - $140",
    generator_config: {
      subtitle: "Complex Brain Training Puzzles",
      num_puzzles: 50,
      difficulty: "hard",
      large_print: false,
    },
  },
];

// ── Format Helpers ──────────────────────────────────────────────

function formatTrim(trim: string): string {
  const parts = trim.split("x");
  if (parts.length === 2) return `${parts[0]}" x ${parts[1]}"`;
  return trim;
}

// ── Page Component ──────────────────────────────────────────────

export default function ResearchPage() {
  const router = useRouter();
  const { books, createBook } = useBooks();

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [createProgress, setCreateProgress] = useState("");
  const [error, setError] = useState<string | null>(null);

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

  const selectAll = () => {
    if (creating) return;
    if (selectedCount === BOOK_IDEAS.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(BOOK_IDEAS.map((i) => i.id)));
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

  return (
    <div className="p-8 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Book Ideas</h1>
          <p className="text-sm text-slate-500 mt-1">
            Curated concepts ready for one-click creation
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={selectAll}
            disabled={creating}
            className="text-sm text-slate-500 hover:text-slate-900 transition-colors disabled:opacity-50"
          >
            {selectedCount === BOOK_IDEAS.length ? "Deselect all" : "Select all"}
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
              generator settings. Select one or more and create production-ready
              book projects instantly. Every idea uses a working generator — your
              books will be ready to produce.
            </p>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 mb-6">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Card Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {BOOK_IDEAS.map((idea) => {
          const selected = selectedIds.has(idea.id);
          const inCatalog = isInCatalog(idea);
          const typeColor =
            BOOK_TYPE_COLORS[idea.book_type] || "bg-gray-100 text-gray-700";

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
              {/* Top Row: Checkbox + Type Badge + Title */}
              <div className="flex items-start gap-3">
                {/* Checkbox */}
                <div
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition-colors ${
                    selected
                      ? "border-blue-600 bg-blue-600"
                      : "border-slate-300 bg-white"
                  }`}
                >
                  {selected && (
                    <IconCheck className="w-3 h-3 text-white" />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${typeColor}`}
                    >
                      {BOOK_TYPE_SHORT[idea.book_type]}
                    </span>
                    <h3 className="text-sm font-semibold text-slate-900 leading-tight">
                      {idea.title}
                    </h3>
                  </div>

                  {/* Description */}
                  <p className="text-xs text-slate-500 mt-2 line-clamp-2">
                    {idea.description}
                  </p>

                  {/* Specs Row */}
                  <div className="flex items-center gap-1.5 mt-3 flex-wrap">
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      {formatTrim(idea.trim_size)}
                    </span>
                    <span className="text-slate-300 text-[10px]">&middot;</span>
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      {idea.page_count} pages
                    </span>
                    <span className="text-slate-300 text-[10px]">&middot;</span>
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      ${idea.list_price.toFixed(2)}
                    </span>
                    <span className="text-slate-300 text-[10px]">&middot;</span>
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      {PAPER_LABELS[idea.paper_type] || idea.paper_type}
                    </span>
                  </div>

                  {/* Bottom Row: Revenue + Audience + In Catalog Badge */}
                  <div className="flex items-center justify-between mt-3">
                    <div className="flex items-center gap-3">
                      <span className="text-[11px] font-medium text-emerald-600">
                        Est. {idea.est_monthly_revenue}/mo
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {idea.target_audience}
                      </span>
                    </div>
                    {inCatalog && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-medium text-green-700">
                        <IconCheck className="w-3 h-3" />
                        In catalog
                      </span>
                    )}
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
                  Create {selectedCount} {selectedCount === 1 ? "Book" : "Books"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
