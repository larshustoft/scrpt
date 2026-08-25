"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { scrpt } from "@/lib/scrpt";

type Fmt = { royalty: number; units: number; kenp_pages: number };
type BookRow = {
  key: string; catalog_number: string | null; title: string; asins: string[];
  royalty: number; units: number; kenp_pages: number; free_units: number;
  royalty_30: number; royalty_prev_30: number; units_30: number; trend: number | null;
  royalty_per_unit: number | null; formats: Record<string, Fmt>;
  first: string; last: string; marketplaces: string[]; series?: string | null; book_number?: number | null;
};
type Overview = {
  base: string; rates_per_usd: Record<string, number>;
  kpi: { this_month: number; last_month: number; last_90: number; trailing_12: number; all_time: number;
         units_30: number; kenp_30: number; units_all: number; kenp_all: number };
  by_month: { month: string; royalty: number; units: number; kenp_pages: number; ebook: number; paperback: number; hardcover: number; kenp: number; estimate: boolean }[];
  by_marketplace: { marketplace: string; royalty: number; units: number; kenp_pages: number }[];
  books: BookRow[];
  payments: { payment_date: string; period: string; marketplace: string; amount: number; currency: string; amount_base: number; method: string; status: string }[];
  paid_total: number;
  imports: { file: string; kind: string; rows: number; added: number; first_date: string | null; last_date: string | null; imported_at: string }[];
  unmatched: { title: string; asin: string; royalty: number }[];
  coverage: { month: string; state: "final" | "estimate" | "missing" }[];
  has_data: boolean;
};
type SeriesData = Awaited<ReturnType<typeof scrpt.reportsSeries>>;
type ShelfBook = { catalog_number: string; title: string };

const CURRENCIES = ["EUR", "USD", "GBP", "NOK", "SEK", "CAD", "AUD"];
const FORMAT_COLOR: Record<string, string> = {
  ebook: "var(--accent)", paperback: "#8fa3b8", hardcover: "#b88f8f", kenp: "#6f9d7e",
};

function money(v: number | null | undefined, cur: string) {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: cur, maximumFractionDigits: v >= 100 ? 0 : 2 }).format(v);
}
function monthLabel(m: string) {
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo - 1, 1).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

export default function AnalyticsPage() {
  const [o, setO] = useState<Overview | null>(null);
  const [seriesData, setSeriesData] = useState<SeriesData | null>(null);
  const [shelf, setShelf] = useState<ShelfBook[]>([]);
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState("");
  const [dragging, setDragging] = useState(false);
  const [adBudget, setAdBudget] = useState(1000);
  const [showRates, setShowRates] = useState(false);
  const [sync, setSync] = useState<{ enabled: boolean; weekday: number; hour: number; last_run: string | null;
    last_result: { signed_in?: boolean; imported?: number; errors?: string[]; files?: { file: string; added: number; rows: number }[] } | null; backfilled: boolean } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [rateEdits, setRateEdits] = useState<Record<string, string>>({});
  const fileRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    const online = await scrpt.health();
    setEngineOnline(online);
    if (!online) return;
    try {
      const [ov, sr, bs] = await Promise.all([
        fetch(`${scrpt.engineUrl}/api/scrpt/reports/overview`).then((r) => r.json()),
        scrpt.reportsSeries().catch(() => null),
        fetch(`${scrpt.engineUrl}/api/scrpt/books`).then((r) => r.json()).catch(() => ({ books: [] })),
      ]);
      setO(ov);
      setSeriesData(sr);
      fetch(`${scrpt.engineUrl}/api/scrpt/reports/sync`).then((r) => r.json()).then(setSync).catch(() => {});
      setShelf(((bs.books || bs) as ShelfBook[]).map((b) => ({ catalog_number: b.catalog_number, title: b.title })));
    } catch { /* nothing imported yet */ }
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const onFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setImporting(true); setImportMsg("");
    const lines: string[] = [];
    try {
      for (const f of Array.from(files)) {
        const r = await scrpt.importReport(f) as unknown as { file: string; total_added: number; total_rows: number; kinds: string[]; first_date: string | null; last_date: string | null };
        lines.push(`${f.name}: ${r.total_added} new of ${r.total_rows} rows (${(r.kinds || []).join(", ")}${r.first_date ? `, ${r.first_date} → ${r.last_date}` : ""})`);
      }
      setImportMsg(lines.join(" · "));
      reload();
    } catch (e) {
      setImportMsg(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  const setBase = async (base: string) => {
    await fetch(`${scrpt.engineUrl}/api/scrpt/reports/fx`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ base }) });
    reload();
  };
  const saveRates = async () => {
    const rates: Record<string, number> = {};
    for (const [k, v] of Object.entries(rateEdits)) if (v && !isNaN(Number(v))) rates[k] = Number(v);
    await fetch(`${scrpt.engineUrl}/api/scrpt/reports/fx`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rates }) });
    setRateEdits({}); setShowRates(false); reload();
  };
  const runSync = async (backfill = false) => {
    setSyncing(true);
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/reports/sync`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ backfill }) });
      const { job_id } = await r.json();
      for (let i = 0; i < 400; i++) {
        await new Promise((res) => setTimeout(res, 5000));
        const j = await fetch(`${scrpt.engineUrl}/api/scrpt/jobs/${job_id}`).then((x) => x.json());
        if (j.status === "done" || j.status === "error") break;
      }
      reload();
    } finally { setSyncing(false); }
  };
  const syncSettings = async (patch: Record<string, unknown>) => {
    const r = await fetch(`${scrpt.engineUrl}/api/scrpt/reports/sync/settings`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
    setSync(await r.json());
  };
  const kdpLogin = async () => {
    await fetch(`${scrpt.engineUrl}/api/scrpt/reports/sync/login`, { method: "POST" });
    setImportMsg("A browser window opened at KDP — sign in there, then close it. SCRPT reuses that session; it never types your password.");
  };

  const link = async (key: string, catalog: string) => {
    await fetch(`${scrpt.engineUrl}/api/scrpt/reports/link`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key, catalog: catalog || null }) });
    reload();
  };

  const maxMonth = useMemo(() => Math.max(1, ...(o?.by_month || []).map((m) => m.royalty)), [o]);
  const cur = o?.base || "USD";

  return (
    <div className="px-10 py-8 fade-up" style={{ maxWidth: 1280 }}>
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="serif-display text-[32px] font-semibold">Analytics &amp; Royalties</h1>
          <p className="text-[12.5px] text-text-secondary mt-1 max-w-[720px]">
            The house ledger. Every KDP report you import lands here — final months, the live estimate,
            pages read, payments — matched to the shelf by ASIN and ISBN, shown in your base currency.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-[11px] uppercase tracking-[0.1em] text-text-faint">Base</label>
          <select value={cur} onChange={(e) => setBase(e.target.value)}
                  className="text-[12px] rounded-[6px] px-2 py-1" style={{ background: "var(--surface)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
            {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button className="btn-ghost text-[12px]" onClick={() => setShowRates((v) => !v)}>Rates</button>
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" multiple className="hidden" onChange={(e) => onFiles(e.target.files)} />
          <button className="btn-brass text-[12px]" disabled={importing} onClick={() => fileRef.current?.click()}>
            {importing ? "Importing…" : "Import KDP reports"}
          </button>
        </div>
      </div>

      {showRates && o && (
        <div className="card mt-4">
          <div className="text-[12px] text-text-secondary mb-2">Rates are units per 1 USD. Edit the ones you care about; the rest keep the house defaults.</div>
          <div className="flex flex-wrap gap-3">
            {Object.entries(o.rates_per_usd).map(([k, v]) => (
              <label key={k} className="text-[12px] flex items-center gap-1">
                <span className="text-text-faint w-9">{k}</span>
                <input value={rateEdits[k] ?? String(v)} onChange={(e) => setRateEdits((r) => ({ ...r, [k]: e.target.value }))}
                       className="w-20 rounded-[6px] px-2 py-1 text-[12px]" style={{ background: "var(--surface-elevated)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }} />
              </label>
            ))}
          </div>
          <div className="mt-3 flex gap-2"><button className="btn-brass text-[12px]" onClick={saveRates}>Save rates</button><button className="btn-ghost text-[12px]" onClick={() => setShowRates(false)}>Close</button></div>
        </div>
      )}

      {/* import zone */}
      <div className="card mt-6" onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
           onDrop={(e) => { e.preventDefault(); setDragging(false); onFiles(e.dataTransfer.files); }}
           style={{ borderStyle: "dashed", borderColor: dragging ? "var(--accent)" : "var(--border-subtle)" }}>
        <div className="grid gap-6" style={{ gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 1fr)" }}>
          <div>
            <div className="serif-display text-[16px] font-semibold">Drop KDP report files here</div>
            <p className="text-[12px] text-text-secondary mt-1 leading-relaxed">
              In KDP go to <b>Reports</b>. Download and drop in any of these — SCRPT recognises each by its columns
              and never double-counts a row you import twice:
            </p>
            <ul className="text-[12px] text-text-secondary mt-2 space-y-1 list-disc pl-4 leading-snug">
              <li><b>Prior Months&apos; Royalties</b> — the final numbers, one file per month. The backbone of the ledger.</li>
              <li><b>Royalties Estimator</b> — this month and last, still estimated. Replaced automatically when the final month arrives.</li>
              <li><b>Orders</b> and <b>KENP Read</b> — daily units ordered and pages read, for velocity.</li>
              <li><b>Payments</b> — what Amazon actually paid, per marketplace.</li>
            </ul>
            {importMsg && <div className="text-[12px] mt-3" style={{ color: importMsg.includes("fail") ? "var(--status-amber)" : "var(--status-green)" }}>{importMsg}</div>}
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-text-faint mb-1">Coverage</div>
            {o?.coverage?.length ? (
              <div className="flex flex-wrap gap-1">
                {o.coverage.map((c) => (
                  <div key={c.month} title={`${monthLabel(c.month)} — ${c.state}`}
                       style={{ width: 22, height: 22, borderRadius: 4,
                                background: c.state === "final" ? "var(--accent)" : c.state === "estimate" ? "color-mix(in srgb, var(--accent) 45%, transparent)" : "var(--surface-elevated)",
                                border: "1px solid var(--border-subtle)" }} />
                ))}
              </div>
            ) : <div className="text-[12px] text-text-faint">No months imported yet.</div>}
            <div className="text-[10.5px] text-text-faint mt-2">solid = final · faded = estimate · empty = missing — download that month&apos;s Prior Months&apos; Royalties.</div>
            {o?.imports?.length ? (
              <div className="mt-3 text-[11px] text-text-faint space-y-0.5" style={{ maxHeight: 96, overflowY: "auto" }}>
                {o.imports.slice(0, 8).map((im) => (
                  <div key={im.imported_at + im.file} className="truncate">{im.imported_at.slice(0, 16)} · {im.file} · {im.added} new ({im.kind})</div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {/* weekly sync */}
      <div className="card mt-6">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="serif-display text-[16px] font-semibold">Weekly sync from KDP</div>
            <p className="text-[12px] text-text-secondary mt-1 leading-relaxed max-w-[620px]">
              Once a week SCRPT opens KDP Reports in your own signed-in session, downloads the estimator, last month&apos;s
              final royalties, the current month and the payments ledger, and imports them. It never types your password
              and never touches a CAPTCHA — if the session has expired it stops and asks you to sign in once.
            </p>
            {sync?.last_result && (
              <div className="text-[12px] mt-2" style={{ color: sync.last_result.signed_in === false || (sync.last_result.errors || []).length ? "var(--status-amber)" : "var(--status-green)" }}>
                Last run {sync.last_run?.replace("T", " ")}: {sync.last_result.signed_in === false ? "needs sign-in" : `${sync.last_result.imported ?? 0} new rows from ${(sync.last_result.files || []).length} files`}
                {(sync.last_result.errors || []).length ? ` · ${(sync.last_result.errors || []).join("; ")}` : ""}
              </div>
            )}
            {sync && !sync.backfilled && <div className="text-[11.5px] text-text-faint mt-1">History not yet backfilled — run &quot;Sync now (with history)&quot; once to pull every month since the start.</div>}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {sync && (
              <>
                <label className="text-[11px] text-text-faint flex items-center gap-1">
                  <input type="checkbox" checked={sync.enabled} onChange={(e) => syncSettings({ enabled: e.target.checked })} /> weekly
                </label>
                <select value={sync.weekday} onChange={(e) => syncSettings({ weekday: Number(e.target.value) })}
                        className="text-[12px] rounded-[6px] px-2 py-1" style={{ background: "var(--surface)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
                  {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((d, i) => <option key={d} value={i}>{d}</option>)}
                </select>
                <select value={sync.hour} onChange={(e) => syncSettings({ hour: Number(e.target.value) })}
                        className="text-[12px] rounded-[6px] px-2 py-1" style={{ background: "var(--surface)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
                  {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
                </select>
              </>
            )}
            <button className="btn-ghost text-[12px]" onClick={kdpLogin}>Sign in to KDP</button>
            <button className="btn-ghost text-[12px]" disabled={syncing} onClick={() => runSync(true)}>{syncing ? "Syncing…" : "Sync now (with history)"}</button>
            <button className="btn-brass text-[12px]" disabled={syncing} onClick={() => runSync(false)}>{syncing ? "Syncing…" : "Sync now"}</button>
          </div>
        </div>
      </div>

      {engineOnline === false && (
        <div className="card mt-8" style={{ borderLeft: "3px solid var(--status-amber)" }}>
          <div className="text-[13px]">The engine is offline — start it to import and read reports.</div>
        </div>
      )}

      {o?.has_data ? (
        <>
          {/* KPIs */}
          <div className="grid gap-4 mt-6" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
            <Kpi label="This month" value={money(o.kpi.this_month, cur)} hint="estimate until final" />
            <Kpi label="Last month" value={money(o.kpi.last_month, cur)} />
            <Kpi label="Last 90 days" value={money(o.kpi.last_90, cur)} />
            <Kpi label="Trailing 12 months" value={money(o.kpi.trailing_12, cur)} />
            <Kpi label="All time" value={money(o.kpi.all_time, cur)} hint={`${Math.round(o.kpi.units_all).toLocaleString()} units · ${Math.round(o.kpi.kenp_all).toLocaleString()} pages`} />
            <Kpi label="Paid out" value={money(o.paid_total, cur)} hint={`${o.payments.length} payments`} />
          </div>

          {/* monthly chart */}
          <div className="card mt-6">
            <div className="flex items-baseline justify-between">
              <div className="serif-display text-[18px] font-semibold">Royalties by month</div>
              <div className="flex gap-3 text-[10px] uppercase tracking-[0.1em] text-text-faint">
                {Object.entries(FORMAT_COLOR).map(([k, c]) => <span key={k} className="flex items-center gap-1"><span style={{ width: 8, height: 8, background: c, display: "inline-block", borderRadius: 2 }} />{k}</span>)}
              </div>
            </div>
            <div className="mt-4 flex items-end gap-[6px]" style={{ height: 180 }}>
              {o.by_month.map((m) => {
                const h = (m.royalty / maxMonth) * 160;
                const parts = (["kenp", "hardcover", "paperback", "ebook"] as const).map((f) => ({ f, v: m[f] }));
                return (
                  <div key={m.month} className="flex-1 flex flex-col items-center justify-end" title={`${monthLabel(m.month)} — ${money(m.royalty, cur)} · ${Math.round(m.units)} units · ${Math.round(m.kenp_pages)} pages${m.estimate ? " (estimate)" : ""}`}>
                    <div className="text-[10px] text-text-faint mb-1">{m.royalty >= maxMonth * 0.15 ? money(m.royalty, cur) : ""}</div>
                    <div className="w-full rounded-t-[3px] overflow-hidden flex flex-col-reverse" style={{ height: Math.max(2, h), opacity: m.estimate ? 0.55 : 1, maxWidth: 46 }}>
                      {parts.map((p) => p.v > 0 && <div key={p.f} style={{ height: `${(p.v / m.royalty) * 100}%`, background: FORMAT_COLOR[p.f] }} />)}
                    </div>
                    <div className="text-[10px] text-text-faint mt-1">{monthLabel(m.month)}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* books */}
          <div className="card mt-6 overflow-x-auto">
            <div className="serif-display text-[18px] font-semibold">By title</div>
            <table className="w-full text-[12.5px] mt-3">
              <thead>
                <tr className="text-[10px] uppercase tracking-[0.1em] text-text-faint text-left">
                  <th className="py-2 pr-3" />
                  <th className="py-2 pr-3">Title</th>
                  <th className="py-2 pr-3 text-right">All time</th>
                  <th className="py-2 pr-3 text-right">Last 30 d</th>
                  <th className="py-2 pr-3 text-right">Trend</th>
                  <th className="py-2 pr-3 text-right">Units</th>
                  <th className="py-2 pr-3 text-right">Pages read</th>
                  <th className="py-2 pr-3 text-right">Per unit</th>
                  <th className="py-2 pr-3">Formats</th>
                  <th className="py-2 pr-3">Markets</th>
                </tr>
              </thead>
              <tbody>
                {o.books.map((b) => (
                  <tr key={b.key} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                    <td className="py-2 pr-3">
                      {b.catalog_number ? (
                        <Link href={`/shelf/${b.catalog_number}?tab=publishing`} className="block" style={{ width: 26 }}>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={`${scrpt.engineUrl}/api/files/${b.catalog_number}/cover-front.png`} alt="" className="w-full rounded-[2px]" style={{ aspectRatio: "2/3", objectFit: "cover", background: "#1a1d24" }}
                               onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = "hidden"; }} />
                        </Link>
                      ) : <div style={{ width: 26, aspectRatio: "2/3", background: "var(--surface-elevated)", borderRadius: 2 }} />}
                    </td>
                    <td className="py-2 pr-3">
                      <div className="font-medium truncate" style={{ maxWidth: 320 }}>{b.title}</div>
                      <div className="text-[10.5px] text-text-faint">{b.series ? `${b.series} · #${b.book_number} · ` : ""}{b.catalog_number || "not on the shelf"}{b.first ? ` · since ${b.first}` : ""}</div>
                    </td>
                    <td className="py-2 pr-3 text-right font-medium">{money(b.royalty, cur)}</td>
                    <td className="py-2 pr-3 text-right">{money(b.royalty_30, cur)}</td>
                    <td className="py-2 pr-3 text-right" style={{ color: b.trend === null ? "var(--text-faint)" : b.trend >= 0 ? "var(--status-green)" : "var(--status-amber)" }}>
                      {b.trend === null ? "—" : `${b.trend >= 0 ? "+" : ""}${Math.round(b.trend * 100)}%`}
                    </td>
                    <td className="py-2 pr-3 text-right">{Math.round(b.units).toLocaleString()}{b.free_units ? <span className="text-text-faint"> +{Math.round(b.free_units)} free</span> : null}</td>
                    <td className="py-2 pr-3 text-right">{Math.round(b.kenp_pages).toLocaleString()}</td>
                    <td className="py-2 pr-3 text-right">{b.royalty_per_unit !== null ? money(b.royalty_per_unit, cur) : "—"}</td>
                    <td className="py-2 pr-3">
                      <div className="flex gap-1">
                        {Object.entries(b.formats).map(([f, v]) => (
                          <span key={f} title={`${f}: ${money(v.royalty, cur)}`} className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: "var(--surface-elevated)", color: FORMAT_COLOR[f] || "var(--text-secondary)" }}>{f}</span>
                        ))}
                      </div>
                    </td>
                    <td className="py-2 pr-3 text-[11px] text-text-faint">{b.marketplaces.map((m) => m.replace("Amazon.", "")).join(" · ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* unmatched */}
          {o.unmatched.length > 0 && (
            <div className="card mt-6" style={{ borderLeft: "3px solid var(--status-amber)" }}>
              <div className="serif-display text-[16px] font-semibold">Titles not yet tied to the shelf</div>
              <p className="text-[12px] text-text-secondary mt-1">KDP&apos;s title differs from the shelf&apos;s, or the ASIN isn&apos;t stored. Pick the book once; the link is remembered.</p>
              <div className="mt-3 space-y-2">
                {o.unmatched.map((u) => (
                  <div key={u.title + u.asin} className="flex items-center gap-3 text-[12.5px]">
                    <div className="flex-1 truncate">{u.title} <span className="text-text-faint">{u.asin}</span></div>
                    <div className="text-text-faint">{money(u.royalty, cur)}</div>
                    <select defaultValue="" onChange={(e) => link(u.asin || u.title, e.target.value)}
                            className="text-[12px] rounded-[6px] px-2 py-1" style={{ background: "var(--surface)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)", maxWidth: 280 }}>
                      <option value="">Tie to…</option>
                      {shelf.map((b) => <option key={b.catalog_number} value={b.catalog_number}>{b.catalog_number} · {b.title}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid gap-6 mt-6" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)" }}>
            {/* marketplaces */}
            <div className="card">
              <div className="serif-display text-[18px] font-semibold">By marketplace</div>
              <div className="mt-3 space-y-2">
                {o.by_marketplace.map((m) => {
                  const top = o.by_marketplace[0]?.royalty || 1;
                  return (
                    <div key={m.marketplace} className="text-[12.5px]">
                      <div className="flex justify-between"><span>{m.marketplace}</span><span className="font-medium">{money(m.royalty, cur)} <span className="text-text-faint">· {Math.round(m.units)} u</span></span></div>
                      <div style={{ height: 4, background: "var(--surface-elevated)", borderRadius: 2 }}><div style={{ width: `${(m.royalty / top) * 100}%`, height: 4, background: "var(--accent)", borderRadius: 2 }} /></div>
                    </div>
                  );
                })}
              </div>
            </div>
            {/* payments */}
            <div className="card">
              <div className="serif-display text-[18px] font-semibold">Payments</div>
              {o.payments.length ? (
                <table className="w-full text-[12px] mt-3">
                  <tbody>
                    {o.payments.slice(0, 12).map((p, i) => (
                      <tr key={i} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                        <td className="py-1.5 pr-2 text-text-faint">{p.payment_date}</td>
                        <td className="py-1.5 pr-2">{p.marketplace}</td>
                        <td className="py-1.5 pr-2 text-text-faint">{p.period}</td>
                        <td className="py-1.5 pr-2 text-right">{money(p.amount, p.currency || "USD")}</td>
                        <td className="py-1.5 text-right font-medium">{money(p.amount_base, cur)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : <div className="text-[12px] text-text-faint mt-2">Import the Payments report to see what Amazon has actually paid.</div>}
            </div>
          </div>

          {/* series */}
          {seriesData && seriesData.series.length > 0 && (
            <div className="card mt-6">
              <div className="flex items-baseline justify-between flex-wrap gap-3">
                <div>
                  <div className="serif-display text-[18px] font-semibold">Series read-through</div>
                  <p className="text-[12px] text-text-secondary mt-1">Read-through = units of book n ÷ book n−1. Value per first sale = what one book-1 reader is worth across the series — the number an ad click should be judged against.</p>
                </div>
                <label className="text-[12px] flex items-center gap-2">Monthly ad budget
                  <input type="number" value={adBudget} onChange={(e) => setAdBudget(Number(e.target.value))} className="w-24 rounded-[6px] px-2 py-1 text-[12px]" style={{ background: "var(--surface-elevated)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }} />
                </label>
              </div>
              <div className="mt-3 space-y-4">
                {seriesData.series.map((s) => (
                  <div key={s.series_id} style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 10 }}>
                    <div className="flex items-baseline justify-between">
                      <div className="text-[13px] font-medium">{s.series_title} <span className="text-text-faint text-[11px]">{s.proven ? "proven" : "unproven — exploring"}</span></div>
                      <div className="text-[12px]">{money(s.royalty_total, cur)} total · {money(s.royalty_recent_60d, cur)} last 60 d · value/first sale {s.value_per_first_sale !== null ? money(s.value_per_first_sale, cur) : "—"} · suggested ads <b>{money(adBudget * s.suggested_ad_share, cur)}</b></div>
                    </div>
                    <div className="flex items-center gap-2 mt-2 flex-wrap">
                      {s.books.map((b, i) => (
                        <div key={b.catalog_number} className="flex items-center gap-2">
                          <div className="text-[11.5px] px-2 py-1 rounded-[6px]" style={{ background: "var(--surface-elevated)" }}>#{b.book_number} {b.title.slice(0, 22)} · {Math.round(b.units)} u</div>
                          {i < s.books.length - 1 && <span className="text-[11px] text-text-faint">→ {s.readthrough[i] === null ? "n/a" : `${Math.round((s.readthrough[i] || 0) * 100)}%`} →</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : engineOnline ? (
        <div className="card mt-10 text-center py-16">
          <div className="serif-display text-[22px] font-semibold">No royalty data yet</div>
          <p className="text-[13px] text-text-secondary mt-2 max-w-[520px] mx-auto">
            Download <b>Prior Months&apos; Royalties</b> for each month you&apos;ve been selling, plus today&apos;s <b>Royalties Estimator</b>,
            from the KDP Reports tab, and drop them above. The ledger builds itself from there.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card">
      <div className="text-[10px] uppercase tracking-[0.12em] text-text-faint">{label}</div>
      <div className="serif-display text-[24px] font-semibold leading-none mt-2">{value}</div>
      {hint && <div className="text-[10.5px] text-text-faint mt-1.5">{hint}</div>}
    </div>
  );
}
