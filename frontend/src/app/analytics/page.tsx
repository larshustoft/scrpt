"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { scrpt } from "@/lib/scrpt";

type Summary = Awaited<ReturnType<typeof scrpt.reportsSummary>>;
type BookRows = Awaited<ReturnType<typeof scrpt.reportsByBook>>["books"];
type SeriesData = Awaited<ReturnType<typeof scrpt.reportsSeries>>;

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [books, setBooks] = useState<BookRows>([]);
  const [seriesData, setSeriesData] = useState<SeriesData | null>(null);
  const [adBudget, setAdBudget] = useState(1000);
  const [importMsg, setImportMsg] = useState("");
  const [importing, setImporting] = useState(false);
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    const online = await scrpt.health();
    setEngineOnline(online);
    if (!online) return;
    try {
      const [s, b, sr] = await Promise.all([
        scrpt.reportsSummary(), scrpt.reportsByBook(),
        scrpt.reportsSeries().catch(() => null),
      ]);
      setSummary(s);
      setBooks(b.books);
      setSeriesData(sr);
    } catch { /* not imported yet */ }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const onFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setImporting(true);
    try {
      let added = 0;
      for (const f of Array.from(files)) {
        const r = await scrpt.importReport(f);
        added += r.total_added;
      }
      setImportMsg(`Imported ${added} new royalty rows.`);
      reload();
    } catch (e) {
      setImportMsg(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  // monthly totals (all formats combined, USD assumed dominant)
  const monthly = useMemo(() => {
    if (!summary) return [];
    const map = new Map<string, { royalty: number; units: number; kenp: number }>();
    for (const r of summary.by_month) {
      const m = map.get(r.month) || { royalty: 0, units: 0, kenp: 0 };
      m.royalty += r.royalty || 0;
      m.units += r.units || 0;
      m.kenp += r.kenp_pages || 0;
      map.set(r.month, m);
    }
    return Array.from(map.entries())
      .filter(([m]) => m && m !== "null")
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-18);
  }, [summary]);

  const maxRoyalty = Math.max(1, ...monthly.map(([, v]) => v.royalty));
  const hasData = Boolean(summary?.totals?.royalty || summary?.totals?.units || books.length);

  return (
    <div className="max-w-[1100px] mx-auto px-8 py-12 fade-up">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="serif-display text-[32px] font-semibold">Analytics & Royalties</h1>
          <p className="text-[13px] text-text-secondary mt-1">
            Amazon has no KDP API — royalties flow in from KDP report files.
            Download them at kdpreports.amazon.com and drop them here.
          </p>
        </div>
        <div>
          <input ref={fileRef} type="file" accept=".xlsx,.csv" multiple className="hidden"
                 onChange={(e) => onFiles(e.target.files)} />
          <button className="btn-brass" disabled={importing || engineOnline === false}
                  onClick={() => fileRef.current?.click()}>
            {importing ? "Importing…" : "Import KDP report"}
          </button>
        </div>
      </div>

      {importMsg && <div className="text-[12px] text-text-tertiary mt-3">{importMsg}</div>}

      {engineOnline === false && (
        <div className="card mt-8" style={{ borderLeft: "3px solid var(--status-amber)" }}>
          <div className="text-[13px] text-text-secondary">
            The local engine is offline — royalty data lives there. Start the
            SCRPT companion.
          </div>
        </div>
      )}

      {summary && hasData && (
        <>
          {/* totals */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8">
            <Stat label="Lifetime royalties" value={`$${(summary.totals.royalty || 0).toFixed(2)}`} accent />
            <Stat label="Units sold" value={(summary.totals.units || 0).toLocaleString()} />
            <Stat label="KENP pages read" value={(summary.totals.kenp_pages || 0).toLocaleString()} />
            <Stat label="Earning titles" value={summary.totals.titles || 0} />
          </div>

          {/* monthly royalties */}
          {monthly.length > 0 && (
            <div className="card mt-6">
              <div className="label-scrpt">Royalties by month</div>
              <div className="mt-4 space-y-2">
                {monthly.map(([month, v]) => (
                  <div key={month} className="flex items-center gap-3">
                    <span className="text-[11px] text-text-tertiary w-16 shrink-0">{month}</span>
                    <div className="flex-1 h-[18px] rounded overflow-hidden"
                         style={{ background: "rgba(236,229,218,0.05)" }}>
                      <div className="h-full rounded transition-all duration-500"
                           style={{
                             width: `${Math.max(1, (v.royalty / maxRoyalty) * 100)}%`,
                             background: "linear-gradient(90deg, var(--accent-deep), var(--accent))",
                           }} />
                    </div>
                    <span className="text-[12px] text-text-secondary w-20 text-right shrink-0">
                      ${v.royalty.toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* series read-through + ad allocation */}
          {seriesData && seriesData.series.length > 0 && (
            <div className="card mt-6">
              <div className="flex items-baseline justify-between flex-wrap gap-3">
                <div>
                  <div className="serif-display text-[18px] font-semibold">Series performance</div>
                  <div className="text-[11px] text-text-faint mt-1 max-w-[520px]">
                    Read-through = units of each book per unit of the one before it.
                    Value per first sale = total series royalty earned per copy of
                    book one — what a book-one ad click is worth.
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-text-tertiary">Monthly ad budget $</span>
                  <input type="number" className="input-scrpt w-24 py-1"
                         value={adBudget}
                         onChange={(e) => setAdBudget(Number(e.target.value) || 0)} />
                </div>
              </div>

              <div className="mt-5 space-y-6">
                {seriesData.series.map((sr) => {
                  const maxUnits = Math.max(1, ...sr.books.map((b) => b.units));
                  return (
                    <div key={sr.series_id} className="rounded-[10px] p-4"
                         style={{ background: "var(--surface-elevated)", border: "1px solid var(--border-subtle)" }}>
                      <div className="flex items-baseline justify-between flex-wrap gap-2">
                        <div className="text-[14px] font-semibold">
                          {sr.series_title}
                          {!sr.proven && (
                            <span className="text-[10px] uppercase tracking-[0.1em] ml-2"
                                  style={{ color: "var(--status-amber)" }}>exploring</span>
                          )}
                        </div>
                        <div className="text-[12px] text-text-secondary">
                          {sr.value_per_first_sale != null && (
                            <span className="mr-4">${sr.value_per_first_sale.toFixed(2)} / first sale</span>
                          )}
                          <span className="text-accent font-semibold">
                            ${Math.round(adBudget * sr.suggested_ad_share)} suggested
                          </span>
                          <span className="text-text-faint ml-1">
                            ({Math.round(sr.suggested_ad_share * 100)}%)
                          </span>
                        </div>
                      </div>
                      <div className="mt-3 space-y-1.5">
                        {sr.books.map((b, i) => (
                          <div key={b.catalog_number} className="flex items-center gap-3">
                            <span className="text-[11px] text-text-faint w-4 shrink-0">{b.book_number}</span>
                            <span className="text-[12px] text-text-secondary w-44 truncate shrink-0">{b.title}</span>
                            <div className="flex-1 h-[14px] rounded overflow-hidden"
                                 style={{ background: "rgba(236,229,218,0.05)" }}>
                              <div className="h-full rounded"
                                   style={{ width: `${Math.max(2, (b.units / maxUnits) * 100)}%`,
                                            background: "linear-gradient(90deg, var(--accent-deep), var(--accent))" }} />
                            </div>
                            <span className="text-[11px] text-text-secondary w-16 text-right shrink-0">
                              {b.units.toLocaleString()} units
                            </span>
                            <span className="text-[11px] text-text-faint w-14 text-right shrink-0">
                              {i > 0 && sr.readthrough[i - 1] != null
                                ? `${Math.round((sr.readthrough[i - 1] as number) * 100)}%`
                                : ""}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* per book */}
          {books.length > 0 && (
            <div className="card mt-6 overflow-x-auto">
              <div className="label-scrpt">By title</div>
              <table className="w-full mt-3 text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-[0.08em] text-text-faint">
                    <th className="py-2 pr-4 font-medium">Title</th>
                    <th className="py-2 pr-4 font-medium">Format</th>
                    <th className="py-2 pr-4 font-medium text-right">Units</th>
                    <th className="py-2 pr-4 font-medium text-right">KENP</th>
                    <th className="py-2 font-medium text-right">Royalty</th>
                  </tr>
                </thead>
                <tbody>
                  {books.slice(0, 60).map((b, i) => (
                    <tr key={i} className="border-t" style={{ borderColor: "var(--border-subtle)" }}>
                      <td className="py-2.5 pr-4">
                        <span className="text-text-primary">{b.title || b.asin}</span>
                        {b.catalog_number && (
                          <span className="text-[11px] text-accent ml-2">{b.catalog_number}</span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4 text-text-tertiary capitalize">{b.format}</td>
                      <td className="py-2.5 pr-4 text-right text-text-secondary">
                        {b.units ? b.units.toLocaleString() : "—"}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-text-secondary">
                        {b.kenp_pages ? b.kenp_pages.toLocaleString() : "—"}
                      </td>
                      <td className="py-2.5 text-right text-text-primary">
                        {b.royalty ? `$${b.royalty.toFixed(2)}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* marketplaces */}
          {summary.by_marketplace.length > 0 && (
            <div className="card mt-6">
              <div className="label-scrpt">Marketplaces</div>
              <div className="flex flex-wrap gap-x-8 gap-y-3 mt-3">
                {summary.by_marketplace.slice(0, 10).map((m, i) => (
                  <div key={i}>
                    <div className="text-[13px] font-medium">{m.marketplace || "Unknown"}</div>
                    <div className="text-[12px] text-text-tertiary">
                      {m.royalty ? `${m.currency} ${m.royalty.toFixed(2)}` : `${m.units} units`}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {engineOnline && !hasData && (
        <div className="card mt-10 text-center py-16">
          <div className="serif-display text-[22px] font-semibold">No royalty data yet</div>
          <p className="text-[13px] text-text-secondary mt-2 max-w-[440px] mx-auto">
            When the first books are live: sign in to kdpreports.amazon.com,
            choose &ldquo;Generate and Download Report&rdquo; (XLSX), and import the file
            here. Re-importing overlapping months is safe — rows deduplicate.
          </p>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, accent = false }: {
  label: string; value: string | number; accent?: boolean;
}) {
  return (
    <div className="card">
      <div className={`serif-display text-[26px] font-semibold leading-none ${
        accent ? "text-accent" : "text-text-primary"}`}>
        {value}
      </div>
      <div className="text-[11px] tracking-[0.08em] uppercase text-text-tertiary mt-2">{label}</div>
    </div>
  );
}
