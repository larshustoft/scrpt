"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { scrpt, type ScrptBook } from "@/lib/scrpt";

const SPINE_COLORS = [
  "#2b2320", "#3a2d25", "#1f2a33", "#33251f", "#26302a", "#2e2233", "#39312a",
];

export default function ShelfPage() {
  const [books, setBooks] = useState<ScrptBook[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);

  useEffect(() => {
    (async () => {
      const online = await scrpt.health();
      setEngineOnline(online);
      if (online) {
        try {
          const list = await scrpt.listBooks();
          setBooks(list.books.filter((b) => b.data.manuscript));
        } catch { /* ignore */ }
      }
      setLoaded(true);
    })();
  }, []);

  const { seriesGroups, standalone } = useMemo(() => {
    const groups = new Map<string, { id: string; title: string; books: ScrptBook[] }>();
    const single: ScrptBook[] = [];
    for (const b of books) {
      const s = b.data.series;
      if (s?.series_id && s.series_title) {
        if (!groups.has(s.series_id)) {
          groups.set(s.series_id, { id: s.series_id, title: s.series_title, books: [] });
        }
        groups.get(s.series_id)!.books.push(b);
      } else {
        single.push(b);
      }
    }
    for (const g of groups.values()) {
      g.books.sort((a, b) =>
        (a.data.series?.book_number || 0) - (b.data.series?.book_number || 0));
    }
    return { seriesGroups: Array.from(groups.values()), standalone: single };
  }, [books]);

  return (
    <div className="max-w-[1200px] mx-auto px-8 py-12 fade-up">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="serif-display text-[32px] font-semibold">The Bookshelf</h1>
          <p className="text-[13px] text-text-secondary mt-1">
            {books.length} {books.length === 1 ? "title" : "titles"} in the catalog.
            Open any book to edit and preview it.
          </p>
        </div>
        <Link href="/workorder" className="btn-brass">New Work Order</Link>
      </div>

      {loaded && engineOnline === false && (
        <div className="card mt-8" style={{ borderLeft: "3px solid var(--status-amber)" }}>
          <div className="text-[13px] text-text-secondary">
            The local engine is offline — the shelf can&apos;t be loaded. Start the
            SCRPT companion.
          </div>
        </div>
      )}

      {seriesGroups.map((group) => (
        <section key={group.id} className="mt-10">
          <Link href={`/shelf/series/${group.id}`}
                className="group/series inline-flex items-baseline gap-3 mb-4">
            <h2 className="serif-display text-[19px] font-semibold text-text-secondary group-hover/series:text-accent transition-colors">
              {group.title}
            </h2>
            <span className="text-[12px] text-text-faint font-sans">
              series · {group.books.length} books
            </span>
            <span className="text-[12px] text-accent opacity-0 group-hover/series:opacity-100 transition-opacity">
              Open series →
            </span>
          </Link>
          <BookRow books={group.books} />
        </section>
      ))}

      {standalone.length > 0 && (
        <section className="mt-10">
          {seriesGroups.length > 0 && (
            <h2 className="serif-display text-[19px] font-semibold text-text-secondary mb-4">
              Standalone
            </h2>
          )}
          <BookRow books={standalone} />
        </section>
      )}

      {loaded && books.length === 0 && engineOnline && (
        <div className="card mt-10 text-center py-16">
          <div className="serif-display text-[22px] font-semibold">
            Nothing on the shelf yet
          </div>
          <p className="text-[13px] text-text-secondary mt-2">
            Commission the first book and it will appear here, spine out.
          </p>
          <Link href="/workorder" className="btn-brass mt-6">New Work Order</Link>
        </div>
      )}
    </div>
  );
}

function BookRow({ books }: { books: ScrptBook[] }) {
  return (
    <div className="grid gap-5"
         style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))" }}>
      {books.map((book, i) => <BookSpine key={book.id} book={book} colorIndex={i} />)}
    </div>
  );
}

function BookSpine({ book, colorIndex }: { book: ScrptBook; colorIndex: number }) {
  const ms = book.data.manuscript;
  const front = book.data.cover?.cover_front_png;
  const spineColor = SPINE_COLORS[colorIndex % SPINE_COLORS.length];
  const progress = ms
    ? ms.status === "drafted" || ms.status === "editing" || ms.status === "locked"
      ? 1
      : ms.chapters.length
        ? ms.chapters.filter((c) => c.blocks.length > 0).length / ms.chapters.length
        : 0
    : 0;

  return (
    <Link href={`/shelf/${book.catalog_number}`} className="group block">
      <div
        className="relative rounded-[6px] overflow-hidden transition-transform duration-200 group-hover:-translate-y-2"
        style={{
          aspectRatio: "5.5 / 8.5",
          background: front
            ? undefined
            : `linear-gradient(160deg, ${spineColor}, #14100d 90%)`,
          boxShadow: "var(--shadow-page)",
          border: "1px solid rgba(236,229,218,0.08)",
        }}
      >
        {front ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={`${scrpt.engineUrl}/api/files/${book.catalog_number}/cover-front.png`}
               alt={book.title} className="absolute inset-0 w-full h-full object-cover" />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center text-center p-4">
            <div className="mt-[22%] serif-display text-[15px] leading-snug text-[#e8dfd0]">
              {book.title}
            </div>
            <div className="mt-auto mb-4 text-[10px] tracking-[0.18em] uppercase text-[#a6987f]">
              {(book.data.author_name as string) || "—"}
            </div>
          </div>
        )}
        {/* status ribbon */}
        <div className="absolute top-2 right-2 px-2 py-[3px] rounded text-[9px] font-semibold tracking-[0.08em] uppercase"
             style={{
               background: "rgba(14,12,9,0.75)",
               color: book.status === "live" ? "var(--status-green)"
                 : book.status === "ready" ? "var(--status-blue)"
                 : book.status === "generating" ? "var(--status-amber)"
                 : "var(--text-tertiary)",
             }}>
          {book.status}
        </div>
        {/* drafting progress */}
        {progress > 0 && progress < 1 && (
          <div className="absolute bottom-0 inset-x-0 h-[3px]" style={{ background: "rgba(0,0,0,0.5)" }}>
            <div className="h-full" style={{ width: `${progress * 100}%`, background: "var(--accent)" }} />
          </div>
        )}
      </div>
      <div className="mt-2.5 px-0.5">
        <div className="text-[12px] font-medium truncate group-hover:text-accent transition-colors">
          {book.title}
        </div>
        <div className="text-[11px] text-text-faint flex justify-between mt-0.5">
          <span>{book.catalog_number}</span>
          {ms?.word_count ? <span>{Math.round(ms.word_count / 1000)}k words</span> : null}
        </div>
      </div>
    </Link>
  );
}
