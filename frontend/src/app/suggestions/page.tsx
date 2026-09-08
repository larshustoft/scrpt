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
  cover?: string; cover_at?: string; publisher_notes?: string;
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

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/suggestions`);
      if (r.ok) { const j = await r.json(); setRows(j.suggestions || []); setLastResearch(j.last_research || ""); }
    } catch { /* engine offline */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  const waitJob = async (jobId: string) => {
    for (let i = 0; i < 120; i++) {
      await new Promise((res) => setTimeout(res, 3000));
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/jobs/${jobId}`);
      const j = await r.json();
      if (j.status && j.status !== "running") return j;
    }
    return null;
  };

  const research = async () => {
    setBusy("research"); setMsg("Reading the market — a few minutes.");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/suggestions/research`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ n: 8, notes }) });
      const { job_id } = await r.json();
      const j = await waitJob(job_id);
      setMsg(j?.status === "done" ? `${j.result?.count ?? 0} new suggestions.` : `Research ${j?.status || "timed out"}: ${j?.error || ""}`);
      await load();
    } catch { setMsg("The engine is offline."); }
    setBusy("");
  };

  const decide = async (ids: string[], action: "approve" | "reject") => {
    if (!ids.length) return;
    setBusy(action); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/suggestions/${action}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }) });
      const j = await r.json();
      if (action === "approve") {
        const ok = (j.results || []).filter((x: { ok: boolean }) => x.ok).length;
        setMsg(`${ok} of ${ids.length} commissioned — writing has started; the release desk takes them from here.`);
      } else setMsg(`${ids.length} set aside.`);
      await load();
    } catch { setMsg("The engine is offline."); }
    setBusy("");
  };

  const covers = async (ids: string[]) => {
    if (!ids.length) return;
    setBusy("covers"); setMsg(`Designing ${ids.length} cover${ids.length > 1 ? "s" : ""} — about a minute each.`);
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/suggestions/covers`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }) });
      const { job_id } = await r.json();
      const j = await waitJob(job_id);
      setMsg(j?.status === "done" ? `${(j.result?.done || []).length} cover(s) designed.` : `Covers ${j?.status || "timed out"}: ${j?.error || ""}`);
      await load();
    } catch { setMsg("The engine is offline."); }
    setBusy("");
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
  const decideHere = async (r: Suggestion, action: "approve" | "reject") => {
    await decide([r.id], action);            // the row leaves this list; the index now points at the next book
  };

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
                <button className="btn-brass text-[12px]" disabled={!!busy} onClick={() => decideHere(cur, "approve")}>Approve</button>
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
          <button className="btn-brass text-[12px]" disabled={!!busy} onClick={() => decide(shown.map((r) => r.id), "approve")}>
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
          <div className="shrink-0" style={{ width: 132 }}>
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
              <button className="btn-brass text-[12px]" disabled={!!busy} onClick={() => decide([s.id], "approve")}>Approve</button>
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
