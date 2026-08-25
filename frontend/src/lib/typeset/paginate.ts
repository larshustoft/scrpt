/**
 * SCRPT pagination engine.
 *
 * Measures real line boxes in the DOM (same fonts, same widths as the final
 * render), then packs lines onto pages with trade-book rules: widow/orphan
 * control, headings kept with their text, atomic boxes, chapter sinks,
 * recto/verso mirrored margins, KDP gutter iteration, blank-page insertion,
 * roman/arabic folios and running heads.
 *
 * Browser-only: call from effects. The /print route runs the same code, so
 * the exported PDF is identical to the studio preview.
 */

import type { Block, Chapter, FormatConfig, Manuscript, ScrptBook } from "@/lib/scrpt";
import {
  estimatePages, kdpMinGutter, resolveFormat,
  textHeightPx, textWidthPx, type FormatSpec,
} from "./geometry";
import { chapterFlowHTML, flowCSS } from "./html";

// ── model ────────────────────────────────────────────────────────

export type FrontKind =
  | "half_title" | "also_by" | "title" | "copyright" | "dedication"
  | "epigraph" | "toc";

export interface BodyWindow {
  /** key into Paginated.flows */
  flowKey: string;
  opener: boolean;
  openerLabel?: string;   // "Chapter 7" | section title
  openerTitle?: string;
  startPx: number;        // clip window start inside the flow
  endPx: number;
}

export interface PageModel {
  kind: FrontKind | "body" | "blank";
  side: "recto" | "verso";
  folio: { style: "roman" | "arabic"; n: number } | null;
  header: string | null;
  body?: BodyWindow;
  tocEntries?: { label: string; title: string; page: number }[];
}

export interface Paginated {
  pages: PageModel[];
  spec: FormatSpec;
  flows: Record<string, string>;        // flowKey -> flow HTML
  chapterStartPages: { label: string; title: string; page: number }[];
  totalPages: number;
  bodyHeightPx: number;
  bodyWidthPx: number;
  sinkPx: number;
}

// ── measurement ──────────────────────────────────────────────────

interface Unit {
  top: number;
  bottom: number;
  kind: "line" | "atomic" | "heading";
  lineIndex: number;      // within its paragraph (line units)
  lineCount: number;
}

function groupRects(rects: DOMRect[]): { top: number; bottom: number }[] {
  const sorted = rects
    .filter((r) => r.height > 0 && r.width > 0)
    .sort((a, b) => a.top - b.top);
  const lines: { top: number; bottom: number }[] = [];
  for (const r of sorted) {
    const last = lines[lines.length - 1];
    if (last && r.top < last.bottom - 2) {
      last.top = Math.min(last.top, r.top);
      last.bottom = Math.max(last.bottom, r.bottom);
    } else {
      lines.push({ top: r.top, bottom: r.bottom });
    }
  }
  return lines;
}

function lineRectsOf(el: Element): { top: number; bottom: number }[] {
  const rects: DOMRect[] = [];
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let node: Node | null;
  while ((node = walker.nextNode())) {
    const range = document.createRange();
    range.selectNodeContents(node);
    for (const r of Array.from(range.getClientRects())) rects.push(r as DOMRect);
  }
  return groupRects(rects);
}

/** Measure a flow's line/atomic units. Container must already be in the DOM. */
function measureFlow(flowRoot: HTMLElement): Unit[] {
  const base = flowRoot.getBoundingClientRect().top;
  const units: Unit[] = [];
  for (const el of Array.from(flowRoot.children)) {
    const tag = el.tagName.toLowerCase();
    const atomic = el.hasAttribute("data-atomic");
    const isHeading = tag === "h2" || tag === "h3";
    if (atomic || isHeading) {
      const r = el.getBoundingClientRect();
      if (r.height > 0) {
        units.push({
          top: r.top - base, bottom: r.bottom - base,
          kind: isHeading ? "heading" : "atomic", lineIndex: 0, lineCount: 1,
        });
      }
    } else if (tag === "ul" || tag === "ol") {
      for (const li of Array.from(el.children)) {
        const r = li.getBoundingClientRect();
        if (r.height > 0) {
          units.push({
            top: r.top - base, bottom: r.bottom - base,
            kind: "atomic", lineIndex: 0, lineCount: 1,
          });
        }
      }
    } else {
      const lines = lineRectsOf(el);
      lines.forEach((l, i) => {
        units.push({
          top: l.top - base, bottom: l.bottom - base,
          kind: "line", lineIndex: i, lineCount: lines.length,
        });
      });
    }
  }
  return units.sort((a, b) => a.top - b.top);
}

/** Greedy packer with widow/orphan/heading rules. Returns window ranges. */
function packUnits(
  units: Unit[], availFirst: number, availRest: number,
): { startPx: number; endPx: number }[] {
  if (units.length === 0) return [{ startPx: 0, endPx: 0 }];
  const pages: { startPx: number; endPx: number }[] = [];
  let i = 0;
  while (i < units.length) {
    const avail = pages.length === 0 ? availFirst : availRest;
    const S = units[i].top;
    let j = i;
    while (j + 1 < units.length && units[j + 1].bottom - S <= avail) j++;

    if (j + 1 < units.length) {
      // orphan: lone first line of a multi-line paragraph at page bottom
      const last = units[j];
      if (last.kind === "line" && last.lineIndex === 0 && last.lineCount > 1 && j > i) j--;
      // widow: paragraph's lone last line would open the next page
      const next = units[j + 1];
      if (next && next.kind === "line" &&
          next.lineIndex === next.lineCount - 1 && next.lineCount > 1 && j > i) {
        j--;
      }
      // heading must not sit alone at the bottom
      while (j > i && units[j].kind === "heading") j--;
    }
    pages.push({ startPx: S, endPx: units[j].bottom });
    i = j + 1;
  }
  return pages;
}

// ── copyright page text ──────────────────────────────────────────

export interface PublisherSettings {
  publisher_name?: string;
  copyright_holder?: string;
  website?: string;
}

export function buildCopyrightHTML(
  book: ScrptBook, ms: Manuscript, settings: PublisherSettings,
): string {
  if (ms.front_matter.copyright_text) {
    return ms.front_matter.copyright_text
      .split(/\n\n+/).map((p) => `<p>${p}</p>`).join("");
  }
  const year = new Date(book.created_at || Date.now()).getFullYear();
  const author = (book.data.author_name as string) || "the Author";
  const publisher = settings.publisher_name || "";
  const fiction = ms.kind === "fiction";
  const parts = [
    `<p>Copyright © ${year} ${author}</p>`,
    `<p>All rights reserved. No part of this publication may be reproduced, distributed, or transmitted in any form or by any means, including photocopying, recording, or other electronic or mechanical methods, without the prior written permission of the publisher, except in the case of brief quotations embodied in critical reviews and certain other noncommercial uses permitted by copyright law.</p>`,
  ];
  if (fiction) {
    parts.push(
      `<p>This is a work of fiction. Names, characters, businesses, places, events, and incidents are either the products of the author's imagination or used in a fictitious manner. Any resemblance to actual persons, living or dead, or actual events is purely coincidental.</p>`,
    );
  }
  if (publisher) parts.push(`<p>Published by ${publisher}${settings.website ? ` · ${settings.website}` : ""}</p>`);
  parts.push(`<p>First edition ${year}</p>`);
  return parts.join("");
}

// ── main entry ───────────────────────────────────────────────────

export async function paginate(
  book: ScrptBook, settings: PublisherSettings = {},
): Promise<Paginated> {
  const ms = book.data.manuscript as Manuscript;
  const cfg = book.data.format as FormatConfig;
  if (!ms || !cfg) throw new Error("Book has no manuscript/format data");

  await document.fonts.ready;

  const chapters = ms.chapters.filter((c) => c.blocks.length > 0);

  // back matter pseudo-sections
  const backSections: { key: string; label: string; title: string; blocks: Block[] }[] = [];
  const bm = ms.back_matter;
  const paraBlocks = (text: string): Block[] =>
    text.split(/\n\n+/).filter(Boolean).map((t, i) => ({
      id: `bm-${i}-${t.length}`, type: "paragraph" as const, text: t.trim(),
    }));
  if (bm?.next_in_series_cta) {
    backSections.push({ key: "back-next", label: "", title: "The story continues",
      blocks: paraBlocks(bm.next_in_series_cta) });
  }
  if (bm?.acknowledgments) {
    backSections.push({ key: "back-ack", label: "", title: "Acknowledgments",
      blocks: paraBlocks(bm.acknowledgments) });
  }
  if (bm?.about_the_author) {
    backSections.push({ key: "back-author", label: "", title: "About the Author",
      blocks: paraBlocks(bm.about_the_author) });
  }

  // gutter iteration: estimate -> paginate -> check tier -> repeat (max 3)
  let assumedPages = estimatePages(ms.word_count || 40000, {
    // the four format values come from the spread below; declaring zeroes
    // here as well made them dead properties that TypeScript rejects in a
    // production build, which is what broke the Vercel deploy
    marginTop: cfg.margin_top, marginBottom: cfg.margin_bottom,
    marginOutside: cfg.margin_outside,
    ...((): { trimW: number; trimH: number; fontSizePt: number; leading: number } => {
      const f = resolveFormat(cfg, 300);
      return { trimW: f.trimW, trimH: f.trimH, fontSizePt: f.fontSizePt, leading: f.leading };
    })(),
  });

  let result: Paginated | null = null;
  for (let iteration = 0; iteration < 3; iteration++) {
    const spec = resolveFormat(cfg, assumedPages);
    result = buildPagination(book, ms, chapters, backSections, spec, settings);
    const actual = result.totalPages;
    if (kdpMinGutter(actual) === kdpMinGutter(assumedPages)) break;
    assumedPages = actual;
  }
  return result!;
}

function buildPagination(
  book: ScrptBook,
  ms: Manuscript,
  chapters: Chapter[],
  backSections: { key: string; label: string; title: string; blocks: Block[] }[],
  spec: FormatSpec,
  settings: PublisherSettings,
): Paginated {
  const bodyW = textWidthPx(spec);
  const bodyH = textHeightPx(spec);
  const sinkPx = Math.round(bodyH * spec.chapterSink);

  // ── measure all flows in one hidden container ──
  const container = document.createElement("div");
  container.style.cssText =
    `position:fixed;left:-100000px;top:0;width:${bodyW}px;visibility:hidden;pointer-events:none;`;
  const style = document.createElement("style");
  style.textContent = flowCSS(spec);
  container.appendChild(style);

  const flows: Record<string, string> = {};
  const flowEls: Record<string, HTMLElement> = {};
  const addFlow = (key: string, html: string) => {
    flows[key] = html;
    const el = document.createElement("div");
    el.className = "sc-flow";
    el.style.width = `${bodyW}px`;
    el.innerHTML = html;
    container.appendChild(el);
    flowEls[key] = el;
  };

  for (const ch of chapters) addFlow(`ch-${ch.index}`, chapterFlowHTML(ch.blocks, spec));
  for (const s of backSections) addFlow(s.key, chapterFlowHTML(s.blocks, spec));

  document.body.appendChild(container);
  const packed: Record<string, { startPx: number; endPx: number }[]> = {};
  try {
    for (const key of Object.keys(flowEls)) {
      const units = measureFlow(flowEls[key]);
      packed[key] = packUnits(units, bodyH - sinkPx, bodyH);
    }
  } finally {
    container.remove();
  }

  // ── assemble pages ──
  const pages: PageModel[] = [];
  const fm = ms.front_matter;
  const author = (book.data.author_name as string) || "";
  const title = book.title;

  const side = (): "recto" | "verso" => (pages.length % 2 === 0 ? "recto" : "verso");
  const pushBlank = () => pages.push({ kind: "blank", side: side(), folio: null, header: null });
  const ensureRecto = () => { if (side() === "verso") pushBlank(); };

  // front matter (roman numbering implicit by position; folios suppressed
  // on display pages, shown on ToC)
  if (fm.half_title) {
    pages.push({ kind: "half_title", side: "recto", folio: null, header: null });
    if (fm.also_by && fm.also_by.length > 0) {
      pages.push({ kind: "also_by", side: "verso", folio: null, header: null });
    } else {
      pushBlank();
    }
  }
  ensureRecto();
  pages.push({ kind: "title", side: side(), folio: null, header: null });
  if (fm.copyright_page !== false) {
    pages.push({ kind: "copyright", side: side(), folio: null, header: null });
  }
  if (fm.dedication) {
    ensureRecto();
    pages.push({ kind: "dedication", side: side(), folio: null, header: null });
  }
  if (fm.epigraph) {
    ensureRecto();
    pages.push({ kind: "epigraph", side: side(), folio: null, header: null });
  }

  const wantToc = fm.toc === null || fm.toc === undefined
    ? ms.kind === "nonfiction"
    : fm.toc;
  const tocPageIdx: number[] = [];
  if (wantToc) {
    ensureRecto();
    tocPageIdx.push(pages.length);
    pages.push({ kind: "toc", side: "recto",
      folio: { style: "roman", n: pages.length + 1 }, header: null });
    pushBlank(); // ToC verso stays empty; body must open recto anyway
  }

  // body — chapter 1 on a recto, arabic folio 1
  ensureRecto();
  const bodyStartIdx = pages.length;
  const chapterStartPages: { label: string; title: string; page: number }[] = [];

  const headerFor = (pageSide: "recto" | "verso", chapterTitle: string): string | null => {
    const mode = pageSide === "verso" ? spec.headerVerso : spec.headerRecto;
    if (mode === "none") return null;
    if (pageSide === "verso") return mode === "author" ? (author || title) : title;
    return mode === "chapter" ? (chapterTitle || title) : title;
  };

  const arabic = (idx: number) => idx - bodyStartIdx + 1;

  for (const ch of chapters) {
    const windows = packed[`ch-${ch.index}`] || [{ startPx: 0, endPx: 0 }];
    const label = ms.kind === "fiction" ? `Chapter ${ch.index}` : `${ch.index}`;
    chapterStartPages.push({ label, title: ch.title, page: arabic(pages.length) });
    windows.forEach((w, wi) => {
      const s = side();
      pages.push({
        kind: "body", side: s,
        folio: wi === 0 ? null : { style: "arabic", n: arabic(pages.length) },
        header: wi === 0 ? null : headerFor(s, ch.title),
        body: {
          flowKey: `ch-${ch.index}`, opener: wi === 0,
          openerLabel: wi === 0 ? label : undefined,
          openerTitle: wi === 0 ? ch.title : undefined,
          startPx: w.startPx, endPx: w.endPx,
        },
      });
    });
  }

  // back matter — each section opens on a recto
  for (const s of backSections) {
    ensureRecto();
    const windows = packed[s.key] || [{ startPx: 0, endPx: 0 }];
    windows.forEach((w, wi) => {
      const sd = side();
      pages.push({
        kind: "body", side: sd,
        folio: wi === 0 ? null : { style: "arabic", n: arabic(pages.length) },
        header: wi === 0 ? null : headerFor(sd, s.title),
        body: {
          flowKey: s.key, opener: wi === 0,
          openerLabel: "", openerTitle: s.title,
          startPx: w.startPx, endPx: w.endPx,
        },
      });
    });
  }

  // even page count
  if (pages.length % 2 === 1) pushBlank();

  // fill ToC entries now that body pages are known
  if (wantToc) {
    for (const idx of tocPageIdx) {
      pages[idx].tocEntries = chapterStartPages.map((c) => ({
        label: c.label, title: c.title, page: c.page,
      }));
    }
  }

  return {
    pages,
    spec,
    flows,
    chapterStartPages,
    totalPages: pages.length,
    bodyHeightPx: bodyH,
    bodyWidthPx: bodyW,
    sinkPx,
  };
}
