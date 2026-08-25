"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useCoverLightbox } from "@/components/CoverLightbox";
import { scrpt, type ScrptBook } from "@/lib/scrpt";

const SPINE_COLORS = [
  "#2b2320", "#3a2d25", "#1f2a33", "#33251f", "#26302a", "#2e2233", "#39312a",
];

export default function ShelfPage() {
  const [builder, setBuilder] = useState(false);
  const [books, setBooks] = useState<ScrptBook[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [royalties, setRoyalties] = useState<number | null>(null);
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);

  useEffect(() => {
    (async () => {
      const online = await scrpt.health();
      setEngineOnline(online);
      if (online) {
        try {
          const list = await scrpt.listBooks();
          setBooks(list.books.filter((b) => b.data.manuscript));
        } catch { /* ignore */ }
        try {
          const r = await scrpt.reportsSummary();
          setRoyalties(r.totals.royalty || 0);
        } catch { /* no reports yet */ }
      }
      setLoaded(true);
    })();
  }, []);

  const kindOf = (b: ScrptBook): "fiction" | "nonfiction" | "childrens" => {
    const d = b.data as { kind?: string; manuscript?: { kind?: string };
                          childrens?: unknown };
    const k = (d.kind || d.manuscript?.kind || "").toLowerCase();
    // a picture book is its own kind of object — different trim, different
    // reader, different shelf. It does not belong under fiction.
    if (k.startsWith("child") || d.childrens) return "childrens";
    return k.startsWith("non") ? "nonfiction" : "fiction";
  };
  const wings = useMemo(() => {
    const build = (subset: ScrptBook[]) => {
      const groups = new Map<string, { id: string; title: string; books: ScrptBook[] }>();
      const single: ScrptBook[] = [];
      for (const b of subset) {
        const s = b.data.series;
        if (s?.series_id && s.series_title) {
          if (!groups.has(s.series_id)) {
            groups.set(s.series_id, { id: s.series_id, title: s.series_title, books: [] });
          }
          groups.get(s.series_id)!.books.push(b);
        } else {
          single.push(b);
        }
      }
      for (const g of groups.values()) {
        g.books.sort((a, b) => (a.data.series?.book_number || 0) - (b.data.series?.book_number || 0));
      }
      return { seriesGroups: Array.from(groups.values()), standalone: single };
    };
    return {
      fiction: build(books.filter((b) => kindOf(b) === "fiction")),
      nonfiction: build(books.filter((b) => kindOf(b) === "nonfiction")),
      childrens: build(books.filter((b) => kindOf(b) === "childrens")),
    };
  }, [books]);
  const { seriesGroups, standalone } = wings.fiction;

  return (
    <div className="max-w-[1200px] mx-auto px-8 py-12 fade-up">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="serif-display text-[32px] font-semibold">The Bookshelf</h1>
          <p className="text-[13px] text-text-secondary mt-1">
            The catalog, spine out. Open any book to write, format, and prepare
            it for publication.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-ghost text-[12px]" onClick={() => setBuilder((b) => !b)}>
            {builder ? "Close series builder" : "Group books into a series"}
          </button>
          <Link href="/workorder" className="btn-brass">New Work Order</Link>
        </div>
      </div>
      {builder && <SeriesBuilder onDone={() => { setBuilder(false); window.location.reload(); }} />}

      {(() => {
        const words = books.reduce((sum, b) => sum + (b.data.manuscript?.word_count || 0), 0);
        const ready = books.filter((b) => b.status === "ready").length;
        const live = books.filter((b) => b.status === "live").length;
        const seriesCount = new Set(books.map((b) => b.data.series?.series_id).filter(Boolean)).size;
        const Stat = ({ label, value, accent = false }: { label: string; value: string | number; accent?: boolean }) => (
          <div className="card py-4">
            <div className="text-[10.5px] tracking-[0.14em] uppercase text-text-faint">{label}</div>
            <div className={`serif-display text-[22px] font-semibold mt-1 ${accent ? "text-accent" : ""}`}>{value}</div>
          </div>
        );
        return loaded && books.length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-7">
            <Stat label="Titles" value={books.length} />
            <Stat label="Series" value={seriesCount} />
            <Stat label="Words in catalog" value={words.toLocaleString()} />
            <Stat label="Ready / Live" value={`${ready} / ${live}`} />
            <Stat label="Lifetime royalties"
                  value={royalties === null ? "—" : `$${royalties.toFixed(0)}`}
                  accent={Boolean(royalties)} />
          </div>
        ) : null;
      })()}

      {loaded && engineOnline === false && (
        <div className="card mt-8" style={{ borderLeft: "3px solid var(--status-amber)" }}>
          <div className="text-[13px] text-text-secondary">
            The local engine is offline — the shelf can&apos;t be loaded. Start the
            SCRPT companion.
          </div>
        </div>
      )}

      {(seriesGroups.length > 0 || standalone.length > 0) && (
        <div className="mt-12 flex items-baseline gap-3 pb-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
          <h2 className="serif-display text-[24px] font-semibold">Fiction</h2>
          <span className="text-[12px] text-text-faint">{seriesGroups.reduce((n, g) => n + g.books.length, 0) + standalone.length} titles</span>
        </div>
      )}
      {seriesGroups.map((group) => (
        <section key={group.id} className="mt-10">
          <Link href={`/shelf/series/${group.id}`}
                className="group/series inline-flex items-baseline gap-3 mb-4">
            <h2 className="serif-display text-[19px] font-semibold text-text-secondary group-hover/series:text-accent transition-colors">
              {group.title}
            </h2>
            <span className="text-[12px] text-text-faint font-sans">
              series · {group.books.length} books
            </span>
            <span className="text-[12px] text-accent opacity-0 group-hover/series:opacity-100 transition-opacity">
              Open series →
            </span>
          </Link>
          <BookRow books={group.books} />
        </section>
      ))}

      {standalone.length > 0 && (
        <section className="mt-10">
          {seriesGroups.length > 0 && (
            <h2 className="serif-display text-[19px] font-semibold text-text-secondary mb-4">
              Standalone
            </h2>
          )}
          <BookRow books={standalone} />
        </section>
      )}

      {(wings.nonfiction.seriesGroups.length > 0 || wings.nonfiction.standalone.length > 0) && (
        <>
          <div className="mt-16 flex items-baseline gap-3 pb-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <h2 className="serif-display text-[24px] font-semibold">Non-fiction</h2>
            <span className="text-[12px] text-text-faint">
              {wings.nonfiction.seriesGroups.reduce((n, g) => n + g.books.length, 0) + wings.nonfiction.standalone.length} titles
            </span>
          </div>
          {wings.nonfiction.seriesGroups.map((group) => (
            <section key={group.id} className="mt-10">
              <Link href={`/shelf/series/${group.id}`} className="group/series inline-flex items-baseline gap-3 mb-4">
                <h2 className="serif-display text-[19px] font-semibold text-text-secondary group-hover/series:text-accent transition-colors">{group.title}</h2>
                <span className="text-[12px] text-text-faint font-sans">series · {group.books.length} books</span>
              </Link>
              <BookRow books={group.books} />
            </section>
          ))}
          {wings.nonfiction.standalone.length > 0 && (
            <section className="mt-10">
              {wings.nonfiction.seriesGroups.length > 0 && (
                <h2 className="serif-display text-[19px] font-semibold text-text-secondary mb-4">Standalone</h2>
              )}
              <BookRow books={wings.nonfiction.standalone} />
            </section>
          )}
        </>
      )}

      {(wings.childrens.seriesGroups.length > 0 || wings.childrens.standalone.length > 0) && (
        <>
          <div className="mt-16 flex items-baseline gap-3 pb-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <h2 className="serif-display text-[24px] font-semibold">Children&rsquo;s books</h2>
            <span className="text-[12px] text-text-faint">
              {wings.childrens.seriesGroups.reduce((n, g) => n + g.books.length, 0) + wings.childrens.standalone.length} titles
            </span>
          </div>
          {wings.childrens.seriesGroups.map((group) => (
            <section key={group.id} className="mt-10">
              <Link href={`/shelf/series/${group.id}`} className="group/series inline-flex items-baseline gap-3 mb-4">
                <h2 className="serif-display text-[19px] font-semibold text-text-secondary group-hover/series:text-accent transition-colors">{group.title}</h2>
                <span className="text-[12px] text-text-faint font-sans">series · {group.books.length} books</span>
              </Link>
              <BookRow books={group.books} />
            </section>
          ))}
          {wings.childrens.standalone.length > 0 && (
            <section className="mt-10">
              {wings.childrens.seriesGroups.length > 0 && (
                <h2 className="serif-display text-[19px] font-semibold text-text-secondary mb-4">Standalone</h2>
              )}
              <BookRow books={wings.childrens.standalone} />
            </section>
          )}
        </>
      )}

      {loaded && books.length === 0 && engineOnline && (
        <div className="card mt-10 text-center py-16">
          <div className="serif-display text-[22px] font-semibold">
            Nothing on the shelf yet
          </div>
          <p className="text-[13px] text-text-secondary mt-2">
            Commission the first book and it will appear here, spine out.
          </p>
          <Link href="/workorder" className="btn-brass mt-6">New Work Order</Link>
        </div>
      )}
    </div>
  );
}

function BookRow({ books }: { books: ScrptBook[] }) {
  return (
    <div className="grid gap-5"
         style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))" }}>
      {books.map((book, i) => <BookSpine key={book.id} book={book} colorIndex={i} />)}
    </div>
  );
}

type ShelfStatus = { label: string; color: string };

/** The real lifecycle state, derived from data — not the stale DB status. */
function releaseLine(book: ScrptBook): string {
  const d = book.data as { release?: { date?: string; mode?: string; status?: string };
                           publishing?: { released_at?: string; asin?: string }; external?: boolean };
  const rel = d.release || {};
  const fmt = (iso: string) => {
    const dt = new Date(iso + "T00:00:00");
    return isNaN(dt.getTime()) ? iso : dt.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  };
  if (d.publishing?.asin || d.external) return rel.date ? `Released ${fmt(rel.date)}` : "Released";
  if (rel.date) return `Release ${fmt(rel.date)}${rel.mode === "scheduled" ? " (scheduled)" : ""}`;
  return "No release date";
}

function deriveStatus(book: ScrptBook): ShelfStatus {
  const d = book.data as {
    publishing?: { asin?: string; uploaded_at?: string; released_at?: string };
    external?: boolean;
    acceptance?: { verdict?: string };
    manuscript?: { status?: string; chapters?: { blocks: unknown[] }[] };
  };
  const pub = d.publishing || {};

  // Released — live on Amazon (carries an ASIN, or imported from KDP)
  if (pub.asin || d.external) return { label: "Released", color: "var(--status-green)" };
  // Uploaded — submitted to KDP, not yet live
  if (pub.uploaded_at) return { label: "Uploaded", color: "var(--status-blue)" };

  const ms = d.manuscript;
  const finished = ms && (
    ["drafted", "accepted", "editing", "locked", "ready"].includes(ms.status || "") ||
    Boolean(d.acceptance?.verdict) ||
    (Boolean(ms.chapters?.length) && ms.chapters!.every((c) => c.blocks.length > 0))
  );
  if (finished) return { label: "Written", color: "var(--status-blue)" };

  // still in production
  if (ms?.status === "drafting" || book.status === "generating")
    return { label: "Writing", color: "var(--status-amber)" };
  return { label: "Draft", color: "var(--text-tertiary)" };
}

function BookSpine({ book, colorIndex }: { book: ScrptBook; colorIndex: number }) {
  const ms = book.data.manuscript;
  const external = Boolean((book.data as { external?: boolean }).external);
  const front = book.data.cover?.cover_front_png || (book.data.cover as { mode?: string })?.mode === "amazon";
  const spineColor = SPINE_COLORS[colorIndex % SPINE_COLORS.length];
  const progress = external
    ? 1
    : ms && ms.chapters
      ? ms.status === "drafted" || ms.status === "editing" || ms.status === "locked"
        ? 1
        : ms.chapters.length
          ? ms.chapters.filter((c) => c.blocks.length > 0).length / ms.chapters.length
          : 0
      : 0;

  const openCover = useCoverLightbox();
  // Every tile used to be forced to 5.5 x 8.5, so a square picture book was
  // cropped to a portrait and lost its title off the edge. Draw each book in
  // its own trim — the shelf should look like the shelf.
  const trimSize = String(
    (book.data?.format as { trim_size?: string } | undefined)?.trim_size
    || (book.data?.trim_size as string | undefined)
    || "5.5x8.5");
  const [trimW, trimH] = (() => {
    const m = trimSize.toLowerCase().split("x").map((n) => parseFloat(n));
    return m.length === 2 && m.every((n) => n > 0) ? m : [5.5, 8.5];
  })();
  return (
    <Link href={`/shelf/${book.catalog_number}`} className="group block">
      <div
        className="relative rounded-[6px] overflow-hidden transition-transform duration-200 group-hover:-translate-y-2 shelf-card"
        style={{
          aspectRatio: `${trimW} / ${trimH}`,
          background: front
            ? undefined
            : `linear-gradient(160deg, ${spineColor}, #14100d 90%)`,
          boxShadow: "var(--shadow-page)",
          border: "1px solid rgba(236,229,218,0.08)",
        }}
      >
        {front ? (
          <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`${scrpt.engineUrl}/api/files/${book.catalog_number}/cover-front.png`}
               alt={book.title} className="absolute inset-0 w-full h-full object-contain" />
          <button
            onClick={(e) => { e.preventDefault(); e.stopPropagation();
              openCover(`${scrpt.engineUrl}/api/files/${book.catalog_number}/cover-front.png`, book.title); }}
            title="View cover fullscreen"
            className="absolute top-2 left-2 z-10 h-7 w-7 rounded-full flex items-center justify-center
                       opacity-0 group-hover:opacity-100 transition-opacity text-[13px] cursor-zoom-in"
            style={{ background: "rgba(8,7,5,0.62)", color: "#ece5da",
                     backdropFilter: "blur(3px)" }}>
            ⛶
          </button>
          </>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center text-center p-4">
            <div className="mt-[22%] serif-display text-[15px] leading-snug text-[#e8dfd0]">
              {book.title}
            </div>
            <div className="mt-auto mb-4 text-[10px] tracking-[0.18em] uppercase text-[#a6987f]">
              {(book.data.author_name as string) || "—"}
            </div>
          </div>
        )}
        {/* drafting progress */}
        {progress > 0 && progress < 1 && (
          <div className="absolute bottom-0 inset-x-0 h-[3px]" style={{ background: "rgba(0,0,0,0.5)" }}>
            <div className="h-full" style={{ width: `${progress * 100}%`, background: "var(--accent)" }} />
          </div>
        )}
      </div>
      <div className="mt-2.5 px-0.5">
        <div className="text-[12px] font-medium truncate group-hover:text-accent transition-colors">
          {book.title}
        </div>
        <div className="text-[11px] text-text-faint flex items-center justify-between mt-1">
          <span className="text-[9px] font-semibold tracking-[0.09em] uppercase px-1.5 py-[2px] rounded"
                style={{ color: deriveStatus(book).color,
                         background: "color-mix(in srgb, currentColor 14%, transparent)" }}>
            {deriveStatus(book).label}
          </span>
          {ms?.word_count ? (
            <span>
              {/* a picture book is hundreds of words, not thousands — rounding
                  to thousands showed "0k words" for a finished book */}
              {ms.word_count < 1000
                ? `${ms.word_count.toLocaleString()} words`
                : `${Math.round(ms.word_count / 1000)}k words`}
            </span>
          ) : null}
        </div>
        <div className="text-[10px] text-text-faint mt-0.5 flex items-center justify-between gap-2">
          <span>{book.catalog_number}</span>
          <span className="truncate" title="Release date">{releaseLine(book)}</span>
        </div>
        {typeof (book as { production_cost_usd?: number | null }).production_cost_usd === "number" && (
          <div className="text-[10px] mt-0.5 flex items-center justify-between" title="Production cost to date — every model call booked to this title">
            <span className="text-text-faint">Production cost</span>
            <span style={{ color: "var(--accent)" }}>${((book as { production_cost_usd?: number }).production_cost_usd ?? 0).toFixed(2)}</span>
          </div>
        )}
      </div>
    </Link>
  );
}


// ── Series builder: make a series from existing standalone books ──
type Candidate = { catalog: string; title: string; author?: string; genre?: string; series?: string | null; book_number?: number | null };

function SeriesBuilder({ onDone }: { onDone: () => void }) {
  const [rows, setRows] = useState<Candidate[]>([]);
  const [order, setOrder] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    fetch(`${scrpt.engineUrl}/api/scrpt/series/candidates`)
      .then((r) => (r.ok ? r.json() : { books: [] })).then((d) => setRows(d.books || [])).catch(() => {});
  }, []);

  const toggle = (c: string) => setOrder((o) => (o.includes(c) ? o.filter((x) => x !== c) : [...o, c]));
  const move = (c: string, dir: -1 | 1) => setOrder((o) => {
    const i = o.indexOf(c); const j = i + dir;
    if (i < 0 || j < 0 || j >= o.length) return o;
    const n = [...o]; [n[i], n[j]] = [n[j], n[i]]; return n;
  });

  const create = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/series/group`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ series_title: name.trim(), catalogs: order }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || "Could not create the series"); return; }
      setMsg(`${d.series_title}: ${d.books.length} books numbered, ${d.wraps_rebuilt.length} print wraps rebuilt.`);
      setTimeout(onDone, 1200);
    } catch { setMsg("Could not create the series"); } finally { setBusy(false); }
  };

  const byCat = Object.fromEntries(rows.map((r) => [r.catalog, r]));
  return (
    <div className="card mt-6">
      <div className="serif-display text-[17px] font-semibold">Group books into a series</div>
      <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed max-w-[640px]">
        Pick unreleased books and put them in reading order. SCRPT numbers them,
        gives them one series identity (for covers, KDP and the release planner),
        and rebuilds the print wraps so the back cover carries “Series · Book N”.
        Live titles are joined to a series on KDP itself.
      </p>
      <div className="grid gap-5 mt-4" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div>
          <div className="text-[11px] uppercase tracking-[0.1em] text-text-faint mb-2">Available books</div>
          <div className="space-y-1 max-h-[300px] overflow-y-auto pr-1">
            {rows.map((r) => (
              <label key={r.catalog} className="flex items-center gap-2 text-[13px] cursor-pointer">
                <input type="checkbox" checked={order.includes(r.catalog)} onChange={() => toggle(r.catalog)} />
                <span className="truncate">{r.title}</span>
                <span className="text-text-faint text-[11px] shrink-0">{r.catalog}{r.series ? ` · ${r.series} #${r.book_number}` : ""}</span>
              </label>
            ))}
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.1em] text-text-faint mb-2">Reading order</div>
          {order.length === 0 && <div className="text-[12px] text-text-faint">Tick books on the left.</div>}
          <div className="space-y-1">
            {order.map((c, i) => (
              <div key={c} className="flex items-center gap-2 text-[13px]">
                <span className="text-text-faint w-5 text-right">{i + 1}</span>
                <span className="truncate flex-1">{byCat[c]?.title || c}</span>
                <button className="btn-ghost text-[11px]" onClick={() => move(c, -1)} disabled={i === 0}>↑</button>
                <button className="btn-ghost text-[11px]" onClick={() => move(c, 1)} disabled={i === order.length - 1}>↓</button>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 mt-4">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Series title"
                   className="flex-1 rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[13px]" />
            <button className="btn-brass text-[12px]" disabled={busy || order.length < 2 || !name.trim()} onClick={create}>
              Create series
            </button>
          </div>
          {msg && <div className="text-[12px] mt-2" style={{ color: "var(--status-green)" }}>{msg}</div>}
        </div>
      </div>
    </div>
  );
}
