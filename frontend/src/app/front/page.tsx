"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useCoverLightbox } from "@/components/CoverLightbox";
import { useOfficeBackground } from "@/lib/background";
import { scrpt, type Job, type ScrptBook } from "@/lib/scrpt";

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Working late";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

/**
 * The HQ — the study. Air, the book on the desk, the assistant.
 * Everything operational lives in the Back Office.
 */
export default function HQPage() {
  const office = useOfficeBackground();
  const [desk, setDesk] = useState<{ book: ScrptBook; job: Job | null }[]>([]);
  const [waiting, setWaiting] = useState<string[]>([]);
  const openCover = useCoverLightbox();
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);


  useEffect(() => {
    let alive = true;
    const load = async () => {
      const online = await scrpt.health();
      if (!alive) return;
      setEngineOnline(online);
      if (online) {
        try {
          const [list, jobs] = await Promise.all([
            scrpt.listBooks(),
            scrpt.jobs(undefined, true),
          ]);
          if (!alive) return;
          const prose = list.books
            .filter((b) => b.data.manuscript)
            .sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
          // every book being written right now (max 4), all the same size;
          // when nothing is writing, the most recent title sits on the desk
          const writing = jobs.jobs
            .filter((j) => j.kind === "full_draft" && j.book_catalog)
            .map((j) => ({ job: j as Job | null, book: prose.find((b) => b.catalog_number === j.book_catalog) }))
            .filter((w): w is { job: Job; book: ScrptBook } => Boolean(w.book))
            // books actually being written outrank queued ones, oldest job
            // first, so the desk never drops a book mid-write for a newcomer
            .sort((a, b) => {
              const run = (s?: string) => (s === "running" ? 0 : 1);
              const d = run(a.job?.status) - run(b.job?.status);
              return d !== 0 ? d : (a.job?.created_at || "").localeCompare(b.job?.created_at || "");
            })
            .slice(0, 4);
          setDesk(writing.length > 0
            ? writing
            : prose[0] ? [{ book: prose[0], job: null }] : []);
          setWaiting(
            jobs.jobs
              .filter((j) => j.kind === "full_draft" && j.status === "queued" && j.book_catalog
                && !writing.some((w) => w.book.catalog_number === j.book_catalog))
              .map((j) => prose.find((b) => b.catalog_number === j.book_catalog)?.title || "")
              .filter(Boolean));
        } catch { /* engine flaked */ }
      }
    };
    load();
    const interval = setInterval(load, 8000);
    return () => { alive = false; clearInterval(interval); };
  }, []);

  const current = desk[0]?.book || null;
  const job = desk[0]?.job || null;
  const ms = current?.data.manuscript;
  const drafting = Boolean(desk.some((d) => d.job));

  // The desk was drawing every book at 5.5 x 8.5, so a square picture book
  // appeared as a cropped portrait. Take the shape from the book itself.
  const trimOf = (b: ScrptBook): [number, number] => {
    const t = String(
      (b.data?.format as { trim_size?: string } | undefined)?.trim_size
      || (b.data?.trim_size as string | undefined) || "5.5x8.5");
    const m = t.toLowerCase().split("x").map((n) => parseFloat(n));
    return m.length === 2 && m.every((n) => n > 0) ? [m[0], m[1]] : [5.5, 8.5];
  };

  const coverSrc = (b: ScrptBook) => {
    if (b.data.cover?.cover_front_png)
      return `${scrpt.engineUrl}/api/files/${b.catalog_number}/cover-front.png`;
    const v = b.data.cover?.variants;
    if (v?.length) return `${scrpt.engineUrl}/api/files/${b.catalog_number}/${v[0].preview}`;
    return null;
  };

  return (
    <div className="relative overflow-hidden" style={{ height: "calc(100vh - 64px)" }}>
      {/* the study */}
      <div
        className="absolute inset-0 bg-cover"
        style={{ backgroundImage: `url(${office})`, backgroundPosition: "center 30%" }}
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(105deg, rgba(14,12,9,0.82) 0%, rgba(14,12,9,0.45) 45%, rgba(14,12,9,0.15) 75%, rgba(14,12,9,0.35) 100%)",
        }}
      />

      {/* everything stacked bottom-left: book first, greeting beneath it */}
      <div className="relative h-full px-16 flex flex-col justify-end pb-24">
        <div>
          {/* the book on the desk */}
          {current && (
            <div className="flex items-center gap-2 mb-4"
                 style={{ textShadow: "0 1px 10px rgba(0,0,0,0.9)" }}>
              <span
                className={`h-[7px] w-[7px] rounded-full ${drafting ? "pulse-soft" : ""}`}
                style={{ background: drafting ? "var(--status-amber)" : "var(--status-green)" }}
              />
              <span className="text-[11px] tracking-[0.22em] uppercase text-text-secondary">
                Writing right now
              </span>
            </div>
          )}
          <div className="flex items-end gap-7 flex-wrap">
          {desk.map(({ book: b, job: j }) => (
            <Link key={b.catalog_number} href={`/shelf/${b.catalog_number}`}
                  className="group relative block"
                  style={{ width: desk.length > 2 ? "clamp(140px, 21vh, 200px)" : "clamp(170px, 27vh, 250px)" }}>
              <div
                className="relative rounded-[5px] overflow-hidden transition-transform duration-300 group-hover:-translate-y-2 group-hover:rotate-[0.6deg]"
                style={{
                  aspectRatio: `${trimOf(b)[0]} / ${trimOf(b)[1]}`,
                  background: "linear-gradient(155deg, #33291f, #171310 88%)",
                  boxShadow:
                    "0 2px 6px rgba(0,0,0,0.6), 0 24px 60px rgba(0,0,0,0.65), inset 0 0 0 1px rgba(236,229,218,0.09)",
                }}
              >
                {coverSrc(b) ? (
                  <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={coverSrc(b)!} alt={b.title}
                       className="absolute inset-0 w-full h-full object-contain" />
                  <button
                    onClick={(e) => { e.preventDefault(); e.stopPropagation();
                      openCover(coverSrc(b)!, b.title); }}
                    title="View cover fullscreen"
                    className="absolute top-2 left-2 z-10 h-7 w-7 rounded-full flex items-center justify-center
                               opacity-0 group-hover:opacity-100 transition-opacity text-[13px] cursor-zoom-in"
                    style={{ background: "rgba(8,7,5,0.6)", color: "#ece5da", backdropFilter: "blur(3px)" }}>
                    ⛶
                  </button>
                  </>
                ) : (
                  <>
                    <div className="absolute inset-y-0 left-0 w-[10px]"
                         style={{ background: "linear-gradient(90deg, rgba(0,0,0,0.5), transparent)" }} />
                    <div className="absolute inset-0 flex flex-col items-center text-center px-5">
                      <div className="mt-[26%] serif-display text-[17px] leading-snug text-[#e8dfd0]">
                        {b.title}
                      </div>
                      <div className="mt-auto mb-6 text-[10px] tracking-[0.22em] uppercase text-[#a6987f]">
                        {(b.data.author_name as string) || "—"}
                      </div>
                    </div>
                  </>
                )}
                {j && (
                  <div className="absolute bottom-0 inset-x-0 h-[3px]" style={{ background: "rgba(0,0,0,0.55)" }}>
                    <div className="h-full transition-all duration-700"
                         style={{ width: `${Math.round(j.progress * 100)}%`,
                                  background: "linear-gradient(90deg, var(--accent-deep), var(--accent))" }} />
                  </div>
                )}
              </div>
              <div className="mt-3 text-[11.5px] text-text-secondary truncate"
                   style={{ textShadow: "0 1px 10px rgba(0,0,0,0.9)" }}>
                {j ? `Writing ${Math.round(j.progress * 100)}%`
                   : `${b.data.manuscript?.word_count ? b.data.manuscript.word_count.toLocaleString() + " words · " : ""}${b.status}`}
                <span className="text-accent ml-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  Open →
                </span>
              </div>
            </Link>
          ))}
          </div>

          {waiting.length > 0 && (
            <div className="mt-4 text-[11px] tracking-[0.14em] uppercase text-text-tertiary"
                 style={{ textShadow: "0 1px 10px rgba(0,0,0,0.9)" }}>
              Next in line: {waiting.join(" · ")}
            </div>
          )}

          {!current && engineOnline && (
            <Link href="/workorder" className="btn-brass mt-10 inline-flex">
              Commission the first book
            </Link>
          )}

          {/* greeting beneath the book */}
          <div className="max-w-[440px] mt-9">
            <h1
              className="serif-display text-[40px] font-semibold leading-tight"
              style={{ textShadow: "0 2px 28px rgba(0,0,0,0.85)" }}
            >
              {getGreeting()}.
            </h1>
            <p
              className="text-[14px] text-text-secondary mt-2 leading-relaxed"
              style={{ textShadow: "0 1px 14px rgba(0,0,0,0.9)" }}
            >
              {engineOnline === false
                ? "The production engine is offline. Start the SCRPT companion."
                : drafting
                  ? `In production — ${job!.detail || "writing"}`
                  : current
                    ? "Continue production on the current title."
                    : "No titles in production. Commission the first."}
            </p>
          </div>
        </div>
      </div>

      {/* the assistant lives in the app shell (Providers) so it survives
          navigation — no second instance here */}
    </div>
  );
}
