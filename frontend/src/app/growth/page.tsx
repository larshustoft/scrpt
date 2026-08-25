"use client";

import { useCallback, useEffect, useState } from "react";
import { scrpt } from "@/lib/scrpt";

type KW = {
  phrase: string; demand: number; competing_titles: number | null;
  avg_price: number | null; opportunity: number; top_titles: string[];
};
type Study = { id: number; seed: string; store: string; created_at: string;
               result: { keywords: KW[]; kdp_slots?: string[] } };
type BookRow = { catalog_number: string; title: string };

const ENGINE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function get<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${ENGINE}${path}`);
    return r.ok ? ((await r.json()) as T) : null;
  } catch { return null; }
}

export default function GrowthPage() {
  const [report, setReport] = useState<string>("");
  const [books, setBooks] = useState<BookRow[]>([]);
  const [seed, setSeed] = useState("");
  const [catalog, setCatalog] = useState("");
  const [study, setStudy] = useState<Study | null>(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [budget, setBudget] = useState(8);
  const [plan, setPlan] = useState<Record<string, number | string> | null>(null);
  const [kdp, setKdp] = useState<{ signed_in?: boolean } | null>(null);
  const [shelf, setShelf] = useState<{ synced_at?: string | null;
    books: { title: string; author?: string; asins: string[]; is_scrpt?: boolean }[] } | null>(null);

  const loadReport = useCallback(async () => {
    try {
      const r = await fetch(`${ENGINE}/api/market/report/daily.txt`);
      setReport(await r.text());
    } catch { setReport("Engine offline."); }
  }, []);

  useEffect(() => {
    loadReport();
    scrpt.listBooks().then((d) => setBooks(d.books || [])).catch(() => {});
    get<{ signed_in: boolean }>("/api/market/kdp/status").then(setKdp);
    get<{ synced_at: string | null; books: [] }>("/api/market/kdp/bookshelf").then(setShelf);
  }, [loadReport]);

  const runResearch = async () => {
    if (!seed.trim()) return;
    setBusy("research"); setMsg("Mining Amazon autosuggest…"); setStudy(null);
    try {
      const res = await fetch(`${ENGINE}/api/market/keywords/research`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed, catalog, top_n: 25, check_competition: 10 }),
      });
      const { job_id } = await res.json();
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 4000));
        const j = await get<{ status: string; detail?: string }>(`/api/scrpt/jobs/${job_id}`);
        if (j?.detail) setMsg(j.detail);
        if (j?.status === "done" || j?.status === "error") {
          if (j.status === "error") setMsg("Research failed.");
          break;
        }
      }
      const s = await get<{ studies: Study[] }>(
        `/api/market/keywords/studies?limit=1${catalog ? `&catalog=${catalog}` : ""}`);
      if (s?.studies?.length) { setStudy(s.studies[0]); setMsg("Study complete."); }
    } finally { setBusy(""); }
  };

  const applySlots = async () => {
    if (!study || !catalog) { setMsg("Pick a book to apply these to."); return; }
    const keywords = study.result.kdp_slots || [];
    const r = await fetch(`${ENGINE}/api/market/keywords/apply/${catalog}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keywords }),
    });
    setMsg(r.ok ? `Seven slots written onto ${catalog}.` : "Could not apply.");
  };

  const loadPlan = async () => {
    if (!catalog) { setMsg("Pick a book first."); return; }
    const p = await get<Record<string, number | string>>(
      `/api/market/ads/plan/${catalog}?daily_budget=${budget}`);
    setPlan(p);
  };

  const card = "card";
  const label = "label-scrpt";

  return (
    <div className="px-16 py-10 space-y-6 max-w-[1180px]">
      <div>
        <h1 className="serif-display text-[26px] font-semibold">Growth</h1>
        <p className="text-[12.5px] text-text-tertiary mt-1">
          Keyword research, advertising economics, rank and royalties — the
          numbers that decide what SCRPT writes next.
        </p>
      </div>

      {/* daily report */}
      <div className={card}>
        <div className="flex items-center justify-between">
          <div className={label}>Daily report</div>
          <button className="btn-ghost text-[11px]" onClick={loadReport}>Refresh</button>
        </div>
        <pre className="mt-2 text-[12px] leading-relaxed whitespace-pre-wrap text-text-secondary">
{report || "…"}
        </pre>
      </div>

      {/* keyword research */}
      <div className={card}>
        <div className={label}>Keyword research</div>
        <p className="text-[12px] text-text-tertiary mt-1">
          Reads Amazon&apos;s own autosuggest and counts the competing titles.
          Opportunity rewards phrases readers search for and few books target.
        </p>
        <div className="flex gap-3 mt-3 flex-wrap items-center">
          <input className="input-scrpt flex-1 min-w-[240px] text-[12px]"
                 placeholder="a niche, e.g. regency romance"
                 value={seed} onChange={(e) => setSeed(e.target.value)} />
          <select className="input-scrpt text-[12px] max-w-[260px]"
                  value={catalog} onChange={(e) => setCatalog(e.target.value)}>
            <option value="">— attach to a book (optional) —</option>
            {books.map((b) => (
              <option key={b.catalog_number} value={b.catalog_number}>
                {b.catalog_number} · {b.title}
              </option>
            ))}
          </select>
          <button className="btn-brass text-[12px]" disabled={busy === "research"}
                  onClick={runResearch}>
            {busy === "research" ? "Researching…" : "Research"}
          </button>
        </div>
        {msg && <div className="text-[11px] text-text-tertiary mt-2">{msg}</div>}

        {study && (
          <div className="mt-4">
            <table className="w-full text-[12px]">
              <thead className="text-text-faint">
                <tr className="text-left">
                  <th className="py-1">Phrase</th>
                  <th className="py-1 text-right">Demand</th>
                  <th className="py-1 text-right">Competing</th>
                  <th className="py-1 text-right">Opportunity</th>
                </tr>
              </thead>
              <tbody>
                {study.result.keywords.slice(0, 14).map((k) => (
                  <tr key={k.phrase} className="border-t border-border-subtle">
                    <td className="py-1.5 text-text-secondary">{k.phrase}</td>
                    <td className="py-1.5 text-right">{k.demand}</td>
                    <td className="py-1.5 text-right">
                      {k.competing_titles?.toLocaleString() ?? "—"}
                    </td>
                    <td className="py-1.5 text-right font-medium text-accent">
                      {k.opportunity}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {study.result.kdp_slots && (
              <div className="mt-4 rounded-md p-3" style={{ background: "var(--surface-elevated)" }}>
                <div className="text-[11px] tracking-[0.1em] uppercase text-text-faint">
                  The seven KDP keyword slots
                </div>
                <ol className="mt-2 space-y-0.5 text-[12px] text-text-secondary">
                  {study.result.kdp_slots.map((s, i) => <li key={i}>{i + 1}. {s}</li>)}
                </ol>
                <button className="btn-ghost text-[11px] mt-3" onClick={applySlots}>
                  Apply to the selected book
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* advertising */}
      <div className={card}>
        <div className={label}>Advertising</div>
        <p className="text-[12px] text-text-tertiary mt-1">
          Give a book a daily budget; SCRPT works out what a reader is worth —
          including read-through across the series — and bids under break-even.
        </p>
        <div className="flex gap-3 mt-3 items-center flex-wrap">
          <input type="number" min={1} step={1} value={budget}
                 onChange={(e) => setBudget(Number(e.target.value))}
                 className="input-scrpt w-[120px] text-[12px]" />
          <button className="btn-ghost text-[12px]" onClick={loadPlan}>
            Plan the spend
          </button>
          {catalog && (
            <a className="btn-ghost text-[12px]"
               href={`${ENGINE}/api/market/ads/bulk-sheet/${catalog}`}
               onClick={async (e) => {
                 e.preventDefault();
                 const r = await fetch(`${ENGINE}/api/market/ads/bulk-sheet/${catalog}`, {
                   method: "POST", headers: { "Content-Type": "application/json" },
                   body: JSON.stringify({ daily_budget: budget }),
                 });
                 if (!r.ok) { setMsg("Run a keyword study first."); return; }
                 const blob = await r.blob();
                 const url = URL.createObjectURL(blob);
                 const a = document.createElement("a");
                 a.href = url; a.download = `${catalog}-ads.csv`; a.click();
                 URL.revokeObjectURL(url);
               }}>
              Download Amazon Ads sheet
            </a>
          )}
        </div>
        {plan && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
            {([
              ["Value per reader", `$${plan.value_per_reader}`],
              ["…of that, read-through", `$${plan.value_read_through}`],
              ["Break-even click", `$${plan.break_even_cpc}`],
              ["Starting bid", `$${plan.starting_bid}`],
              ["Royalty per sale", `$${plan.royalty_per_sale}`],
              ["Full KU read", `$${plan.royalty_per_full_read}`],
              ["Break-even ACOS", `${Math.round(Number(plan.break_even_acos) * 100)}%`],
              ["Target ACOS", `${Math.round(Number(plan.target_acos) * 100)}%`],
            ] as [string, string][]).map(([k, v]) => (
              <div key={k}>
                <div className="text-[10px] tracking-[0.1em] uppercase text-text-faint">{k}</div>
                <div className="text-[15px] text-text-primary mt-0.5">{v}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* KDP + data in */}
      <div className={card}>
        <div className={label}>Amazon KDP</div>
        <p className="text-[12px] text-text-tertiary mt-1">
          {kdp?.signed_in
            ? "Signed in. SCRPT can read the bookshelf and pull reports."
            : "Not signed in. SCRPT never types your password — sign in yourself in the window it opens."}
        </p>
        <div className="flex gap-3 mt-3 flex-wrap">
          <button className="btn-ghost text-[12px]"
                  onClick={async () => {
                    setMsg("Opening a sign-in window…");
                    await fetch(`${ENGINE}/api/market/kdp/login`, { method: "POST" });
                    setMsg("Sign in, then close that window.");
                  }}>Sign in to KDP</button>
          <button className="btn-ghost text-[12px]"
                  onClick={async () => {
                    setMsg("Reading the KDP bookshelf…");
                    await fetch(`${ENGINE}/api/market/kdp/sync-bookshelf`, { method: "POST" });
                    setMsg("Bookshelf sync started.");
                  }}>Sync bookshelf</button>
          <button className="btn-ghost text-[12px]"
                  onClick={async () => {
                    setMsg("Fetching KDP reports…");
                    await fetch(`${ENGINE}/api/market/kdp/reports`, { method: "POST" });
                    setMsg("Report download started.");
                  }}>Pull sales reports</button>
          <label className="btn-ghost text-[12px] cursor-pointer">
            Import a report file
            <input type="file" className="hidden" accept=".csv,.xlsx,.xls"
                   onChange={async (e) => {
                     const f = e.target.files?.[0]; if (!f) return;
                     const fd = new FormData(); fd.append("file", f);
                     const r = await fetch(`${ENGINE}/api/market/sales/import`,
                                           { method: "POST", body: fd });
                     const d = await r.json();
                     setMsg(r.ok ? `Imported ${d.imported} rows.` : "Import failed.");
                     loadReport();
                     e.target.value = "";
                   }} />
          </label>
        </div>
        {shelf?.books?.length ? (
          <div className="mt-5">
            <div className="text-[11px] tracking-[0.1em] uppercase text-text-faint mb-2">
              On your KDP account{shelf.synced_at ? ` · synced ${shelf.synced_at}` : ""}
            </div>
            <div className="space-y-1.5">
              {shelf.books.map((b, i) => (
                <div key={i} className="flex items-center justify-between gap-4 text-[12px]
                                        rounded-md px-3 py-2"
                     style={{ background: "var(--surface-elevated)" }}>
                  <div className="min-w-0">
                    <div className="text-text-secondary truncate">{b.title}</div>
                    <div className="text-[11px] text-text-faint">
                      {b.author || "—"} · {b.asins.length} format{b.asins.length > 1 ? "s" : ""}
                      {" · "}{b.asins.join(", ")}
                    </div>
                  </div>
                  {b.is_scrpt ? (
                    <span className="text-[10px] px-2 py-0.5 rounded shrink-0"
                          style={{ background: "rgba(70,140,90,0.2)", color: "var(--status-green)" }}>
                      SCRPT
                    </span>
                  ) : (
                    <span className="text-[10px] text-text-faint shrink-0">existing</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="mt-4 text-[11px] text-text-faint">
            No catalogue synced yet — sign in and press “Sync bookshelf”.
          </div>
        )}
      </div>
    </div>
  );
}
