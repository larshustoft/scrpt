"use client";

/**
 * Headless print route — loaded by the engine's Playwright exporter.
 * Runs the exact same pagination engine as the Formatting Studio, renders
 * every page at trim size with hard page breaks, then signals readiness via
 * window.__PAGINATION_DONE__ / window.__PAGE_SPEC__.
 */

import { use, useEffect, useState } from "react";
import { scrpt, type Manuscript, type ScrptBook } from "@/lib/scrpt";
import { paginate, type Paginated, type PublisherSettings } from "@/lib/typeset/paginate";
import { PageView, pageStyleCSS } from "@/lib/typeset/render";
import { flowCSS } from "@/lib/typeset/html";

declare global {
  interface Window {
    __PAGINATION_DONE__?: boolean;
    __PAGE_SPEC__?: Record<string, unknown>;
  }
}

export default function PrintPage({ params }: { params: Promise<{ catalog: string }> }) {
  const { catalog } = use(params);
  const [book, setBook] = useState<ScrptBook | null>(null);
  const [pg, setPg] = useState<Paginated | null>(null);
  const [settings, setSettings] = useState<PublisherSettings>({});
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const b = await scrpt.getBook(catalog);
        let s: PublisherSettings = {};
        try {
          const res = await fetch(`${scrpt.engineUrl}/api/settings`);
          if (res.ok) s = await res.json();
        } catch { /* defaults */ }
        setBook(b);
        setSettings(s);
        const result = await paginate(b, s);
        setPg(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [catalog]);

  // signal the exporter once pages are actually in the DOM
  useEffect(() => {
    if (!pg || !book) return;
    const f = pg.spec;
    window.__PAGE_SPEC__ = {
      widthIn: f.trimW,
      heightIn: f.trimH,
      pageCount: pg.totalPages,
      gutterIn: f.gutter,
      outsideIn: f.marginOutside,
      bodyFontPt: f.fontSizePt,
      trimKey: f.trimKey,
      paperType: f.paperType,
    };
    // let the browser paint before declaring done
    requestAnimationFrame(() => requestAnimationFrame(() => {
      window.__PAGINATION_DONE__ = true;
    }));
  }, [pg, book]);

  if (error) {
    return <div style={{ padding: 40, color: "red" }} data-print-error>{error}</div>;
  }
  if (!book || !pg) {
    return <div style={{ padding: 40 }}>Paginating…</div>;
  }

  const ms = book.data.manuscript as Manuscript;

  return (
    <>
      <style>{`
        html, body { margin: 0 !important; padding: 0 !important; background: #fff; }
        .print-page { break-after: page; page-break-after: always; }
        .print-page .sc-page { background: #fff !important; color: #000 !important; }
        ${pageStyleCSS()}
        ${flowCSS(pg.spec)}
        .sc-flow { color: #000 !important; }
      `}</style>
      {pg.pages.map((page, i) => (
        <div className="print-page" key={i}>
          <PageView page={page} pg={pg} book={book} ms={ms} settings={settings} />
        </div>
      ))}
    </>
  );
}
