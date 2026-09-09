"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { scrpt } from "@/lib/scrpt";

interface Suggestion {
  id: string; created_at: string; status: string; catalog?: string | null;
  title: string; kind: string; genre_preset: string; series_title?: string; series_books?: number;
  pen_name?: string; pitch?: string; why?: string; comparables?: string[]; target_words?: number;
  price_kindle?: number; price_paperback?: number; cover_direction?: string; season?: string;
  estimate_monthly_usd?: { conservative?: number; realistic?: number; stretch?: number }; confidence?: string;
  cover?: string; cover_at?: string; publisher_notes?: string; universe?: string; niche?: string;
  niche_data?: { seed?: string; competing_titles?: number; measured?: number; units_month_top?: number; median_units_month?: number;
                 avg_price?: number; revenue_month_top?: number; new_book_units_month?: { conservative?: number; realistic?: number; stretch?: number };
                 leaders?: { title: string; bsr: number; price?: number }[]; measured_at?: string };
}

/** SUGGESTED BOOKS — the acquisitions desk. SCRPT reads the market and lays
 *  out concrete books to commission; the publisher okays them one by one or
 *  all at once, and each one is written, edited, designed and uploaded. */
export default function SuggestionsPage() {
  const [rows, setRows] = useState<Suggestion[]>([]);
  const [lastResearch, setLastResearch] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [notes, setNotes] = useState("");
  const [tab, setTab] = useState<"new" | "approved" | "rejected">("new");
  const [big, setBig] = useState<number | null>(null);   // index into the visible list
  const [designing, setDesigning] = useState<Record<string, number>>({});   // id -> started at (ms)
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!Object.keys(designing).length) return;
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [designing]);
  const EXPECT_MS = 100_000;   // a cover usually takes about a minute and a half

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/suggestions`);
      if (r.ok) { const j = await r.json(); setRows(j.suggestions || []); setLastResearch(j.last_research || ""); }
    } catch { /* engine offline */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  type JobRow = { status?: string; progress?: number; stage?: string; detail?: string; result?: { count?: number; done?: unknown[] }; error?: string };
  const waitJob = async (jobId: string, onTick?: (j: JobRow) => void) => {
    for (let i = 0; i < 240; i++) {
      await new Promise((res) => setTimeout(res, 3000));
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/jobs/${jobId}`);
      const j = (await r.json()) as JobRow;
      onTick?.(j);
      if (j.status && j.status !== "running") return j;
    }
    return null;
  };

  // "Research more" progress (Lars, 2026-09-08): reading the market is one long
  // call (~2 min), then a cover per book (~100 s each, three at a time). The
  // engine reports its stage; the ring fills with the engine's fraction or the
  // expected time, whichever is further, and never past 95% until it returns.
  const RESEARCH_N = 8;
  const RESEARCH_EXPECT_MS = 120_000 + Math.ceil(RESEARCH_N / 3) * EXPECT_MS;
  const [researchRun, setResearchRun] = useState<{ startedAt: number; fraction: number; detail: string } | null>(null);

  const research = async () => {
    setBusy("research"); setMsg("");
    const startedAt = Date.now();
    setResearchRun({ startedAt, fraction: 0, detail: "Reading the market" });
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/suggestions/research`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ n: RESEARCH_N, notes }) });
      const { job_id } = await r.json();
      const j = await waitJob(job_id, (row) => setResearchRun({ startedAt, fraction: row.progress || 0, detail: row.detail || row.stage || "" }));
      setMsg(j?.status === "done" ? `${j.result?.count ?? 0} new suggestions.` : `Research ${j?.status || "timed out"}: ${j?.error || ""}`);
      await load();
    } catch { setMsg("The engine is offline."); }
    setResearchRun(null);
    setBusy("");
  };

  /** The small ring beside the button: engine fraction vs elapsed time, and the minutes left. */
  const ResearchRing = ({ run }: { run: { startedAt: number; fraction: number; detail: string } }) => {
    void tick;
    const elapsed = Date.now() - run.startedAt;
    const pct = Math.min(95, Math.max(Math.round(run.fraction * 100), Math.round((elapsed / RESEARCH_EXPECT_MS) * 100)));
    const leftMs = Math.max(0, RESEARCH_EXPECT_MS * (1 - pct / 100));
    const left = leftMs < 60_000 ? "under a minute left" : `about ${Math.ceil(leftMs / 60_000)} min left`;
    const r = 11, c = 2 * Math.PI * r;
    return (
      <div className="flex items-center gap-2 text-[11.5px] text-text-secondary" aria-live="polite">
        <svg width="28" height="28" viewBox="0 0 28 28" aria-label={`research ${pct}%`}>
          <circle cx="14" cy="14" r={r} fill="none" stroke="rgba(128,128,128,.3)" strokeWidth="3" />
          <circle cx="14" cy="14" r={r} fill="none" stroke="#c9a45c" strokeWidth="3" strokeLinecap="round"
                  strokeDasharray={`${c}`} strokeDashoffset={`${c * (1 - pct / 100)}`}
                  transform="rotate(-90 14 14)" style={{ transition: "stroke-dashoffset .9s linear" }} />
        </svg>
        <span>{pct}% · {run.detail || "Reading the market"} · {left}</span>
      </div>
    );
  };

  // scope "series": every planned book is commissioned and written one after
  // another; "first": only book one, the rest of the series stays a plan
  // (Lars, 2026-09-08: "only commit to create one of them")
  const decide = async (ids: string[], action: "approve" | "reject", scope: "series" | "first" = "series") => {
    if (!ids.length) return;
    setBusy(action); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/suggestions/${action}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(action === "approve" ? { ids, commission_all: scope === "series" } : { ids }) });
      const j = await r.json();
      if (action === "approve") {
        const res = (j.results || []).filter((x: { ok: boolean }) => x.ok) as { ok: boolean; scope?: string; books?: number }[];
        const series = res.filter((x) => x.scope === "series");
        const extra = series.reduce((n, x) => n + Math.max(0, (x.books || 1) - 1), 0);
        setMsg(`${res.length} of ${ids.length} commissioned — writing has started; the release desk takes them from here.` +
          (extra ? ` ${series.length} series approved in full: ${extra} later book${extra > 1 ? "s" : ""} will be written one after another.` : ""));
      } else setMsg(`${ids.length} set aside.`);
      await load();
    } catch { setMsg("The engine is offline."); }
    setBusy("");
  };

  const covers = async (ids: string[]) => {
    if (!ids.length) return;
    setBusy("covers"); setMsg(`Designing ${ids.length} cover${ids.length > 1 ? "s" : ""} — about a minute and a half each.`);
    const started = Date.now();
    setDesigning((d) => ({ ...d, ...Object.fromEntries(ids.map((id) => [id, started])) }));
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/suggestions/covers`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }) });
      const { job_id } = await r.json();
      const j = await waitJob(job_id);
      setMsg(j?.status === "done" ? `${(j.result?.done || []).length} cover(s) designed.` : `Covers ${j?.status || "timed out"}: ${j?.error || ""}`);
      await load();
    } catch { setMsg("The engine is offline."); }
    setDesigning((d) => { const n = { ...d }; ids.forEach((id) => delete n[id]); return n; });
    setBusy("");
  };

  /** A progress ring over a cover while its redesign runs: fills with the
   *  expected time (never past 95%), completes when the job returns. */
  const Ring = ({ startedAt }: { startedAt: number }) => {
    void tick;
    const pct = Math.min(95, Math.round(((Date.now() - startedAt) / EXPECT_MS) * 100));
    const r = 26, c = 2 * Math.PI * r;
    return (
      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
                    background: "rgba(0,0,0,.55)", borderRadius: 4 }}>
        <svg width="72" height="72" viewBox="0 0 72 72" aria-label={`designing, ${pct}%`}>
          <circle cx="36" cy="36" r={r} fill="none" stroke="rgba(255,255,255,.25)" strokeWidth="5" />
          <circle cx="36" cy="36" r={r} fill="none" stroke="#c9a45c" strokeWidth="5" strokeLinecap="round"
                  strokeDasharray={`${c}`} strokeDashoffset={`${c * (1 - pct / 100)}`}
                  transform="rotate(-90 36 36)" style={{ transition: "stroke-dashoffset .9s linear" }} />
          <text x="36" y="40" textAnchor="middle" fontSize="13" fill="#fff" fontWeight={600}>{pct}%</text>
        </svg>
      </div>
    );
  };

  const saveNotes = async (id: string, notes: string) => {
    try {
      await fetch(`${scrpt.engineUrl}/api/scrpt/suggestions/${id}/notes`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ notes }) });
      setRows((rs) => rs.map((r) => (r.id === id ? { ...r, publisher_notes: notes } : r)));
    } catch { /* engine offline */ }
  };

  const shown = rows.filter((r) => r.status === tab);
  const money = (n?: number) => (n == null ? "–" : `$${Math.round(n).toLocaleString()}`);
  const coverUrl = (r: Suggestion) => `${scrpt.engineUrl}/api/scrpt/suggestions/${r.id}/cover.png?v=${r.cover_at || ""}`;
  const shortPitch = (t?: string) => {
    const sents = (t || "").replace(/\s+/g, " ").match(/[^.!?]+[.!?]+/g) || [t || ""];
    return sents.slice(0, 3).join(" ").trim();
  };
  // what was READ OFF AMAZON for this niche (the Bookbeam method, Lars 2026-09-09) — shown before any opinion
  const measuredLine = (r: Suggestion) => {
    const d = r.niche_data; if (!d || !d.measured) return "";
    const nb = d.new_book_units_month || {};
    return `Measured on Amazon (${(d.measured_at || "").slice(0, 10)}): "${d.seed}" · ${d.competing_titles?.toLocaleString() ?? "?"} competing titles · ` +
      `top ${d.measured} sell about ${d.units_month_top?.toLocaleString()} units a month (≈${money(d.revenue_month_top)}) · median title ${d.median_units_month} a month · ` +
      `avg price ${money(d.avg_price)} · a new title landing mid-page: ${nb.conservative}/${nb.realistic}/${nb.stretch} units a month.`;
  };
  const marketLine = (r: Suggestion) => {
    const first = ((r.why || "").match(/[^.!?]+[.!?]/) || [""])[0].trim();
    const e = r.estimate_monthly_usd || {};
    return `${first}${first ? " " : ""}Realistic ${money(e.realistic)} a month per book for a new pen name, ${money(e.conservative)} to ${money(e.stretch)}.`;
  };
  const cur = big != null && big >= 0 && big < shown.length ? shown[big] : null;
  const step = useCallback((d: number) => {
    setBig((i) => (i == null ? i : Math.max(0, Math.min(shown.length - 1, i + d))));
  }, [shown.length]);
  useEffect(() => {
    if (big == null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;
      if (e.key === "Escape") setBig(null);
      if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); step(1); }
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); step(-1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [big, step]);
  useEffect(() => { if (big != null && big >= shown.length) setBig(shown.length ? shown.length - 1 : null); }, [shown.length, big]);
  const decideHere = async (r: Suggestion, action: "approve" | "reject", scope: "series" | "first" = "series") => {
    await decide([r.id], action, scope);     // the row leaves this list; the index now points at the next book
  };
  const isSeries = (r: Suggestion) => !!r.series_title && (r.series_books || 1) > 1;

  return (<>
    {cur && typeof document !== "undefined" && createPortal(
      <div onClick={() => setBig(null)} role="dialog" aria-label={cur.title}
           style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(0,0,0,.84)", display: "flex", alignItems: "center",
                    justifyContent: "center", padding: 24 }}>
        <div onClick={(e) => e.stopPropagation()}
             style={{ display: "flex", gap: 28, alignItems: "stretch", maxWidth: "94vw", maxHeight: "92vh" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={coverUrl(cur)} alt={cur.title}
               style={{ height: "88vh", maxWidth: "58vw", objectFit: "contain", borderRadius: 6, boxShadow: "0 24px 80px rgba(0,0,0,.6)" }} />
          <div style={{ width: 380, maxWidth: "36vw", display: "flex", flexDirection: "column", justifyContent: "center", color: "#f2ede4" }}>
            <div className="serif-display" style={{ fontSize: 26, fontWeight: 600, lineHeight: 1.15 }}>{cur.title}</div>
            <div style={{ fontSize: 12, opacity: .7, marginTop: 6 }}>
              {cur.kind} · {cur.genre_preset.replace(/_/g, " ")}{cur.series_title ? ` · ${cur.series_title}, ${cur.series_books || 1} books` : " · standalone"}{cur.pen_name ? ` · ${cur.pen_name}` : ""}
            </div>
            <p style={{ fontSize: 14, lineHeight: 1.55, marginTop: 16 }}>{shortPitch(cur.pitch)}</p>
            <p style={{ fontSize: 12.5, lineHeight: 1.5, marginTop: 12, opacity: .8 }}>{marketLine(cur)}</p>
            {cur.publisher_notes && <p style={{ fontSize: 12, marginTop: 10, opacity: .7 }}>Your notes: {cur.publisher_notes}</p>}
            <div style={{ display: "flex", gap: 8, marginTop: 22, alignItems: "center" }}>
              {cur.status === "new" ? (<>
                <button className="btn-brass text-[12px]" disabled={!!busy} onClick={() => decideHere(cur, "approve", "series")}>
                  {isSeries(cur) ? `Approve book series (${cur.series_books})` : "Approve"}
                </button>
                {isSeries(cur) && <button className="btn-ghost text-[12px]" disabled={!!busy} title="Only book one is written; the rest stays a plan"
                  onClick={() => decideHere(cur, "approve", "first")}>Create first book</button>}
                <button className="btn-ghost text-[12px]" disabled={!!busy} onClick={() => decideHere(cur, "reject")}>Set aside</button>
              </>) : <span style={{ fontSize: 12, opacity: .7 }}>{cur.status === "approved" ? "in production" : "set aside"}</span>}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 18, alignItems: "center", fontSize: 12, opacity: .65 }}>
              <button className="btn-ghost text-[12px]" disabled={big === 0} onClick={() => step(-1)}>← Previous</button>
              <button className="btn-ghost text-[12px]" disabled={big === shown.length - 1} onClick={() => step(1)}>Next →</button>
              <span style={{ marginLeft: "auto" }}>{(big ?? 0) + 1} of {shown.length} · arrow keys · Esc closes</span>
            </div>
          </div>
        </div>
      </div>, document.body)}
    <div className="max-w-[980px] mx-auto px-8 py-10 fade-up">

      <div className="flex items-end justify-between gap-6 flex-wrap">
        <div>
          <h1 className="serif-display text-[32px] font-semibold">Suggested Books</h1>
          <p className="text-[13px] text-text-secondary mt-1 max-w-[62ch]">
            SCRPT reads the live market and proposes books it can write, edit, design and upload by itself.
            Approve one, or all of them, and they go into production. Nothing else is needed from you.
          </p>
          {lastResearch && <div className="text-[11px] text-text-tertiary mt-1">Last research {lastResearch.replace("T", " ")}</div>}
        </div>
        <div className="flex items-center gap-2">
          <input className="input-scrpt text-[12px]" style={{ width: 260 }} placeholder="Notes for the next research (optional)"
                 value={notes} onChange={(e) => setNotes(e.target.value)} />
          {researchRun && <ResearchRing run={researchRun} />}
          <button className="btn-ghost text-[12px]" disabled={!!busy} onClick={research}>
            {busy === "research" ? "Researching…" : "Research more"}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 mt-6">
        {(["new", "approved", "rejected"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
                  className={`px-3 py-[5px] rounded-md text-[12.5px] font-medium ${tab === t ? "text-accent bg-accent-subtle" : "text-text-tertiary hover:text-text-primary"}`}>
            {t === "new" ? "To decide" : t === "approved" ? "In production" : "Set aside"} ({rows.filter((r) => r.status === t).length})
          </button>
        ))}
        <div className="flex-1" />
        {tab === "new" && shown.some((r) => !r.cover) && (
          <button className="btn-ghost text-[12px]" disabled={!!busy} onClick={() => covers(shown.filter((r) => !r.cover).map((r) => r.id))}>
            {busy === "covers" ? "Designing…" : "Design all covers"}
          </button>
        )}
        {tab === "new" && shown.length > 0 && (
          <button className="btn-brass text-[12px]" disabled={!!busy} title="Series are approved in full and written one book after another"
            onClick={() => decide(shown.map((r) => r.id), "approve", "series")}>
            {busy === "approve" ? "Commissioning…" : `Approve all ${shown.length}`}
          </button>
        )}
      </div>
      {msg && <div className="text-[12px] text-text-secondary mt-3">{msg}</div>}

      {shown.length === 0 && (
        <div className="card mt-6 text-[13px] text-text-secondary">
          {tab === "new" ? "No open suggestions. Press Research more." : "Nothing here yet."}
        </div>
      )}

      {shown.map((s) => (
        <div key={s.id} className="card mt-4">
          <div className="flex items-start gap-5">
          <div className="shrink-0" style={{ width: 132, position: "relative" }}>
            {designing[s.id] && <Ring startedAt={designing[s.id]} />}
            {s.cover ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={`${scrpt.engineUrl}/api/scrpt/suggestions/${s.id}/cover.png?v=${s.cover_at || ""}`} alt={s.title}
                   title="Click to see it large"
                   onClick={() => setBig(shown.findIndex((r) => r.id === s.id))}
                   style={{ width: 132, aspectRatio: "2 / 3", objectFit: "cover", borderRadius: 4, boxShadow: "0 6px 18px rgba(0,0,0,.35)", cursor: "zoom-in" }} />
            ) : (
              <button className="btn-ghost text-[11px]" style={{ width: 132, aspectRatio: "2 / 3" }} disabled={!!busy}
                      onClick={() => covers([s.id])}>{busy === "covers" ? "Designing…" : "Design the cover"}</button>
            )}
          </div>
          <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="serif-display text-[19px] font-semibold">{s.title}</div>
              <div className="text-[12px] text-text-tertiary mt-[2px]">
                {s.kind} · {s.genre_preset}{s.series_title ? ` · ${s.series_title}, ${s.series_books || 1} books` : " · standalone"}
                {s.pen_name ? ` · ${s.pen_name}` : ""}{s.season ? ` · ${s.season}` : ""}
                {s.target_words ? ` · ${s.target_words.toLocaleString()} words` : ""}
                {s.price_kindle ? ` · Kindle $${s.price_kindle}` : ""}{s.price_paperback ? ` · paperback $${s.price_paperback}` : ""}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="label-scrpt">Monthly, per book</div>
              <div className="text-[12.5px] tabular-nums">
                {money(s.estimate_monthly_usd?.conservative)} · <span className="font-semibold">{money(s.estimate_monthly_usd?.realistic)}</span> · {money(s.estimate_monthly_usd?.stretch)}
              </div>
              <div className="text-[11px] text-text-tertiary">conservative · realistic · stretch{s.confidence ? ` · ${s.confidence} confidence` : ""}</div>
            </div>
          </div>
          {s.pitch && <p className="text-[13.5px] mt-3 leading-relaxed">{s.pitch}</p>}
          {s.why && <p className="text-[12.5px] text-text-secondary mt-2 leading-relaxed"><span className="font-medium text-text-primary">Why: </span>{s.why}</p>}
          {measuredLine(s) && <p className="text-[12px] text-text-secondary mt-1 leading-relaxed"><span className="font-medium text-text-primary">Measured: </span>{measuredLine(s)}</p>}
          {s.comparables && s.comparables.length > 0 && (
            <p className="text-[12px] text-text-tertiary mt-2">Comparable: {s.comparables.join(" · ")}</p>
          )}
          {s.status === "new" && (
            <div className="mt-3">
              <div className="label-scrpt">Your notes for the finished book</div>
              <textarea className="input-scrpt text-[12.5px]" rows={2} placeholder="Anything the book must do or avoid — tone, names, scenes, what to leave out. Carried into the work order when you approve."
                        defaultValue={s.publisher_notes || ""}
                        onBlur={(e) => { if ((e.target.value || "") !== (s.publisher_notes || "")) saveNotes(s.id, e.target.value); }} />
            </div>
          )}
          {s.status !== "new" && s.publisher_notes && (
            <p className="text-[12px] text-text-tertiary mt-2"><span className="font-medium text-text-secondary">Your notes: </span>{s.publisher_notes}</p>
          )}
          <div className="flex items-center gap-2 mt-4">
            {s.status === "new" && (<>
              <button className="btn-brass text-[12px]" disabled={!!busy} onClick={() => decide([s.id], "approve", "series")}>
                {isSeries(s) ? `Approve book series (${s.series_books})` : "Approve"}
              </button>
              {isSeries(s) && <button className="btn-ghost text-[12px]" disabled={!!busy} title="Only book one is written; the rest stays a plan"
                onClick={() => decide([s.id], "approve", "first")}>Create first book</button>}
              <button className="btn-ghost text-[12px]" disabled={!!busy} onClick={() => decide([s.id], "reject")}>Set aside</button>
            </>)}
            {s.status === "approved" && s.catalog && (
              <Link href={`/shelf/${s.catalog}`} className="btn-ghost text-[12px]">In production · open {s.title}</Link>
            )}
            {s.status === "approved" && !s.catalog && <span className="text-[12px] text-text-tertiary">approved</span>}
            {s.cover && s.status === "new" && (
              <button className="btn-ghost text-[11px]" disabled={!!busy} onClick={() => covers([s.id])}>Redesign cover</button>
            )}
            <span className="text-[11px] text-text-tertiary ml-auto">{s.created_at?.replace("T", " ")}</span>
          </div>
          </div>
          </div>
        </div>
      ))}
    </div>
  </>);
}
