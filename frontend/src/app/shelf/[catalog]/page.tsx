"use client";

import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCoverLightbox, useLightboxRun } from "@/components/CoverLightbox";
import {
  pollJob, scrpt, type Job, type Manuscript, type ScrptBook, type ValidationReport,
} from "@/lib/scrpt";

type Tab = "manuscript" | "spreads" | "cover" | "audiobook" | "trailer" | "movie" | "publishing";

export default function BookWorkspace({ params }: { params: Promise<{ catalog: string }> }) {
  const { catalog } = use(params);
  const searchParams = useSearchParams();
  const initialTab = (["manuscript", "spreads", "cover", "audiobook", "trailer", "movie", "publishing"] as Tab[])
    .includes(searchParams.get("tab") as Tab) ? (searchParams.get("tab") as Tab) : "manuscript";
  const [book, setBook] = useState<ScrptBook | null>(null);
  const [tab, setTab] = useState<Tab>(initialTab);
  // a children's book has no chapters to show — open it on its spreads
  const kindRef = useRef<string>("");
  useEffect(() => {
    const k = book?.data.kind || "";
    if (k && k !== kindRef.current) {
      kindRef.current = k;
      if (k === "childrens" && tab === "manuscript" && !searchParams.get("tab")) setTab("spreads");
      if (k !== "childrens" && tab === "spreads") setTab("manuscript");
    }
  }, [book, tab, searchParams]);
  const [activeJobs, setActiveJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    try {
      const [b, j] = await Promise.all([
        scrpt.getBook(catalog),
        scrpt.jobs(catalog, true),
      ]);
      setBook(b);
      setActiveJobs(j.jobs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load book");
    }
  }, [catalog]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Poll ALWAYS, not only when a job happened to be running at mount.
  // Starting a job from this page left activeJobs at 0, so polling never
  // began, no progress bar ever appeared, and the work ran invisibly on the
  // server — it looked like the button had done nothing.
  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      const j = await scrpt.jobs(catalog, true).catch(() => ({ jobs: [] }));
      if (stopped) return;
      setActiveJobs(j.jobs);
      if (j.jobs.length) reload();      // only refetch the book while working
    };
    const interval = setInterval(tick, 3000);
    return () => { stopped = true; clearInterval(interval); };
  }, [catalog, reload]);

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
  if (!book) {
    return (
      <div className="min-h-[50vh] flex items-center justify-center">
        <span className="serif-display text-accent tracking-[0.3em] pulse-soft">SCRPT</span>
      </div>
    );
  }

  const ms = book.data.manuscript as Manuscript;
  const series = book.data.series;

  // Books imported from the KDP catalogue arrive with an EMPTY manuscript
  // object — not a missing one — so a truthiness check passes and the page
  // then crashes on ms.word_count.toLocaleString(). Test for a real
  // manuscript. There is nothing here to edit; show the cover and say plainly
  // where the book came from.
  const imported = !ms || ms.word_count === undefined || ms.word_count === null;
  if (imported) {
    const ext = (book.data.external || {}) as Record<string, unknown>;
    const cover = (book.data.cover || {}) as Record<string, unknown>;
    const art = (cover.cover_front_png || cover.artwork_path)
      ? `/api/scrpt/cover/${catalog}/front.png`
      : "";
    return (
      <div className="max-w-[900px] mx-auto px-8 py-10 fade-up">
        <Link href="/shelf" className="text-accent text-[13px]">← Back to the shelf</Link>
        <div className="flex flex-col md:flex-row gap-8 mt-6 items-start">
          {art ? (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img src={art} alt={book.title}
                 className="rounded-[6px] w-full md:w-[380px] shrink-0"
                 style={{ border: "1px solid var(--border-subtle)",
                          boxShadow: "var(--shadow-card)" }} />
          ) : (
            <div className="rounded-[6px] w-full md:w-[380px] shrink-0
                            flex items-center justify-center text-text-faint text-[12px]"
                 style={{ aspectRatio: "5.5 / 8.5", background: "var(--surface)",
                          border: "1px solid var(--border-subtle)" }}>
              No cover on file
            </div>
          )}
          <div className="min-w-0">
            <div className="text-[11px] tracking-[0.12em] text-text-faint">
              {book.catalog_number}
            </div>
            <h1 className="serif-display text-[30px] font-semibold leading-tight mt-1">
              {book.title}
            </h1>
            <div className="text-[13px] text-text-secondary mt-2">
              {(book.data.author_name as string) || "no pen name"}
            </div>
            <div className="mt-6 rounded-[8px] px-4 py-3 text-[13px] text-text-secondary"
                 style={{ background: "var(--surface-elevated)",
                          border: "1px solid var(--border-subtle)" }}>
              Not created in SCRPT
              <div className="text-[12px] text-text-faint mt-1">
                Imported from the existing catalogue, so there is no manuscript,
                interior or cover project to open here.
              </div>
            </div>
            {!!ext.asin && (
              <div className="text-[12px] text-text-faint mt-3">
                ASIN {String(ext.asin)}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[1100px] mx-auto px-8 py-10 fade-up">
      {/* header */}
      <div className="flex items-start gap-6">
        <div className="flex-1 min-w-0">
          <div className="text-[11px] tracking-[0.12em] text-text-faint">
            {book.catalog_number}
            {series?.series_title && (
              <span className="ml-3">{series.series_title} · Book {series.book_number} of {series.total_planned}</span>
            )}
          </div>
          <h1 className="serif-display text-[30px] font-semibold leading-tight mt-1">
            {book.title}
          </h1>
          <div className="flex items-center gap-4 mt-2 text-[12px] text-text-secondary">
            <span className="capitalize">{ms.kind}</span>
            <span>·</span>
            <span>{(book.data.author_name as string) || "no pen name"}</span>
            <span>·</span>
            <span>{ms.word_count.toLocaleString()} words</span>
            <span>·</span>
            <span className="capitalize">{book.status}</span>
          </div>
        </div>
        <Link href={`/shelf/${catalog}/studio`} className="btn-brass shrink-0">
          Open Formatting Studio
        </Link>
      </div>

      {/* live jobs */}
      {activeJobs.map((job) => (
        <div key={job.id} className="card mt-6 flex items-center gap-5"
             style={{ borderLeft: "3px solid var(--status-amber)" }}>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold">
              {{ full_draft: "Writing the manuscript", plot_options: "Developing plot directions",
                 cover_variants: "Creating 4 covers", front_cover: "Creating the front cover",
                 acceptance: "The acceptance desk is reading", audition: "Narrator audition",
                 interior_export: "Exporting the print interior", audiobook: "Narrating the audiobook",
                 blurb: "Writing listing copy" }[job.kind] || job.kind}
            </div>
            <div className="text-[12px] text-text-tertiary truncate">{job.detail || job.stage}</div>
          </div>
          <div className="w-44 h-[5px] rounded-full overflow-hidden shrink-0"
               style={{ background: "rgba(236,229,218,0.08)" }}>
            <div className="h-full transition-all duration-500"
                 style={{ width: `${Math.round(job.progress * 100)}%`,
                          background: "linear-gradient(90deg, var(--accent-deep), var(--accent))" }} />
          </div>
          <span className="text-[12px] text-text-secondary w-9 text-right">
            {Math.round(job.progress * 100)}%
          </span>
          <button className="text-[11px] text-text-faint hover:text-status-red transition-colors"
                  onClick={async () => { await scrpt.cancelJob(job.id); reload(); }}>
            Cancel
          </button>
        </div>
      ))}

      {/* tabs */}
      <div className="inline-flex p-0.5 rounded-lg mt-8"
           style={{ background: "var(--surface-elevated)" }}>
        {((book.data.kind === "childrens"
            ? ["spreads", "cover", "audiobook", "trailer", "movie", "publishing"]
            : ["manuscript", "cover", "audiobook", "trailer", "movie", "publishing"]) as Tab[]).map((t) => (
          <button key={t} onClick={() => {
                    setTab(t);
                    // the tab survives a refresh: it lives in the URL
                    const u = new URL(window.location.href);
                    u.searchParams.set("tab", t);
                    window.history.replaceState(null, "", u.toString());
                  }}
                  className={`px-4 h-8 rounded-md text-[13px] font-medium capitalize transition-all ${
                    tab === t ? "text-text-primary" : "text-text-tertiary hover:text-text-secondary"
                  }`}
                  style={tab === t ? { background: "var(--surface)", boxShadow: "var(--shadow-card)" } : {}}>
            {t === "movie" ? "full movie" : t}</button>
        ))}
      </div>

      {tab === "manuscript" && <ManuscriptTab book={book} ms={ms} reload={reload} busy={activeJobs.length > 0} />}
      {tab === "spreads" && <SpreadsTab book={book} reload={reload} busy={activeJobs.length > 0} />}
      {tab === "cover" && <CoverTab book={book} reload={reload} />}
      {tab === "audiobook" && <AudiobookTab book={book} reload={reload} busy={activeJobs.some((j) => j.kind === "audiobook")} />}
      {tab === "trailer" && <TrailerTab book={book} />}
      {tab === "movie" && <FullMovieTab book={book} />}
      {tab === "publishing" && <PublishingTab book={book} ms={ms} reload={reload} />}
    </div>
  );
}

// ── Manuscript ───────────────────────────────────────────────────

function ManuscriptTab({ book, ms, reload, busy }: {
  book: ScrptBook; ms: Manuscript; reload: () => void; busy: boolean;
}) {
  const [notes, setNotes] = useState("");
  const [choosing, setChoosing] = useState<number | null>(null);
  const catalog = book.catalog_number;

  const choose = async (i: number) => {
    setChoosing(i);
    try {
      await scrpt.choosePlot(catalog, i, notes);
      reload();
    } finally {
      setChoosing(null);
    }
  };

  const rewrite = async () => {
    const ok = window.confirm(
      `Rewrite "${book.title}" from scratch?\n\nKeeps: title, pen name, cover artwork, the idea, and series membership.\nDiscards: the current manuscript, outline and audio — the whole book is written again through the current line (market check, architecture, quality gates, acceptance desk).`
    );
    if (!ok) return;
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/rewrite/${catalog}`, { method: "POST" });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        alert(d.detail || "Could not start the rewrite");
        return;
      }
      reload();
    } catch { /* offline */ }
  };

  return (
    <div className="mt-6 space-y-5">
      {/* idea */}
      <div className="card">
        <div className="label-scrpt">The idea</div>
        <p className="text-[13px] text-text-secondary leading-relaxed">{ms.idea}</p>
      </div>

      {/* start writing — commissioned book that has not been written yet
          (series siblings land here: no plot options, status still "idea") */}
      {ms.status === "idea" && !ms.chapters.some((c) => c.blocks.length > 0) && !busy && (
        <div className="card flex items-center justify-between gap-5 flex-wrap"
             style={{ borderLeft: "3px solid var(--accent)" }}>
          <div className="min-w-[260px] flex-1">
            <div className="serif-display text-[15px] font-semibold">Ready to write</div>
            <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
              {book.data.series?.series_id
                ? "SCRPT writes this book through the full line - market check, story architecture, quality gates and the acceptance desk. It follows the series bible: same main characters, same universe, and a story that stands completely on its own. The cover will match Book 1."
                : "SCRPT writes this book through the full line - market check, story architecture, quality gates and the acceptance desk."}
            </p>
          </div>
          <button className="btn-brass shrink-0 text-[12px] px-4 py-2"
                  disabled={choosing !== null}
                  onClick={async () => {
                    setChoosing(-1);
                    try {
                      await fetch(`${scrpt.engineUrl}/api/scrpt/draft/${catalog}`, { method: "POST" });
                      reload();
                    } finally { setChoosing(null); }
                  }}>
            {choosing === -1 ? "Starting…" : "Write this book"}
          </button>
        </div>
      )}

      {/* rewrite from scratch */}
      {ms.chapters.some((c) => c.blocks.length > 0) && !busy && (
        <div className="card flex items-center justify-between gap-5 flex-wrap">
          <div className="min-w-[260px] flex-1">
            <div className="serif-display text-[15px] font-semibold">Rewrite from scratch</div>
            <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
              Keeps the title, pen name, cover artwork and idea — discards the
              manuscript and writes the whole book again through the current
              line. Made for books produced before the line was at full strength.
            </p>
          </div>
          <button className="btn-ghost text-[12px] shrink-0" onClick={rewrite}>
            Rewrite this book
          </button>
        </div>
      )}

      {/* promote a standalone into a series */}
      {ms.kind === "fiction" && ms.story_bible && !book.data.series?.series_id && !busy && (
        <CreateSeriesCard book={book} />
      )}

      {/* plot options awaiting choice */}
      {ms.status === "plotting" && ms.plot_options.length > 0 && (
        <div className="card" style={{ borderLeft: "3px solid var(--accent)" }}>
          <div className="serif-display text-[18px] font-semibold">
            Three directions — pick one
          </div>
          <p className="text-[12px] text-text-tertiary mt-1">
            SCRPT writes the full book from the direction you choose. Add notes
            below to bend it before drafting begins.
          </p>
          <div className="space-y-4 mt-5">
            {ms.plot_options.map((opt, i) => (
              <div key={i} className="rounded-[10px] p-4"
                   style={{ background: "var(--surface-elevated)", border: "1px solid var(--border-subtle)" }}>
                <div className="flex items-baseline justify-between gap-4">
                  <div className="serif-display text-[16px] font-semibold">{opt.title}</div>
                  <button className="btn-brass shrink-0 text-[12px] px-4 py-2"
                          disabled={busy || choosing !== null}
                          onClick={() => choose(i)}>
                    {choosing === i ? "Starting…" : "Write this book"}
                  </button>
                </div>
                <div className="text-[12px] text-accent mt-1 italic">{opt.logline}</div>
                <details className="mt-2">
                  <summary className="text-[12px] text-text-tertiary cursor-pointer hover:text-text-secondary">
                    Full synopsis
                  </summary>
                  <p className="text-[13px] text-text-secondary leading-relaxed mt-2 whitespace-pre-line">
                    {opt.synopsis}
                  </p>
                </details>
              </div>
            ))}
          </div>
          <div className="mt-4">
            <div className="label-scrpt">Notes for the author (optional)</div>
            <textarea className="input-scrpt min-h-[60px]" value={notes}
                      placeholder="Make the protagonist older. Set it in Marseille. Less violence."
                      onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
      )}

      {/* idea stage, nothing generated yet */}
      {ms.status === "idea" && !busy && (
        <div className="card text-center py-10">
          <p className="text-[13px] text-text-secondary">
            No plot directions yet.
          </p>
          <button className="btn-brass mt-4"
                  onClick={async () => { await scrpt.regeneratePlots(book.catalog_number); reload(); }}>
            Develop plot directions
          </button>
        </div>
      )}

      {/* chapters */}
      {ms.chapters.length > 0 && (
        <div className="card">
          <div className="flex items-baseline justify-between">
            <div className="serif-display text-[18px] font-semibold">Chapters</div>
            <div className="text-[12px] text-text-tertiary">
              {ms.chapters.filter((c) => c.blocks.length > 0).length} of {ms.chapters.length} written
            </div>
          </div>
          <div className="mt-4 divide-y" style={{ borderColor: "var(--border-subtle)" }}>
            {ms.chapters.map((ch) => (
              <div key={ch.id} className="py-3 flex items-center gap-4"
                   style={{ borderColor: "var(--border-subtle)" }}>
                <span className="text-[12px] text-text-faint w-8 shrink-0">{ch.index}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-medium truncate">{ch.title}</div>
                  <div className="text-[11px] text-text-faint truncate">{ch.outline_summary}</div>
                </div>
                {ch.quality_score != null && (
                  <span className="text-[11px] shrink-0"
                        title={ch.quality_notes || "Quality gate score"}
                        style={{ color: ch.quality_score >= 7 ? "var(--status-green)" : "var(--status-amber)" }}>
                    Q{ch.quality_score.toFixed(1)}{ch.revised ? " ·r" : ""}
                  </span>
                )}
                <span className="text-[11px] text-text-tertiary shrink-0">
                  {ch.blocks.length > 0 ? `${ch.word_count.toLocaleString()} words` : ch.status}
                </span>
                <span className="h-[7px] w-[7px] rounded-full shrink-0"
                      style={{ background: ch.blocks.length > 0 ? "var(--status-green)" : "var(--text-faint)" }} />
              </div>
            ))}
          </div>
          {ms.status !== "drafted" && ms.status !== "locked" && !busy &&
           ms.chapters.some((c) => c.blocks.length === 0) && (
            <button className="btn-ghost mt-4"
                    onClick={async () => { await scrpt.resumeDraft(book.catalog_number); reload(); }}>
              Resume drafting
            </button>
          )}
        </div>
      )}

      {/* blurb */}
      {ms.blurb && (
        <div className="card">
          <div className="flex items-baseline justify-between">
            <div className="label-scrpt">Listing description</div>
            <button className="text-[12px] text-accent hover:underline"
                    onClick={async () => { await scrpt.regenerateBlurb(book.catalog_number); reload(); }}>
              Regenerate
            </button>
          </div>
          {ms.tagline && <div className="serif-display italic text-[15px] mb-2">“{ms.tagline}”</div>}
          <p className="text-[13px] text-text-secondary leading-relaxed whitespace-pre-line">{ms.blurb}</p>
        </div>
      )}
    </div>
  );
}

// ── Cover ────────────────────────────────────────────────────────

function CoverTab({ book, reload }: { book: ScrptBook; reload: () => void }) {
  const catalog = book.catalog_number;
  const cover = book.data.cover || {};
  const interior = book.data.interior || {};
  const hasPages = Boolean(interior.page_count);
  const [uploading, setUploading] = useState(false);
  const [report, setReport] = useState<ValidationReport | null>(cover.validation || null);
  const [pkgReady, setPkgReady] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const stale = cover.status === "stale";

  return (
    <div className="mt-6 space-y-5">
      {!hasPages && (
        <div className="card" style={{ borderLeft: "3px solid var(--status-amber)" }}>
          <div className="text-[13px] text-text-secondary">
            The cover&apos;s spine width depends on the final page count, so the
            interior must be exported first. Finish the manuscript, open the
            Formatting Studio, and export — then come back here.
          </div>
        </div>
      )}

      {stale && (
        <div className="card" style={{ borderLeft: "3px solid var(--status-red)" }}>
          <div className="text-[13px]">
            The interior page count changed since this cover was made — the
            spine no longer fits. Regenerate or re-request the cover at{" "}
            {interior.page_count} pages.
          </div>
        </div>
      )}

      <AICoverCard book={book} reload={reload} />

      <CoverFilesCard catalog={catalog} />

      {hasPages && (
        <>
          <CoverSpecCard catalog={catalog} pageCount={interior.page_count!} />

          <div className="grid md:grid-cols-2 gap-5">
            {/* Path B: upload */}
            <div className="card">
              <div className="serif-display text-[17px] font-semibold">
                External designer
              </div>
              <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
                Hand your designer the exact spec, validate their file on return.
              </p>
              <div className="flex flex-wrap gap-2 mt-4">
                <button className="btn-ghost text-[12px]"
                        onClick={async () => {
                          await scrpt.designerPackage(catalog);
                          setPkgReady(true);
                        }}>
                  Generate designer package
                </button>
                {pkgReady && (
                  <>
                    <a className="btn-ghost text-[12px]" href={scrpt.designerFileUrl(catalog, "spec")}>
                      Spec sheet
                    </a>
                    <a className="btn-ghost text-[12px]" href={scrpt.designerFileUrl(catalog, "template")}>
                      Template PDF
                    </a>
                  </>
                )}
              </div>
              <div className="mt-4 pt-4" style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <input ref={fileRef} type="file" accept=".pdf,.png,.tif,.tiff" className="hidden"
                       onChange={async (e) => {
                         const f = e.target.files?.[0];
                         if (!f) return;
                         setUploading(true);
                         try {
                           const r = await scrpt.uploadCover(catalog, f);
                           setReport(r);
                           reload();
                         } catch (err) {
                           setReport({ passed: false, checks: [{ name: "upload", ok: false, detail: String(err) }] });
                         } finally {
                           setUploading(false);
                         }
                       }} />
                <button className="btn-brass text-[12px]" disabled={uploading}
                        onClick={() => fileRef.current?.click()}>
                  {uploading ? "Validating…" : "Upload finished cover"}
                </button>
              </div>
            </div>
          </div>

          {report && (
            <div className="card" style={{ borderLeft: `3px solid ${report.passed ? "var(--status-green)" : "var(--status-red)"}` }}>
              <div className="text-[13px] font-semibold">
                {report.passed ? "Cover accepted — dimensions verified" : "Cover rejected"}
              </div>
              <div className="mt-3 space-y-1.5">
                {report.checks.map((c, i) => (
                  <div key={i} className="flex items-center gap-3 text-[12px]">
                    <span style={{ color: c.ok ? "var(--status-green)" : "var(--status-red)" }}>
                      {c.ok ? "✓" : "✕"}
                    </span>
                    <span className="text-text-tertiary w-28 shrink-0">{c.name.replace(/_/g, " ")}</span>
                    <span className="text-text-secondary">{c.detail}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function AICoverCard({ book, reload }: { book: ScrptBook; reload: () => void }) {
  const catalog = book.catalog_number;
  const cover = book.data.cover || {};
  const hasArt = Boolean(cover.cover_front_png);
  const [direction, setDirection] = useState("");
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState("");
  const [imgKey, setImgKey] = useState(0);
  const openCover = useCoverLightbox();

  const [selecting, setSelecting] = useState<number | null>(null);
  const variants = cover.variants || [];

  const generate = async () => {
    setRunning(true);
    setMsg("Art-directing from the book's bible…");
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/cover/generate-variants/${catalog}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction, count: 4 }),
      });
      const { job_id } = await res.json();
      const job = await pollJob(job_id, (j) => setMsg(j.detail || j.stage || "Creating…"));
      if (job.status === "done") {
        setMsg("Four covers ready — pick one.");
        setImgKey((k) => k + 1);
        reload();
      } else {
        setMsg(`Failed: ${(job.error || "").split("\n")[0]}`);
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setRunning(false);
    }
  };

  const choose = async (index: number) => {
    setSelecting(index);
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/cover/select-variant/${catalog}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index }),
      });
      if (!res.ok) throw new Error("Could not select variant");
      setImgKey((k) => k + 1);
      setMsg(`Variant ${index} is now the cover.`);
      reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Selection failed");
    } finally {
      setSelecting(null);
    }
  };

  return (
    <div className="card">
      <div className="serif-display text-[17px] font-semibold">AI front cover</div>
      <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
        No art direction: the image engine gets six facts — title, genre, a
        short summary, subtitle, author, series — and designs. If you have
        supplied your own cover, every alternative is made to its standard,
        with your cover as the reference. Output meets Amazon&apos;s
        ebook cover spec (1600×2560) and doubles as the print designer&apos;s
        reference.
      </p>

      <div className="mt-4 flex gap-5 flex-wrap items-start">
        {hasArt && (
          <div className="w-[150px] shrink-0">
            <button
              onClick={() => openCover(`${scrpt.engineUrl}/api/files/${catalog}/cover-front.png?v=${imgKey}`, book.title)}
              className="rounded-[5px] overflow-hidden block w-full cursor-zoom-in transition-transform hover:scale-[1.03]"
              style={{ boxShadow: "var(--shadow-page)" }}
              title="Click to view fullscreen">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img key={imgKey}
                   src={`${scrpt.engineUrl}/api/files/${catalog}/cover-front.png?v=${imgKey}`}
                   alt="Front cover" className="w-full block" />
            </button>
            <div className="text-[10px] tracking-[0.12em] uppercase text-text-faint text-center mt-2">
              Current cover · click to enlarge
            </div>
          </div>
        )}
        {variants.length > 0 && (
          <div className="flex-1 min-w-[300px]">
            <div className="label-scrpt">Alternatives — click to make it the cover</div>
            <div className="grid grid-cols-4 gap-3 mt-1">
              {variants.map((v) => (
                <div key={v.index}>
                  <button onClick={() => choose(v.index)}
                          disabled={selecting !== null}
                          className="relative rounded-[5px] overflow-hidden transition-transform hover:scale-[1.04] w-full"
                          style={{
                            boxShadow: cover.selected_variant === v.index
                              ? "0 0 0 2px var(--accent), var(--shadow-page)"
                              : "var(--shadow-page)",
                            opacity: selecting !== null && selecting !== v.index ? 0.5 : 1,
                          }}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={`${scrpt.engineUrl}/api/files/${catalog}/${v.preview}?v=${imgKey}`}
                         alt={`Variant ${v.index}`} className="w-full block" />
                    {selecting === v.index && (
                      <span className="absolute inset-0 flex items-center justify-center text-[11px]"
                            style={{ background: "rgba(14,12,9,0.6)" }}>
                        Installing…
                      </span>
                    )}
                  </button>
                  <button
                    onClick={() => openCover(`${scrpt.engineUrl}/api/files/${catalog}/cover-variant-${v.index}.png?v=${imgKey}`, `Variant ${v.index}`)}
                    className="mt-1 w-full text-[10px] text-text-faint hover:text-accent transition-colors"
                    title="View this option fullscreen">
                    Enlarge
                  </button>
                  {v.concept && (
                    <div className="text-[10px] text-text-faint text-center mt-1.5 leading-snug">
                      {v.concept}
                    </div>
                  )}
                </div>
              ))}
            </div>
            {variants.some((v: { brief?: string }) => v.brief) && (
              <details className="mt-3">
                <summary className="text-[11px] text-text-tertiary cursor-pointer hover:text-text-primary transition-colors">
                  Show the cover briefs
                </summary>
                <div className="mt-2 space-y-3">
                  {variants.filter((v: { brief?: string }) => v.brief).map((v: { index: number; concept?: string; brief?: string }) => (
                    <div key={v.index} className="text-[11px] text-text-tertiary leading-relaxed rounded-md p-3"
                         style={{ background: "var(--surface-elevated)" }}>
                      <span className="font-medium text-text-secondary">
                        {v.index}. {v.concept || `Variant ${v.index}`}:
                      </span>{" "}
                      {v.brief}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </div>

      <div className="mt-4">
        <div className="label-scrpt">Art direction (optional)</div>
        <textarea className="input-scrpt min-h-[54px] text-[12px]"
                  placeholder="e.g. an avalanche tearing through the title, lone rescuer in red, dam far below"
                  value={direction}
                  onChange={(e) => setDirection(e.target.value)} />
      </div>
      <div className="flex items-center gap-3 mt-3 flex-wrap">
        <button className="btn-brass text-[12px]" disabled={running} onClick={generate}>
          {running ? "Creating…" : "Generate 4 covers"}
        </button>
        <button className="btn-ghost text-[12px]"
                title="The six-fact cover prompt, ready to paste into your own ChatGPT conversation"
                onClick={async () => {
                  try {
                    const res = await fetch(`${scrpt.engineUrl}/api/scrpt/cover/fact-sheet/${catalog}`);
                    const { prompt } = await res.json();
                    await navigator.clipboard.writeText(prompt);
                    setMsg("Cover prompt copied — paste it into ChatGPT.");
                  } catch {
                    setMsg("Could not copy the prompt");
                  }
                }}>
          Copy the ChatGPT prompt
        </button>
        <button className="btn-ghost text-[12px]" disabled={running}
                title="Compose the final KDP print file: back cover + spine + front cover with bleed"
                onClick={async () => {
                  setRunning(true);
                  setMsg("Composing the print wrap…");
                  try {
                    const res = await fetch(`${scrpt.engineUrl}/api/scrpt/cover/print-wrap/${catalog}`, { method: "POST" });
                    const d = await res.json();
                    if (!res.ok) throw new Error(d.detail || "Wrap failed");
                    setMsg(`Print wrap ready (${d.spec.total_width_in}″ × ${d.spec.total_height_in}″, spine ${d.spec.spine_width_in}″${d.estimated_pages ? ", page count estimated" : ""}). It's in Cover files below.`);
                    reload();          // the wrap appears in the Cover files card — no new window
                  } catch (e) {
                    setMsg(e instanceof Error ? e.message : "Wrap failed");
                  } finally {
                    setRunning(false);
                  }
                }}>
          Build print wrap
        </button>
        <label className="btn-ghost text-[12px] cursor-pointer">
          Upload finished cover
          <input type="file" accept="image/*" className="hidden"
                 onChange={async (e) => {
                   const f = e.target.files?.[0];
                   if (!f) return;
                   setMsg("Installing your cover…");
                   try {
                     const fd = new FormData();
                     fd.append("file", f);
                     const res = await fetch(`${scrpt.engineUrl}/api/scrpt/cover/install-art/${catalog}`, {
                       method: "POST", body: fd,
                     });
                     if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Upload failed");
                     setMsg("Your cover is installed.");
                     setImgKey((k) => k + 1);
                     reload();
                   } catch (err) {
                     setMsg(err instanceof Error ? err.message : "Upload failed");
                   } finally {
                     e.target.value = "";
                   }
                 }} />
        </label>
        {book.data.series?.series_id && (
          <button className="btn-ghost text-[12px]" disabled={running}
                  title="One design conversation creates every book's cover in order, each one seeing all the covers before it"
                  onClick={async () => {
                    setRunning(true);
                    setMsg("Creating the series covers in one go…");
                    try {
                      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/cover/series-suite/${catalog}`, { method: "POST" });
                      const { job_id } = await res.json();
                      const job = await pollJob(job_id, (j) => setMsg(j.detail || "Creating…"));
                      if (job.status === "done") {
                        setMsg("Series covers complete.");
                        setImgKey((k) => k + 1);
                        reload();
                      } else {
                        setMsg(`Failed: ${(job.error || "").split("\n")[0]}`);
                      }
                    } catch (e) {
                      setMsg(e instanceof Error ? e.message : "Suite failed");
                    } finally {
                      setRunning(false);
                    }
                  }}>
          Create the series covers in one go
          </button>
        )}
        {msg && <span className="text-[11px] text-text-tertiary truncate max-w-[200px]">{msg}</span>}
      </div>
    </div>
  );
}

function CoverFilesCard({ catalog }: { catalog: string }) {
  const [files, setFiles] = useState<{
    front?: { file?: string; url?: string; ebook_url?: string };
    full?: { file?: string; url?: string; validation?: { passed?: boolean }; source?: string };
  } | null>(null);
  const [msg, setMsg] = useState("");
  const [key, setKey] = useState(0);
  const openCover = useCoverLightbox();

  const load = useCallback(() => {
    fetch(`${scrpt.engineUrl}/api/scrpt/cover/files/${catalog}`)
      .then((r) => (r.ok ? r.json() : null)).then(setFiles).catch(() => {});
  }, [catalog]);
  useEffect(load, [load, key]);

  const uploadFull = async (f: File) => {
    setMsg("Validating the full cover against KDP's spec…");
    const fd = new FormData(); fd.append("file", f);
    const r = await fetch(`${scrpt.engineUrl}/api/scrpt/cover/install-full/${catalog}`,
                          { method: "POST", body: fd });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { setMsg(d.detail || "Upload failed"); return; }
    const ok = d.validation?.passed;
    setMsg(ok ? "Full cover installed — passes KDP's spec."
              : "Full cover installed, but its size does not match the spec — check paper type and page count.");
    setKey((k) => k + 1);
  };

  const front = files?.front, full = files?.full;
  return (
    <div className="card">
      <div className="label-scrpt">Cover files</div>
      <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
        Two deliverables per book: the front cover for the ebook listing and
        ads, and the full wrap (back + spine + front) for the KDP paperback.
      </p>
      <div className="grid md:grid-cols-2 gap-5 mt-4">
        {/* front */}
        <div className="rounded-md p-4" style={{ background: "var(--surface-elevated)" }}>
          <div className="text-[12px] font-semibold text-text-secondary">Front cover</div>
          <div className="text-[11px] text-text-faint mt-0.5">Ebook + advertising</div>
          {front?.url ? (
            <div className="flex gap-3 mt-3 items-start">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`${scrpt.engineUrl}${front.url}?v=${key}`} alt="Front"
                   onClick={() => openCover(`${scrpt.engineUrl}${front.url}`, "Front cover")}
                   className="w-[70px] rounded cursor-zoom-in" />
              <div className="space-y-1 text-[11px]">
                <a className="text-accent hover:underline block"
                   href={`${scrpt.engineUrl}${front.url}`} download>Download front (PNG)</a>
                {front.ebook_url && (
                  <a className="text-accent hover:underline block"
                     href={`${scrpt.engineUrl}${front.ebook_url}`} download>Download ebook 1600×2560 (JPG)</a>
                )}
              </div>
            </div>
          ) : <div className="text-[11px] text-text-faint mt-3">No front cover yet.</div>}
        </div>
        {/* full */}
        <div className="rounded-md p-4" style={{ background: "var(--surface-elevated)" }}>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[12px] font-semibold text-text-secondary">Full cover</div>
              <div className="text-[11px] text-text-faint mt-0.5">KDP paperback wrap</div>
            </div>
            {full?.validation && (
              <span className="text-[10px] px-2 py-0.5 rounded"
                    style={{ background: full.validation.passed ? "rgba(70,140,90,0.2)" : "rgba(170,110,50,0.2)",
                             color: full.validation.passed ? "var(--status-green)" : "var(--status-amber)" }}>
                {full.validation.passed ? "spec ✓" : "check size"}
              </span>
            )}
          </div>
          {full?.url ? (
            <div className="mt-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${scrpt.engineUrl}/api/scrpt/cover/wrap-image/${catalog}?dpi=150&v=${key}`}
                alt="Full cover wrap"
                onClick={() => openCover(
                  `${scrpt.engineUrl}/api/scrpt/cover/wrap-image/${catalog}?dpi=350&v=${key}`,
                  "Full cover — back, spine and front")}
                className="w-full rounded cursor-zoom-in transition-transform hover:scale-[1.02]"
                style={{ boxShadow: "var(--shadow-page)" }}
              />
              <div className="text-[10px] text-text-faint text-center mt-1.5">
                Click to view full size · barcode shown for preview only
              </div>
              <div className="mt-2 space-y-1 text-[11px]">
                <a className="text-accent hover:underline block"
                   href={`${scrpt.engineUrl}${full.url}`} download target="_blank">
                  Download upload file ({full.file?.split(".").pop()?.toUpperCase()}) — no barcode
                </a>
                <div className="text-text-faint">
                  {full.source === "upload" ? "Publisher-supplied" : "Composed by SCRPT"}
                </div>
              </div>
            </div>
          ) : <div className="text-[11px] text-text-faint mt-3">No full cover yet — build the print wrap or upload one.</div>}
          <label className="btn-ghost text-[11px] mt-3 inline-block cursor-pointer">
            Upload full cover
            <input type="file" className="hidden" accept="image/png,image/jpeg,application/pdf"
                   onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadFull(f); e.target.value = ""; }} />
          </label>
        </div>
      </div>
      {msg && <div className="text-[11px] text-text-tertiary mt-3">{msg}</div>}
    </div>
  );
}

function CoverSpecCard({ catalog, pageCount }: { catalog: string; pageCount: number }) {
  const [spec, setSpec] = useState<Awaited<ReturnType<typeof scrpt.coverSpec>> | null>(null);
  useEffect(() => {
    scrpt.coverSpec(catalog).then(setSpec).catch(() => {});
  }, [catalog, pageCount]);
  if (!spec) return null;
  return (
    <div className="card">
      <div className="label-scrpt">Computed cover specification</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
        <SpecItem label="Full wrap" value={`${spec.total_width_in}″ × ${spec.total_height_in}″`} />
        <SpecItem label="Spine" value={`${spec.spine_width_in}″`} />
        <SpecItem label="At 300 DPI" value={`${spec.total_width_px} × ${spec.total_height_px}px`} />
        <SpecItem label="Spine text" value={spec.spine_has_text ? "Allowed" : "Not allowed"} />
      </div>
    </div>
  );
}

function SpecItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] tracking-[0.1em] uppercase text-text-faint">{label}</div>
      <div className="text-[14px] font-medium mt-0.5">{value}</div>
    </div>
  );
}

// ── Audiobook ────────────────────────────────────────────────────

interface CastingVoice {
  id: string; name: string; category: string; preview_url: string;
  labels: Record<string, string>; description: string;
}

function CastingBoard({ book, reload }: { book: ScrptBook; reload: () => void }) {
  const audio = book.data.audio || {};
  const [voices, setVoices] = useState<CastingVoice[]>([]);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [defaultId, setDefaultId] = useState("");
  const [auditioning, setAuditioning] = useState("");
  const [auditions, setAuditions] = useState<Record<string, string>>({});
  const [casting, setCasting] = useState("");
  const [castNote, setCastNote] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    fetch(`${scrpt.engineUrl}/api/scrpt/audio/voices`)
      .then((r) => r.json())
      .then((d) => { setConfigured(!!d.configured); setVoices(d.voices || []); setDefaultId(d.default_voice_id || ""); })
      .catch(() => setConfigured(false));
  }, []);

  const audition = async (v: CastingVoice) => {
    setAuditioning(v.id);
    setErr("");
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/audio/audition/${book.catalog_number}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: v.id, voice_name: v.name }),
      });
      const { job_id } = await res.json();
      const job = await pollJob(job_id, () => {});
      if (job.status === "done" && (job.result as { file?: string })?.file) {
        setAuditions((a) => ({ ...a, [v.id]: (job.result as { file: string }).file }));
      } else {
        setErr((job.error || "Audition failed").split("\n")[0]);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Audition failed");
    } finally {
      setAuditioning("");
    }
  };

  const cast = async (v: CastingVoice, asDefault: boolean) => {
    setCasting(v.id);
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/audio/voice/${book.catalog_number}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: v.id, voice_name: v.name, set_as_default: asDefault }),
      });
      // a series shares its narrator — say so rather than changing books silently
      const d = await r.json().catch(() => ({}));
      const n = (d.also_cast || []).length;
      setCastNote(n
        ? `${v.name} now narrates all ${n + 1} books in ${d.series || "the series"}.`
        : "");
      if (asDefault) setDefaultId(v.id);
      reload();
    } finally {
      setCasting("");
    }
  };

  const labelLine = (v: CastingVoice) =>
    [v.labels?.gender, v.labels?.age, v.labels?.accent, v.labels?.descriptive || v.labels?.description]
      .filter(Boolean).join(" · ");

  // ── the search desk ──────────────────────────────────────────
  const [search, setSearch] = useState("");
  const [chips, setChips] = useState<Record<string, boolean>>({
    female: false, male: false, american: false, british: false,
  });
  const [showAll, setShowAll] = useState(false);
  const toggleChip = (k: string) => setChips((c) => ({ ...c, [k]: !c[k] }));

  // ── the full ElevenLabs Voice Library ────────────────────────
  interface LibraryVoice {
    id: string; owner: string; name: string; gender: string; accent: string;
    age: string; descriptive: string; preview_url: string; popularity: number;
    free_ok: boolean;
  }
  const [source, setSource] = useState<"mine" | "library">("library");
  const [libVoices, setLibVoices] = useState<LibraryVoice[]>([]);
  const [libPage, setLibPage] = useState(0);
  const [libHasMore, setLibHasMore] = useState(false);
  const [libLoading, setLibLoading] = useState(false);
  const [adding, setAdding] = useState("");

  const loadLibrary = useCallback(async (page: number, append: boolean) => {
    setLibLoading(true);
    try {
      const gender = chips.female !== chips.male ? (chips.female ? "female" : "male") : "";
      const accent = chips.american !== chips.british ? (chips.american ? "american" : "british") : "";
      const qs = new URLSearchParams({ search, gender, accent, page: String(page),
                                       narration: String(!showAll) });
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/audio/library?${qs}`);
      const d = await res.json();
      setLibVoices((prev) => append ? [...prev, ...(d.voices || [])] : (d.voices || []));
      setLibHasMore(!!d.has_more);
      setLibPage(page);
    } catch { /* offline */ } finally {
      setLibLoading(false);
    }
  }, [search, chips, showAll]);

  useEffect(() => {
    if (source !== "library") return;
    const t = setTimeout(() => loadLibrary(0, false), 350); // debounce typing
    return () => clearTimeout(t);
  }, [source, loadLibrary]);

  const addAndCast = async (v: LibraryVoice) => {
    setAdding(v.id);
    setErr("");
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/audio/library/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner: v.owner, voice_id: v.id, name: v.name }),
      });
      const d = await res.json();
      if (!res.ok) { setErr(d.detail || "Could not add the voice"); return; }
      await fetch(`${scrpt.engineUrl}/api/scrpt/audio/voice/${book.catalog_number}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: d.voice_id, voice_name: v.name, set_as_default: false }),
      });
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not add the voice");
    } finally {
      setAdding("");
    }
  };

  const isNarration = (v: CastingVoice) => {
    const uc = (v.labels?.use_case || "").toLowerCase();
    return uc.includes("audiobook") || uc.includes("narrat");
  };

  const filtered = voices.filter((v) => {
    if (v.id === audio.voice_id) return true; // the cast narrator always shows
    const L = v.labels || {};
    // house rule: American and British narrators only
    const acc = (L.accent || "").toLowerCase();
    if (acc && !["american", "british", "english"].some((a) => acc.includes(a))) return false;
    if (!showAll) {
      // house standard: English-language voices labeled for narration
      if ((L.language || "en").toLowerCase() !== "en") return false;
      if (!isNarration(v)) return false;
    }
    const gender = (L.gender || "").toLowerCase();
    if (chips.female !== chips.male) {
      if (chips.female && gender !== "female") return false;
      if (chips.male && gender !== "male") return false;
    }
    const accent = (L.accent || "").toLowerCase();
    if (chips.american !== chips.british) {
      if (chips.american && !accent.includes("american")) return false;
      if (chips.british && !(accent.includes("british") || accent.includes("english"))) return false;
    }
    if (search.trim()) {
      const hay = `${v.name} ${v.description} ${Object.values(L).join(" ")}`.toLowerCase();
      if (!search.toLowerCase().split(/\s+/).every((t) => hay.includes(t))) return false;
    }
    return true;
  });

  return (
    <div className="card">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <div className="serif-display text-[17px] font-semibold">Casting — the narrator</div>
        {audio.voice_name && (
          <span className="text-[12px]" style={{ color: "var(--status-green)" }}>
            Cast: {audio.voice_name}
          </span>
        )}
      </div>
      <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed max-w-[560px]">
        English voices labeled for narration, from your ElevenLabs library —
        the house standard for audiobooks. Preview plays the stock sample;
        Audition has the candidate read this book&apos;s actual opening. Cast
        the winner and it narrates the whole book — and every other book in
        the same series, so a series sounds like one series.
      </p>
      {castNote && (
        <div className="text-[12px] mt-2" style={{ color: "var(--status-green)" }}>{castNote}</div>
      )}
      {configured === false && (
        <div className="text-[12px] mt-3" style={{ color: "var(--status-amber)" }}>
          ElevenLabs is not configured — add your API key in{" "}
          <Link className="underline" href="/settings">Settings</Link>.
        </div>
      )}
      {err && <div className="text-[12px] mt-3" style={{ color: "var(--status-red)" }}>{err}</div>}

      <div className="flex items-center gap-2 flex-wrap mt-4">
        <div className="flex rounded-md overflow-hidden" style={{ border: "1px solid var(--border-subtle)" }}>
          {([["library", "ElevenLabs library"], ["mine", "My voices"]] as const).map(([k, lbl]) => (
            <button key={k} onClick={() => setSource(k)}
                    className={`px-3 py-[5px] text-[12px] transition-all ${
                      source === k ? "bg-accent-subtle text-accent" : "text-text-tertiary hover:text-text-primary"}`}>
              {lbl}
            </button>
          ))}
        </div>
        <input className="input-scrpt w-[200px] text-[12.5px] py-[6px]"
               placeholder="Search narrators…"
               value={search} onChange={(e) => setSearch(e.target.value)} />
        {(["female", "male", "american", "british"] as const).map((k) => (
          <button key={k}
                  onClick={() => toggleChip(k)}
                  className={`px-3 py-[5px] rounded-md text-[12px] capitalize transition-all ${
                    chips[k] ? "bg-accent-subtle text-accent"
                             : "border border-border-subtle text-text-tertiary hover:text-text-primary"}`}
                  style={chips[k] ? { border: "1px solid var(--accent-deep)" } : {}}
                  title={k === "british" ? "British accent" : k === "american" ? "American accent" : ""}>
            {k}
          </button>
        ))}
        <span className="flex-1" />
        <span className="text-[11px] text-text-faint">
          {source === "library"
            ? `${libVoices.length}${libHasMore ? "+" : ""} narrators`
            : `${filtered.length} narration ${filtered.length === 1 ? "voice" : "voices"}`}
        </span>
        <button className="text-[11px] text-text-tertiary hover:text-text-primary transition-colors underline"
                onClick={() => setShowAll((s) => !s)}>
          {showAll ? "Narration voices only" : "All English voices"}
        </button>
      </div>

      {source === "library" && (
        <>
          <div className="grid md:grid-cols-2 gap-3 mt-3">
            {libVoices.map((v) => (
              <div key={v.id} className="rounded-[9px] p-4"
                   style={{ background: "var(--surface-elevated)", border: "1px solid var(--border-subtle)" }}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[13.5px] font-semibold truncate">{v.name}</span>
                  {v.popularity > 0 && (
                    <span className="text-[10px] text-text-faint shrink-0"
                          title="How many publishers use this narrator">
                      {v.popularity.toLocaleString()} in use
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-text-tertiary mt-0.5 capitalize">
                  {[v.gender, v.age, v.accent, v.descriptive].filter(Boolean).join(" · ")}
                </div>
                {v.preview_url && (
                  <audio controls preload="none" className="h-8 w-full mt-3" src={v.preview_url} />
                )}
                <div className="flex items-center gap-2 mt-3">
                  <span className="flex-1" />
                  <button className="btn-brass text-[11px]" disabled={adding !== ""}
                          onClick={() => addAndCast(v)}>
                    {adding === v.id ? "Adding…" : "Add & cast"}
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-3 mt-3">
            {libLoading && <span className="text-[11px] text-text-tertiary pulse-soft">Searching the library…</span>}
            {!libLoading && libHasMore && (
              <button className="btn-ghost text-[11px]" onClick={() => loadLibrary(libPage + 1, true)}>
                More narrators
              </button>
            )}
            {!libLoading && libVoices.length === 0 && (
              <span className="text-[11px] text-text-faint">No narrators match — loosen the search.</span>
            )}
          </div>
        </>
      )}

      <div className="grid md:grid-cols-2 gap-3 mt-3" style={source === "library" ? { display: "none" } : {}}>
        {filtered.map((v) => {
          const isCast = audio.voice_id === v.id;
          return (
            <div key={v.id} className="rounded-[9px] p-4"
                 style={{
                   background: "var(--surface-elevated)",
                   border: isCast ? "1px solid var(--accent-deep)" : "1px solid var(--border-subtle)",
                 }}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[13.5px] font-semibold">{v.name}</span>
                <span className="text-[10px] uppercase tracking-[0.08em] text-text-faint">
                  {v.id === defaultId ? "house default" : v.category}
                </span>
              </div>
              {labelLine(v) && (
                <div className="text-[11px] text-text-tertiary mt-0.5 capitalize">{labelLine(v)}</div>
              )}
              {auditions[v.id] ? (
                <audio controls preload="none" className="h-8 w-full mt-3"
                       src={`${scrpt.engineUrl}/api/scrpt/audio/file/${book.catalog_number}/${auditions[v.id]}`} />
              ) : v.preview_url ? (
                <audio controls preload="none" className="h-8 w-full mt-3" src={v.preview_url} />
              ) : null}
              <div className="flex items-center gap-2 mt-3">
                <button className="btn-ghost text-[11px]"
                        disabled={auditioning !== ""}
                        onClick={() => audition(v)}>
                  {auditioning === v.id ? "Reading…" : auditions[v.id] ? "Audition again" : "Audition with this book"}
                </button>
                <span className="flex-1" />
                {!isCast && (
                  <button className="btn-brass text-[11px]" disabled={casting !== ""}
                          onClick={() => cast(v, false)}>
                    {casting === v.id ? "Casting…" : "Cast"}
                  </button>
                )}
                {isCast && v.id !== defaultId && (
                  <button className="btn-ghost text-[11px]" onClick={() => cast(v, true)}>
                    Make house default
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AudiobookTab({ book, reload, busy }: { book: ScrptBook; reload: () => void; busy: boolean }) {
  const audio = book.data.audio || {};
  const ms = book.data.manuscript as Manuscript;
  const drafted = ms.chapters.some((c) => c.blocks.length > 0);
  const hasNarrator = Boolean(audio.voice_id);
  const [starting, setStarting] = useState(false);
  const [err, setErr] = useState("");

  return (
    <div className="mt-6 space-y-5">
      <OpeningPreviewCard catalog={book.catalog_number} voiceKey={String((book.data.audio as { voice_id?: string } | undefined)?.voice_id || "")} />
      <CastingBoard book={book} reload={reload} />
      <div className="card">
        <div className="flex items-start justify-between gap-6">
          <div>
            <div className="serif-display text-[17px] font-semibold">Narration</div>
            <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed max-w-[480px]">
              ElevenLabs narrates chapter by chapter, then SCRPT masters every
              file to retail audiobook spec (192 kbps CBR, loudness-normalized,
              retail sample included). Distribute wide via Spotify, Google Play
              and Kobo; use KDP Virtual Voice for the Amazon side.
            </p>
          </div>
          {audio.status !== "mastered" && (
            <button className="btn-brass shrink-0" disabled={!drafted || !hasNarrator || busy || starting}
                    onClick={async () => {
                      setStarting(true);
                      setErr("");
                      try {
                        await scrpt.startAudiobook(book.catalog_number);
                        reload();
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : String(e));
                      } finally {
                        setStarting(false);
                      }
                    }}>
              {busy ? "Narrating…" : "Narrate this book"}
            </button>
          )}
        </div>
        {!drafted && (
          <div className="text-[12px] text-text-faint mt-3">
            The manuscript must be written before narration.
          </div>
        )}
        {drafted && !hasNarrator && (
          <div className="text-[12px] text-text-faint mt-3">
            Cast a narrator above — the button unlocks once a voice is cast.
          </div>
        )}
        {err && (
          <div className="text-[12px] mt-3" style={{ color: "var(--status-red)" }}>
            {err} {err.includes("configured") && <span>— add your key in <Link className="underline" href="/settings">Settings</Link>.</span>}
          </div>
        )}
      </div>

      {(audio.chapters?.length || 0) > 0 && (
        <div className="card">
          <div className="flex items-baseline justify-between">
            <div className="serif-display text-[17px] font-semibold">Files</div>
            <div className="text-[12px] text-text-tertiary">
              {audio.status === "mastered" ? "Mastered · " : ""}
              {Math.round((audio.total_duration_s || 0) / 60)} min ·{" "}
              {audio.voice_name || "AI voice"}
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {audio.sample_path && (
              <AudioRow label="Retail sample" src={scrpt.audioFileUrl(book.catalog_number, audio.sample_path)} />
            )}
            {(audio.chapters || []).map((ch) => (
              <AudioRow key={ch.index}
                        label={ch.title || `Segment ${ch.index}`}
                        meta={`${Math.round(ch.duration_s / 60)} min`}
                        src={scrpt.audioFileUrl(book.catalog_number, ch.audio_path)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AudioRow({ label, src, meta }: { label: string; src: string; meta?: string }) {
  return (
    <div className="flex items-center gap-4">
      <div className="flex-1 min-w-0">
        <div className="text-[13px] font-medium truncate">{label}</div>
        {meta && <div className="text-[11px] text-text-faint">{meta}</div>}
      </div>
      <audio controls preload="none" src={src} className="h-8" style={{ maxWidth: 280 }} />
    </div>
  );
}

/** Promote a standalone into Book 1 of a new series. */
function CreateSeriesCard({ book }: { book: ScrptBook }) {
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState("");

  const create = async () => {
    setRunning(true);
    setMsg("Naming the series and writing its bible…");
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/series/create-from/${book.catalog_number}`,
        { method: "POST" });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setMsg(d.detail || "Could not create the series");
        return;
      }
      const { job_id } = await res.json();
      const job = await pollJob(job_id, (j) => setMsg(j.detail || j.stage || "Working…"));
      if (job.status === "done") {
        const sid = (job.result as { series_id?: string })?.series_id;
        window.location.href = sid ? `/shelf/series/${sid}` : `/shelf/${book.catalog_number}`;
      } else {
        setMsg(`Failed: ${(job.error || "").split("\n")[0]}`);
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="card flex items-center justify-between gap-5 flex-wrap">
      <div className="min-w-[260px] flex-1">
        <div className="serif-display text-[15px] font-semibold">Create a series from this book</div>
        <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
          Same characters, same universe — this becomes Book 1. SCRPT names the
          series, writes the series bible from this book, and opens the series
          page where you commission the next installments.
        </p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        {msg && <span className="text-[11px] text-text-tertiary pulse-soft max-w-[200px]">{msg}</span>}
        <button className="btn-brass text-[12px]" disabled={running} onClick={create}>
          {running ? "Creating…" : "Create series"}
        </button>
      </div>
    </div>
  );
}

// ── Publishing ───────────────────────────────────────────────────

function ScheduleCard({ book }: { book: ScrptBook }) {
  const [releaseDate, setReleaseDate] = useState<string>(
    (book.data.release_date as string) || "");
  const [uploadDate, setUploadDate] = useState<string>(
    (book.data.upload_date as string) || "");
  const [saved, setSaved] = useState(false);

  const save = async (field: string, value: string) => {
    setSaved(false);
    try {
      await fetch(`${scrpt.engineUrl}/api/scrpt/schedule/${book.catalog_number}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch { /* offline */ }
  };

  return (
    <div className="card">
      <div className="flex items-baseline justify-between">
        <div className="serif-display text-[17px] font-semibold">Release schedule</div>
        {saved && <span className="text-[11px] text-status-green">saved</span>}
      </div>
      <p className="text-[12px] text-text-tertiary mt-1">
        Plan the catalog like a production line — upload day (files go to KDP)
        and release day (the book goes live).
      </p>
      <div className="grid md:grid-cols-2 gap-5 mt-4">
        <div>
          <div className="label-scrpt">Upload date</div>
          <input type="date" className="input-scrpt" value={uploadDate}
                 onChange={(e) => { setUploadDate(e.target.value); save("upload_date", e.target.value); }} />
        </div>
        <div>
          <div className="label-scrpt">Release date</div>
          <input type="date" className="input-scrpt" value={releaseDate}
                 onChange={(e) => { setReleaseDate(e.target.value); save("release_date", e.target.value); }} />
        </div>
      </div>
    </div>
  );
}

function AcceptanceCard({ book, reload }: { book: ScrptBook; reload: () => void }) {
  const acc = book.data.acceptance;
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState("");

  const run = async () => {
    setRunning(true);
    setMsg("The acceptance desk takes the manuscript…");
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/acceptance/${book.catalog_number}`,
        { method: "POST" });
      const { job_id } = await res.json();
      const job = await pollJob(job_id, (j) => setMsg(j.detail || j.stage || "Reading…"));
      setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
      reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally {
      setRunning(false);
    }
  };

  const verdictColor = acc?.verdict === "accept" ? "var(--status-green)" : "var(--status-amber)";
  return (
    <div className="card">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <div className="serif-display text-[17px] font-semibold">The acceptance desk</div>
        {acc?.verdict && (
          <span className="text-[12px] font-semibold uppercase tracking-[0.1em]"
                style={{ color: verdictColor }}>
            {acc.verdict === "accept" ? "Accepted" : "Revise"}
            {acc.score ? ` · ${acc.score}/10` : ""}
          </span>
        )}
      </div>
      <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
        Length gate plus a managing-editor read of the whole manuscript, with
        automated repair. Runs on the house writing model — re-run after a
        model upgrade to hold the catalog to the new standard.
      </p>
      {acc?.length && (
        <div className="text-[12px] mt-3"
             style={{ color: acc.length.ok ? "var(--status-green)" : "var(--status-amber)" }}>
          {acc.length.total_words.toLocaleString()} words — commercial band{" "}
          {acc.length.floor.toLocaleString()}–{acc.length.ceiling.toLocaleString()}
          {(acc.length_repairs?.length || 0) > 0 &&
            ` · chapters redrafted for length: ${acc.length_repairs!.join(", ")}`}
        </div>
      )}
      {(acc?.revision_orders?.length || 0) > 0 && (
        <div className="text-[12px] text-text-secondary mt-1">
          Editor&apos;s orders executed on ch. {acc!.revision_orders!.map((o) => o.chapter).join(", ")}
        </div>
      )}
      {acc?.review?.editor_letter && (
        <details className="mt-3">
          <summary className="text-[11px] text-text-tertiary cursor-pointer hover:text-text-primary transition-colors">
            The editor&apos;s letter
          </summary>
          <p className="text-[12.5px] text-text-secondary leading-relaxed mt-2 italic">
            {acc.review.editor_letter}
          </p>
        </details>
      )}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-ghost text-[12px]" disabled={running} onClick={run}>
          {running ? "Reading…" : acc ? "Re-run the acceptance desk" : "Run the acceptance desk"}
        </button>
        {msg && <span className="text-[11px] text-text-tertiary pulse-soft">{msg}</span>}
      </div>
    </div>
  );
}

function PublishingTab({ book, ms, reload }: { book: ScrptBook; ms: Manuscript; reload: () => void }) {
  const interior = book.data.interior || {};
  const cover = book.data.cover || {};
  const pages = interior.page_count || 0;
  const [price, setPrice] = useState<number>((book.data.list_price as number) || 12.99);
  const [genreNorm, setGenreNorm] = useState<{ min: number; target: number } | null>(null);

  useEffect(() => {
    scrpt.presets().then((p) => {
      const g = p.genres[ms.genre_preset] as unknown as { min_words?: number; target_words?: number };
      if (g?.target_words) {
        setGenreNorm({ min: g.min_words || 0, target: g.target_words });
      }
    }).catch(() => {});
  }, [ms.genre_preset]);

  // KDP US paperback B&W economics (docs/KDP_INTERIOR_SPEC.md)
  const printCost = pages > 0
    ? pages <= 110 ? 2.30 : 1.00 + pages * 0.012
    : 0;
  const rate = price >= 9.99 ? 0.6 : 0.5;
  const royalty = Math.max(0, rate * price - printCost);
  const ebookRoyalty = price >= 2.99 && price <= 9.99 ? price * 0.7 : price * 0.35;

  const checklist: { label: string; done: boolean; note?: string }[] = [
    { label: "Manuscript drafted", done: ms.status === "drafted" || ms.status === "editing" || ms.status === "locked" },
    ...(genreNorm ? [{
      label: "Length within genre norms",
      done: ms.word_count >= genreNorm.min,
      note: ms.word_count >= genreNorm.min
        ? `${ms.word_count.toLocaleString()} words (genre floor ${genreNorm.min.toLocaleString()}, market target ${genreNorm.target.toLocaleString()})`
        : `${ms.word_count.toLocaleString()} words is BELOW the ${genreNorm.min.toLocaleString()}-word genre floor — readers will punish a thin book at full price. Market target: ${genreNorm.target.toLocaleString()}.`,
    }] : []),
    { label: "Interior exported and KDP-validated",
      done: Boolean(interior.validation && (interior.validation as ValidationReport).passed),
      note: pages ? `${pages} pages` : undefined },
    { label: "Cover final at current page count",
      done: cover.status === "final" && cover.spec_page_count === pages },
    { label: "Listing description written", done: Boolean(ms.blurb) },
    { label: "Keywords chosen", done: Boolean((book.data.keywords as string[])?.length) },
    { label: "AI-generated content disclosure — REQUIRED on KDP upload",
      done: false,
      note: "Amazon requires disclosing AI-generated text during upload. SCRPT books are AI-generated with human editing." },
  ];

  return (
    <div className="mt-6 space-y-5">
      <ReleaseCard book={book} reload={reload} />
      {/* files */}
      <div className="card">
        <div className="serif-display text-[17px] font-semibold">Print files</div>
        <div className="flex flex-wrap gap-3 mt-4">
          <a className={`btn-ghost text-[12px] ${!interior.pdf_path ? "opacity-40 pointer-events-none" : ""}`}
             href={scrpt.interiorPdfUrl(book.catalog_number)}>
            Interior PDF {pages ? `(${pages} pages)` : ""}
          </a>
          <span className="text-[12px] text-text-faint self-center">
            {interior.exported_at
              ? `exported ${new Date(interior.exported_at).toLocaleString()}`
              : "not exported yet — use the Formatting Studio"}
          </span>
        </div>
        {interior.validation && (
          <div className="mt-4 space-y-1.5">
            {(interior.validation as ValidationReport).checks?.map((c, i) => (
              <div key={i} className="flex items-center gap-3 text-[12px]">
                <span style={{ color: c.ok ? "var(--status-green)" : "var(--status-red)" }}>
                  {c.ok ? "✓" : "✕"}
                </span>
                <span className="text-text-tertiary w-32 shrink-0">{c.name.replace(/_/g, " ")}</span>
                <span className="text-text-secondary">{c.detail}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* pricing */}
      <div className="card">
        <div className="serif-display text-[17px] font-semibold">Pricing</div>
        <div className="grid md:grid-cols-4 gap-5 mt-4 items-end">
          <div>
            <div className="label-scrpt">List price (USD)</div>
            <input type="number" step="0.5" className="input-scrpt" value={price}
                   onChange={(e) => setPrice(Number(e.target.value) || 0)} />
          </div>
          <SpecItem label="Printing cost" value={pages ? `$${printCost.toFixed(2)}` : "—"} />
          <SpecItem label={`Paperback royalty (${Math.round(rate * 100)}%)`}
                    value={pages ? `$${royalty.toFixed(2)}` : "—"} />
          <SpecItem label="Ebook royalty" value={`$${ebookRoyalty.toFixed(2)}`} />
        </div>
        {price < 9.99 && (
          <div className="text-[12px] mt-3" style={{ color: "var(--status-amber)" }}>
            Below $9.99 the print royalty drops to 50%. Price at $9.99+ for the 60% tier.
          </div>
        )}
      </div>

      {/* keywords */}
      {Boolean((book.data.keywords as string[])?.length) && (
        <div className="card">
          <div className="label-scrpt">KDP keywords</div>
          <div className="flex flex-wrap gap-2 mt-1">
            {(book.data.keywords as string[]).map((k, i) => (
              <span key={i} className="px-2.5 py-1 rounded text-[12px]"
                    style={{ background: "var(--surface-elevated)", border: "1px solid var(--border-subtle)" }}>
                {k}
              </span>
            ))}
          </div>
          {Boolean((book.data.categories as string[])?.length) && (
            <>
              <div className="label-scrpt mt-4">Categories</div>
              <div className="text-[13px] text-text-secondary space-y-1 mt-1">
                {(book.data.categories as string[]).map((c, i) => <div key={i}>{c}</div>)}
              </div>
            </>
          )}
        </div>
      )}

      {/* release schedule */}
      <AcceptanceCard book={book} reload={reload} />
      <ScheduleCard book={book} />

      {/* checklist */}
      <div className="card">
        <div className="serif-display text-[17px] font-semibold">KDP checklist</div>
        <div className="mt-4 space-y-3">
          {checklist.map((item, i) => (
            <div key={i} className="flex items-start gap-3">
              <span className="mt-0.5"
                    style={{ color: item.done ? "var(--status-green)" : "var(--text-faint)" }}>
                {item.done ? "✓" : "○"}
              </span>
              <div>
                <div className="text-[13px]">{item.label}</div>
                {item.note && <div className="text-[11px] text-text-faint mt-0.5">{item.note}</div>}
              </div>
            </div>
          ))}
        </div>
        <p className="text-[12px] text-text-faint mt-5">
          Upload manually at kdp.amazon.com — 3 titles per day per account
          maximum. SCRPT prepares everything; you press publish.
        </p>
      </div>
    </div>
  );
}


// ── Book trailer ─────────────────────────────────────────────────
function TrailerTab({ book }: { book: ScrptBook }) {
  return (
    <div className="mt-6 space-y-5">
      <TrailerCard catalog={book.catalog_number} title={book.title} />
    </div>
  );
}

type TrailerVersion = {
  n: number; mode?: string; format?: string; quality?: string; seconds?: number; credits_used?: number;
  created?: string; url: string; poster_url?: string | null;
};

const TRAILER_FORMATS = [
  { key: "wide", label: "Widescreen 16:9", hint: "Cinema and YouTube master" },
  { key: "vertical", label: "Vertical 9:16", hint: "Reels, Shorts, TikTok" },
  { key: "ad", label: "Ad 4:5", hint: "Feed ads — framed from the vertical shoot" },
] as const;

/** A padlock, drawn rather than typed — closed when the face is canon. */
function Lock({ closed }: { closed: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden
         stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <rect x="4" y="11" width="16" height="9" rx="2" />
      {closed
        ? <path d="M8 11V7a4 4 0 0 1 8 0v4" />
        : <path d="M8 11V7a4 4 0 0 1 7.5-2" />}
    </svg>
  );
}

/** One character: the face that is canon, and the way to change your mind.
 *
 *  A locked face is what every book in the series will show, so it is locked
 *  by default the moment it is first drawn — otherwise a job that runs twice
 *  quietly recasts the lead. Opening the padlock is the deliberate act that
 *  allows alternatives to be drawn and a different one chosen; choosing writes
 *  that face across every book in the series at once.
 */
function CastCard({ c, catalog, onChanged, openOne }: {
  c: { name?: string; role?: string; look?: string; plate_url?: string | null;
       locked?: boolean; variant_urls?: string[]; variants?: string[]; kind?: string };
  catalog: string;
  onChanged: () => void;
  openOne: (src: string, alt?: string) => void;
}) {
  const [busy, setBusy] = useState("");
  const [showAlts, setShowAlts] = useState(false);
  const locked = !!c.locked;

  const call = async (path: string, body: object) => {
    setBusy("…");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/bible/${catalog}/${path}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: c.name, ...body }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Failed");
      setBusy("");
      onChanged();
      return d;
    } catch (e) {
      setBusy(e instanceof Error ? e.message.slice(0, 30) : "Failed");
      setTimeout(() => setBusy(""), 3500);
      return null;
    }
  };

  const toggleLock = async () => {
    const d = await call("lock", { locked: !locked });
    if (d && locked) setShowAlts(true);      // just opened: offer alternatives
  };

  const drawMore = async () => {
    setBusy("drawing…");
    const r = await fetch(`${scrpt.engineUrl}/api/scrpt/bible/${catalog}/variants`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: c.name, n: 3 }),
    });
    const d = await r.json();
    if (!r.ok) { setBusy(d.detail || "Failed"); setTimeout(() => setBusy(""), 3500); return; }
    // the drawing runs as a job; poll until it settles, then refresh
    for (let i = 0; i < 60; i++) {
      await new Promise((res) => setTimeout(res, 4000));
      const j = await (await fetch(`${scrpt.engineUrl}/api/scrpt/jobs/${d.job_id}`)).json();
      if (j.status !== "running") break;
    }
    setBusy("");
    onChanged();
  };

  const alts = c.variant_urls || [];

  return (
    <div className="shrink-0" style={{ width: 128 }}>
      <div className="relative">
        {c.plate_url ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img src={`${scrpt.engineUrl}${c.plate_url}`} alt={c.name || ""}
               onClick={() => openOne(`${scrpt.engineUrl}${c.plate_url}`, c.name || "Cast")}
               className="w-full rounded cursor-zoom-in object-cover"
               style={{ height: 128, border: "1px solid var(--line)" }} />
        ) : (
          <div className="w-full rounded flex items-center justify-center text-[10px] text-text-faint text-center px-2"
               style={{ height: 128, border: "1px dashed var(--line)" }}>
            not drawn yet
          </div>
        )}
        <button onClick={toggleLock} disabled={!!busy}
                title={locked
                  ? "Locked for the whole series — click to open and draw alternatives"
                  : "Open: click to lock this face across the series"}
                className="absolute top-1 right-1 rounded p-1 transition-colors"
                style={{ background: "rgba(14,12,9,0.72)",
                         color: locked ? "var(--accent)" : "var(--status-red)",
                         border: "1px solid rgba(236,229,218,0.18)" }}>
          <Lock closed={locked} />
        </button>
      </div>
      <div className="text-[11px] text-text mt-1 truncate" title={c.name}>{c.name}</div>
      <div className="text-[10px] text-text-faint leading-snug line-clamp-2">{c.role}</div>
      {busy && <div className="text-[10px] text-accent mt-0.5">{busy}</div>}

      {!locked && (
        <div className="mt-1">
          <button onClick={() => setShowAlts((v) => !v)}
                  className="text-[10px] text-accent hover:underline">
            {showAlts ? "hide looks" : `other looks${alts.length > 1 ? ` (${alts.length})` : ""}`}
          </button>
          {showAlts && (
            <div className="mt-1">
              <div className="grid grid-cols-2 gap-1">
                {alts.map((u, i) => (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img key={u} src={`${scrpt.engineUrl}${u}`} alt={`${c.name} option ${i + 1}`}
                       onClick={() => call("choose", {
                         variant: (c.variants || [])[i], lock: true })}
                       title="Use this face and lock it for the series"
                       className="w-full rounded cursor-pointer hover:opacity-80"
                       style={{ aspectRatio: "1", objectFit: "cover",
                                border: `1px solid ${u === c.plate_url ? "var(--accent)" : "var(--line)"}` }} />
                ))}
              </div>
              <button onClick={drawMore} disabled={!!busy}
                      className="btn-ghost text-[10px] mt-1 w-full">
                Draw 3 more
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** The cast sheet and the board, under the film they produced.
 *
 *  These are the two things the trailer is actually built from, and until now
 *  they lived only in the database — so a trailer whose faces drifted gave no
 *  clue why. Seeing the cast means seeing whether the same man was handed to
 *  every shot; seeing the board means judging the film before paying to shoot
 *  it. Either can be replaced with your own picture.
 */
function CastAndBoard({ st, catalog, onChanged }: {
  st: TrailerStatus; catalog: string; onChanged: () => void;
}) {
  const openRun = useLightboxRun();
  const openOne = useCoverLightbox();
  const bibleInput = useRef<HTMLInputElement | null>(null);
  const [kind, setKind] = useState<"main" | "supporting">("main");
  const [busy, setBusy] = useState("");
  const [open, setOpen] = useState(true);

  const cast = Object.entries(st.bibles || {}).flatMap(([k, b]) =>
    (b?.characters || []).map((c) => ({ ...c, kind: k })));
  const panels = st.storyboard?.panels || [];
  if (!cast.length && !panels.length) return null;

  const uploadBible = async (f: File) => {
    setBusy("Reading the cast sheet…");
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await fetch(
        `${scrpt.engineUrl}/api/scrpt/bible/${catalog}?kind=${kind}`,
        { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Upload failed");
      onChanged();
    } catch (e) {
      setBusy(e instanceof Error ? e.message : "Upload failed");
      setTimeout(() => setBusy(""), 4000);
      return;
    }
    setBusy("");
    if (bibleInput.current) bibleInput.current.value = "";
  };

  const frames = panels.filter((p) => p.frame_url);
  const [redoPanel, setRedoPanel] = useState<string | null>(null);
  const [redoPrompt, setRedoPrompt] = useState("");
  const [redoBusy, setRedoBusy] = useState(false);
  // which panel has a job running, and how far along it is (0..1)
  const [frameJob, setFrameJob] = useState<{ panel: string; pct: number } | null>(null);
  // bumps after every redraw/reshoot so the browser refetches frame images
  const [bust, setBust] = useState(0);
  const redrawFrame = async () => {
    if (!redoPanel) return;
    setRedoBusy(true);
    const panel = redoPanel;
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/board-frame/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ panel, prompt: redoPrompt }),
      });
      const d = await r.json();
      if (!r.ok) { setRedoPrompt(d.detail || "Could not redraw"); return; }
      setRedoPanel(null); setRedoPrompt("");
      setFrameJob({ panel, pct: 0.05 });
      await pollJob(d.job_id, (j) => setFrameJob({ panel, pct: Number(j.progress) || 0.05 }));
      setBust(Date.now());
      onChanged();
    } finally { setRedoBusy(false); setFrameJob(null); }
  };
  const reshootScene = async (panel: string, secsLabel: string) => {
    const q = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/reshoot-scene/${catalog}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ panel }),
    }).then((r) => r.json());
    if (!window.confirm(
      `Re-shoot scene ${panel} (${q.seconds ?? secsLabel}s)?\n\nEstimated up to ${q.estimate_credits_max} credits. ` +
      `Every other take, the voice and the music are reused; the re-cut is free.`)) return;
    const d = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/reshoot-scene/${catalog}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ panel, confirm: true }),
    }).then((r) => r.json());
    if (d.job_id) {
      setFrameJob({ panel, pct: 0.03 });
      try {
        await pollJob(d.job_id, (j) => setFrameJob({ panel, pct: Number(j.progress) || 0.03 }));
      } finally { setFrameJob(null); }
      setBust(Date.now());
      onChanged();
    }
  };

  return (
    <div className="mt-4 border-t border-line pt-3">
      <button onClick={() => setOpen((v) => !v)}
              className="flex items-center gap-2 text-[12px] text-text-secondary hover:text-text">
        <span style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform 140ms" }}>›</span>
        Cast sheet &amp; storyboard
        <span className="text-text-faint">
          {cast.length ? `· ${cast.length} character${cast.length > 1 ? "s" : ""}` : ""}
          {panels.length ? ` · ${panels.length} panels` : ""}
        </span>
      </button>

      {open && (
        <div className="mt-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[11px] uppercase tracking-[0.14em] text-text-faint">Cast</span>
            <select value={kind} onChange={(e) => setKind(e.target.value as "main" | "supporting")}
                    className="input-scrpt text-[11px] py-0.5 px-1">
              <option value="main">main</option>
              <option value="supporting">supporting</option>
            </select>
            <input ref={bibleInput} type="file" accept="image/*" className="hidden"
                   onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadBible(f); }} />
            <button className="btn-ghost text-[11px]" disabled={!!busy}
                    onClick={() => bibleInput.current?.click()}>
              {busy || "Upload your own cast sheet"}
            </button>
          </div>

          <div className="flex gap-3 overflow-x-auto pb-2">
            {cast.map((c) => (
              <CastCard key={`${c.kind}-${c.name}`} c={c} catalog={catalog}
                        onChanged={onChanged} openOne={openOne} />
            ))}
          </div>

          {panels.length > 0 && (
            <>
              <div className="flex items-center gap-3 mt-4 mb-2">
                <div className="text-[11px] uppercase tracking-[0.14em] text-text-faint">
                  Storyboard
                </div>
                <button className="btn-ghost text-[10px] px-2 py-0.5" disabled={!!frameJob}
                        onClick={async () => {
                          const q = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/reshoot-scene/${catalog}`, {
                            method: "POST", headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ panel: "all" }),
                          }).then((r) => r.json());
                          if (!window.confirm(
                            `Re-shoot ALL ${q.scenes} scenes (${Math.round(q.seconds)}s of footage)?\n\n` +
                            `Estimated up to ${q.estimate_credits_max} credits. Voice and music are reused; ` +
                            `every old take is kept on disk.`)) return;
                          const d = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/reshoot-scene/${catalog}`, {
                            method: "POST", headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ panel: "all", confirm: true }),
                          }).then((r) => r.json());
                          if (d.job_id) {
                            setFrameJob({ panel: "all", pct: 0.02 });
                            try {
                              await pollJob(d.job_id, (j) => setFrameJob({ panel: "all", pct: Number(j.progress) || 0.02 }));
                            } finally { setFrameJob(null); }
                            setBust(Date.now());
                            onChanged();
                          }
                        }}>
                  Re-shoot all scenes…
                </button>
                {frameJob?.panel === "all" && (
                  <svg width="30" height="30" viewBox="0 0 30 30">
                    <circle cx="15" cy="15" r="12" fill="none" stroke="var(--line)" strokeWidth="2.5" />
                    <circle cx="15" cy="15" r="12" fill="none" stroke="var(--accent, #c9a96a)"
                            strokeWidth="2.5" strokeLinecap="round"
                            strokeDasharray={`${Math.max(3, frameJob.pct * 75)} 75`}
                            transform="rotate(-90 15 15)"
                            style={{ transition: "stroke-dasharray 0.6s ease" }} />
                    <text x="15" y="18.5" textAnchor="middle" fontSize="8.5"
                          fill="var(--text-secondary, #bbb)">{Math.round(frameJob.pct * 100)}%</text>
                  </svg>
                )}
              </div>
              <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}>
                {panels.map((p, i) => (
                  <div key={String(p.n ?? i)}>
                    {p.frame_url ? (
                      <div className="relative">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={`${scrpt.engineUrl}${p.frame_url}`} alt={String(p.title || p.n || i + 1)}
                             onClick={() => openRun({
                               index: frames.findIndex((f) => f.n === p.n),
                               frames: frames.map((f) => ({
                                 label: `Panel ${f.n} · ${f.title || ""}`,
                                 srcs: [`${scrpt.engineUrl}${f.frame_url}`],
                               })),
                             }, `Panel ${p.n}`)}
                             className="w-full rounded cursor-zoom-in"
                             style={{ aspectRatio: "16/9", objectFit: "cover", border: "1px solid var(--line)",
                                      opacity: frameJob?.panel === String(p.n) ? 0.35 : 1 }} />
                        {frameJob?.panel === String(p.n) && (
                          <div className="absolute inset-0 flex items-center justify-center">
                            <svg width="44" height="44" viewBox="0 0 44 44">
                              <circle cx="22" cy="22" r="18" fill="none"
                                      stroke="var(--line)" strokeWidth="3" />
                              <circle cx="22" cy="22" r="18" fill="none"
                                      stroke="var(--accent, #c9a96a)" strokeWidth="3"
                                      strokeLinecap="round"
                                      strokeDasharray={`${Math.max(4, frameJob.pct * 113)} 113`}
                                      transform="rotate(-90 22 22)"
                                      style={{ transition: "stroke-dasharray 0.6s ease" }} />
                              <text x="22" y="26" textAnchor="middle" fontSize="10"
                                    fill="var(--text-secondary, #bbb)">
                                {Math.round(frameJob.pct * 100)}%
                              </text>
                            </svg>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="w-full rounded flex items-center justify-center text-[10px] text-text-faint"
                           style={{ aspectRatio: "16/9", border: "1px dashed var(--line)" }}>
                        panel {String(p.n ?? i + 1)}
                      </div>
                    )}
                    <div className="text-[11px] text-text mt-1">
                      {p.n}. {p.title}
                      {p.dur ? <span className="text-text-faint"> · {p.dur}s</span> : null}
                    </div>
                    {p.characters?.length ? (
                      <div className="text-[10px] text-accent">{p.characters.join(", ")}</div>
                    ) : (
                      <div className="text-[10px] text-text-faint">no cast referenced</div>
                    )}
                    {p.vo ? <div className="text-[10px] text-text-secondary italic leading-snug">“{p.vo}”</div> : null}
                    <div className="flex gap-1.5 mt-1">
                      <button className="btn-ghost text-[10px] px-2 py-0.5"
                              disabled={!!frameJob}
                              onClick={() => { setRedoPanel(String(p.n)); setRedoPrompt(""); }}>
                        Redraw image
                      </button>
                      <button className="btn-ghost text-[10px] px-2 py-0.5"
                              disabled={!!frameJob}
                              onClick={() => reshootScene(String(p.n), String(p.dur || 4))}>
                        Re-shoot scene
                      </button>
                    </div>
                    {redoPanel === String(p.n) && (
                      <div className="mt-1.5 p-2 rounded-[6px] border border-border-subtle">
                        <textarea value={redoPrompt} onChange={(e) => setRedoPrompt(e.target.value)}
                                  rows={3} autoFocus
                                  className="w-full rounded-[5px] border border-border-subtle bg-transparent p-1.5 text-[11px] leading-snug"
                                  placeholder="Describe the image you want — or leave empty to redraw from the shot description." />
                        <div className="flex gap-1.5 mt-1.5">
                          <button className="btn-brass text-[10px] px-2 py-0.5" disabled={redoBusy}
                                  onClick={redrawFrame}>
                            {redoBusy ? "Starting…" : "Redraw"}
                          </button>
                          <button className="btn-ghost text-[10px] px-2 py-0.5" disabled={redoBusy}
                                  onClick={() => setRedoPanel(null)}>Cancel</button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {st.storyboard?.music ? (
                <div className="text-[10px] text-text-faint mt-2">Score: {st.storyboard.music}</div>
              ) : null}
            </>
          )}
        </div>
      )}
    </div>
  );
}

type TrailerShot = { n: number; seconds?: number; camera?: string; prompt?: string; voiceover?: string; sound?: string };

type TrailerStatus = {
  treatment?: { concept?: string; shots?: TrailerShot[]; music?: string; end_card_text?: string } | null;
  production?: { mode?: string; seconds?: number; credits_used?: number; credits_left?: number } | null;
  approved?: boolean;
  reference?: { title?: string; duration?: number; shots?: number; avg_shot_seconds?: number;
                analysis?: { lessons?: string[] } } | null;
  storyboard_pending?: { panels: number; source: string } | null;
  storyboard?: {
    count: number;
    music?: string;
    panels: Array<{
      n?: string | number; title?: string; dur?: number; shot?: string;
      vo?: string; characters?: string[]; frame_url?: string | null;
      line?: { speaker?: string; text?: string } | null;
    }>;
  } | null;
  bibles?: Record<string, {
    source?: string; style?: string;
    characters?: Array<{ name?: string; role?: string; look?: string;
                         plate_url?: string | null; locked?: boolean;
                         variants?: string[]; variant_urls?: string[] }>;
    locations?: Array<{ name?: string; look?: string }>;
  } | null> | null;
  review?: { score?: number; reads_as_trailer?: boolean; notes?: string[]; defects?: { plate?: string; what?: string }[] } | null;
  workorder_prompt?: string | null;
  direction?: { angle?: string; look?: string; seconds?: number; shots?: number; pacing?: string;
                voice?: { register?: string; query?: string }; music?: string; end_card?: string } | null;
  voice?: { id?: string; name?: string; auto?: boolean; why?: string } | null;
  versions?: TrailerVersion[];
  has_video?: boolean;
  video_url?: string | null;
  poster_url?: string | null;
  runway?: { connected?: boolean; credits?: number | null };
  estimates?: { full?: number; draft?: number; voiceover?: number; finish_4k?: number };
};

function TrailerCard({ catalog, title }: { catalog: string; title?: string }) {
  const [st, setSt] = useState<TrailerStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [key, setKey] = useState(0);
  const [watching, setWatching] = useState<number | "latest">("latest");
  const [format, setFormat] = useState<"wide" | "vertical" | "ad">("wide");
  const [quality, setQuality] = useState<"draft" | "full" | "seedance" | "seedance_master">("seedance");   // drafts first; master the approved cut
  const [desk] = useState(true);   // the director's desk stays open (Lars, 2026-08-29)
  const [shooting, setShooting] = useState<{ stage: string; detail: string; progress: number; started: number; total: number } | null>(null);
  const [brief, setBrief] = useState("");
  const [voEdits, setVoEdits] = useState<Record<number, string>>({});
  const [sceneEdits, setSceneEdits] = useState<Record<number, string>>({});
  const [soundEdits, setSoundEdits] = useState<Record<number, string>>({});
  const [ideas, setIdeas] = useState<Record<string, string[]>>({});
  const [ideasLoading, setIdeasLoading] = useState<string | null>(null);
  const [tagline, setTagline] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    fetch(`${scrpt.engineUrl}/api/scrpt/trailer/${catalog}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: TrailerStatus | null) => {
        setSt(d);
        setVoEdits({});
        setSceneEdits({});
        setSoundEdits({});
        setTagline(null);
        setDirty(false);
      }).catch(() => {});
    // re-attach to a trailer job already running for this book (the desk
    // works in the engine; leaving the page never stops it)
    fetch(`${scrpt.engineUrl}/api/scrpt/jobs`)
      .then((r) => (r.ok ? r.json() : []))
      .then(async (js: unknown) => {
        const list = (Array.isArray(js) ? js : (js as { jobs?: Job[] }).jobs || []) as (Job & { book_catalog?: string; kind?: string; created_at?: string })[];
        const live = list.find((j) => j.book_catalog === catalog && /trailer/.test(j.kind || "") && (j.status === "running" || j.status === "queued"));
        if (!live || shooting) return;
        const started = Date.now() - 60_000;
        const total = 900;
        setBusy(true);
        setShooting({ stage: live.stage || "producing", detail: live.detail || "", progress: live.progress || 0, started, total });
        try {
          const job = await pollJob(live.id, (j) => {
            setShooting({ stage: j.stage || "producing", detail: j.detail || "", progress: j.progress || 0, started, total });
          }, 4000);
          setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
          setWatching("latest");
          setKey((k) => k + 1);
        } finally { setBusy(false); setShooting(null); }
      }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog, key]);

  const shots = st?.treatment?.shots || [];
  const versions = st?.versions || [];
  const currentTag = tagline ?? (st?.treatment?.end_card_text || "");

  const watchUrl = watching === "latest"
    ? (st?.has_video ? st?.video_url : null)
    : versions.find((v) => v.n === watching)?.url;
  const watchPoster = watching === "latest"
    ? st?.poster_url
    : versions.find((v) => v.n === watching)?.poster_url;

  const rewriteLine = async (key: string, n?: number, field?: string) => {
    setIdeasLoading(key);
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/line/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(key === "tagline" ? { tagline: true } : { n, field: field || "voiceover" }),
      });
      const d = await r.json();
      if (r.ok) setIdeas((m) => ({ ...m, [key]: d.suggestions || [] }));
      else setMsg(d.detail || "Could not fetch suggestions");
    } catch {
      setMsg("Could not fetch suggestions");
    } finally { setIdeasLoading(null); }
  };

  const [inserting, setInserting] = useState<number | null>(null);

  const insertShot = async (after: number) => {
    setBusy(true); setInserting(after); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/shot/insert/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ after }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not start"); setBusy(false); return; }
      const job = await pollJob(d.job_id, () => {});
      setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
      setKey((k) => k + 1);
    } catch { setMsg("Failed"); } finally { setBusy(false); setInserting(null); }
  };

  const deleteShot = async (n: number) => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/shot/delete/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ n }),
      });
      const d = await r.json();
      if (!r.ok) setMsg(d.detail || "Could not remove the scene");
      setKey((k) => k + 1);
    } catch { setMsg("Failed"); } finally { setBusy(false); }
  };

  const saveScript = async (approve: boolean) => {
    setBusy(true); setMsg("");
    try {
      const body = {
        shots: shots.map((s) => ({
          n: s.n,
          voiceover: voEdits[s.n] ?? s.voiceover ?? "",
          prompt: sceneEdits[s.n] ?? s.prompt ?? "",
          sound: soundEdits[s.n] ?? s.sound ?? "",
        })),
        end_card_text: currentTag,
        approved: approve,
      };
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/edit/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Save failed"); return; }
      setMsg(approve ? "Script approved — ready to shoot." : "Saved.");
      setKey((k) => k + 1);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally { setBusy(false); }
  };

  const [refUrl, setRefUrl] = useState("");
  const [sbBusy, setSbBusy] = useState(false);
  const sbFileInput = useRef<HTMLInputElement | null>(null);
  const startOver = async () => {
    if (!window.confirm("Start over? The script, the director's choices and every take are discarded (archived versions stay). SCRPT then creates the trailer again from the book.")) return;
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/reset/${catalog}`, { method: "POST" });
      if (!r.ok) { setMsg("Could not reset"); setBusy(false); return; }
      setWatching("latest"); setKey((k) => k + 1);
    } catch { setMsg("Could not reset"); setBusy(false); return; }
    setBusy(false);
    await makeInOrder();
  };

  // Starting over means the house order, every time: character bible from
  // the cover, storyboard written from that bible, then the shoot. The
  // work-order path (one Seedance take from title + cover + blurb) skips
  // both, so a re-run there only re-rolled the same dice — it could not be
  // better than the last one, only different.
  const makeInOrder = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/auto/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format, rebuild_board: true }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not start"); setBusy(false); return; }
      setShooting({ stage: "bible", detail: "writing the cast sheet from the cover",
                    progress: 0.02, started: Date.now(), total: 1200 });
      setWatching("latest"); setKey((k) => k + 1);
    } catch { setMsg("Could not start"); }
    setBusy(false);
  };

  const makeLikeThis = async () => {
    setBusy(true); setMsg("");
    try {
      // Every trailer is made the same way: character bible, then a
      // storyboard written from that bible, then the shoot. The one-take
      // work order skipped both, so the faces drifted between shots and a
      // re-run could only be different, never better. It is reachable now
      // only by naming a reference trailer to imitate.
      if (!refUrl.trim()) { setBusy(false); await makeInOrder(); return; }
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/like-this/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: refUrl.trim(), mode: quality, format }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not start"); setBusy(false); return; }
      const started = Date.now();
      const total = quality === "full" || quality === "seedance_master" ? 1200 : 600;      // direction + casting + inspected shoot
      const hasRef = !!(refUrl.trim() || st?.reference);
      setShooting({ stage: hasRef ? "reference" : "directing",
                    detail: hasRef ? "studying the reference trailer" : "reading the book",
                    progress: 0.02, started, total });
      const job = await pollJob(d.job_id, (j) => {
        setShooting({ stage: j.stage || "producing", detail: j.detail || "", progress: j.progress || 0, started, total });
      }, 4000);
      setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
      setRefUrl(""); setWatching("latest");
      setKey((k) => k + 1);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally { setBusy(false); setShooting(null); }
  };

  const studyReference = async () => {
    if (!refUrl.trim()) return;
    setBusy(true); setMsg("Studying the reference trailer — rhythm, voice, music, look…");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/reference/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: refUrl.trim() }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not start"); setBusy(false); return; }
      const job = await pollJob(d.job_id, (j) => setMsg(j.detail || "Studying…"));
      setMsg(job.status === "done" ? "Reference learned — rewrite the script to apply its rhythm." : `Failed: ${(job.error || "").split("\n")[0]}`);
      setRefUrl("");
      setKey((k) => k + 1);
    } catch { setMsg("Failed"); } finally { setBusy(false); }
  };

  const uploadStoryboard = async (file: File) => {
    setSbBusy(true); setMsg("Reading the storyboard, panel by panel…");
    try {
      const { job_id } = await scrpt.uploadStoryboard(catalog, file);
      const job = await pollJob(job_id, (j) => setMsg(j.detail || "Reading…"));
      const panels = typeof job.result?.panels === "number" ? job.result.panels : "?";
      setMsg(job.status === "done"
        ? `Storyboard read: ${panels} panels — ready to shoot`
        : `Failed: ${(job.error || "").split("\n")[0]}`);
      setKey((k) => k + 1);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not read that storyboard");
    } finally {
      setSbBusy(false);
      if (sbFileInput.current) sbFileInput.current.value = "";
    }
  };

  const shootStoryboard = async () => {
    setBusy(true); setMsg("");
    try {
      const { job_id } = await scrpt.shootStoryboard(catalog, format);
      const started = Date.now();
      setShooting({ stage: "shooting", detail: "shooting the storyboard, panel by panel",
                    progress: 0.05, started, total: 600 });
      const job = await pollJob(job_id, (j) => {
        setShooting({ stage: j.stage || "producing", detail: j.detail || "", progress: j.progress || 0, started, total: 600 });
      }, 4000);
      setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
      setWatching("latest");
      setKey((k) => k + 1);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally { setBusy(false); setShooting(null); }
  };

  const writeScript = async (useBrief: boolean) => {
    setBusy(true);
    setMsg(useBrief ? "The director develops your idea…" : "The director rewrites from the book…");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/script/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(useBrief ? { brief } : {}),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not start"); return; }
      const job = await pollJob(d.job_id, (j) => setMsg(j.detail || j.stage || "Writing…"));
      setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
      setKey((k) => k + 1);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally { setBusy(false); }
  };

  const finish = async () => {
    setBusy(true); setMsg("Sending the master to the 4K lab…");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/finish/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolution: "4k" }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not start"); setBusy(false); return; }
      const started = Date.now();
      setShooting({ stage: "finishing", detail: "the 4K lab", progress: 0, started, total: 600 });
      const job = await pollJob(d.job_id, (j) => {
        setShooting({ stage: j.stage || "finishing", detail: j.detail || "",
                      progress: j.progress || 0, started, total: 600 });
      }, 5000);
      setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
      setKey((k) => k + 1);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally { setBusy(false); setShooting(null); }
  };

  const produce = async (mode: "full" | "draft" | "voiceover" | "seedance" | "seedance_master", fresh = false) => {
    setBusy(true);
    setMsg(mode === "full" ? "Shooting the master…" : "Shooting the draft cut…");
    try {
      // the shoot IS the sign-off: save the script as it stands and approve it
      await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/edit/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shots: shots.map((s) => ({
            n: s.n,
            voiceover: voEdits[s.n] ?? s.voiceover ?? "",
            prompt: sceneEdits[s.n] ?? s.prompt ?? "",
            sound: soundEdits[s.n] ?? s.sound ?? "",
          })),
          end_card_text: currentTag,
          approved: true,
        }),
      }).catch(() => {});
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/produce/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, format, fresh }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not start"); setBusy(false); return; }
      const started = Date.now();
      const total = mode === "full" ? 480 : 300;
      setShooting({ stage: "starting", detail: "", progress: 0, started, total });
      const job = await pollJob(d.job_id, (j) => {
        setShooting({ stage: j.stage || "producing", detail: j.detail || "",
                      progress: j.progress || 0, started, total });
      }, 4000);
      setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
      setWatching("latest");
      setKey((k) => k + 1);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally { setBusy(false); setShooting(null); }
  };

  if (!st) return null;
  const credits = st.runway?.credits ?? null;

  return (
    <>
      {/* The cinema */}
      <div className="card">
        <div className="flex items-baseline justify-between flex-wrap gap-2">
          <div className="serif-display text-[17px] font-semibold">The cinema</div>
          {versions.length > 0 && (
            <div className="flex items-center gap-1 flex-wrap">
              {versions.map((v) => (
                <button key={v.n} onClick={() => setWatching(v.n)}
                        title={`${v.created || ""} · ${v.quality || v.mode || ""} · ${v.format || "wide"} · ${v.seconds || "?"}s`}
                        className={`px-2.5 py-1 rounded-full text-[11px] uppercase tracking-[0.08em] ${
                          watching === v.n ? "text-text-primary" : "text-text-faint hover:text-text-secondary"}`}
                        style={watching === v.n ? { background: "var(--surface)", boxShadow: "var(--shadow-card)" } : {}}>
                  v{v.n}
                </button>
              ))}
              <button onClick={() => setWatching("latest")}
                      className={`px-2.5 py-1 rounded-full text-[11px] uppercase tracking-[0.08em] ${
                        watching === "latest" ? "text-text-primary" : "text-text-faint hover:text-text-secondary"}`}
                      style={watching === "latest" ? { background: "var(--surface)", boxShadow: "var(--shadow-card)" } : {}}>
                Latest
              </button>
            </div>
          )}
        </div>
        {!watchUrl && !shooting && (
          <div className="mt-4 flex items-center gap-3 flex-wrap">
            <button disabled={busy} onClick={makeLikeThis}
                    className="flex items-center justify-center gap-3 rounded-[10px]"
                    style={{ background: "linear-gradient(180deg, #17181B 0%, #0E0F11 100%)", border: "1px solid #33353A",
                             padding: "14px 28px", color: "#E8E6E1", fontSize: 13, fontWeight: 600, letterSpacing: "0.14em",
                             textTransform: "uppercase", cursor: busy ? "default" : "pointer" }}>
              <span aria-hidden style={{ width: 14, height: 14, borderRadius: "50%",
                    background: "radial-gradient(circle at 35% 35%, #F1584C, #A81E17 70%)",
                    border: "2px solid #050505", outline: "1px solid #3D3F44", boxShadow: "0 0 8px 1px rgba(224,62,54,.45)" }} />
              Create the trailer
            </button>
            <span className="text-[12px] text-text-tertiary">
              {quality.startsWith("seedance")
                ? `The work order: the title, the front cover as the reference, the back-cover text, and the end screen — one 30-second take on Seedance 2.5 (${quality === "seedance_master" ? "1080p master" : "720p draft"}). No art direction from SCRPT; the model directs.`
                : `The director's desk on Veo 3.1: SCRPT writes a cut — clips, inserts, title cards — shoots through inspection, reviews it, and premieres the ${quality === "full" ? "master" : "draft"}.`}
            </span>
            {msg && <div className="w-full text-[12px]" style={{ color: "var(--status-amber)" }}>{msg}</div>}
          </div>
        )}
        <div className="mt-4 rounded-[10px] px-4 pt-5 pb-6"
             style={{ background: "linear-gradient(180deg, #05060a 0%, #0b0d14 70%, #05060a 100%)" }}>
          <div className="mx-auto w-full">
            <div className="rounded-[4px] overflow-hidden"
                 style={{ boxShadow: "0 0 60px rgba(120,140,190,0.18), 0 0 6px rgba(0,0,0,0.9)" }}>
              {shooting ? (
                <ShootingScreen s={shooting} />
              ) : watchUrl ? (
                <video key={watchUrl + key} controls
                       poster={watchPoster ? `${scrpt.engineUrl}${watchPoster}` : undefined}
                       className="w-full block bg-black" src={`${scrpt.engineUrl}${watchUrl}`} />
              ) : (
                <div className="w-full flex items-center justify-center bg-black" style={{ aspectRatio: "16/9" }}>
                  <span className="text-[12px] uppercase tracking-[0.2em]" style={{ color: "#3c4254" }}>
                    No picture on the reel yet
                  </span>
                </div>
              )}
            </div>
            <div className="flex items-center justify-center gap-4 mt-5 text-[11px] uppercase tracking-[0.25em]" style={{ color: "#3c4254" }}>
              <span>{shooting ? "Now shooting" : watching === "latest" ? "Latest cut" : `Version ${watching}`}</span>
              {watchUrl && !shooting && (
                <button type="button" className="tracking-[0.18em] uppercase"
                        style={{ color: "#8a8f9c", background: "none", border: "1px solid #2a2e3a", padding: "4px 10px", borderRadius: 6, cursor: "pointer", fontSize: 11 }}
                        title="Save this version to your Downloads"
                        onClick={async (e) => {
                          e.preventDefault();
                          const btn = e.currentTarget; btn.textContent = "Saving…";
                          try {
                            const res = await fetch(`${scrpt.engineUrl}${watchUrl.split("?")[0]}`);
                            const blob = await res.blob();
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url; a.download = `${title || catalog} - trailer${watching === "latest" ? "" : ` v${watching}`}.mp4`;
                            document.body.appendChild(a); a.click(); a.remove();
                            setTimeout(() => URL.revokeObjectURL(url), 10000);
                            btn.textContent = "Saved";
                          } catch { btn.textContent = "Could not save"; }
                          setTimeout(() => { btn.textContent = "Download"; }, 2500);
                        }}>Download</button>
              )}
            </div>
          </div>
        </div>
        {(watchUrl || st.treatment) && !shooting && (
          <div className="mt-4 flex items-center gap-3 flex-wrap">
            <button className="btn-ghost text-[12px]" disabled={busy} onClick={startOver}
                    title="Discard the script, the director's choices and all takes, then create the trailer again from the book">
              Start over — new trailer
            </button>
            <span className="text-[11px] text-text-faint">Uses the quality selected below ({quality.startsWith("seedance") ? "Seedance" : "Veo"} {quality.endsWith("master") || quality === "full" ? "master" : "draft"}). Archived versions stay in the cinema.</span>
          </div>
        )}
        {watchUrl && !shooting && (st.production as { quality?: string } | null)?.quality === "draft" && (
          <div className="mt-4 flex items-center gap-3 flex-wrap">
            <button disabled={busy} onClick={async () => {
                      const prod = st.production as { provider?: string; mode?: string; seconds?: number } | null;
                      if (prod?.mode === "workorder") {
                        const est = Math.round(((prod.seconds || 60) - 8) * 62);
                        if (!window.confirm(`Finish this exact cut in 4K? Runway's upscaler bills per second — about ${est} credits for this film. Nothing else changes.`)) return;
                        setBusy(true); setMsg("");
                        try {
                          const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/workorder/${catalog}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ quality: "4k", format }) });
                          const d = await r.json();
                          if (!r.ok) { setMsg(d.detail || "Could not start"); setBusy(false); return; }
                          const started = Date.now();
                          setShooting({ stage: "4k", detail: "upscaling the footage", progress: 0.05, started, total: 900 });
                          const job = await pollJob(d.job_id, (j) => setShooting({ stage: j.stage || "4k", detail: j.detail || "", progress: j.progress || 0, started, total: 900 }), 4000);
                          setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
                          setWatching("latest"); setKey((k) => k + 1);
                        } finally { setBusy(false); setShooting(null); }
                        return;
                      }
                      produce(prod?.provider === "seedance" ? "seedance_master" : "full");
                    }}
                    className="flex items-center justify-center gap-3 rounded-[10px]"
                    style={{ background: "linear-gradient(180deg, #17181B 0%, #0E0F11 100%)", border: "1px solid #33353A",
                             padding: "12px 24px", color: "#E8E6E1", fontSize: 12.5, fontWeight: 600, letterSpacing: "0.14em",
                             textTransform: "uppercase", cursor: busy ? "default" : "pointer" }}>
              <span aria-hidden style={{ width: 12, height: 12, borderRadius: "50%",
                    background: "radial-gradient(circle at 35% 35%, #F1584C, #A81E17 70%)",
                    border: "2px solid #050505", outline: "1px solid #3D3F44" }} />
              {(st.production as { mode?: string } | null)?.mode === "workorder" ? "Finish this cut in 4K" : `Master this cut${st.estimates?.full ? ` (~${st.estimates.full} cr)` : ""}`}
            </button>
            <span className="text-[12px] text-text-tertiary">
              Same script, same edit — shot again on full veo3.1 at 1080p with native sound. Only approve a draft you would ship.
            </span>
          </div>
        )}
        {(quality.startsWith("seedance") || (st.production as { mode?: string } | null)?.mode === "workorder") ? (
          st.workorder_prompt ? (
            <div className="mt-4 text-[12px]">
              <span className="text-text-faint uppercase tracking-[0.1em] text-[10px] block">The work order — everything Runway receives, with the front cover attached</span>
              <pre className="mt-1 whitespace-pre-wrap font-sans text-text-secondary leading-relaxed" style={{ fontFamily: "inherit" }}>{st.workorder_prompt}</pre>
            </div>
          ) : null
        ) : st.review && (st.review.score || st.review.notes?.length) ? (
          <div className="mt-4 text-[12px]">
            <span className="text-text-faint uppercase tracking-[0.1em] text-[10px] block">The director&apos;s review of the cut</span>
            {st.review.score ? <span className="font-semibold">{st.review.score}/10</span> : null}
            {st.review.reads_as_trailer === false ? <span style={{ color: "var(--status-amber)" }}> · does not yet read as a trailer</span> : null}
            {(st.review.notes || []).length > 0 && (
              <ul className="list-disc pl-4 mt-1 text-text-secondary leading-snug">
                {(st.review.notes || []).map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            )}
          </div>
        ) : null}
        {st.direction && !(quality.startsWith("seedance") || (st.production as { mode?: string } | null)?.mode === "workorder") && (
          <div className="mt-4 grid gap-x-6 gap-y-2 text-[12px]" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
            <div className="col-span-full serif-display text-[15px] font-semibold">The director&apos;s choices</div>
            {st.direction.angle && <div><span className="text-text-faint uppercase tracking-[0.1em] text-[10px] block">Angle</span>{st.direction.angle}</div>}
            {st.voice?.name && <div><span className="text-text-faint uppercase tracking-[0.1em] text-[10px] block">Narrator</span>{st.voice.name}{st.voice.auto === false ? " (your cast)" : ""}{st.voice.why ? <span className="text-text-faint"> — {st.voice.why}</span> : null}</div>}
            {st.direction.music && <div><span className="text-text-faint uppercase tracking-[0.1em] text-[10px] block">Score</span>{st.direction.music}</div>}
            {st.direction.look && <div><span className="text-text-faint uppercase tracking-[0.1em] text-[10px] block">Look</span>{st.direction.look}</div>}
            {st.direction.pacing && <div><span className="text-text-faint uppercase tracking-[0.1em] text-[10px] block">Rhythm</span>{st.direction.seconds}s · {st.direction.shots} shots — {st.direction.pacing}</div>}
          </div>
        )}
        {st.production && (
          <div className="text-[12px] text-text-tertiary mt-3">
            Last production: {(st.production as { quality?: string }).quality === "draft" ? "draft"
              : st.production.mode === "full" ? "master" : st.production.mode} ·{" "}
            {st.production.seconds}s · {st.production.credits_used} credits
            {credits !== null ? ` · ${credits} credits left` : ""}
          </div>
        )}
      </div>

      <div className="text-[11px] uppercase tracking-[0.14em] text-text-faint self-start"
           style={{ padding: "4px 0" }}>
        The director&apos;s desk
      </div>
      <div style={{ display: desk ? "contents" : "none" }}>
      {/* The screenplay */}
      <div className="card">
        <div className="flex items-baseline justify-between flex-wrap gap-2">
          <div className="serif-display text-[17px] font-semibold">The trailer script</div>
          {st.treatment && (
            <span className="text-[12px] font-semibold uppercase tracking-[0.1em]"
                  style={{ color: st.approved ? "var(--status-green)" : "var(--status-amber)" }}>
              {st.approved ? "Approved" : "Awaiting approval"}
            </span>
          )}
        </div>
        <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
          Nothing is shot before the words are right. Edit the voice-over and
          the tagline here, approve the script, and only then does the camera
          roll. Only what you change is re-recorded or re-shot — approved
          takes are kept.
        </p>

        <div className="mt-3 flex items-center gap-2">
          <input value={refUrl} onChange={(e) => setRefUrl(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter") studyReference(); }}
                 placeholder="Reference trailer — paste a YouTube link to match its rhythm and feel"
                 className="flex-1 rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[12.5px]" />
          <button className="btn-ghost text-[12px] shrink-0" disabled={busy || !refUrl.trim()} onClick={studyReference}>
            Study reference
          </button>
          <button className="btn-brass text-[12px] shrink-0" disabled={busy}
                  title={refUrl.trim() || st.reference
                    ? "Analyse the reference, write this book's script in its rhythm, and shoot it"
                    : "Write the script from the book and shoot it — one click"}
                  onClick={makeLikeThis}>
            {refUrl.trim() || st.reference ? "Make a trailer like this" : "Create the trailer"}
          </button>
        </div>
        {st.reference?.title && (
          <div className="text-[11px] text-text-faint mt-1.5">
            Reference: <span className="text-text-secondary">{st.reference.title}</span>
            {st.reference.shots ? ` · ${st.reference.shots} shots, avg ${st.reference.avg_shot_seconds}s` : ""}
            {st.reference.analysis?.lessons?.[0] ? ` · “${st.reference.analysis.lessons[0]}”` : ""}
          </div>
        )}

        <div className="mt-3 flex items-center gap-2">
          <input ref={sbFileInput} type="file" accept="image/*" className="hidden"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadStoryboard(f); }} />
          <button className="btn-ghost text-[12px] shrink-0" disabled={busy || sbBusy}
                  onClick={() => sbFileInput.current?.click()}>
            {sbBusy ? "Reading storyboard…" : "Upload storyboard"}
          </button>
          <span className="text-[11px] text-text-faint flex-1">
            A panel-by-panel storyboard image — SCRPT reads every panel and shoots it, one clip per panel.
          </span>
          {st.storyboard_pending && (
            <button className="btn-brass text-[12px] shrink-0" disabled={busy}
                    title="Shoot the uploaded storyboard: one clip per panel, narrated, scored, closed on the real cover"
                    onClick={shootStoryboard}>
              Shoot this storyboard
            </button>
          )}
        </div>
        <CastAndBoard st={st} catalog={catalog} onChanged={() => setKey((k) => k + 1)} />
        {st.storyboard_pending && (
          <div className="text-[11px] text-text-faint mt-1.5">
            Storyboard ready: <span className="text-text-secondary">{st.storyboard_pending.panels} panels</span>
            {st.storyboard_pending.source ? ` · ${st.storyboard_pending.source}` : ""}
          </div>
        )}
        {!st.storyboard_pending && st.storyboard && (
          <div className="text-[11px] text-text-faint mt-1.5">
            Last cut from a storyboard: <span className="text-text-secondary">{st.storyboard.count} panels</span>
          </div>
        )}

        <div className="mt-3">
          <textarea value={brief} onChange={(e) => setBrief(e.target.value)}
                    placeholder="Describe the trailer you want — mood, images, what it must say. The director follows this."
                    className="w-full rounded-[8px] border border-border-subtle bg-transparent p-3 text-[13px] leading-relaxed"
                    rows={2} />
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <button className="btn-brass text-[12px]" disabled={busy || !brief.trim()}
                    title={!brief.trim() ? "Describe the trailer you want first" : undefined}
                    onClick={() => writeScript(true)}>
              Extend idea
            </button>
            <button className="btn-ghost text-[12px]" disabled={busy} onClick={() => writeScript(false)}>
              {st.treatment ? "Rewrite full script" : "Write script"}
            </button>
            <span className="text-[11px] text-text-faint">
              Both build strictly on the book&apos;s plot.
            </span>
          </div>
        </div>

        {st.treatment?.concept && (
          <div className="text-[12px] text-text-tertiary mt-3 italic">“{st.treatment.concept}”</div>
        )}

        {shots.length > 0 && (
          <div className="mt-4 space-y-0">
            <div className="flex justify-center">
              <button className="btn-ghost text-[11px]" disabled={busy} onClick={() => insertShot(0)}>
                {inserting === 0 ? "Writing the new scene…" : "+ Insert scene"}
              </button>
            </div>
            {inserting === 0 && (
              <div className="my-2 rounded-[8px] border border-dashed px-4 py-3 text-[12px]"
                   style={{ borderColor: "var(--text-tertiary)", color: "var(--text-secondary)" }}>
                The director writes the new scene from the book — it appears here in a moment…
              </div>
            )}
            {shots.map((sh, i) => (
              <div key={sh.n} className="py-3"
                   style={i > 0 ? { borderTop: "1px solid var(--border-subtle)" } : {}}>
              <div className="flex items-start gap-4">
                <div className="text-[11px] text-text-faint w-5 pt-[7px] text-right shrink-0">{sh.n}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] uppercase tracking-[0.12em] text-text-faint">Scene — what the camera sees</div>
                  <textarea value={sceneEdits[sh.n] ?? sh.prompt ?? ""}
                            onChange={(e) => { setSceneEdits((m) => ({ ...m, [sh.n]: e.target.value })); setDirty(true); }}
                            rows={3}
                            className="mt-1 w-full rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[12.5px] leading-relaxed text-text-secondary" />
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    <button className="btn-ghost text-[11px]" disabled={ideasLoading !== null}
                            onClick={() => rewriteLine(`scene-${sh.n}`, sh.n, "scene")}>
                      {ideasLoading === `scene-${sh.n}` ? "Writing…" : "Rewrite scene"}
                    </button>
                  </div>
                  {(ideas[`scene-${sh.n}`] || []).map((opt, oi) => (
                    <button key={oi}
                            className="block text-left text-[12px] mt-1.5 w-full px-3 py-2 rounded-[6px] border border-border-subtle hover:border-text-tertiary transition-colors leading-relaxed"
                            onClick={() => {
                              setSceneEdits((m) => ({ ...m, [sh.n]: opt }));
                              setDirty(true);
                              setIdeas((m) => ({ ...m, [`scene-${sh.n}`]: [] }));
                            }}>
                      {opt}
                    </button>
                  ))}
                  <div className="text-[10px] uppercase tracking-[0.12em] text-text-faint mt-3">Voice-over</div>
                  <input value={voEdits[sh.n] ?? sh.voiceover ?? ""}
                         onChange={(e) => { setVoEdits((m) => ({ ...m, [sh.n]: e.target.value })); setDirty(true); }}
                         placeholder="(no voice-over on this shot)"
                         className="mt-1 w-full rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[13px] font-medium" />
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <button className="btn-ghost text-[11px]" disabled={ideasLoading !== null}
                            onClick={() => rewriteLine(`shot-${sh.n}`, sh.n)}>
                      {ideasLoading === `shot-${sh.n}` ? "Writing…" : "Rewrite"}
                    </button>
                    {(ideas[`shot-${sh.n}`] || []).map((opt, oi) => (
                      <button key={oi}
                              className="text-left text-[12px] px-2.5 py-1 rounded-[6px] border border-border-subtle hover:border-text-tertiary transition-colors"
                              onClick={() => {
                                setVoEdits((m) => ({ ...m, [sh.n]: opt }));
                                setDirty(true);
                                setIdeas((m) => ({ ...m, [`shot-${sh.n}`]: [] }));
                              }}>
                        {opt || "(silent)"}
                      </button>
                    ))}
                  </div>
                  <div className="text-[10px] uppercase tracking-[0.12em] text-text-faint mt-3">Sound</div>
                  <div className="flex items-center gap-2 mt-1">
                    <input value={soundEdits[sh.n] ?? sh.sound ?? ""}
                           onChange={(e) => { setSoundEdits((m) => ({ ...m, [sh.n]: e.target.value })); setDirty(true); }}
                           placeholder="(no sound cue)"
                           className="flex-1 rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[12px] text-text-secondary" />
                    <button className="btn-ghost text-[11px] shrink-0" disabled={ideasLoading !== null}
                            onClick={() => rewriteLine(`sound-${sh.n}`, sh.n, "sound")}>
                      {ideasLoading === `sound-${sh.n}` ? "…" : "Rewrite"}
                    </button>
                  </div>
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    {(ideas[`sound-${sh.n}`] || []).map((opt, oi) => (
                      <button key={oi}
                              className="text-left text-[12px] px-2.5 py-1 rounded-[6px] border border-border-subtle hover:border-text-tertiary transition-colors"
                              onClick={() => {
                                setSoundEdits((m) => ({ ...m, [sh.n]: opt }));
                                setDirty(true);
                                setIdeas((m) => ({ ...m, [`sound-${sh.n}`]: [] }));
                              }}>
                        {opt}
                      </button>
                    ))}
                  </div>
                </div>
                <button className="btn-ghost text-[11px] shrink-0" disabled={busy || shots.length <= 2}
                        title={shots.length <= 2 ? "A trailer needs at least two scenes" : "Cut this scene"}
                        onClick={() => deleteShot(sh.n)}>
                  Remove
                </button>
              </div>
              <div className="flex justify-center mt-2">
                <button className="btn-ghost text-[11px]" disabled={busy} onClick={() => insertShot(sh.n)}>
                  {inserting === sh.n ? "Writing the new scene…" : "+ Insert scene"}
                </button>
              </div>
            {inserting === sh.n && (
              <div className="my-2 rounded-[8px] border border-dashed px-4 py-3 text-[12px]"
                   style={{ borderColor: "var(--text-tertiary)", color: "var(--text-secondary)" }}>
                The director writes the new scene from the book — it appears here in a moment…
              </div>
            )}
              </div>
            ))}
            <div className="pt-3" style={{ borderTop: "1px solid var(--border-subtle)" }}>
              <div className="text-[11px] uppercase tracking-[0.1em] text-text-faint">Tagline — read over the final cover card</div>
              <input value={currentTag}
                     onChange={(e) => { setTagline(e.target.value); setDirty(true); }}
                     className="mt-1.5 w-full rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[13px] font-medium" />
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                <button className="btn-ghost text-[11px]" disabled={ideasLoading !== null}
                        onClick={() => rewriteLine("tagline")}>
                  {ideasLoading === "tagline" ? "Writing…" : "Rewrite"}
                </button>
                {(ideas["tagline"] || []).map((opt, oi) => (
                  <button key={oi}
                          className="text-left text-[12px] px-2.5 py-1 rounded-[6px] border border-border-subtle hover:border-text-tertiary transition-colors"
                          onClick={() => {
                            setTagline(opt); setDirty(true);
                            setIdeas((m) => ({ ...m, tagline: [] }));
                          }}>
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {st.treatment && dirty && (
          <div className="flex items-center gap-3 mt-5 pt-4 flex-wrap" style={{ borderTop: "1px solid var(--border-subtle)" }}>
            <button className="btn-ghost text-[12px]" disabled={busy} onClick={() => saveScript(false)}>
              Save script
            </button>
            <span className="text-[11px] text-text-faint">
              Unsaved edits — they are also saved automatically when you shoot.
            </span>
          </div>
        )}
        {msg && <div className="text-[12px] mt-2" style={{ color: "var(--status-amber)" }}>{msg}</div>}
      </div>

      <TrailerVoiceCard catalog={catalog} onCast={() => setKey((k) => k + 1)} />

      <TrailerScoreCard catalog={catalog} />

      {/* The shoot */}
      <div className="card">
        <div className="serif-display text-[17px] font-semibold">The shoot</div>
        <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
          Full production shoots with native sound, sound design and score;
          the voice-over cut carries the picture on the trailer voice alone.
          Every finished cut is archived and watchable in the cinema above.
        </p>
        <div className="flex items-center gap-1.5 mt-3 flex-wrap">
          {TRAILER_FORMATS.map((f) => (
            <button key={f.key} onClick={() => setFormat(f.key)} title={f.hint}
                    className={`px-3 py-1 rounded-full text-[11px] uppercase tracking-[0.08em] ${
                      format === f.key ? "text-text-primary" : "text-text-faint hover:text-text-secondary"}`}
                    style={format === f.key ? { background: "var(--surface)", boxShadow: "var(--shadow-card)" } : {}}>
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5 mt-3 flex-wrap">
          {([["seedance", "Seedance 2.5 draft 720p"],
             ["seedance_master", "Seedance 2.5 master 1080p"],
             ["draft", `Veo draft (~${st.estimates?.draft ?? "?"} cr)`],
             ["full", `Veo master 1080p (~${st.estimates?.full ?? "?"} cr)`]] as const).map(([q, label]) => (
            <button key={q} onClick={() => setQuality(q)}
                    className={`px-3 py-1 rounded-full text-[11px] uppercase tracking-[0.08em] ${
                      quality === q ? "text-text-primary" : "text-text-faint hover:text-text-secondary"}`}
                    style={quality === q ? { background: "var(--surface)", boxShadow: "var(--shadow-card)" } : {}}>
              {label}
            </button>
          ))}
        </div>

        <button disabled={busy} onClick={() => produce(quality)}
                className="w-full mt-4 flex items-center justify-center gap-3 rounded-[10px] transition-colors"
                style={{
                  background: "linear-gradient(180deg, #17181B 0%, #0E0F11 100%)",
                  border: "1px solid #33353A",
                  padding: "16px 20px",
                  color: busy ? "#8A8F98" : "#E8E6E1",
                  fontSize: 13, fontWeight: 600,
                  letterSpacing: "0.14em", textTransform: "uppercase",
                  cursor: busy ? "default" : "pointer",
                }}>
          <span aria-hidden style={{
            width: 15, height: 15, borderRadius: "50%", flexShrink: 0,
            background: busy
              ? "radial-gradient(circle at 35% 35%, #FF6B5E, #C22B22 70%)"
              : "radial-gradient(circle at 35% 35%, #F1584C, #A81E17 70%)",
            border: "2px solid #050505",
            outline: "1px solid #3D3F44",
            animation: busy ? "recPulse 1.1s ease-in-out infinite" : "none",
            boxShadow: busy ? undefined : "0 0 8px 1px rgba(224, 62, 54, 0.45)",
          }} />
          {busy ? "Recording…" : "Shoot the trailer"}
        </button>
        {shooting && <ShootProgressBar s={shooting} />}
        {!shooting && (
          <div className="flex justify-center mt-2">
            <button className="btn-ghost text-[11px]" disabled={busy}
                    title="Same script, everything rolled again — new footage, new recordings. Full cost; a pinned score is kept."
                    onClick={() => produce(quality, true)}>
              Re-roll everything — fresh takes
            </button>
          </div>
        )}
        <p className="text-[11px] text-text-faint mt-2 text-center leading-relaxed">
          Shooting is the sign-off — the script above is saved and locked as
          approved when the camera rolls. Only changed scenes and lines are
          re-made; the rest comes from the archive.
        </p>
        {(st.production && st.production.mode &&
          (st.production as { quality?: string }).quality !== "draft") && (
          <div className="flex justify-center mt-2">
            <button className="btn-ghost text-[12px]" disabled={busy} onClick={finish}
                    title="Faithful AI sharpening of the shot master — best for YouTube and TV">
              Finish in 4K{st.estimates?.finish_4k ? ` (~${st.estimates.finish_4k} cr)` : ""}
            </button>
          </div>
        )}
      </div>
      </div>
    </>
  );
}


// ── Hear the opening ─────────────────────────────────────────────
type OpeningPreview = {
  live?: { voice?: string; total?: number; parts?: string[]; done?: boolean; chapter_title?: string; urls?: string[] } | null;
  preview?: { voice?: string; words?: number; chapter_title?: string } | null;
  chapter1?: { voice?: string; words?: number; seconds?: number; chapter_title?: string; parts?: number } | null;
  has_audio?: boolean;
  audio_url?: string | null;
  chapter_url?: string | null;
  voice?: string;
  voice_id?: string;
  voice_preview_url?: string | null;
  chapter_chars?: number | null;
  chapter_minutes?: number | null;
};

/** Plays the chapter while it is still being recorded: parts arrive in the
 *  live manifest as they are mastered; the player chains them gaplessly. */
function LivePartsPlayer({ urls, total, done }: { urls: string[]; total: number; done: boolean }) {
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const aRef = useRef<HTMLAudioElement | null>(null);
  const urlsRef = useRef(urls);
  urlsRef.current = urls;
  // a part finished: move on, or wait for the next one to be mastered
  const onEnded = () => {
    const next = idx + 1;
    if (next < urlsRef.current.length) { setIdx(next); setWaiting(false); }
    else if (!done) { setWaiting(true); }
    else { setPlaying(false); }
  };
  useEffect(() => {
    if (waiting && idx + 1 < urls.length) { setIdx(idx + 1); setWaiting(false); }
  }, [urls, waiting, idx]);
  useEffect(() => {
    const a = aRef.current;
    if (!a || !urls[idx]) return;
    a.src = `${scrpt.engineUrl}${urls[idx]}`;
    if (playing) { a.play().catch(() => {}); }
    // warm the next part
    if (urls[idx + 1]) { const pre = new Audio(`${scrpt.engineUrl}${urls[idx + 1]}`); pre.preload = "auto"; }
  }, [idx, urls, playing]);
  return (
    <div className="mt-1.5 flex items-center gap-3">
      <button className="btn-brass text-[12px]" onClick={() => {
        const a = aRef.current; if (!a) return;
        if (playing) { a.pause(); setPlaying(false); } else { setPlaying(true); a.play().catch(() => {}); }
      }}>{playing ? "Pause" : idx === 0 ? "Listen now" : "Resume"}</button>
      <audio ref={aRef} onEnded={onEnded} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} controls className="h-9 flex-1" />
      <span className="text-[11px] text-text-faint whitespace-nowrap">
        part {Math.min(idx + 1, Math.max(1, urls.length))} of {total}{waiting ? " — next part is being mastered…" : done ? "" : ` · ${urls.length} ready`}
      </span>
    </div>
  );
}


function OpeningPreviewCard({ catalog, voiceKey }: { catalog: string; voiceKey?: string }) {
  const [st, setSt] = useState<OpeningPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [key, setKey] = useState(0);
  const [rec, setRec] = useState<{ stage: string; detail: string; progress: number; started: number; total: number } | null>(null);

  useEffect(() => {
    fetch(`${scrpt.engineUrl}/api/scrpt/audiobook/preview/${catalog}`)
      .then((r) => (r.ok ? r.json() : null)).then(setSt).catch(() => {});
  }, [catalog, key, voiceKey]);

  const record = async (scope: "chapter" | "opening") => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/audiobook/preview/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not start"); setBusy(false); return; }
      const started = Date.now();
      // a chapter records at roughly 6-8x real time on ElevenLabs
      const total = scope === "chapter" ? Math.max(60, ((st?.chapter_minutes || 15) * 60) / 7) : 40;
      setRec({ stage: "recording", detail: "", progress: 0, started, total });
      let tick = 0;
      const job = await pollJob(d.job_id, (j) => {
        setRec({ stage: j.stage || "recording", detail: j.detail || "", progress: j.progress || 0, started, total });
        if (scope === "chapter" && tick++ % 2 === 0) {
          fetch(`${scrpt.engineUrl}/api/scrpt/audiobook/preview/${catalog}`).then((r) => r.json())
            .then((s) => setSt((cur) => cur ? { ...cur, live: s.live } : s)).catch(() => {});
        }
      }, 3000);
      setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
      setKey((k) => k + 1);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally { setBusy(false); setRec(null); }
  };

  if (!st) return null;
  const voiceShort = (st.voice || "").split(" - ")[0].split(" – ")[0];
  const staleVoice = (file?: { voice?: string } | null) => file?.voice && st.voice && file.voice !== st.voice;

  return (
    <div className="card">
      <div className="serif-display text-[17px] font-semibold">Hear the opening</div>
      <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
        Chapter one read aloud by the cast narrator. Two checks in one: what
        the audiobook will sound like, and whether the opening holds when you
        hear it — weak sentences hide on the page and stand up in a reading.
      </p>

      {/* the cast voice, front and centre */}
      <div className="mt-4 rounded-[10px] px-4 py-3 flex items-center gap-4 flex-wrap"
           style={{ background: "var(--surface)", boxShadow: "var(--shadow-card)" }}>
        <div className="min-w-[160px]">
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-faint">On the mic</div>
          <div className="serif-display text-[20px] font-semibold">{voiceShort || "House narrator"}</div>
          {st.voice && st.voice !== voiceShort && <div className="text-[11px] text-text-faint">{st.voice}</div>}
        </div>
        {st.voice_preview_url ? (
          <audio key={st.voice_id} controls preload="none" src={st.voice_preview_url} className="h-8 flex-1" style={{ maxWidth: 360 }} />
        ) : (
          <span className="text-[11px] text-text-faint">Cast a voice on the casting board above — it appears here immediately.</span>
        )}
      </div>

      {/* live: listen while the chapter is still being read */}
      {rec && st.live && (st.live.urls || []).length > 0 && !st.live.done && (
        <div className="mt-4">
          <div className="flex items-baseline justify-between">
            <div className="text-[11px] uppercase tracking-[0.1em]" style={{ color: "var(--status-amber)" }}>Chapter one — recording, listen as it lands</div>
            <div className="text-[11px] text-text-faint">read by {st.live.voice || st.voice}</div>
          </div>
          <LivePartsPlayer urls={st.live.urls || []} total={st.live.total || 0} done={!!st.live.done} />
        </div>
      )}

      {/* recordings */}
      {st.chapter_url && !(rec && st.live && !st.live.done) && (
        <div className="mt-4">
          <div className="flex items-baseline justify-between">
            <div className="text-[11px] uppercase tracking-[0.1em] text-text-faint">Chapter one — full</div>
            <div className="text-[11px] text-text-faint">
              {st.chapter1?.seconds ? `${Math.floor(st.chapter1.seconds / 60)}:${String(st.chapter1.seconds % 60).padStart(2, "0")} · ` : ""}
              read by {st.chapter1?.voice || "—"}{staleVoice(st.chapter1) ? " · recorded with the previous voice" : ""}
            </div>
          </div>
          <audio key={st.chapter_url} controls preload="none" src={`${scrpt.engineUrl}${st.chapter_url}`} className="mt-1.5 w-full h-9" />
        </div>
      )}

      {/* progress */}
      {rec && (
        <div className="mt-4">
          <div style={{ width: "100%", height: 3, background: "var(--border-subtle)", borderRadius: 2 }}>
            <div style={{ width: `${Math.max(2, Math.min(1, rec.progress) * 100)}%`, height: "100%", background: "#C9A96A", borderRadius: 2, transition: "width 1s linear" }} />
          </div>
          <div className="flex items-baseline justify-between mt-1.5 text-[11px]">
            <span className="uppercase tracking-[0.12em]" style={{ color: "var(--status-amber)" }}>{rec.detail || rec.stage}</span>
            <span className="text-text-faint">{shootEta(rec).label}</span>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 mt-4 flex-wrap">
        <button className="btn-brass text-[12px]" disabled={busy} onClick={() => record("chapter")}>
          {st.chapter_url ? "Re-record chapter one" : "Record chapter one"}
          {st.chapter_minutes ? ` (~${Math.round(st.chapter_minutes)} min of audio)` : ""}
        </button>
        <span className="text-[11px] text-text-faint">Billed to your ElevenLabs plan by characters — not Runway credits.</span>
      </div>
      {msg && <div className="text-[12px] mt-2" style={{ color: "var(--status-amber)" }}>{msg}</div>}
    </div>
  );
}

// ── Full Movie (framework — the studio to come) ──────────────────
// The plan: adapt the finished book into a movie-grade screenplay, an
// episodic TV breakdown, or an animated children's film — then have the
// generation stack shoot it, scene by scene, in the cover's universe.
// This tab is the front door built ahead of the machinery. The screening
// room already works: it plays whatever film the house has (today, the
// trailer) in a cinema or TV frame.

const MOVIE_FORMATS = [
  { key: "feature", name: "Feature film",
    line: "One book, one film. A three-act screenplay adapted from the manuscript, shot in the cover's universe." },
  { key: "series", name: "TV series",
    line: "The book broken into episodes — or a whole series arc across a book series. One season per Larkspur, one show per world." },
  { key: "cartoon", name: "Animated — children's",
    line: "Stories written for young readers become cartoons: illustrated-book look, gentle pacing, read-along narration." },
];

const MOVIE_PIPELINE = [
  { step: "Screenplay", line: "The book adapted into a real script — screenplay grammar learned from produced films, not prose reformatted." },
  { step: "Casting & look", line: "Characters locked to one face, one wardrobe, one world — the same continuity discipline the trailer already uses." },
  { step: "Storyboard", line: "Every scene broken into shots with camera, light and sound, budgeted before a single frame is generated." },
  { step: "The shoot", line: "The trailer desk's mechanics at feature scale: films are assembled from 4\u20138 second AI clips with native sound, shot in sequence and stitched \u2014 a 20-minute episode is ~200 clips; content-addressed takes mean edited scenes reshoot alone." },
  { step: "Post", line: "Score, sound design, titles, and the final mix — mastered for the screening room." },
  { step: "The premiere", line: "Watch it inside SCRPT on a cinema screen or a TV set, or cast it straight to the television." },
];

function FullMovieTab({ book }: { book: ScrptBook }) {
  const [screen, setScreen] = useState<"cinema" | "tv">("cinema");
  const [format, setFormat] = useState("feature");
  const catalog = book.catalog_number;
  type MoviePanel = { n?: string | number; title?: string; dur?: number; vo?: string;
                      frame_url?: string | null; characters?: string[] };
  const [mv, setMv] = useState<{ panels: MoviePanel[]; count: number; minutes?: number; music?: string;
                                 film_url?: string | null; film_poster_url?: string | null;
                                 voice_cast?: Record<string, { id: string; name: string }> } | null>(null);
  const [castFor, setCastFor] = useState<string | null>(null);
  const [castQ, setCastQ] = useState("");
  const [castGender, setCastGender] = useState("");
  const [castAccent, setCastAccent] = useState("");
  const [castSearched, setCastSearched] = useState(false);
  const [castResults, setCastResults] = useState<{ id: string; name: string; description?: string; preview_url?: string }[]>([]);
  const [castBusy, setCastBusy] = useState(false);
  const searchCastVoice = async () => {
    setCastBusy(true); setCastResults([]); setCastSearched(false);
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/voice-library/search?q=${encodeURIComponent(castQ)}&gender=${castGender}&accent=${castAccent}`);
      const d = await r.json();
      if (r.ok) setCastResults((d.voices || []).slice(0, 10));
    } finally { setCastBusy(false); setCastSearched(true); }
  };
  const castVoice = async (character: string, v: { id: string; name: string }) => {
    await fetch(`${scrpt.engineUrl}/api/scrpt/movie/voice-cast/${catalog}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character, voice_id: v.id, voice_name: v.name }),
    });
    setCastFor(null); setCastQ(""); setCastResults([]);
    setMvKey((k) => k + 1);
  };
  const [mvKey, setMvKey] = useState(0);
  const [mvFormat, setMvFormat] = useState<"childrens" | "feature" | "series">(
    book.data.kind === "childrens" ? "childrens" : "feature");
  const [minutes, setMinutes] = useState(8);
  const [premise, setPremise] = useState("");
  const FORMAT_MINUTES: Record<string, number[]> = {
    childrens: [5, 8, 12], feature: [30, 60, 75, 90, 120], series: [12, 22, 44, 60] };
  const [mvMsg, setMvMsg] = useState("");
  const [mvJob, setMvJob] = useState<{ what: string; pct: number } | null>(null);
  const [mvRedo, setMvRedo] = useState<string | null>(null);
  const [mvPrompt, setMvPrompt] = useState("");
  useEffect(() => {
    fetch(`${scrpt.engineUrl}/api/scrpt/trailer/${catalog}`)
      .then((r) => r.json()).then((d) => setMv(d.movie || null)).catch(() => {});
  }, [catalog, mvKey]);
  const runJob = async (url: string, bodyObj: object, what: string) => {
    setMvMsg("");
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                 body: JSON.stringify(bodyObj) });
    const d = await r.json();
    if (!r.ok) { setMvMsg(d.detail || "Could not start"); return null; }
    if (!d.job_id) return d;
    setMvJob({ what, pct: 0.02 });
    try {
      const job = await pollJob(d.job_id, (j) => setMvJob({ what, pct: Number(j.progress) || 0.02 }));
      if (job.status !== "done") setMvMsg(`Failed: ${(job.error || "").split("\n")[0]}`);
    } finally { setMvJob(null); }
    setMvKey((k) => k + 1);
    return d;
  };
  // The screening room shows the FILM. The trailer lives on the Trailer tab —
  // this screen stays dark until the movie engine ships.

  const filmBoard = (
    <div className="card">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <div className="serif-display text-[17px] font-semibold">The film board</div>
        {mv && <div className="text-[11px] text-text-faint">{mv.count} shots · ~{mv.minutes} min</div>}
      </div>
      {!mv ? (
        <div className="mt-3">
          <div className="grid grid-cols-3 gap-3">
            {([["childrens", "Animated Children's", "5–12 min, storybook wonder"],
               ["feature", "Feature Film", "30–120 min, the book's own genre"],
               ["series", "TV Series", "an episode, 12–60 min, own premise"]] as const).map(([k, label, sub]) => (
              <button key={k}
                      onClick={() => { setMvFormat(k); setMinutes(FORMAT_MINUTES[k][1] ?? FORMAT_MINUTES[k][0]); }}
                      className={`text-left rounded-[10px] border p-3 ${
                        mvFormat === k ? "border-accent" : "border-border-subtle hover:border-border"}`}>
                <div className={`text-[13px] font-semibold ${mvFormat === k ? "text-accent" : ""}`}>{label}</div>
                <div className="text-[11px] text-text-faint mt-0.5">{sub}</div>
              </button>
            ))}
          </div>
          <p className="text-[12px] text-text-tertiary leading-relaxed mt-3">
            The book is ADAPTED into a screenplay for the chosen format —
            dialogue and action carry the story; narration is a storyteller&apos;s
            spice. Then the screenplay breaks into shots with a frame each. No
            video is shot yet.
          </p>
          {mvFormat === "series" && (
            <input value={premise} onChange={(e) => setPremise(e.target.value)}
                   placeholder="This episode's premise (optional) — e.g. Princess and Moss get lost in the winter caves"
                   className="w-full rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[12px] mt-2" />
          )}
          <div className="flex items-center gap-2 mt-3 flex-wrap">
            {FORMAT_MINUTES[mvFormat].map((m) => (
              <button key={m}
                      className={`text-[11px] px-2.5 py-1 rounded-full border ${
                        minutes === m ? "border-accent text-accent" : "border-border-subtle text-text-tertiary"}`}
                      onClick={() => setMinutes(m)}>~{m} min</button>
            ))}
            <button className="btn-brass text-[12px]" disabled={!!mvJob}
                    onClick={() => runJob(`${scrpt.engineUrl}/api/scrpt/movie/board/${catalog}`,
                                          { minutes, format: mvFormat, premise }, "Boarding the film")}>
              Build the film board
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 mt-3 flex-wrap">
            <button className="btn-brass text-[12px]" disabled={!!mvJob}
                    onClick={async () => {
                      const q = await fetch(`${scrpt.engineUrl}/api/scrpt/movie/produce/${catalog}`, {
                        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
                      }).then((r) => r.json());
                      if (!window.confirm(
                        `Shoot the film? ${q.shots} shots · ~${Math.round((q.seconds || 0) / 60)} min.\n\n` +
                        `Estimated up to ${q.estimate_credits_max} credits (cached takes are free).`)) return;
                      await runJob(`${scrpt.engineUrl}/api/scrpt/movie/produce/${catalog}`,
                                   { confirm: true }, "Shooting the film");
                    }}>
              Shoot the film…
            </button>
            <button className="btn-ghost text-[12px]" disabled={!!mvJob}
                    onClick={() => runJob(`${scrpt.engineUrl}/api/scrpt/trailer/rerecord/${catalog}`,
                                          { board: "movie" }, "Re-recording")}>
              Re-record VO &amp; re-cut
            </button>
            <button className="btn-ghost text-[12px]" disabled={!!mvJob}
                    onClick={() => { if (window.confirm("Rebuild the board from the book? Frames redraw; shot takes stay cached.")) runJob(`${scrpt.engineUrl}/api/scrpt/movie/board/${catalog}`, { minutes: mv.minutes || 8 }, "Re-boarding"); }}>
              Rebuild board
            </button>
            {mvJob && (
              <span className="flex items-center gap-2 text-[11px] text-text-faint">
                <svg width="30" height="30" viewBox="0 0 30 30">
                  <circle cx="15" cy="15" r="12" fill="none" stroke="var(--line)" strokeWidth="2.5" />
                  <circle cx="15" cy="15" r="12" fill="none" stroke="var(--accent, #c9a96a)"
                          strokeWidth="2.5" strokeLinecap="round"
                          strokeDasharray={`${Math.max(3, mvJob.pct * 75)} 75`}
                          transform="rotate(-90 15 15)"
                          style={{ transition: "stroke-dasharray 0.6s ease" }} />
                  <text x="15" y="18.5" textAnchor="middle" fontSize="8.5"
                        fill="var(--text-secondary, #bbb)">{Math.round(mvJob.pct * 100)}%</text>
                </svg>
                {mvJob.what}…
              </span>
            )}
          </div>
          <div className="grid gap-2 mt-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}>
            {mv.panels.map((p, i) => (
              <div key={String(p.n ?? i)}>
                {p.frame_url ? (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img src={`${scrpt.engineUrl}${p.frame_url}`} alt={String(p.title || p.n)}
                       className="w-full rounded" style={{ aspectRatio: "16/9", objectFit: "cover", border: "1px solid var(--line)" }} />
                ) : (
                  <div className="w-full rounded flex items-center justify-center text-[10px] text-text-faint"
                       style={{ aspectRatio: "16/9", border: "1px dashed var(--line)" }}>
                    shot {String(p.n ?? i + 1)}
                  </div>
                )}
                <div className="text-[11px] text-text mt-1">{p.n}. {p.title}
                  {p.dur ? <span className="text-text-faint"> · {p.dur}s</span> : null}</div>
                {p.vo ? <div className="text-[10px] text-text-secondary italic leading-snug">“{p.vo}”</div> : null}
                <div className="flex gap-1.5 mt-1">
                  <button className="btn-ghost text-[10px] px-2 py-0.5" disabled={!!mvJob}
                          onClick={() => { setMvRedo(String(p.n)); setMvPrompt(""); }}>
                    Redraw image
                  </button>
                  <button className="btn-ghost text-[10px] px-2 py-0.5" disabled={!!mvJob}
                          onClick={async () => {
                            const q = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/reshoot-scene/${catalog}`, {
                              method: "POST", headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({ panel: String(p.n), board: "movie" }),
                            }).then((r) => r.json());
                            if (!window.confirm(`Re-shoot shot ${p.n} (${q.seconds}s)?\n\nEstimated up to ${q.estimate_credits_max} credits.`)) return;
                            await runJob(`${scrpt.engineUrl}/api/scrpt/trailer/reshoot-scene/${catalog}`,
                                         { panel: String(p.n), board: "movie", confirm: true }, `Shooting ${p.n}`);
                          }}>
                    Re-shoot shot
                  </button>
                </div>
                {mvRedo === String(p.n) && (
                  <div className="mt-1.5 p-2 rounded-[6px] border border-border-subtle">
                    <textarea value={mvPrompt} onChange={(e) => setMvPrompt(e.target.value)} rows={3} autoFocus
                              className="w-full rounded-[5px] border border-border-subtle bg-transparent p-1.5 text-[11px] leading-snug"
                              placeholder="Describe the image — or leave empty for the shot description." />
                    <div className="flex gap-1.5 mt-1.5">
                      <button className="btn-brass text-[10px] px-2 py-0.5" disabled={!!mvJob}
                              onClick={async () => {
                                const panel = String(p.n);
                                setMvRedo(null);
                                await runJob(`${scrpt.engineUrl}/api/scrpt/trailer/board-frame/${catalog}`,
                                             { panel, prompt: mvPrompt, board: "movie" }, `Painting ${panel}`);
                              }}>Redraw</button>
                      <button className="btn-ghost text-[10px] px-2 py-0.5" onClick={() => setMvRedo(null)}>Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
          {mv.music && <div className="text-[10px] text-text-faint mt-2">Score: {mv.music}</div>}
          <div className="text-[11px] uppercase tracking-[0.14em] text-text-faint mt-5 mb-2">
            The voice cast
          </div>
          <div className="space-y-2">
            {Array.from(new Set(mv.panels.map((p: MoviePanel & { line?: { speaker?: string } }) =>
                (p as { line?: { speaker?: string } }).line?.speaker).filter(Boolean))).map((name) => (
              <div key={String(name)} className="rounded-[8px] border border-border-subtle px-3 py-2">
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="text-[13px] font-medium min-w-[110px]">{String(name)}</div>
                  <div className="text-[11px] text-text-faint flex-1">
                    {mv.voice_cast?.[String(name)]
                      ? `voiced by ${mv.voice_cast[String(name)].name}`
                      : "no voice cast — lines fall back to the narrator"}
                  </div>
                  <button className="btn-ghost text-[11px] px-2 py-0.5"
                          onClick={() => { setCastFor(castFor === name ? null : String(name)); setCastQ(""); setCastResults([]); }}>
                    {castFor === name ? "Close" : "Cast voice…"}
                  </button>
                </div>
                {castFor === name && (
                  <div className="mt-2">
                    <div className="flex items-center gap-1.5 flex-wrap mb-1.5">
                      {[["female", "Female"], ["male", "Male"]].map(([v, label]) => (
                        <button key={v}
                                className={`text-[10px] px-2 py-0.5 rounded-full border ${
                                  castGender === v ? "border-accent text-accent" : "border-border-subtle text-text-tertiary hover:text-text-secondary"}`}
                                onClick={() => setCastGender(castGender === v ? "" : v)}>{label}</button>
                      ))}
                      <span className="w-1.5" />
                      {[["american", "American"], ["british", "British"]].map(([v, label]) => (
                        <button key={v}
                                className={`text-[10px] px-2 py-0.5 rounded-full border ${
                                  castAccent === v ? "border-accent text-accent" : "border-border-subtle text-text-tertiary hover:text-text-secondary"}`}
                                onClick={() => setCastAccent(castAccent === v ? "" : v)}>{label}</button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      <input value={castQ} onChange={(e) => setCastQ(e.target.value)}
                             onKeyDown={(e) => { if (e.key === "Enter") searchCastVoice(); }}
                             placeholder="small brave dragon, cheeky bird, warm young unicorn…"
                             className="flex-1 rounded-[6px] border border-border-subtle bg-transparent px-2.5 py-1 text-[12px]" />
                      <button className="btn-ghost text-[11px]" disabled={castBusy || (!castQ.trim() && !castGender && !castAccent)}
                              onClick={searchCastVoice}>{castBusy ? "…" : "Search"}</button>
                    </div>
                    {castSearched && castResults.length === 0 && (
                      <div className="text-[10px] text-text-faint mt-1.5">
                        No voices matched — describe the SOUND (&quot;bright playful child&quot;,
                        &quot;gentle shy young voice&quot;); trademarked names find nothing.
                      </div>
                    )}
                    {castResults.map((v) => (
                      <div key={v.id} className="flex items-center gap-2 flex-wrap mt-1.5 rounded-[6px] border border-border-subtle px-2 py-1.5">
                        <div className="flex-1 min-w-[140px]">
                          <div className="text-[12px]">{v.name}</div>
                          {v.description && <div className="text-[10px] text-text-faint">{v.description.slice(0, 90)}</div>}
                        </div>
                        {v.preview_url && <audio controls preload="none" src={v.preview_url} className="h-6" style={{ maxWidth: 180 }} />}
                        <button className="btn-brass text-[10px] px-2 py-0.5"
                                onClick={() => castVoice(String(name), v)}>Cast</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
      {mvMsg && <div className="text-[12px] mt-2" style={{ color: "var(--status-red)" }}>{mvMsg}</div>}
    </div>
  );

  return (
    <div className="mt-6 space-y-5">
      {/* The screening room — the viewer leads the page (Lars, 2026-08-30) */}
      <div className="card">
        <div className="flex items-baseline justify-between flex-wrap gap-2">
          <div className="serif-display text-[17px] font-semibold">The screening room</div>
          <div className="flex items-center gap-1">
            {(["cinema", "tv"] as const).map((m) => (
              <button key={m} onClick={() => setScreen(m)}
                      className={`px-3 py-1 rounded-full text-[11px] uppercase tracking-[0.1em] ${
                        screen === m ? "text-text-primary" : "text-text-faint hover:text-text-secondary"}`}
                      style={screen === m ? { background: "var(--surface)", boxShadow: "var(--shadow-card)" } : {}}>
                {m === "cinema" ? "Cinema" : "TV"}
              </button>
            ))}
          </div>
        </div>

        {screen === "cinema" ? (
          <div className="mt-4 rounded-[10px] px-6 pt-8 pb-10"
               style={{ background: "linear-gradient(180deg, #05060a 0%, #0b0d14 70%, #05060a 100%)" }}>
            <div className="mx-auto w-full">
              <div className="rounded-[4px] overflow-hidden"
                   style={{ boxShadow: "0 0 60px rgba(120,140,190,0.18), 0 0 6px rgba(0,0,0,0.9)" }}>
                {mv?.film_url ? (
                  <video key={mv.film_url} controls className="w-full block bg-black"
                         poster={mv.film_poster_url ? `${scrpt.engineUrl}${mv.film_poster_url}` : undefined}
                         src={`${scrpt.engineUrl}${mv.film_url}`} />
                ) : (
                  <div className="w-full flex items-center justify-center bg-black" style={{ aspectRatio: "16/9" }}>
                    <span className="text-[12px] uppercase tracking-[0.2em]" style={{ color: "#3c4254" }}>
                      Waiting for the blockbuster
                    </span>
                  </div>
                )}
              </div>
              <div className="text-center mt-6 text-[11px] uppercase tracking-[0.25em]" style={{ color: "#3c4254" }}>
                {book.title}
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-4 rounded-[10px] px-6 py-8 flex flex-col items-center"
               style={{ background: "linear-gradient(180deg, #101217 0%, #191c23 100%)" }}>
            <div className="w-full" style={{ maxWidth: 640 }}>
              <div className="rounded-[10px] p-2" style={{ background: "#000", boxShadow: "0 14px 40px rgba(0,0,0,0.55)" }}>
                <div className="rounded-[6px] overflow-hidden">
                  {mv?.film_url ? (
                    <video key={mv.film_url} controls className="w-full block bg-black"
                           poster={mv.film_poster_url ? `${scrpt.engineUrl}${mv.film_poster_url}` : undefined}
                           src={`${scrpt.engineUrl}${mv.film_url}`} />
                  ) : (
                    <div className="w-full flex items-center justify-center bg-black" style={{ aspectRatio: "16/9" }}>
                      <span className="text-[12px] uppercase tracking-[0.2em]" style={{ color: "#3c4254" }}>
                        Waiting for the blockbuster
                      </span>
                    </div>
                  )}
                </div>
              </div>
              <div className="mx-auto mt-[2px]" style={{ width: 120, height: 8, background: "#0a0b0e", borderRadius: "0 0 6px 6px" }} />
            </div>
          </div>
        )}

        <div className="flex items-center gap-2 mt-4 flex-wrap">
          <button className="btn-ghost text-[12px]" disabled title="Coming with the movie engine">Cast to TV</button>
          <span className="text-[11px] uppercase tracking-[0.1em] text-text-faint">In development</span>
        </div>
      </div>

      {filmBoard}

      {/* Format (legacy) — gone once the choice above is made */}
      {!mv && (<>
      <div className="card">
        <div className="serif-display text-[17px] font-semibold">The production</div>
        <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
          When the movie engine ships, every finished book can go to screen.
          Choose the shape this story should take — the plan is remembered
          here and picked up by the engine later.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {MOVIE_FORMATS.map((f) => (
            <button key={f.key} onClick={() => setFormat(f.key)}
                    className="text-left rounded-[10px] border p-4 transition-colors"
                    style={{
                      borderColor: format === f.key ? "var(--text-secondary)" : "var(--border-subtle)",
                      background: format === f.key ? "var(--surface)" : "transparent",
                    }}>
              <div className="text-[13px] font-semibold">{f.name}</div>
              <div className="text-[12px] text-text-tertiary mt-1 leading-relaxed">{f.line}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Pipeline */}
      <div className="card">
        <div className="serif-display text-[17px] font-semibold">The production line</div>
        <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
          Built in the same house style as the writing and trailer desks:
          reviewable on paper before anything expensive is generated.
        </p>
        <div className="mt-4 space-y-0">
          {MOVIE_PIPELINE.map((st, i) => (
            <div key={st.step} className="flex items-start gap-4 py-3"
                 style={i > 0 ? { borderTop: "1px solid var(--border-subtle)" } : {}}>
              <div className="text-[11px] text-text-faint w-5 pt-[2px] text-right shrink-0">{i + 1}</div>
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-medium">{st.step}</div>
                <div className="text-[12px] text-text-tertiary mt-[2px] leading-relaxed">{st.line}</div>
              </div>
              <span className="text-[10px] uppercase tracking-[0.12em] text-text-faint pt-[3px] shrink-0">Planned</span>
            </div>
          ))}
        </div>
      </div>
      </>)}
    </div>
  );
}


// ── The trailer voice bench ──────────────────────────────────────
type BenchVoice = { id: string; name: string; category?: string; preview_url?: string | null };

function TrailerVoiceCard({ catalog, onCast }: { catalog: string; onCast: () => void }) {
  const [voices, setVoices] = useState<BenchVoice[]>([]);
  const [current, setCurrent] = useState<{ id: string; name: string } | null>(null);
  const [picked, setPicked] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<(BenchVoice & { description?: string; owner_id?: string })[]>([]);

  const [vGender, setVGender] = useState("");
  const [vAccent, setVAccent] = useState("");
  const search = async () => {
    setSearching(true); setResults([]);
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/voice-library/search?q=${encodeURIComponent(query)}&gender=${vGender}&accent=${vAccent}`);
      const d = await r.json();
      if (r.ok) setResults(d.voices || []);
      else setMsg(d.detail || "Search failed");
    } catch { setMsg("Search failed"); } finally { setSearching(false); }
  };

  const hire = async (v: BenchVoice & { owner_id?: string }) => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/voice/hire/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: v.id, owner_id: v.owner_id, name: v.name }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not hire the voice"); return; }
      setVoices((list) => list.some((x) => x.id === v.id) ? list
        : [{ id: v.id, name: v.name, category: "hired" }, ...list]);
      setCurrent({ id: v.id, name: v.name });
      setPicked(v.id);
      setResults([]);
      setQuery("");
      setMsg(`${v.name.split(" - ")[0].split(" – ")[0]} hired and on the mic.`);
      loadBank();
      onCast();
    } catch { setMsg("Could not hire the voice"); } finally { setBusy(false); }
  };

  const loadBank = useCallback(() => {
    fetch(`${scrpt.engineUrl}/api/scrpt/trailer/voices/${catalog}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) { setVoices(d.voices || []); setCurrent(d.current || null); } })
      .catch(() => {});
  }, [catalog]);
  useEffect(loadBank, [loadBank]);

  const sel = voices.find((v) => v.id === (picked || current?.id));

  const cast = async () => {
    if (!sel) return;
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/voice/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: sel.id, name: sel.name }),
      });
      if (r.ok) {
        setCurrent({ id: sel.id, name: sel.name });
        setMsg(`${sel.name.split(" - ")[0].split(" – ")[0]} is on the mic.`);
        onCast();
      } else setMsg("Could not cast the voice");
    } catch { setMsg("Could not cast the voice"); } finally { setBusy(false); }
  };

  const [rrPct, setRrPct] = useState<number | null>(null);
  const rerecord = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/rerecord/${catalog}`, { method: "POST" });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not start"); return; }
      setMsg("Re-recording every line in the new voice…");
      setRrPct(0.03);
      const job = await pollJob(d.job_id, (j) => {
        setRrPct(Number(j.progress) || 0.03);
        setMsg(j.detail || j.stage || "Re-recording…");
      });
      setRrPct(null);
      setMsg(job.status === "done"
        ? "Done — the trailer is re-cut with the new voice. No footage was re-shot."
        : `Failed: ${(job.error || "").split("\n")[0]}`);
      onCast();
    } catch { setMsg("Could not start"); } finally { setBusy(false); }
  };

  if (voices.length === 0) return null;
  return (
    <div className="card">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <div className="serif-display text-[17px] font-semibold">The voice</div>
        {current && (
          <span className="text-[11px] uppercase tracking-[0.1em] text-text-tertiary">
            On the mic · {current.name.split(" - ")[0].split(" – ")[0]}
          </span>
        )}
      </div>
      <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
        The trailer narrator, cast per book. Search the whole voice library
        for the sound the film needs, or pick from your bank below — every
        line is re-recorded in the new voice on the next production, and
        nothing else is re-made.
      </p>

      <div className="flex items-center gap-1.5 mt-3 flex-wrap">
        {[["female", "Female"], ["male", "Male"]].map(([v, label]) => (
          <button key={v}
                  className={`text-[11px] px-2.5 py-1 rounded-full border ${
                    vGender === v ? "border-accent text-accent" : "border-border-subtle text-text-tertiary hover:text-text-secondary"}`}
                  onClick={() => setVGender(vGender === v ? "" : v)}>
            {label}
          </button>
        ))}
        <span className="w-2" />
        {[["american", "American"], ["british", "British"]].map(([v, label]) => (
          <button key={v}
                  className={`text-[11px] px-2.5 py-1 rounded-full border ${
                    vAccent === v ? "border-accent text-accent" : "border-border-subtle text-text-tertiary hover:text-text-secondary"}`}
                  onClick={() => setVAccent(vAccent === v ? "" : v)}>
            {label}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2 mt-2">
        <input value={query} onChange={(e) => setQuery(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter") search(); }}
               placeholder="Disney, deep movie trailer, warm storyteller…"
               className="flex-1 rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[13px]" />
        <button className="btn-ghost text-[12px] shrink-0"
                disabled={busy || (!query.trim() && !vGender && !vAccent)} onClick={search}>
          {searching ? "Searching…" : "Search"}
        </button>
      </div>
      {!searching && results.length === 0 && query.trim() && (
        <div className="text-[11px] text-text-faint mt-2">
          No voices matched. The library has no trademarked names (searching
          &quot;Disney&quot; finds nothing) — describe the SOUND instead:
          &quot;warm animated storyteller&quot;, &quot;bright playful narrator&quot;.
        </div>
      )}
      {results.length > 0 && (
        <div className="mt-2 space-y-2">
          {results.map((v) => (
            <div key={v.id} className="flex items-center gap-3 flex-wrap rounded-[8px] border border-border-subtle px-3 py-2">
              <div className="flex-1 min-w-[180px]">
                <div className="text-[13px] font-medium">{v.name}</div>
                {v.description && <div className="text-[11px] text-text-faint">{v.description}</div>}
              </div>
              {v.preview_url && (
                <audio controls preload="none" src={v.preview_url} className="h-7" style={{ maxWidth: 220 }} />
              )}
              <button className="btn-brass text-[11px] shrink-0" disabled={busy}
                      onClick={() => hire(v)}>
                Hire &amp; cast
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="text-[11px] uppercase tracking-[0.1em] text-text-faint mt-4">Your voice bank</div>
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        <select value={picked || current?.id || ""}
                onChange={(e) => setPicked(e.target.value)}
                className="rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[13px] max-w-full"
                style={{ background: "var(--surface)", color: "var(--text-primary)" }}>
          {voices.map((v) => (
            <option key={v.id} value={v.id}>{v.name}{v.category === "premade" ? "" : ` · ${v.category}`}</option>
          ))}
        </select>
        <button className="btn-brass text-[12px]" disabled={busy || !sel || sel.id === current?.id} onClick={cast}>
          Cast this voice
        </button>
        <button className="btn-ghost text-[12px]" disabled={busy} onClick={rerecord}
                title="Re-records every narration line in the cast voice and re-cuts the trailer. Reuses all footage and music — cannot shoot video.">
          Re-record VO &amp; re-cut
        </button>
        {rrPct !== null && (
          <svg width="38" height="38" viewBox="0 0 38 38" className="shrink-0">
            <circle cx="19" cy="19" r="15" fill="none" stroke="var(--line)" strokeWidth="3" />
            <circle cx="19" cy="19" r="15" fill="none" stroke="var(--accent, #c9a96a)"
                    strokeWidth="3" strokeLinecap="round"
                    strokeDasharray={`${Math.max(4, rrPct * 94)} 94`}
                    transform="rotate(-90 19 19)"
                    style={{ transition: "stroke-dasharray 0.6s ease" }} />
            <text x="19" y="22.5" textAnchor="middle" fontSize="10"
                  fill="var(--text-secondary, #bbb)">
              {Math.round(rrPct * 100)}%
            </text>
          </svg>
        )}
      </div>
      {sel?.preview_url && (
        <audio key={sel.id} controls preload="none" src={sel.preview_url} className="mt-3 h-8" style={{ maxWidth: 360 }} />
      )}
      {msg && <div className="text-[12px] mt-2" style={{ color: "var(--status-green)" }}>{msg}</div>}
    </div>
  );
}


// ── The production display: what the cinema shows while the camera rolls ──
function ShootingScreen({ s }: { s: { stage: string; detail: string; progress: number; started: number; total: number } }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const elapsed = (Date.now() - s.started) / 1000;
  const p = Math.max(0, Math.min(1, s.progress));
  const remaining = p > 0.08
    ? Math.max(15, (elapsed * (1 - p)) / p)
    : Math.max(30, s.total - elapsed);
  const mins = Math.floor(remaining / 60);
  const eta = remaining >= 90 ? `about ${mins + (remaining % 60 > 30 ? 1 : 0)} minutes left`
    : remaining >= 45 ? "about a minute left" : "almost done";
  const STAGES: Record<string, string> = {
    starting: "Preparing the production", directing: "Writing the treatment",
    look: "Reading the cover's world", shooting: "Shooting",
    voice: "Recording the voice-over", sound: "Sound design",
    score: "Scoring", cutting: "Cutting", upload: "Sending to the lab",
    upscale: "Finishing", finishing: "Finishing",
  };
  return (
    <div className="w-full flex flex-col items-center justify-center bg-black" style={{ aspectRatio: "16/9" }}>
      <span aria-hidden style={{
        width: 16, height: 16, borderRadius: "50%",
        background: "radial-gradient(circle at 35% 35%, #FF6B5E, #C22B22 70%)",
        border: "2px solid #050505", outline: "1px solid #3D3F44",
        animation: "recPulse 1.1s ease-in-out infinite",
      }} />
      <div className="mt-4 text-[13px] uppercase tracking-[0.22em]" style={{ color: "#B9BDC7" }}>
        {STAGES[s.stage] || s.stage || "Producing"}
      </div>
      {s.detail && (
        <div className="mt-1 text-[12px]" style={{ color: "#6B7280" }}>{s.detail}</div>
      )}
      <div className="mt-5" style={{ width: "56%", height: 2, background: "#22252D", borderRadius: 2 }}>
        <div style={{ width: `${Math.max(2, p * 100)}%`, height: "100%",
                      background: "#C9A96A", borderRadius: 2, transition: "width 1s linear" }} />
      </div>
      <div className="mt-3 text-[11px] uppercase tracking-[0.14em]" style={{ color: "#565B66" }}>
        {eta} — the film premieres here
      </div>
    </div>
  );
}


// ── The score bench ──────────────────────────────────────────────
type ScoreOption = { n: number; file: string; brief?: string; url: string };

function TrailerScoreCard({ catalog }: { catalog: string }) {
  const [options, setOptions] = useState<ScoreOption[]>([]);
  const [pinned, setPinned] = useState<{ file?: string; brief?: string; url?: string } | null>(null);
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [key, setKey] = useState(0);

  useEffect(() => {
    fetch(`${scrpt.engineUrl}/api/scrpt/trailer/score/${catalog}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) { setOptions(d.options || []); setPinned(d.pinned || null); } })
      .catch(() => {});
  }, [catalog, key]);

  const [composing, setComposing] = useState(false);

  const refreshBench = () => {
    fetch(`${scrpt.engineUrl}/api/scrpt/trailer/score/${catalog}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setOptions(d.options || []); })
      .catch(() => {});
  };

  const compose = async () => {
    setBusy(true); setComposing(true); setOptions([]); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/score/options/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ brief }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not start"); setBusy(false); setComposing(false); return; }
      const job = await pollJob(d.job_id, () => refreshBench(), 4000);
      setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
      setKey((k) => k + 1);
    } catch { setMsg("Failed"); } finally { setBusy(false); setComposing(false); }
  };

  const pick = async (n: number) => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/trailer/score/pick/${catalog}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ n }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not pin the score"); return; }
      setMsg("Score pinned — every future cut uses it.");
      setKey((k) => k + 1);
    } catch { setMsg("Failed"); } finally { setBusy(false); }
  };

  return (
    <div className="card">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <div className="serif-display text-[17px] font-semibold">The score</div>
        {pinned?.file && (
          <span className="text-[11px] uppercase tracking-[0.1em]" style={{ color: "var(--status-green)" }}>
            Pinned
          </span>
        )}
      </div>
      <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
        Describe the energy you want and audition three composed takes.
        Pick one and it becomes the trailer&apos;s score in every cut until you
        change it. Without a pick, the score is composed from the script&apos;s
        own music brief.
      </p>
      <div className="flex items-center gap-2 mt-3">
        <input value={brief} onChange={(e) => setBrief(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter" && brief.trim()) compose(); }}
               placeholder="driving dark percussion that never lets go… / warm hopeful strings that bloom…"
               className="flex-1 rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[13px]" />
        <button className="btn-ghost text-[12px] shrink-0" disabled={busy || !brief.trim()} onClick={compose}>
          Compose 3 (~15 cr)
        </button>
      </div>
      {pinned?.url && (
        <div className="flex items-center gap-3 mt-3">
          <span className="text-[11px] uppercase tracking-[0.1em] text-text-faint w-16 shrink-0">Current</span>
          <audio controls preload="none" src={`${scrpt.engineUrl}${pinned.url}`} className="h-8 flex-1" style={{ maxWidth: 380 }} />
        </div>
      )}
      <div className="mt-2 space-y-2">
        {(composing ? [1, 2, 3] : options.map((o) => o.n)).map((n) => {
          const o = options.find((x) => x.n === n);
          return (
            <div key={n} className="flex items-center gap-3 flex-wrap rounded-[8px] border border-border-subtle px-3 py-2">
              <span className="text-[11px] text-text-faint w-16 shrink-0">Take {n}</span>
              {o ? (
                <>
                  <audio controls preload="none" src={`${scrpt.engineUrl}${o.url}`} className="h-7 flex-1" style={{ maxWidth: 320 }} />
                  <button className="btn-brass text-[11px] shrink-0" disabled={busy} onClick={() => pick(o.n)}>
                    Use this score
                  </button>
                </>
              ) : (
                <span className="text-[12px] italic flex-1" style={{ color: "var(--status-amber)" }}>
                  Writing…
                </span>
              )}
            </div>
          );
        })}
      </div>
      {msg && <div className="text-[12px] mt-2" style={{ color: "var(--status-amber)" }}>{msg}</div>}
    </div>
  );
}


// ── compact progress under the recording button ──────────────────
function shootEta(s: { progress: number; started: number; total: number }) {
  const elapsed = (Date.now() - s.started) / 1000;
  const p = Math.max(0, Math.min(1, s.progress));
  const remaining = p > 0.08
    ? Math.max(15, (elapsed * (1 - p)) / p)
    : Math.max(30, s.total - elapsed);
  const mins = Math.floor(remaining / 60);
  return {
    p,
    label: remaining >= 90 ? `about ${mins + (remaining % 60 > 30 ? 1 : 0)} minutes left`
      : remaining >= 45 ? "about a minute left" : "almost done",
  };
}

function ShootProgressBar({ s }: { s: { stage: string; detail: string; progress: number; started: number; total: number } }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const { p, label } = shootEta(s);
  return (
    <div className="mt-3">
      <div style={{ width: "100%", height: 3, background: "var(--border-subtle)", borderRadius: 2 }}>
        <div style={{ width: `${Math.max(2, p * 100)}%`, height: "100%",
                      background: "#C9A96A", borderRadius: 2, transition: "width 1s linear" }} />
      </div>
      <div className="flex items-baseline justify-between mt-1.5 text-[11px]">
        <span className="uppercase tracking-[0.12em]" style={{ color: "var(--status-amber)" }}>
          {s.detail || s.stage || "Producing"}
        </span>
        <span className="text-text-faint">{label}</span>
      </div>
    </div>
  );
}


// ── Release plan ─────────────────────────────────────────────────
function ReleaseCard({ book, reload }: { book: ScrptBook; reload: () => void }) {
  const rel = ((book.data as { release?: { date?: string; mode?: string; status?: string; note?: string } }).release) || {};
  const [date, setDate] = useState(rel.date || "");
  const [mode, setMode] = useState<"immediate" | "scheduled">((rel.mode as "immediate" | "scheduled") || "immediate");
  const [note, setNote] = useState(rel.note || "");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/release/${book.catalog_number}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date, mode, note }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not save"); return; }
      setMsg("Release plan saved.");
      reload();
    } catch { setMsg("Could not save"); } finally { setBusy(false); }
  };

  const status = rel.status || (rel.date ? "planned" : "unplanned");
  return (
    <div className="card">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <div className="serif-display text-[17px] font-semibold">Release</div>
        <span className="text-[11px] uppercase tracking-[0.1em]"
              style={{ color: status === "released" ? "var(--status-green)" : status === "planned" ? "var(--status-blue)" : "var(--text-faint)" }}>
          {status}
        </span>
      </div>
      <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
        Every launch gets its own 30-day new-release window on Amazon, so
        series books are spaced — the house rhythm is one book every four
        weeks, ebook and paperback on the same day, the next book on
        pre-order from launch day. This date is what KDP should be set to.
      </p>
      <div className="flex items-center gap-2 mt-3 flex-wrap">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
               className="rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[13px]"
               style={{ colorScheme: "dark" }} />
        {(["immediate", "scheduled"] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)}
                  className={`px-3 py-1 rounded-full text-[11px] uppercase tracking-[0.08em] ${
                    mode === m ? "text-text-primary" : "text-text-faint hover:text-text-secondary"}`}
                  style={mode === m ? { background: "var(--surface)", boxShadow: "var(--shadow-card)" } : {}}>
            {m === "immediate" ? "Release on publish" : "Scheduled on KDP"}
          </button>
        ))}
        <button className="btn-brass text-[12px]" disabled={busy} onClick={save}>Save release plan</button>
      </div>
      <input value={note} onChange={(e) => setNote(e.target.value)}
             placeholder="Note — e.g. open book 2 pre-order on this day"
             className="mt-2 w-full rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[12px]" />
      {msg && <div className="text-[12px] mt-2" style={{ color: "var(--status-green)" }}>{msg}</div>}
    </div>
  );
}

// ── Spreads (children's books) ───────────────────────────────────
// A picture book is not chapters. The unit is a SPREAD: a facing pair of
// pages carrying a few words and one picture. This is the whole book on one
// screen — text, art brief, and the illustration once it is drawn.

type Spread = { n: number; text: string; picture: string; turn?: string; art_prompt?: string };
type LayoutOpt = {
  key: string; band: string; column: string; width: string;
  score: number; light_text: boolean; scrim: boolean;
};

type ChildrensRec = {
  label?: string; age?: string; words?: number; target_words?: number;
  value_shift?: string; art_style?: string;
  characters?: Record<string, string>;
  spreads?: Spread[]; art?: Record<string, string>;
};

/* ── Layout desk ──────────────────────────────────────────────────
   SCRPT picks where the words go. This is the override: every sensible
   placement for a spread, ranked, with the house pick marked. Choosing a
   different one pins it AND teaches the scorer — the position you move to
   gains weight for the next book, the one you moved from loses a little. */
function LayoutDesk({ catalog, spreads, art, onChanged }: {
  catalog: string; spreads: Spread[]; art: Record<string, string>;
  onChanged: () => void;
}) {
  const drawn = spreads.filter((s) => art[String(s.n)]);
  const [n, setN] = useState<number | null>(drawn[0]?.n ?? null);
  const [opts, setOpts] = useState<LayoutOpt[]>([]);
  const [chosen, setChosen] = useState<string>("");
  const [auto, setAuto] = useState<string>("");
  const [busyKey, setBusyKey] = useState("");

  const load = useCallback(async () => {
    if (n == null) return;
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/childrens/${catalog}/layout/${n}`);
      if (!r.ok) return;
      const d = await r.json();
      setOpts(d.options || []);
      setChosen(d.chosen?.key || "");
      setAuto(d.auto?.key || "");
    } catch { /* engine offline */ }
  }, [catalog, n]);
  useEffect(() => { load(); }, [load]);

  const pick = async (key: string) => {
    if (n == null) return;
    setBusyKey(key || "auto");
    try {
      await fetch(`${scrpt.engineUrl}/api/scrpt/childrens/${catalog}/layout/${n}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
      await load(); onChanged();
    } finally { setBusyKey(""); }
  };

  if (!drawn.length) return null;
  return (
    <div className="card">
      <div className="serif-display text-[17px] font-semibold">Where the words go</div>
      <p className="text-[12px] text-text-tertiary mt-1 max-w-[640px] leading-relaxed">
        SCRPT reads each picture and sets the text where the artwork is quietest.
        Override it here if a page wants something else — your choice is pinned for
        this spread and nudges the house style for every book after it.
      </p>

      <div className="flex flex-wrap gap-1.5 mt-3">
        {drawn.map((s) => (
          <button key={s.n} onClick={() => setN(s.n)}
                  className={`px-2 py-[3px] rounded text-[11.5px] transition-all ${
                    n === s.n ? "bg-accent-subtle text-accent"
                              : "border border-border-subtle text-text-secondary hover:text-text-primary"}`}>
            {s.n}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-2 mt-4">
        <button onClick={() => pick("")} disabled={!!busyKey}
                className={`px-2.5 py-[6px] rounded-md text-[11.5px] transition-all ${
                  !chosen ? "bg-accent-subtle text-accent"
                          : "border border-border-subtle text-text-secondary hover:text-text-primary"}`}>
          SCRPT decides{auto && !chosen ? ` · ${auto.replace(/-/g, " ")}` : ""}
        </button>
        {opts.map((o) => (
          <button key={o.key} onClick={() => pick(o.key)} disabled={!!busyKey}
                  title={`score ${o.score} · ${o.light_text ? "white" : "dark"} text`}
                  className={`px-2.5 py-[6px] rounded-md text-[11.5px] transition-all ${
                    chosen === o.key ? "bg-accent-subtle text-accent"
                                     : "border border-border-subtle text-text-secondary hover:text-text-primary"}`}>
            {o.band} {o.column}
            <span className="text-text-faint"> · {o.light_text ? "white" : "dark"}</span>
          </button>
        ))}
      </div>
      <div className="text-[11px] text-text-faint mt-3">
        Rebuild the interior to see a change on the page.
      </div>
    </div>
  );
}

/* ── Read the book ────────────────────────────────────────────────
   Not a reconstruction from the artwork — the BUILT PRINT FILE, page by
   page. Front matter, the story, the blank pages at the back, in the order
   and at the count that goes to KDP. If it is not in here, it is not in the
   book. */
function ReadThrough({ catalog, trim, onBuild, building, coverSig }: {
  catalog: string; trim: string; onBuild: () => void; building: boolean;
  coverSig: string;
}) {
  const [pages, setPages] = useState(0);
  const [ok8, setOk8] = useState(true);
  // 0 is the closed book — the cover, before the first page turn
  const [i, setI] = useState(0);
  const [spread, setSpread] = useState(true);
  const [tw, th] = (() => {
    const m = (trim || "8.5x8.5").toLowerCase().split("x").map(Number);
    return m.length === 2 && m.every((n) => n > 0) ? m : [8.5, 8.5];
  })();
  // The cover file is overwritten in place when a variant is chosen, so the
  // URL never changes and the browser keeps the old picture. Bust the cache
  // whenever the chosen cover changes — page count is not a proxy for it.
  const [coverBust, setCoverBust] = useState(0);
  useEffect(() => { setCoverBust(Date.now()); }, [coverSig, building]);

  // how many pages the built print file actually has — this is what makes
  // the viewer show the real book rather than the "not built yet" state
  const loadPages = useCallback(async () => {
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/childrens/${catalog}/pages`);
      if (!r.ok) return;
      const d = await r.json();
      setPages(d.pages || 0);
      setOk8(!!d.divisible_by_8);
    } catch { /* engine offline */ }
  }, [catalog]);
  useEffect(() => { loadPages(); }, [loadPages, building]);
  const openRun = useLightboxRun();
  // the pages are rendered small to fit the panel; a click should give the
  // real thing full size — and let you keep turning pages from in there
  const big = useCallback((n: number) =>
    n === 0
      ? `${scrpt.engineUrl}/api/files/${catalog}/cover-front.png?v=${coverSig}-${coverBust}`
      : `${scrpt.engineUrl}/api/scrpt/childrens/${catalog}/page/${n}.png?dpi=200&v=${pages}`,
    [catalog, pages, coverSig, coverBust]);

  // ONE list of frames, used by the panel and by the lightbox, so the two
  // can never disagree about what faces what. A bound book opens on the
  // cover alone, then the title page alone (it is a recto), and everything
  // after that falls into facing pairs.
  const frames = useMemo(() => {
    const f: { label: string; srcs: string[]; pages: number[] }[] = [];
    f.push({ label: "Cover", srcs: [], pages: [0] });
    if (pages >= 1) f.push({ label: `Page 1 of ${pages}`, srcs: [], pages: [1] });
    for (let n = 2; n <= pages; n += 2) {
      const pair = n + 1 <= pages ? [n, n + 1] : [n];
      f.push({
        label: pair.length === 2 ? `Pages ${pair[0]}–${pair[1]} of ${pages}`
                                 : `Page ${pair[0]} of ${pages}`,
        srcs: [], pages: pair,
      });
    }
    return f;
  }, [pages]);

  const frameOf = useCallback((n: number) =>
    Math.max(0, frames.findIndex((f: { pages: number[] }) => f.pages.includes(n))),
    [frames]);

  const src = (n: number) =>
    `${scrpt.engineUrl}/api/scrpt/childrens/${catalog}/page/${n}.png?dpi=90&v=${pages}`;

  // stepping moves a whole FRAME — the cover, then page one, then facing
  // pairs — so a turn never lands mid-spread
  const nextPage = useCallback((d: number) => {
    const j = Math.max(0, Math.min(frameOf(i) + d, frames.length - 1));
    return frames[j].pages[0];
  }, [frames, frameOf, i]);

  const openAt = useCallback((n: number) => openRun({
    index: frameOf(n),
    frames: frames.map((f: { label: string; pages: number[] }) => ({
      label: f.label, srcs: f.pages.map((k: number) => big(k)),
    })),
  }, "Page"), [openRun, frames, frameOf, big]);

  if (!pages) {
    return (
      <div className="card">
        <div className="serif-display text-[17px] font-semibold">Read the book</div>
        <p className="text-[12px] text-text-tertiary mt-1 max-w-[560px] leading-relaxed">
          Build the interior and the whole book appears here exactly as it goes to
          KDP — title page, copyright page, every spread, and the blank pages at
          the back.
        </p>
        <button className="btn-brass text-[12px] mt-3" onClick={onBuild} disabled={building}>
          {building ? "Building…" : "Build the book"}
        </button>
      </div>
    );
  }

  const coverSrc =
    `${scrpt.engineUrl}/api/files/${catalog}/cover-front.png?v=${coverSig}-${coverBust}`;
  const fi = Math.max(0, Math.min(frameOf(i), frames.length - 1));
  const cur = frames[fi] || frames[0];
  const onCover = cur.pages[0] === 0;
  const left = !onCover && cur.pages.length === 2 ? cur.pages[0] : null;
  const right = cur.pages[cur.pages.length - 1];

  return (
    <div className="card">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <div className="serif-display text-[17px] font-semibold">Read the book</div>
        <div className="flex items-center gap-3">
          <span className="text-[12px] text-text-tertiary">
            {cur.label}
            {" · "}{trim.replace("x", "\u2033 × ")}\u2033
          </span>
          <button className="text-[11px] text-text-faint hover:text-accent"
                  onClick={() => setSpread((v) => !v)}>
            {spread ? "Single page" : "Facing pages"}
          </button>
        </div>
      </div>

      <div className="mt-4 flex items-start justify-center gap-1">
        {onCover && (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img src={coverSrc} alt="Front cover"
               onClick={() => openAt(0)}
               style={{ width: `min(52%, ${400 * (tw / th)}px)`, aspectRatio: `${tw} / ${th}`,
                        border: "1px solid var(--border-subtle)",
                        boxShadow: "var(--shadow-page)" }}
               className="rounded-[4px] cursor-zoom-in" />
        )}
        {!onCover && spread && left && (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img src={src(left)} alt={`Page ${left}`}
               onClick={() => openAt(left)}
               style={{ width: `min(46%, ${360 * (tw / th)}px)`, aspectRatio: `${tw} / ${th}` }}
               className="rounded-l-[3px] cursor-zoom-in"
               // eslint-disable-next-line react/no-unknown-property
               />
        )}
        {!onCover && (
        /* eslint-disable-next-line @next/next/no-img-element */
        <img src={src(right)} alt={`Page ${right}`}
             onClick={() => openAt(right)}
             className="cursor-zoom-in"
             style={{ width: `min(46%, ${360 * (tw / th)}px)`, aspectRatio: `${tw} / ${th}`,
                      border: "1px solid var(--border-subtle)",
                      boxShadow: "var(--shadow-page)" }} />
        )}
      </div>

      <div className="flex items-center justify-center gap-4 mt-4">
        <button className="btn-ghost text-[12px]" disabled={fi === 0}
                onClick={() => setI(nextPage(-1))}>
          ← Back
        </button>
        <span className="text-[11px] text-text-faint">
          {pages} pages{ok8 ? " · accepted by KDP" : " · NOT divisible by 8"} · arrow keys work
        </span>
        <button className="btn-ghost text-[12px]" disabled={fi >= frames.length - 1}
                onClick={() => setI(nextPage(1))}>
          {onCover ? "Open the book →" : "Next →"}
        </button>
      </div>
      {!ok8 && (
        <div className="text-[11.5px] mt-2 text-center" style={{ color: "var(--status-amber)" }}>
          A print binder needs a page count divisible by 8 — rebuild the interior.
        </div>
      )}
    </div>
  );
}

function SpreadsTab({ book, reload, busy }: { book: ScrptBook; reload: () => void; busy: boolean }) {
  const catalog = book.catalog_number;
  const [rec, setRec] = useState<ChildrensRec | null>(null);
  const [working, setWorking] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/childrens/${catalog}`);
      if (r.ok) setRec(await r.json());
    } catch { /* engine offline */ }
  }, [catalog]);
  useEffect(() => { load(); }, [load]);

  const run = async (path: string, label: string, body?: object) => {
    setWorking(label); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/childrens/${catalog}${path}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Failed");
      const job = await pollJob(d.job_id, (j) => setMsg(j.detail || ""));
      setMsg(job.status === "done" ? "" : `Failed: ${(job.error || "").split("\n")[0]}`);
      await load(); reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally { setWorking(""); }
  };

  const spreads = rec?.spreads || [];
  const art = rec?.art || {};
  const drawn = Object.keys(art).length;

  const trim = String(
    (book.data?.format as { trim_size?: string } | undefined)?.trim_size
    || (book.data?.trim_size as string | undefined) || "8.5x8.5");

  return (
    <div className="mt-6 space-y-5">
      {spreads.length > 0 && (
        <ReadThrough catalog={catalog} trim={trim}
                     coverSig={String(
                       (book.data.cover as { selected_variant?: number } | undefined)
                         ?.selected_variant ?? "none")}
                     building={working === "Building the interior"}
                     onBuild={() => run("/interior", "Building the interior")} />
      )}
      {drawn > 0 && (
        <LayoutDesk catalog={catalog} spreads={spreads} art={art}
                    onChanged={() => load()} />
      )}
      {drawn > 0 && (
        <div className="card flex items-center gap-4 flex-wrap">
          <div className="flex-1 min-w-[240px]">
            <div className="serif-display text-[15px] font-semibold">Print interior</div>
            <div className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
              Full-bleed art at {trim.replace("x", "″ × ")}″ plus bleed, words inside the
              safe margin and clear of the gutter, padded to a page count the binder
              accepts. {drawn < spreads.length
                && `${spreads.length - drawn} spread${spreads.length - drawn === 1 ? "" : "s"} still undrawn.`}
            </div>
          </div>
          <button className="btn-brass text-[12px]" disabled={!!working || busy}
                  onClick={() => run("/interior", "Building the interior")}>
            {working === "Building the interior" ? "Building…" : "Build interior PDF"}
          </button>
          <a className="btn-ghost text-[12px]" target="_blank" rel="noreferrer"
             href={`${scrpt.engineUrl}/api/files/${catalog}/interior.pdf`}>Open PDF</a>
        </div>
      )}
      <div className="card">
        <div className="flex items-baseline justify-between flex-wrap gap-2">
          <div className="serif-display text-[17px] font-semibold">The picture book</div>
          {rec?.label && (
            <span className="text-[12px] text-text-tertiary">
              {rec.label} · ages {rec.age} · {spreads.length} spreads
              {rec.words ? ` · ${rec.words} words` : ""}
              {rec.target_words ? ` of ~${rec.target_words}` : ""}
            </span>
          )}
        </div>
        <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed max-w-[620px]">
          Written in spreads, not chapters — a few words and one picture per page turn.
          The first spread sets the look; every other illustration is drawn against it, so
          the characters stay the same throughout.
        </p>
        {rec?.value_shift && (
          <div className="text-[12px] mt-2" style={{ color: "var(--status-green)" }}>
            Value shift: {rec.value_shift}
          </div>
        )}
        <div className="flex items-center gap-2 mt-4 flex-wrap">
          <button className="btn-brass text-[12px]" disabled={!!working || busy}
                  onClick={() => run("", "writing")}>
            {working === "writing" ? "Writing…" : spreads.length ? "Rewrite the book" : "Write the book"}
          </button>
          <button className="btn-ghost text-[12px]" disabled={!!working || busy || !spreads.length}
                  onClick={() => run("/illustrate", "drawing")}>
            {working === "drawing" ? "Illustrating…" : drawn ? `Redraw all ${spreads.length}` : "Illustrate every spread"}
          </button>
          {spreads.length > 0 && (
            <span className="text-[11px] text-text-faint">
              {drawn} of {spreads.length} illustrated
            </span>
          )}
        </div>
        {msg && <div className="text-[12px] mt-2" style={{ color: "var(--status-amber)" }}>{msg}</div>}
      </div>

      {rec?.characters && Object.keys(rec.characters).length > 0 && (
        <div className="card">
          <div className="serif-display text-[15px] font-semibold">The cast</div>
          <p className="text-[11px] text-text-faint mt-1">
            Repeated word for word on every illustration prompt — this is what keeps a face the same.
          </p>
          <div className="mt-3 space-y-2">
            {Object.entries(rec.characters).map(([name, look]) => (
              <div key={name} className="text-[12.5px]">
                <span className="font-semibold text-text-primary">{name}</span>
                <span className="text-text-tertiary"> — {look}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {spreads.map((s) => (
        <div key={s.n} className="card">
          <div className="flex items-baseline justify-between">
            <div className="text-[11px] uppercase tracking-[0.12em] text-text-faint">Spread {s.n}</div>
            <button className="btn-ghost text-[11px]" disabled={!!working || busy}
                    onClick={() => run("/illustrate", `draw-${s.n}`, { spread: s.n })}>
              {working === `draw-${s.n}` ? "Drawing…" : art[String(s.n)] ? "Redraw" : "Draw"}
            </button>
          </div>
          <div className="grid gap-4 mt-3" style={{ gridTemplateColumns: art[String(s.n)] ? "1fr 1fr" : "1fr" }}>
            <div>
              <div className="serif-display text-[17px] leading-relaxed text-text-primary">{s.text}</div>
              <div className="text-[11.5px] text-text-tertiary mt-3 leading-relaxed">
                <span className="uppercase tracking-[0.1em] text-text-faint">Picture · </span>{s.picture}
              </div>
              {s.turn && (
                <div className="text-[11.5px] mt-2" style={{ color: "var(--status-amber)" }}>
                  Page turn: {s.turn}
                </div>
              )}
            </div>
            {art[String(s.n)] && (
              // eslint-disable-next-line @next/next/no-img-element
              <img alt={`Spread ${s.n}`} className="w-full rounded-[8px]"
                   src={`${scrpt.engineUrl}/api/files/${catalog}/${art[String(s.n)]}`} />
            )}
          </div>
        </div>
      ))}

      {!spreads.length && (
        <div className="card text-[12.5px] text-text-tertiary">
          No spreads yet. Write the book and it will appear here, page turn by page turn.
        </div>
      )}
    </div>
  );
}
