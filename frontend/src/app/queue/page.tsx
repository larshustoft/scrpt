"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { pollJob, scrpt } from "@/lib/scrpt";

interface QueueRow {
  catalog_number: string; title: string; status: string; author: string;
  series_title: string; upload_date: string; release_date: string;
  assets: Record<string, boolean>; ready: boolean; due: boolean;
}

interface UploadPackage {
  metadata: { title: string; author: string; description: string;
    keywords: string[]; categories: string[]; ai_disclosure: string;
    series_title: string; series_number: number | null };
  print: { trim_size: string; paper: string; pages: number; price_usd: number;
    interior_pdf: string };
  ebook: { epub: string; cover_jpg: string; price_usd: number; royalty_note: string };
  audiobook: { mastered: boolean; cover_square: string;
    chapters: { title: string; file: string }[]; narrator_credit: string;
    portals: Record<string, string>; uploaded_to: Record<string, string> };
  kdp_portal: string;
}

const ASSET_LABELS: Record<string, string> = {
  manuscript: "Manuscript", quality: "Quality gate", interior_pdf: "Print PDF",
  epub: "EPUB", cover: "Cover", audiobook: "Audiobook",
};

export default function QueuePage() {
  const [queue, setQueue] = useState<QueueRow[]>([]);
  const [today, setToday] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [pkg, setPkg] = useState<UploadPackage | null>(null);
  const [busy, setBusy] = useState<Record<string, string>>({});
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);

  const reload = useCallback(async () => {
    const online = await scrpt.health();
    setEngineOnline(online);
    if (!online) return;
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/queue`);
      const d = await res.json();
      setQueue(d.queue);
      setToday(d.today);
    } catch { /* offline */ }
  }, []);

  useEffect(() => { reload(); const t = setInterval(reload, 15000); return () => clearInterval(t); }, [reload]);

  const prepare = async (catalog: string) => {
    setBusy((b) => ({ ...b, [catalog]: "Preparing…" }));
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/prepare/${catalog}`, { method: "POST" });
      const { job_id } = await res.json();
      await pollJob(job_id, (j) =>
        setBusy((b) => ({ ...b, [catalog]: j.detail || j.stage || "Preparing…" })));
      reload();
    } finally {
      setBusy((b) => { const c = { ...b }; delete c[catalog]; return c; });
    }
  };

  const openPackage = async (catalog: string) => {
    if (open === catalog) { setOpen(null); setPkg(null); return; }
    setOpen(catalog);
    const res = await fetch(`${scrpt.engineUrl}/api/scrpt/upload-package/${catalog}`);
    setPkg(await res.json());
  };

  const mark = async (catalog: string, status: string, platform = "") => {
    await fetch(`${scrpt.engineUrl}/api/scrpt/mark/${catalog}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, platform }),
    });
    reload();
    if (open === catalog) {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/upload-package/${catalog}`);
      setPkg(await res.json());
    }
  };

  const copy = (text: string) => navigator.clipboard?.writeText(text);

  const due = queue.filter((r) => r.due);
  const scheduled = queue.filter((r) => !r.due && r.upload_date && r.status !== "live");
  const unscheduled = queue.filter((r) => !r.upload_date && r.status !== "live");
  const live = queue.filter((r) => r.status === "live");

  return (
    <div className="max-w-[1150px] mx-auto px-8 py-12 fade-up">
      <h1 className="serif-display text-[32px] font-semibold">Production Queue</h1>
      <p className="text-[13px] text-text-secondary mt-1">
        The daily line: what to prepare, what to upload today ({today}), what is
        scheduled. Uploads stay manual by design — SCRPT stages everything.
      </p>

      {engineOnline === false && (
        <div className="card mt-8" style={{ borderLeft: "3px solid var(--status-amber)" }}>
          <div className="text-[13px] text-text-secondary">The engine is offline.</div>
        </div>
      )}

      {[
        { label: `Due for upload — today`, rows: due, accent: "var(--status-amber)" },
        { label: "Scheduled", rows: scheduled, accent: "" },
        { label: "Unscheduled", rows: unscheduled, accent: "" },
        { label: "Live", rows: live, accent: "var(--status-green)" },
      ].map(({ label, rows, accent }) => rows.length > 0 && (
        <section key={label} className="mt-8">
          <h2 className="serif-display text-[19px] font-semibold mb-3"
              style={accent ? { color: accent } : {}}>
            {label} <span className="text-[12px] text-text-faint font-sans">({rows.length})</span>
          </h2>
          <div className="space-y-3">
            {rows.map((r) => (
              <div key={r.catalog_number} className="card"
                   style={r.due ? { borderLeft: "3px solid var(--status-amber)" } : {}}>
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="flex-1 min-w-[220px]">
                    <Link href={`/shelf/${r.catalog_number}`}
                          className="text-[14px] font-semibold hover:text-accent transition-colors">
                      {r.title}
                    </Link>
                    <div className="text-[11px] text-text-faint mt-0.5">
                      {r.catalog_number} · {r.author || "no pen name"}
                      {r.series_title && ` · ${r.series_title}`}
                      {r.upload_date && ` · upload ${r.upload_date}`}
                      {r.release_date && ` · release ${r.release_date}`}
                    </div>
                  </div>
                  <div className="flex gap-1.5 flex-wrap">
                    {Object.entries(ASSET_LABELS).map(([k, lbl]) => (
                      <span key={k}
                            className="px-2 py-[3px] rounded text-[10px] tracking-[0.05em] uppercase"
                            style={{
                              background: r.assets[k] ? "rgba(93,161,115,0.12)" : "var(--surface-elevated)",
                              color: r.assets[k] ? "var(--status-green)" : "var(--text-faint)",
                              border: "1px solid var(--border-subtle)",
                            }}>
                        {lbl}
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2 items-center shrink-0">
                    {busy[r.catalog_number] ? (
                      <span className="text-[11px] text-text-tertiary pulse-soft max-w-[180px] truncate">
                        {busy[r.catalog_number]}
                      </span>
                    ) : (
                      <>
                        {!r.ready && (
                          <button className="btn-ghost text-[12px]"
                                  onClick={() => prepare(r.catalog_number)}>
                            Prepare all assets
                          </button>
                        )}
                        {r.ready && r.status !== "live" && (
                          <button className="btn-brass text-[12px]"
                                  onClick={() => openPackage(r.catalog_number)}>
                            {open === r.catalog_number ? "Close package" : "Upload package"}
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>

                {open === r.catalog_number && pkg && (
                  <div className="mt-5 pt-5 space-y-5" style={{ borderTop: "1px solid var(--border-subtle)" }}>
                    {/* metadata desk */}
                    <div>
                      <div className="label-scrpt">Listing metadata — click to copy</div>
                      <div className="flex flex-wrap gap-2">
                        {[
                          ["Title", pkg.metadata.title],
                          ["Author", pkg.metadata.author],
                          ["Description", pkg.metadata.description],
                          ["Keywords", pkg.metadata.keywords.join("; ")],
                          ["Categories", pkg.metadata.categories.join(" | ")],
                          ...(pkg.metadata.series_title
                            ? [["Series", `${pkg.metadata.series_title} #${pkg.metadata.series_number}`]] : []),
                        ].map(([k, v]) => (
                          <button key={k} className="btn-ghost text-[11px] max-w-[240px] truncate"
                                  title={String(v)} onClick={() => copy(String(v))}>
                            {k}
                          </button>
                        ))}
                      </div>
                      <div className="text-[11px] mt-2" style={{ color: "var(--status-amber)" }}>
                        {pkg.metadata.ai_disclosure}
                      </div>
                    </div>

                    {/* files + portals */}
                    <div className="grid md:grid-cols-3 gap-5">
                      <div>
                        <div className="label-scrpt">Print — ${pkg.print.price_usd} · {pkg.print.pages}pp · {pkg.print.trim_size}</div>
                        <a className="btn-ghost text-[11px]" href={`${scrpt.engineUrl}${pkg.print.interior_pdf}`}>
                          Interior PDF
                        </a>
                      </div>
                      <div>
                        <div className="label-scrpt">Ebook — ${pkg.ebook.price_usd} suggested</div>
                        <div className="flex gap-2 flex-wrap">
                          <a className="btn-ghost text-[11px]" href={`${scrpt.engineUrl}${pkg.ebook.epub}`}>EPUB</a>
                          <a className="btn-ghost text-[11px]" href={`${scrpt.engineUrl}${pkg.ebook.cover_jpg}`}>Cover</a>
                        </div>
                        <div className="text-[10px] text-text-faint mt-1">{pkg.ebook.royalty_note}</div>
                      </div>
                      <div>
                        <div className="label-scrpt">
                          Audiobook {pkg.audiobook.mastered ? `— ${pkg.audiobook.chapters.length} files` : "— not produced"}
                        </div>
                        {pkg.audiobook.mastered && (
                          <a className="btn-ghost text-[11px]"
                             href={`${scrpt.engineUrl}${pkg.audiobook.cover_square}`}>
                            Square cover
                          </a>
                        )}
                        <div className="text-[10px] text-text-faint mt-1">{pkg.audiobook.narrator_credit}</div>
                      </div>
                    </div>

                    {/* portals + status */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <a className="btn-brass text-[12px]" href={pkg.kdp_portal}
                         target="_blank" rel="noreferrer">Open KDP</a>
                      {pkg.audiobook.mastered && Object.entries(pkg.audiobook.portals).map(([name, url]) => (
                        <a key={name} className="btn-ghost text-[11px] capitalize"
                           href={url} target="_blank" rel="noreferrer"
                           style={pkg.audiobook.uploaded_to[name]
                             ? { color: "var(--status-green)", borderColor: "var(--status-green)" } : {}}
                           onAuxClick={() => {}}>
                          {name.replace("_", " ")}
                          {pkg.audiobook.uploaded_to[name] ? " ✓" : ""}
                        </a>
                      ))}
                      <span className="flex-1" />
                      {pkg.audiobook.mastered && (
                        <select className="input-scrpt w-auto text-[11px] py-1"
                                defaultValue=""
                                onChange={(e) => { if (e.target.value) { mark(r.catalog_number, "", e.target.value); e.target.value = ""; } }}>
                          <option value="" disabled>Mark audio uploaded to…</option>
                          {Object.keys(pkg.audiobook.portals).map((p) => (
                            <option key={p} value={p}>{p.replace("_", " ")}</option>
                          ))}
                        </select>
                      )}
                      {r.status !== "in_review" && (
                        <button className="btn-ghost text-[12px]"
                                onClick={() => mark(r.catalog_number, "in_review")}>
                          Mark uploaded to KDP
                        </button>
                      )}
                      <button className="btn-ghost text-[12px]"
                              style={{ color: "var(--status-green)" }}
                              onClick={() => mark(r.catalog_number, "live")}>
                        Mark live
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}

      {queue.length === 0 && engineOnline && (
        <div className="card mt-10 text-center py-14">
          <div className="serif-display text-[20px] font-semibold">The line is empty</div>
          <p className="text-[13px] text-text-secondary mt-2">
            Commission books and set their upload dates — the queue runs the days.
          </p>
        </div>
      )}
    </div>
  );
}
