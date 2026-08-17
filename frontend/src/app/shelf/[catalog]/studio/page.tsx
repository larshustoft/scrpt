"use client";

/**
 * The Formatting Studio — true-to-print page preview and editor.
 * 1 / 2 (spread) / 4 page views, zoom, click-a-paragraph-to-edit with live
 * re-pagination, and vector PDF export through the engine.
 */

import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  pollJob, scrpt, type Block, type Manuscript, type ScrptBook,
} from "@/lib/scrpt";
import { paginate, type Paginated, type PublisherSettings } from "@/lib/typeset/paginate";
import { PageView, pageStyleCSS } from "@/lib/typeset/render";
import { flowCSS } from "@/lib/typeset/html";

type ViewMode = 1 | 2 | 4;

export default function StudioPage({ params }: { params: Promise<{ catalog: string }> }) {
  const { catalog } = use(params);
  const [book, setBook] = useState<ScrptBook | null>(null);
  const [settings, setSettings] = useState<PublisherSettings>({});
  const [pg, setPg] = useState<Paginated | null>(null);
  const [pageIdx, setPageIdx] = useState(0);
  const [view, setView] = useState<ViewMode>(2);
  const [zoom, setZoom] = useState(0.9);
  const [paginating, setPaginating] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState("");
  const [editing, setEditing] = useState<{ chapterId: string; block: Block } | null>(null);
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const pageInputRef = useRef<HTMLInputElement>(null);

  // load book + settings
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
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load book");
      }
    })();
  }, [catalog]);

  // paginate whenever the manuscript changes
  const repaginate = useCallback(async (b: ScrptBook, s: PublisherSettings) => {
    setPaginating(true);
    try {
      const result = await paginate(b, s);
      setPg(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Pagination failed");
    } finally {
      setPaginating(false);
    }
  }, []);

  useEffect(() => {
    if (book) repaginate(book, settings);
  }, [book, settings, repaginate]);

  const ms = book?.data.manuscript as Manuscript | undefined;
  const hasContent = Boolean(ms?.chapters.some((c) => c.blocks.length > 0));

  // block lookup for editing
  const blockIndex = useMemo(() => {
    const map = new Map<string, { chapterId: string; block: Block }>();
    ms?.chapters.forEach((ch) =>
      ch.blocks.forEach((b) => map.set(b.id, { chapterId: ch.id, block: b })));
    return map;
  }, [ms]);

  const openEditor = useCallback((blockId: string) => {
    const found = blockIndex.get(blockId);
    if (!found) return;
    setEditing(found);
    setEditText(
      found.block.type === "bullet_list" || found.block.type === "numbered_list"
        ? (found.block.items || []).join("\n")
        : found.block.text,
    );
  }, [blockIndex]);

  const saveEdit = async () => {
    if (!editing || !book || !ms) return;
    setSaving(true);
    try {
      const ch = ms.chapters.find((c) => c.id === editing.chapterId)!;
      const newBlocks = ch.blocks.map((b) => {
        if (b.id !== editing.block.id) return b;
        if (b.type === "bullet_list" || b.type === "numbered_list") {
          return { ...b, items: editText.split("\n").filter((l) => l.trim()) };
        }
        return { ...b, text: editText.trim() };
      }).filter((b) =>
        // deleting all text deletes the block
        b.type === "scene_break" || b.text.trim() || (b.items || []).length);
      await scrpt.saveChapter(catalog, editing.chapterId, newBlocks);
      const fresh = await scrpt.getBook(catalog);
      setBook(fresh);
      setEditing(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const doExport = async () => {
    setExporting(true);
    setExportMsg("Rendering in the print engine…");
    try {
      const { job_id } = await scrpt.exportInterior(catalog);
      const job = await pollJob(job_id, (j) => setExportMsg(j.detail || j.stage || "Exporting…"));
      if (job.status === "done") {
        const pages = (job.result as { page_count?: number })?.page_count;
        const passed = (job.result as { validation?: { passed?: boolean } })?.validation?.passed;
        setExportMsg(`Exported ${pages} pages — KDP validation ${passed ? "passed" : "FAILED"}`);
        const fresh = await scrpt.getBook(catalog);
        setBook(fresh);
      } else {
        setExportMsg(`Export ${job.status}: ${job.error?.split("\n")[0] || ""}`);
      }
    } catch (e) {
      setExportMsg(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  // keyboard paging
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editing || !pg) return;
      if (document.activeElement === pageInputRef.current) return;
      if (e.key === "ArrowRight" || e.key === "PageDown") {
        setPageIdx((i) => Math.min(pg.totalPages - 1, i + view));
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        setPageIdx((i) => Math.max(0, i - view));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pg, view, editing]);

  if (error) {
    return (
      <div className="max-w-[900px] mx-auto px-8 py-16">
        <div className="card" style={{ borderLeft: "3px solid var(--status-red)" }}>
          <div className="text-[13px]">{error}</div>
        </div>
      </div>
    );
  }

  if (!book || !ms) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <span className="serif-display text-accent tracking-[0.3em] pulse-soft">SCRPT</span>
      </div>
    );
  }

  // which pages to show
  const startIdx = view === 2 ? pageIdx - (pageIdx % 2) : pageIdx;
  const visiblePages = pg
    ? pg.pages.slice(startIdx, startIdx + view)
    : [];

  return (
    <div className="flex flex-col" style={{ height: "calc(100vh - 64px)" }}>
      {/* toolbar */}
      <div className="h-[52px] px-6 flex items-center gap-4 border-b border-border-subtle shrink-0"
           style={{ background: "var(--surface)" }}>
        <Link href={`/shelf/${catalog}`}
              className="text-[12px] text-text-tertiary hover:text-text-primary transition-colors">
          ← {book.title.length > 32 ? book.title.slice(0, 32) + "…" : book.title}
        </Link>

        <div className="h-4 w-px bg-border-subtle" />

        {/* view modes */}
        <div className="inline-flex p-0.5 rounded-md" style={{ background: "var(--surface-elevated)" }}>
          {([1, 2, 4] as ViewMode[]).map((v) => (
            <button key={v} onClick={() => setView(v)}
                    className={`px-2.5 h-6 rounded text-[11px] font-medium transition-all ${
                      view === v ? "text-text-primary" : "text-text-tertiary"
                    }`}
                    style={view === v ? { background: "var(--surface)" } : {}}>
              {v === 1 ? "Single" : v === 2 ? "Spread" : "Quad"}
            </button>
          ))}
        </div>

        {/* zoom */}
        <div className="flex items-center gap-2">
          <button className="btn-ghost px-2 py-1 text-[12px]" onClick={() => setZoom((z) => Math.max(0.3, z - 0.1))}>−</button>
          <span className="text-[11px] text-text-tertiary w-9 text-center">{Math.round(zoom * 100)}%</span>
          <button className="btn-ghost px-2 py-1 text-[12px]" onClick={() => setZoom((z) => Math.min(2, z + 0.1))}>+</button>
        </div>

        <div className="flex-1" />

        {/* pager */}
        {pg && (
          <div className="flex items-center gap-2 text-[12px] text-text-tertiary">
            <button className="btn-ghost px-2 py-1" onClick={() => setPageIdx((i) => Math.max(0, i - view))}>‹</button>
            <span>
              Page{" "}
              <input
                ref={pageInputRef}
                className="w-12 text-center input-scrpt py-0.5 px-1 inline-block"
                defaultValue={startIdx + 1}
                key={startIdx}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    const n = Number((e.target as HTMLInputElement).value);
                    if (n >= 1 && n <= pg.totalPages) setPageIdx(n - 1);
                  }
                }}
              />{" "}
              of {pg.totalPages}
            </span>
            <button className="btn-ghost px-2 py-1" onClick={() => setPageIdx((i) => Math.min(pg.totalPages - 1, i + view))}>›</button>
          </div>
        )}

        <div className="h-4 w-px bg-border-subtle" />

        <div className="flex items-center gap-3">
          {paginating && <span className="text-[11px] text-text-faint pulse-soft">Repaginating…</span>}
          {exportMsg && !paginating && (
            <span className="text-[11px] text-text-tertiary max-w-[260px] truncate">{exportMsg}</span>
          )}
          <button className="btn-brass text-[12px]" disabled={exporting || !hasContent} onClick={doExport}>
            {exporting ? "Exporting…" : "Export print PDF"}
          </button>
        </div>
      </div>

      {/* page canvas */}
      <div className="flex-1 overflow-auto flex items-start justify-center py-10"
           style={{ background: "#0a0908" }}>
        <style>{pageStyleCSS()}</style>
        {pg && <style>{flowCSS(pg.spec)}</style>}

        {!hasContent && (
          <div className="card mt-20 max-w-[420px] text-center py-12">
            <div className="serif-display text-[20px] font-semibold">Nothing to typeset yet</div>
            <p className="text-[13px] text-text-secondary mt-2">
              The manuscript hasn&apos;t been drafted. Once chapters exist, the
              studio lays them out exactly as they will print.
            </p>
          </div>
        )}

        {pg && hasContent && (
          <div
            className={`grid gap-8 ${view === 4 ? "grid-cols-2" : view === 2 ? "grid-cols-2" : "grid-cols-1"}`}
            style={{ transform: `scale(${zoom})`, transformOrigin: "top center" }}
          >
            {visiblePages.map((page, i) => (
              <div key={startIdx + i} className="relative">
                <PageView page={page} pg={pg} book={book} ms={ms} settings={settings}
                          onBlockClick={openEditor}
                          highlightBlockId={editing?.block.id || null} />
                <div className="absolute -bottom-6 inset-x-0 text-center text-[10px] text-text-faint">
                  {page.side} · {startIdx + i + 1}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* editor drawer */}
      {editing && (
        <div className="shrink-0 border-t border-border-subtle p-5"
             style={{ background: "var(--surface)" }}>
          <div className="max-w-[900px] mx-auto">
            <div className="flex items-center justify-between mb-2">
              <span className="label-scrpt mb-0">
                Editing {editing.block.type.replace("_", " ")} — changes reflow the book instantly
              </span>
              <div className="flex gap-2">
                <button className="btn-ghost text-[12px]" onClick={() => setEditing(null)}>
                  Cancel
                </button>
                <button className="btn-brass text-[12px]" disabled={saving} onClick={saveEdit}>
                  {saving ? "Saving…" : "Save & reflow"}
                </button>
              </div>
            </div>
            <textarea
              className="input-scrpt min-h-[110px] leading-relaxed"
              style={{ fontFamily: "var(--font-display)", fontSize: 15 }}
              value={editText}
              autoFocus
              onChange={(e) => setEditText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) saveEdit();
                if (e.key === "Escape") setEditing(null);
              }}
            />
            <div className="text-[11px] text-text-faint mt-1.5">
              *asterisks* for italics · ⌘⏎ saves · clearing all text deletes the block
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
