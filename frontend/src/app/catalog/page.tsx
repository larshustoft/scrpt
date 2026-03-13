"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useBooks } from "@/hooks/useBooks";
import { BOOK_TYPE_LABELS, BOOK_TYPE_SHORT, STATUS_COLORS, STATUS_LABELS } from "@/lib/types";
import type { BookType, BookStatus } from "@/lib/types";
import { IconLibrary, IconPlus, IconEye, IconTrash } from "@/components/icons";

export default function CatalogPage() {
  const router = useRouter();
  const { books, loading, deleteBook: remove } = useBooks();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("");

  const filtered = useMemo(() => {
    return books.filter((b) => {
      if (statusFilter && b.status !== statusFilter) return false;
      if (typeFilter && b.data.book_type !== typeFilter) return false;
      return true;
    });
  }, [books, statusFilter, typeFilter]);

  const handleDelete = async (book: { id: string; title: string; catalog_number: string }) => {
    if (!confirm(`Delete "${book.title}" (${book.catalog_number})?`)) return;
    try {
      await remove(book.id);
    } catch (e) {
      alert(`Failed to delete: ${(e as Error).message}`);
    }
  };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Catalog</h1>
          <p className="text-[13px] text-slate-400 mt-1">
            All books in your SCRPT catalog
          </p>
        </div>
        <Link
          href="/create"
          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          <IconPlus className="w-4 h-4" />
          New Book
        </Link>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-6">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        >
          <option value="">All Statuses</option>
          <option value="draft">Draft</option>
          <option value="generating">Generating</option>
          <option value="quality_check">Quality Check</option>
          <option value="ready">Ready</option>
          <option value="uploading">Uploading</option>
          <option value="in_review">In Review</option>
          <option value="live">Live</option>
          <option value="rejected">Rejected</option>
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        >
          <option value="">All Types</option>
          {Object.entries(BOOK_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
            <IconLibrary className="w-6 h-6 text-slate-400" />
          </div>
          <h2 className="text-lg font-semibold text-slate-900">No books found</h2>
          <p className="text-[13px] text-slate-400 mt-1">
            {statusFilter || typeFilter
              ? "Try changing the filters"
              : "Create your first book to get started"}
          </p>
          {!statusFilter && !typeFilter && (
            <Link
              href="/create"
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
            >
              <IconPlus className="w-4 h-4" />
              Create Book
            </Link>
          )}
        </div>
      ) : (
        <>
          <div className="text-[11px] text-slate-400 mb-3">
            Showing {filtered.length} of {books.length} books
          </div>
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
            <table className="min-w-full divide-y divide-slate-100">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Catalog #</th>
                  <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Title</th>
                  <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Type</th>
                  <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Pages</th>
                  <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Price</th>
                  <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Created</th>
                  <th className="px-4 py-3 text-right text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((book) => (
                  <tr
                    key={book.id}
                    className="hover:bg-slate-50/70 transition-colors cursor-pointer"
                    onClick={() => router.push(`/catalog/${book.id}`)}
                  >
                    <td className="px-4 py-3 text-[11px] font-mono text-slate-400">{book.catalog_number}</td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/catalog/${book.id}`}
                        className="text-[13px] font-medium truncate max-w-xs text-blue-600 hover:text-blue-800 hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {book.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-2">
                        <span className="inline-flex items-center justify-center rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-mono font-medium text-slate-500 leading-none">
                          {BOOK_TYPE_SHORT[book.data.book_type as BookType] || "--"}
                        </span>
                        <span className="text-[13px] text-slate-600">
                          {BOOK_TYPE_LABELS[book.data.book_type as BookType] || book.data.book_type}
                        </span>
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_COLORS[book.status as BookStatus] || "bg-gray-100 text-gray-600"}`}
                      >
                        {STATUS_LABELS[book.status as BookStatus] || book.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[13px] text-slate-500">{book.data.page_count}</td>
                    <td className="px-4 py-3 text-[13px] font-medium text-slate-900">${book.data.list_price?.toFixed(2) || "0.00"}</td>
                    <td className="px-4 py-3 text-[11px] text-slate-400">{new Date(book.created_at).toLocaleDateString()}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        <Link
                          href={`/catalog/${book.id}`}
                          className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium text-blue-600 hover:bg-blue-50 transition-colors"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <IconEye className="w-3.5 h-3.5" />
                          Preview
                        </Link>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(book);
                          }}
                          className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium text-red-500 hover:bg-red-50 transition-colors"
                        >
                          <IconTrash className="w-3.5 h-3.5" />
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
