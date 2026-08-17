"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { scrpt, type ScrptBook } from "@/lib/scrpt";

export default function BackOfficePage() {
  const [books, setBooks] = useState<ScrptBook[]>([]);
  const [royalties, setRoyalties] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      if (await scrpt.health()) {
        try {
          const list = await scrpt.listBooks();
          setBooks(list.books.filter((b) => b.data.manuscript));
        } catch { /* ignore */ }
        try {
          const s = await scrpt.reportsSummary();
          setRoyalties(s.totals.royalty || 0);
        } catch { /* no data yet */ }
      }
      setLoaded(true);
    })();
  }, []);

  const words = books.reduce((s, b) => s + (b.data.manuscript?.word_count || 0), 0);
  const ready = books.filter((b) => b.status === "ready").length;
  const live = books.filter((b) => b.status === "live").length;
  const series = new Set(
    books.map((b) => b.data.series?.series_id).filter(Boolean)).size;

  return (
    <div className="max-w-[1100px] mx-auto px-8 py-12 fade-up">
      <h1 className="serif-display text-[32px] font-semibold">Back Office</h1>
      <p className="text-[13px] text-text-secondary mt-1">
        The operational side of the house — catalog, numbers, configuration.
      </p>

      {/* overview strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-8">
        <Stat label="Titles" value={books.length} />
        <Stat label="Series" value={series} />
        <Stat label="Words in catalog" value={words.toLocaleString()} />
        <Stat label="Ready / Live" value={`${ready} / ${live}`} />
        <Stat label="Lifetime royalties"
              value={royalties === null ? "—" : `$${royalties.toFixed(0)}`}
              accent={Boolean(royalties)} />
      </div>

      {/* sections */}
      <div className="grid md:grid-cols-3 gap-5 mt-8">
        <SectionCard
          href="/shelf"
          title="Bookshelf"
          body="Every title in the catalog, spine out. Open a book to write, format, and prepare it for publication."
          meta={loaded ? `${books.length} ${books.length === 1 ? "title" : "titles"}` : ""}
        />
        <SectionCard
          href="/analytics"
          title="Analytics & Royalties"
          body="KDP report imports, royalty history by month, marketplace and title, KENP reads."
          meta={royalties !== null ? `$${royalties.toFixed(2)} lifetime` : "no reports imported yet"}
        />
        <SectionCard
          href="/settings"
          title="Settings"
          body="Publisher identity, pen names, writing model, narration voice, KDP account reference."
          meta=""
        />
      </div>
    </div>
  );
}

function Stat({ label, value, accent = false }: {
  label: string; value: string | number; accent?: boolean;
}) {
  return (
    <div className="card" style={{ padding: 18 }}>
      <div className={`serif-display text-[24px] font-semibold leading-none ${
        accent ? "text-accent" : "text-text-primary"}`}>
        {value}
      </div>
      <div className="text-[10px] tracking-[0.09em] uppercase text-text-tertiary mt-2">{label}</div>
    </div>
  );
}

function SectionCard({ href, title, body, meta }: {
  href: string; title: string; body: string; meta: string;
}) {
  return (
    <Link href={href} className="card card-hover block">
      <div className="serif-display text-[19px] font-semibold">{title}</div>
      <p className="text-[12px] text-text-secondary mt-2 leading-relaxed">{body}</p>
      <div className="flex items-center justify-between mt-4">
        <span className="text-[11px] text-text-faint">{meta}</span>
        <span className="text-accent text-[13px]">→</span>
      </div>
    </Link>
  );
}
