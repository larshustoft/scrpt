"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  pollJob, scrpt, type Job, type Manuscript, type ScrptBook, type ValidationReport,
} from "@/lib/scrpt";

type Tab = "manuscript" | "cover" | "audiobook" | "publishing";

export default function BookWorkspace({ params }: { params: Promise<{ catalog: string }> }) {
  const { catalog } = use(params);
  const [book, setBook] = useState<ScrptBook | null>(null);
  const [tab, setTab] = useState<Tab>("manuscript");
  const [activeJobs, setActiveJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");
  const pollRef = useRef(false);

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

  // poll while jobs are running
  useEffect(() => {
    if (activeJobs.length === 0 || pollRef.current) return;
    pollRef.current = true;
    const interval = setInterval(async () => {
      const j = await scrpt.jobs(catalog, true).catch(() => ({ jobs: [] }));
      if (j.jobs.length === 0) {
        clearInterval(interval);
        pollRef.current = false;
      }
      reload();
    }, 3000);
    return () => { clearInterval(interval); pollRef.current = false; };
  }, [activeJobs.length, catalog, reload]);

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
        {(["manuscript", "cover", "audiobook", "publishing"] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)}
                  className={`px-4 h-8 rounded-md text-[13px] font-medium capitalize transition-all ${
                    tab === t ? "text-text-primary" : "text-text-tertiary hover:text-text-secondary"
                  }`}
                  style={tab === t ? { background: "var(--surface)", boxShadow: "var(--shadow-card)" } : {}}>
            {t}
          </button>
        ))}
      </div>

      {tab === "manuscript" && <ManuscriptTab book={book} ms={ms} reload={reload} busy={activeJobs.length > 0} />}
      {tab === "cover" && <CoverTab book={book} reload={reload} />}
      {tab === "audiobook" && <AudiobookTab book={book} reload={reload} busy={activeJobs.some((j) => j.kind === "audiobook")} />}
      {tab === "publishing" && <PublishingTab book={book} ms={ms} />}
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

  return (
    <div className="mt-6 space-y-5">
      {/* idea */}
      <div className="card">
        <div className="label-scrpt">The idea</div>
        <p className="text-[13px] text-text-secondary leading-relaxed">{ms.idea}</p>
      </div>

      {/* plot options awaiting choice */}
      {ms.status === "plotting" && ms.plot_options.length > 0 && (
        <div className="card" style={{ borderLeft: "3px solid var(--accent)" }}>
          <div className="serif-display text-[18px] font-semibold">
            Three directions — pick one
          </div>
          <p className="text-[12px] text-text-tertiary mt-1">
            SCRPT drafts the full book from the direction you choose. Add notes
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
              {ms.chapters.filter((c) => c.blocks.length > 0).length} of {ms.chapters.length} drafted
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

      {hasPages && (
        <>
          <CoverSpecCard catalog={catalog} pageCount={interior.page_count!} />

          <div className="grid md:grid-cols-2 gap-5">
            {/* Path A: AI */}
            <div className="card">
              <div className="serif-display text-[17px] font-semibold">AI cover</div>
              <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">
                SCRPT designs the full wrap — artwork by image model, typography
                rendered as a crisp overlay, sized exactly for {interior.page_count} pages.
              </p>
              <div className="text-[12px] text-text-faint mt-3">
                The AI cover designer for fiction is being trained on the new
                genre templates — coming in the next update. Until then, use the
                designer package on the right.
              </div>
            </div>

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

function AudiobookTab({ book, reload, busy }: { book: ScrptBook; reload: () => void; busy: boolean }) {
  const audio = book.data.audio || {};
  const ms = book.data.manuscript as Manuscript;
  const drafted = ms.chapters.some((c) => c.blocks.length > 0);
  const [starting, setStarting] = useState(false);
  const [err, setErr] = useState("");

  return (
    <div className="mt-6 space-y-5">
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
            <button className="btn-brass shrink-0" disabled={!drafted || busy || starting}
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
            The manuscript must be drafted before narration.
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

// ── Publishing ───────────────────────────────────────────────────

function PublishingTab({ book, ms }: { book: ScrptBook; ms: Manuscript }) {
  const interior = book.data.interior || {};
  const cover = book.data.cover || {};
  const pages = interior.page_count || 0;
  const [price, setPrice] = useState<number>((book.data.list_price as number) || 12.99);

  // KDP US paperback B&W economics (docs/KDP_INTERIOR_SPEC.md)
  const printCost = pages > 0
    ? pages <= 110 ? 2.30 : 1.00 + pages * 0.012
    : 0;
  const rate = price >= 9.99 ? 0.6 : 0.5;
  const royalty = Math.max(0, rate * price - printCost);
  const ebookRoyalty = price >= 2.99 && price <= 9.99 ? price * 0.7 : price * 0.35;

  const checklist: { label: string; done: boolean; note?: string }[] = [
    { label: "Manuscript drafted", done: ms.status === "drafted" || ms.status === "editing" || ms.status === "locked" },
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
