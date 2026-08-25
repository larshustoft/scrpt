"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { scrpt } from "@/lib/scrpt";

type Release = {
  catalog: string; title: string; author?: string; genre?: string;
  series?: string | null; book_number?: number | null;
  date?: string | null; mode: string; status: string; note?: string | null;
};
type Proposal = {
  catalog: string; title: string; series?: string | null; book_number?: number | null;
  ready: boolean; current?: string | null; date: string; why: string[];
  tasks: { date: string; task: string }[];
};

const STATUS_COLOR: Record<string, string> = {
  released: "var(--status-green)",
  submitted: "var(--status-blue)",
  planned: "var(--accent)",
  proposed: "var(--status-amber)",
  unplanned: "var(--text-faint)",
};

function ymd(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function monthCells(year: number, month: number): (Date | null)[] {
  const first = new Date(year, month, 1);
  const lead = (first.getDay() + 6) % 7;                 // Monday first
  const days = new Date(year, month + 1, 0).getDate();
  const cells: (Date | null)[] = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => new Date(year, month, i + 1))];
  while (cells.length % 7) cells.push(null);
  return cells;
}

export default function CalendarPage() {
  const [rows, setRows] = useState<Release[]>([]);
  const [months, setMonths] = useState<1 | 2>(2);
  const [cursor, setCursor] = useState(() => { const d = new Date(); d.setDate(1); return d; });
  const [plan, setPlan] = useState<Proposal[] | null>(null);
  const [planning, setPlanning] = useState(false);
  const [msg, setMsg] = useState("");

  const reload = useCallback(() => {
    fetch(`${scrpt.engineUrl}/api/scrpt/release-calendar`)
      .then((r) => (r.ok ? r.json() : { releases: [] }))
      .then((d) => setRows(d.releases || []))
      .catch(() => {});
  }, []);
  useEffect(reload, [reload]);

  const suggest = async () => {
    setPlanning(true); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/release-calendar/suggest`);
      const d = await r.json();
      setPlan(d.proposals || []);
      // jump the calendar to the first proposal
      if (d.proposals?.length) { const f = new Date(d.proposals[0].date + "T00:00:00"); f.setDate(1); setCursor(f); }
    } catch { setMsg("The planner is unavailable"); } finally { setPlanning(false); }
  };

  const applyAll = async () => {
    if (!plan) return;
    setPlanning(true);
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/release-calendar/apply`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: plan.map((p) => ({ catalog: p.catalog, date: p.date })) }),
      });
      const d = await r.json();
      setMsg(`${(d.applied || []).length} release dates set.`);
      setPlan(null);
      reload();
    } catch { setMsg("Could not apply"); } finally { setPlanning(false); }
  };

  // what sits on each day: real plans, plus proposals (ghosted) while reviewing
  const byDate = useMemo(() => {
    const m: Record<string, { r: Release; proposed?: boolean }[]> = {};
    for (const r of rows) if (r.date) (m[r.date] ||= []).push({ r });
    if (plan) for (const p of plan) {
      (m[p.date] ||= []).push({
        r: { catalog: p.catalog, title: p.title, series: p.series, book_number: p.book_number,
             date: p.date, mode: "immediate", status: "proposed" }, proposed: true });
    }
    return m;
  }, [rows, plan]);

  const today = ymd(new Date());
  const unplanned = rows.filter((r) => !r.date && r.status !== "released");
  const monthList = Array.from({ length: months }, (_, i) => new Date(cursor.getFullYear(), cursor.getMonth() + i, 1));

  return (
    <div className="px-10 py-8 fade-up" style={{ maxWidth: "none" }}>
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="serif-display text-[30px] font-semibold">Release Calendar</h1>
          <p className="text-[12.5px] text-text-secondary mt-1 max-w-[700px]">
            The slate at a glance. Each launch earns its own 30-day new-release window —
            series books four weeks apart, ebook and paperback together, the next book on
            pre-order from launch day. KDP allows three new titles a day; the house plans one a week.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1">
            {([1, 2] as const).map((n) => (
              <button key={n} onClick={() => setMonths(n)}
                      className={`px-3 py-1 rounded-full text-[11px] uppercase tracking-[0.08em] ${months === n ? "text-text-primary" : "text-text-faint hover:text-text-secondary"}`}
                      style={months === n ? { background: "var(--surface)", boxShadow: "var(--shadow-card)" } : {}}>
                {n} month{n > 1 ? "s" : ""}
              </button>
            ))}
          </div>
          <button className="btn-ghost text-[12px]" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}>‹</button>
          <button className="btn-ghost text-[12px]" onClick={() => { const d = new Date(); d.setDate(1); setCursor(d); }}>Today</button>
          <button className="btn-ghost text-[12px]" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}>›</button>
          {!plan ? (
            <button className="btn-brass text-[12px] ml-2" disabled={planning} onClick={suggest}>
              {planning ? "Planning…" : "Suggest schedule"}
            </button>
          ) : (
            <>
              <button className="btn-brass text-[12px] ml-2" disabled={planning} onClick={applyAll}>
                Apply {plan.length} dates
              </button>
              <button className="btn-ghost text-[12px]" onClick={() => setPlan(null)}>Discard</button>
            </>
          )}
        </div>
      </div>
      {msg && <div className="text-[12px] mt-2" style={{ color: "var(--status-green)" }}>{msg}</div>}

      <div className="grid gap-6 mt-6" style={{ gridTemplateColumns: plan ? "minmax(0, 1fr) 360px" : "minmax(0, 1fr)" }}>
        <div className="space-y-8">
          {monthList.map((m) => {
            const y = m.getFullYear(), mo = m.getMonth();
            const cells = monthCells(y, mo);
            return (
              <div key={`${y}-${mo}`}>
                <div className="serif-display text-[20px] font-semibold mb-2">
                  {m.toLocaleDateString("en-GB", { month: "long", year: "numeric" })}
                </div>
                <div className="grid grid-cols-7 text-[10px] uppercase tracking-[0.12em] text-text-faint mb-1">
                  {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="px-2">{d}</div>)}
                </div>
                <div className="grid grid-cols-7 gap-[4px]">
                  {cells.map((d, i) => {
                    const key = d ? ymd(d) : "";
                    const items = d ? byDate[key] || [] : [];
                    const isToday = key === today;
                    const weekend = d ? d.getDay() === 0 || d.getDay() === 6 : false;
                    return (
                      <div key={i} className="rounded-[8px] px-2 pt-1.5 pb-2"
                           style={{ minHeight: 150, background: d ? (weekend ? "color-mix(in srgb, var(--surface) 55%, transparent)" : "var(--surface)") : "transparent",
                                    border: isToday ? "1px solid var(--accent)" : "1px solid var(--border-subtle)",
                                    opacity: d ? 1 : 0.2 }}>
                        {d && (
                          <div className="text-[11px] mb-1.5" style={{ color: isToday ? "var(--accent)" : "var(--text-faint)" }}>
                            {d.getDate()}
                          </div>
                        )}
                        <div className="flex flex-wrap gap-1.5">
                          {items.map(({ r, proposed }) => (
                            <Link key={r.catalog + (proposed ? "-p" : "")} href={`/shelf/${r.catalog}?tab=publishing`}
                                  title={`${r.title}${r.series ? ` — ${r.series} #${r.book_number}` : ""} · ${r.status}`}
                                  className="block" style={{ width: 62, opacity: proposed ? 0.72 : 1 }}>
                              <div className="rounded-[3px] overflow-hidden"
                                   style={{ aspectRatio: "2/3", background: "#1a1d24",
                                            boxShadow: "0 4px 12px rgba(0,0,0,.45)",
                                            outline: `2px solid ${STATUS_COLOR[r.status] || "transparent"}`, outlineOffset: 1 }}>
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img src={`${scrpt.engineUrl}/api/files/${r.catalog}/cover-front.png`} alt=""
                                     className="w-full h-full object-cover"
                                     onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = "hidden"; }} />
                              </div>
                              <div className="text-[9.5px] leading-tight mt-1 truncate" style={{ color: STATUS_COLOR[r.status] || "var(--text-secondary)" }}>
                                {r.series ? `#${r.book_number} ` : ""}{r.title}
                              </div>
                            </Link>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
          <div className="flex items-center gap-4 text-[10px] uppercase tracking-[0.1em] text-text-faint">
            {Object.entries(STATUS_COLOR).map(([k, c]) => (
              <span key={k} className="flex items-center gap-1.5">
                <span style={{ width: 8, height: 8, borderRadius: 4, background: c, display: "inline-block" }} /> {k}
              </span>
            ))}
            {unplanned.length > 0 && <span className="ml-auto">{unplanned.length} title{unplanned.length > 1 ? "s" : ""} without a date — set them on each book&apos;s Publishing tab, or let the planner suggest</span>}
          </div>
        </div>

        {plan && (
          <div className="card self-start" style={{ position: "sticky", top: 16 }}>
            <div className="serif-display text-[16px] font-semibold">The planner&apos;s slate</div>
            <p className="text-[11px] text-text-faint mt-1">
              Ghosted covers show the proposal. Every date carries its reasons; apply all, or set dates
              individually on the books you disagree with.
            </p>
            <div className="mt-3 space-y-3 overflow-y-auto" style={{ maxHeight: "70vh" }}>
              {plan.map((p) => (
                <div key={p.catalog} style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 8 }}>
                  <div className="flex items-baseline justify-between gap-2">
                    <div className="text-[12.5px] font-medium truncate">{p.series ? `#${p.book_number} ` : ""}{p.title}</div>
                    <div className="text-[11px] shrink-0" style={{ color: p.ready ? "var(--accent)" : "var(--status-amber)" }}>
                      {new Date(p.date + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })}
                    </div>
                  </div>
                  <ul className="text-[11px] text-text-faint mt-1 leading-snug list-disc pl-4">
                    {p.why.map((w, i) => <li key={i}>{w}</li>)}
                    {p.tasks.map((t, i) => <li key={`t${i}`} style={{ color: "var(--text-secondary)" }}>{t.date}: {t.task}</li>)}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
