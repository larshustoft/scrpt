"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { scrpt, type ScrptBook } from "@/lib/scrpt";

interface SeriesData {
  series_id: string;
  series_title: string;
  series_bible: string;
  total_planned: number;
  books: ScrptBook[];
}

export default function SeriesPage({ params }: { params: Promise<{ sid: string }> }) {
  const { sid } = use(params);
  const router = useRouter();
  const [series, setSeries] = useState<SeriesData | null>(null);
  const [error, setError] = useState("");
  const [extending, setExtending] = useState(false);
  const [steer, setSteer] = useState("");
  const [showExtend, setShowExtend] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/series/${sid}`);
      if (!res.ok) throw new Error("Series not found");
      setSeries(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load series");
    }
  }, [sid]);

  useEffect(() => { load(); }, [load]);

  const extend = async () => {
    setExtending(true);
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/series/${sid}/extend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count: 1, idea: steer }),
      });
      if (!res.ok) throw new Error("Could not extend series");
      const { books } = await res.json();
      router.push(`/shelf/${books[0].catalog_number}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Extension failed");
      setExtending(false);
    }
  };

  if (error) {
    return (
      <div className="max-w-[900px] mx-auto px-8 py-16">
        <div className="card" style={{ borderLeft: "3px solid var(--status-red)" }}>
          <div className="text-[13px]">{error}</div>
          <Link href="/shelf" className="text-accent text-[13px] mt-2 inline-block">
            Back to the shelf
          </Link>
        </div>
      </div>
    );
  }
  if (!series) {
    return (
      <div className="min-h-[50vh] flex items-center justify-center">
        <span className="serif-display text-accent tracking-[0.3em] pulse-soft">SCRPT</span>
      </div>
    );
  }

  const drafted = series.books.filter(
    (b) => b.data.manuscript?.chapters?.some((c) => c.blocks.length > 0)).length;
  const words = series.books.reduce(
    (s, b) => s + (b.data.manuscript?.word_count || 0), 0);

  return (
    <div className="max-w-[1100px] mx-auto px-8 py-12 fade-up">
      <Link href="/shelf" className="text-[12px] text-text-tertiary hover:text-text-primary transition-colors">
        ← Bookshelf
      </Link>

      <div className="flex items-start justify-between gap-6 mt-3 flex-wrap">
        <div>
          <div className="text-[11px] tracking-[0.14em] uppercase text-text-faint">Series</div>
          <h1 className="serif-display text-[32px] font-semibold leading-tight">
            {series.series_title}
          </h1>
          <div className="text-[13px] text-text-secondary mt-2">
            {series.books.length} of {series.total_planned} planned ·{" "}
            {drafted} written · {words.toLocaleString()} words
          </div>
        </div>
        <button className="btn-brass shrink-0" disabled={extending}
                onClick={() => setShowExtend(!showExtend)}>
          Create more books in this series
        </button>
      </div>

      {showExtend && (
        <div className="card mt-6" style={{ borderLeft: "3px solid var(--accent)" }}>
          <div className="label-scrpt">
            Book {series.books.length + 1} — direction (optional)
          </div>
          <textarea className="input-scrpt min-h-[70px]"
                    placeholder="Where should the next book take the series? Leave empty and SCRPT continues from the series bible."
                    value={steer} onChange={(e) => setSteer(e.target.value)} />
          <div className="flex items-center gap-3 mt-3">
            <button className="btn-brass text-[13px]" disabled={extending} onClick={extend}>
              {extending ? "Commissioning…" : `Commission book ${series.books.length + 1}`}
            </button>
            <span className="text-[12px] text-text-faint">
              Same pen name, genre and format — plot directions arrive in about a minute.
            </span>
          </div>
        </div>
      )}

      {series.series_bible && (
        <div className="card mt-6">
          <div className="label-scrpt">Series bible</div>
          <p className="text-[13px] text-text-secondary leading-relaxed whitespace-pre-line">
            {series.series_bible}
          </p>
        </div>
      )}

      <div className="grid gap-5 mt-8"
           style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))" }}>
        {series.books.map((book) => {
          const ms = book.data.manuscript;
          const no = book.data.series?.book_number;
          // each book at its own trim, so a square picture book is not cropped
          const [tw, th] = (() => {
            const t = String((book.data?.format as { trim_size?: string } | undefined)?.trim_size
              || (book.data?.trim_size as string | undefined) || "5.5x8.5");
            const m = t.toLowerCase().split("x").map((n) => parseFloat(n));
            return m.length === 2 && m.every((n) => n > 0) ? m : [5.5, 8.5];
          })();
          return (
            <Link key={book.id} href={`/shelf/${book.catalog_number}`} className="group block">
              <div className="relative rounded-[6px] overflow-hidden transition-transform duration-200 group-hover:-translate-y-2"
                   style={{
                     aspectRatio: `${tw} / ${th}`,
                     background: "linear-gradient(160deg, #2b2320, #14100d 90%)",
                     boxShadow: "var(--shadow-page)",
                     border: "1px solid rgba(236,229,218,0.08)",
                   }}>
                {book.data.cover?.cover_front_png ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={`${scrpt.engineUrl}/api/files/${book.catalog_number}/cover-front.png`}
                       alt={book.title} className="absolute inset-0 w-full h-full object-contain" />
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
                <div className="absolute top-2 left-2 h-6 w-6 rounded-full flex items-center justify-center text-[11px] font-semibold"
                     style={{ background: "rgba(14,12,9,0.8)", color: "var(--accent)" }}>
                  {no}
                </div>
              </div>
              <div className="mt-2.5 px-0.5">
                <div className="text-[12px] font-medium truncate group-hover:text-accent transition-colors">
                  {book.title}
                </div>
                <div className="text-[11px] text-text-faint flex justify-between mt-0.5">
                  <span>{book.catalog_number}</span>
                  {ms?.word_count ? <span>{Math.round(ms.word_count / 1000)}k</span> : <span>{ms?.status}</span>}
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
