"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useBooks } from "@/hooks/useBooks";
import { checkHealth } from "@/lib/companion";
import {
  IconLibrary,
  IconGlobe,
  IconClock,
  IconTarget,
  IconAlertTriangle,
  IconArrowRight,
} from "@/components/icons";

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    draft: "bg-slate-100 text-slate-600",
    generating: "bg-blue-50 text-blue-600",
    quality_check: "bg-amber-50 text-amber-700",
    ready: "bg-emerald-50 text-emerald-700",
    uploading: "bg-violet-50 text-violet-600",
    in_review: "bg-orange-50 text-orange-600",
    live: "bg-emerald-50 text-emerald-700",
    rejected: "bg-red-50 text-red-600",
    paused: "bg-slate-100 text-slate-500",
  };

  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ${colors[status] || "bg-slate-100 text-slate-600"}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

const STAT_CARDS = [
  {
    key: "total_books" as const,
    label: "Total Books",
    Icon: IconLibrary,
    accent: "text-slate-900",
  },
  {
    key: "books_live" as const,
    label: "Live on Amazon",
    Icon: IconGlobe,
    accent: "text-emerald-600",
  },
  {
    key: "books_in_progress" as const,
    label: "In Progress",
    Icon: IconClock,
    accent: "text-blue-600",
  },
  {
    key: "validated_niches" as const,
    label: "Validated Niches",
    Icon: IconTarget,
    accent: "text-slate-900",
  },
];

export default function Dashboard() {
  const { dashboardStats: stats, loading } = useBooks();
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);

  useEffect(() => {
    checkHealth().then(setEngineOnline);
  }, []);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-[1200px]">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-slate-900 tracking-tight">Dashboard</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Publishing engine overview
          </p>
        </div>
        {engineOnline !== null && (
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`h-2 w-2 rounded-full ${engineOnline ? "bg-emerald-500" : "bg-red-400"}`}
            />
            <span className={engineOnline ? "text-slate-500" : "text-red-400"}>
              {engineOnline ? "Engine running" : "Engine offline"}
            </span>
          </div>
        )}
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        {STAT_CARDS.map((card) => (
          <div
            key={card.key}
            className="rounded-lg border border-slate-200 bg-white px-5 py-4"
          >
            <div className="flex items-center justify-between">
              <card.Icon className="w-4 h-4 text-slate-400" />
              <span className={`text-2xl font-semibold tabular-nums ${card.accent}`}>
                {(stats as unknown as Record<string, unknown>)?.[card.key] as number ?? 0}
              </span>
            </div>
            <p className="mt-2 text-xs text-slate-500 font-medium">{card.label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Books */}
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900">Recent Books</h2>
            <Link
              href="/catalog"
              className="text-[11px] font-medium text-slate-400 hover:text-slate-600 transition-colors flex items-center gap-1"
            >
              View all
              <IconArrowRight className="w-3 h-3" />
            </Link>
          </div>
          <div className="divide-y divide-slate-50">
            {stats.recent_books && stats.recent_books.length > 0 ? (
              stats.recent_books.slice(0, 8).map((book) => (
                <Link
                  key={book.id}
                  href={`/catalog/${book.id}`}
                  className="flex items-center justify-between px-5 py-3 hover:bg-slate-50 transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-mono text-slate-400">
                        {book.catalog_number}
                      </span>
                      <StatusBadge status={book.status} />
                    </div>
                    <p className="mt-0.5 text-sm font-medium text-slate-700 truncate">
                      {book.title}
                    </p>
                  </div>
                  <span className="text-[11px] text-slate-400 ml-4 shrink-0">
                    {new Date(book.created_at).toLocaleDateString()}
                  </span>
                </Link>
              ))
            ) : (
              <div className="px-5 py-10 text-center">
                <p className="text-sm text-slate-400">No books yet</p>
                <Link
                  href="/create"
                  className="mt-2 inline-flex text-xs font-medium text-blue-600 hover:text-blue-700"
                >
                  Create your first book
                </Link>
              </div>
            )}
          </div>
        </div>

        {/* Pipeline Status */}
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="px-5 py-3 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900">Pipeline Status</h2>
          </div>
          <div className="px-5 py-4">
            {stats.books_by_status &&
            Object.keys(stats.books_by_status).length > 0 ? (
              <div className="space-y-2.5">
                {Object.entries(stats.books_by_status).map(([status, count]) => (
                  <div key={status} className="flex items-center justify-between">
                    <StatusBadge status={status} />
                    <span className="text-sm font-semibold text-slate-700 tabular-nums">{count}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-6 text-center">
                <p className="text-sm text-slate-400">
                  Pipeline stats will appear here
                </p>
              </div>
            )}
          </div>

          <div className="px-5 py-3 border-t border-slate-100">
            <p className="text-[11px] font-medium text-slate-400 uppercase tracking-wider mb-2.5">
              Quick Actions
            </p>
            <div className="grid grid-cols-2 gap-2">
              <Link
                href="/create"
                className="rounded border border-slate-200 px-3 py-1.5 text-center text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
              >
                New Book
              </Link>
              <Link
                href="/research"
                className="rounded border border-slate-200 px-3 py-1.5 text-center text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
              >
                Research
              </Link>
              <Link
                href="/catalog"
                className="rounded border border-slate-200 px-3 py-1.5 text-center text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
              >
                Catalog
              </Link>
              <Link
                href="/settings"
                className="rounded border border-slate-200 px-3 py-1.5 text-center text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
              >
                Settings
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
