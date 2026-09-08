"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { scrpt } from "@/lib/scrpt";

interface Suggestion {
  id: string; created_at: string; status: string; catalog?: string | null;
  title: string; kind: string; genre_preset: string; series_title?: string; series_books?: number;
  pen_name?: string; pitch?: string; why?: string; comparables?: string[]; target_words?: number;
  price_kindle?: number; price_paperback?: number; cover_direction?: string; season?: string;
  estimate_monthly_usd?: { conservative?: number; realistic?: number; stretch?: number }; confidence?: string;
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

  const shown = rows.filter((r) => r.status === tab);
  const money = (n?: number) => (n == null ? "–" : `$${Math.round(n).toLocaleString()}`);

  return (
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
          <div className="flex items-center gap-2 mt-4">
            {s.status === "new" && (<>
              <button className="btn-brass text-[12px]" disabled={!!busy} onClick={() => decide([s.id], "approve")}>Approve</button>
              <button className="btn-ghost text-[12px]" disabled={!!busy} onClick={() => decide([s.id], "reject")}>Set aside</button>
            </>)}
            {s.status === "approved" && s.catalog && (
              <Link href={`/shelf/${s.catalog}`} className="btn-ghost text-[12px]">In production · open {s.title}</Link>
            )}
            {s.status === "approved" && !s.catalog && <span className="text-[12px] text-text-tertiary">approved</span>}
            <span className="text-[11px] text-text-tertiary ml-auto">{s.created_at?.replace("T", " ")}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
