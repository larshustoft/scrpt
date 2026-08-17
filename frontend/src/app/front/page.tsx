"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { scrpt, type Job, type ScrptBook } from "@/lib/scrpt";
import { AssistantDock } from "@/components/AssistantDock";

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
  const [current, setCurrent] = useState<ScrptBook | null>(null);
  const [job, setJob] = useState<Job | null>(null);
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
          setCurrent(prose[0] || null);
          setJob(jobs.jobs[0] || null);
        } catch { /* engine flaked */ }
      }
    };
    load();
    const interval = setInterval(load, 8000);
    return () => { alive = false; clearInterval(interval); };
  }, []);

  const ms = current?.data.manuscript;
  const drafting = job && current && job.book_catalog === current.catalog_number;

  return (
    <div className="relative overflow-hidden" style={{ height: "calc(100vh - 64px)" }}>
      {/* the study */}
      <div
        className="absolute inset-0 bg-cover"
        style={{ backgroundImage: "url(/hq-background.png)", backgroundPosition: "center 30%" }}
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
          {current && (
            <Link
              href={`/shelf/${current.catalog_number}`}
              className="group relative block"
              style={{ width: "clamp(190px, 34vh, 310px)" }}
            >
              <div
                className="relative rounded-[5px] overflow-hidden transition-transform duration-300 group-hover:-translate-y-2 group-hover:rotate-[0.6deg]"
                style={{
                  aspectRatio: "5.5 / 8.5",
                  background: "linear-gradient(155deg, #33291f, #171310 88%)",
                  boxShadow:
                    "0 2px 6px rgba(0,0,0,0.6), 0 24px 60px rgba(0,0,0,0.65), inset 0 0 0 1px rgba(236,229,218,0.09)",
                }}
              >
                {current.data.cover?.cover_front_png ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={`${scrpt.engineUrl}/api/files/${current.catalog_number}/cover-front.png`}
                       alt={current.title}
                       className="absolute inset-0 w-full h-full object-cover" />
                ) : (
                  <>
                    {/* spine shadow fold */}
                    <div className="absolute inset-y-0 left-0 w-[10px]"
                         style={{ background: "linear-gradient(90deg, rgba(0,0,0,0.5), transparent)" }} />
                    <div className="absolute inset-0 flex flex-col items-center text-center px-6">
                      <div className="mt-[26%] serif-display text-[20px] leading-snug text-[#e8dfd0]">
                        {current.title}
                      </div>
                      <div className="mt-auto mb-7 text-[10px] tracking-[0.22em] uppercase text-[#a6987f]">
                        {(current.data.author_name as string) || "—"}
                      </div>
                    </div>
                  </>
                )}
                {drafting && (
                  <div className="absolute bottom-0 inset-x-0 h-[3px]" style={{ background: "rgba(0,0,0,0.55)" }}>
                    <div
                      className="h-full transition-all duration-700"
                      style={{ width: `${Math.round(job!.progress * 100)}%`,
                               background: "linear-gradient(90deg, var(--accent-deep), var(--accent))" }}
                    />
                  </div>
                )}
              </div>
              <div className="mt-4 text-[12px] text-text-secondary"
                   style={{ textShadow: "0 1px 10px rgba(0,0,0,0.9)" }}>
                {(() => {
                  const isBook = Boolean(current.data.interior?.page_count);
                  const kindLabel = isBook ? "Book" : "Manuscript";
                  if (drafting) return `${kindLabel} — writing ${Math.round(job!.progress * 100)}%`;
                  return `${kindLabel}${ms?.word_count ? " · " + ms.word_count.toLocaleString() + " words" : ""} · ${current.status}`;
                })()}
                <span className="text-accent ml-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  Open →
                </span>
              </div>
            </Link>
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

      {/* the assistant — bottom right */}
      <AssistantDock />
    </div>
  );
}
