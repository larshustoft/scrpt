"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { scrpt, type Job, type ScrptBook } from "@/lib/scrpt";

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Working late";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  generating: "Writing",
  quality_check: "Quality check",
  ready: "Ready",
  uploading: "Uploading",
  in_review: "In review",
  live: "Live",
  rejected: "Rejected",
  paused: "Paused",
};

export default function HQPage() {
  const [books, setBooks] = useState<ScrptBook[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const online = await scrpt.health();
      if (!alive) return;
      setEngineOnline(online);
      if (online) {
        try {
          const [bookList, jobList] = await Promise.all([
            scrpt.listBooks(),
            scrpt.jobs(undefined, true),
          ]);
          if (!alive) return;
          setBooks(bookList.books.filter((b) => b.data.manuscript));
          setJobs(jobList.jobs);
        } catch { /* engine flaked mid-load */ }
      }
      setLoaded(true);
    };
    load();
    const interval = setInterval(load, 10_000);
    return () => { alive = false; clearInterval(interval); };
  }, []);

  const totalWords = books.reduce(
    (sum, b) => sum + (b.data.manuscript?.word_count || 0), 0);
  const liveBooks = books.filter((b) => b.status === "live").length;
  const inProduction = books.filter((b) =>
    ["draft", "generating", "quality_check"].includes(b.status)).length;
  const readyBooks = books.filter((b) => b.status === "ready").length;

  return (
    <div className="fade-up">
      {/* The study — hero */}
      <section className="relative overflow-hidden" style={{ minHeight: 380 }}>
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url(/hq-background.png)" }}
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(180deg, rgba(14,12,9,0.25) 0%, rgba(14,12,9,0.55) 62%, var(--bg) 100%)",
          }}
        />
        <div className="relative max-w-[1200px] mx-auto px-8 pt-20 pb-16">
          <h1
            className="serif-display text-[40px] font-semibold text-text-primary"
            style={{ textShadow: "0 2px 24px rgba(0,0,0,0.8)" }}
          >
            {getGreeting()}.
          </h1>
          <p className="text-text-secondary text-[15px] mt-1 max-w-[520px]"
             style={{ textShadow: "0 1px 12px rgba(0,0,0,0.9)" }}>
            {inProduction > 0
              ? `${inProduction} book${inProduction === 1 ? "" : "s"} in production. The presses are warm.`
              : "The study is quiet. Commission the next book."}
          </p>
          <div className="flex gap-3 mt-8">
            <Link href="/workorder" className="btn-brass">
              <PlusIcon /> New Work Order
            </Link>
            <Link href="/shelf" className="btn-ghost"
                  style={{ background: "rgba(14,12,9,0.5)", backdropFilter: "blur(8px)" }}>
              Open the Bookshelf
            </Link>
          </div>
        </div>
      </section>

      <div className="max-w-[1200px] mx-auto px-8 pb-16 -mt-2">
        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Books on the shelf" value={books.length} />
          <StatCard label="Words written" value={totalWords.toLocaleString()} />
          <StatCard label="Ready to publish" value={readyBooks} accent={readyBooks > 0} />
          <StatCard label="Live on Amazon" value={liveBooks} accent={liveBooks > 0} />
        </div>

        {/* Engine offline notice */}
        {loaded && engineOnline === false && (
          <div className="card mt-6 flex items-center gap-4"
               style={{ borderLeft: "3px solid var(--status-amber)" }}>
            <div>
              <div className="text-[14px] font-semibold">The engine is offline</div>
              <div className="text-[13px] text-text-secondary mt-0.5">
                Start the SCRPT companion on this machine to write, format, and
                export books: <code className="text-accent">./start.sh</code> in
                the SCRPT folder, or install the launch agent from Settings.
              </div>
            </div>
          </div>
        )}

        {/* Production line */}
        {jobs.length > 0 && (
          <section className="mt-10">
            <h2 className="serif-display text-[20px] font-semibold mb-4">
              Production line
            </h2>
            <div className="space-y-3">
              {jobs.map((job) => (
                <div key={job.id} className="card flex items-center gap-5">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-3">
                      <span className="text-[13px] font-semibold">
                        {jobLabel(job.kind)}
                      </span>
                      {job.book_catalog && (
                        <Link href={`/shelf/${job.book_catalog}`}
                              className="text-[12px] text-accent hover:underline">
                          {job.book_catalog}
                        </Link>
                      )}
                    </div>
                    <div className="text-[12px] text-text-tertiary truncate mt-0.5">
                      {job.detail || job.stage || "Working…"}
                    </div>
                  </div>
                  <div className="w-40 shrink-0">
                    <div className="h-[5px] rounded-full overflow-hidden"
                         style={{ background: "rgba(236,229,218,0.08)" }}>
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${Math.round(job.progress * 100)}%`,
                          background: "linear-gradient(90deg, var(--accent-deep), var(--accent))",
                        }}
                      />
                    </div>
                  </div>
                  <span className="text-[12px] text-text-secondary w-10 text-right shrink-0">
                    {Math.round(job.progress * 100)}%
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Recent books */}
        {books.length > 0 && (
          <section className="mt-10">
            <div className="flex items-baseline justify-between mb-4">
              <h2 className="serif-display text-[20px] font-semibold">
                Recently on the desk
              </h2>
              <Link href="/shelf" className="text-[12px] text-accent hover:underline">
                View all
              </Link>
            </div>
            <div className="grid md:grid-cols-3 gap-4">
              {books.slice(0, 6).map((book) => (
                <Link key={book.id} href={`/shelf/${book.catalog_number}`}
                      className="card card-hover block">
                  <div className="text-[11px] tracking-[0.1em] text-text-faint">
                    {book.catalog_number}
                  </div>
                  <div className="serif-display text-[17px] font-semibold mt-1 leading-snug">
                    {book.title}
                  </div>
                  <div className="flex items-center gap-2 mt-3">
                    <StatusDot status={book.status} />
                    <span className="text-[12px] text-text-secondary">
                      {STATUS_LABELS[book.status] || book.status}
                    </span>
                    {book.data.manuscript?.word_count ? (
                      <span className="text-[12px] text-text-faint ml-auto">
                        {book.data.manuscript.word_count.toLocaleString()} words
                      </span>
                    ) : null}
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}

        {/* Zero state */}
        {loaded && books.length === 0 && engineOnline && (
          <div className="card mt-10 text-center py-14">
            <div className="serif-display text-[24px] font-semibold text-text-primary">
              The shelf is empty
            </div>
            <p className="text-[13px] text-text-secondary mt-2 max-w-[400px] mx-auto">
              Every catalog starts with one title. Describe the book you want —
              SCRPT plots it, writes it, formats it for KDP, and narrates it.
            </p>
            <Link href="/workorder" className="btn-brass mt-6">
              <PlusIcon /> Commission the first book
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

function jobLabel(kind: string): string {
  const labels: Record<string, string> = {
    full_draft: "Writing manuscript",
    plot_options: "Developing plot directions",
    blurb: "Writing listing copy",
    interior_export: "Exporting print interior",
    audiobook: "Narrating audiobook",
  };
  return labels[kind] || kind;
}

function StatCard({ label, value, accent = false }: {
  label: string; value: string | number; accent?: boolean;
}) {
  return (
    <div className="card">
      <div className={`serif-display text-[30px] font-semibold leading-none ${
        accent ? "text-accent" : "text-text-primary"}`}>
        {value}
      </div>
      <div className="text-[11px] tracking-[0.08em] uppercase text-text-tertiary mt-2">
        {label}
      </div>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "live" ? "var(--status-green)"
    : status === "ready" ? "var(--status-blue)"
    : status === "generating" ? "var(--status-amber)"
    : status === "rejected" ? "var(--status-red)"
    : "var(--text-faint)";
  return <span className="h-[7px] w-[7px] rounded-full inline-block"
               style={{ background: color }} />;
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.8"
            strokeLinecap="round" />
    </svg>
  );
}
