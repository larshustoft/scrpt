"use client";

/**
 * PageView — renders one paginated page at exact physical size (CSS inches).
 * Shared by the Formatting Studio preview and the /print export route, so
 * what you see is byte-for-byte what KDP receives.
 */

import type { Manuscript, ScrptBook } from "@/lib/scrpt";
import { romanNumeral } from "./geometry";
import type { PageModel, Paginated, PublisherSettings } from "./paginate";
import { buildCopyrightHTML } from "./paginate";
import { inline } from "./html";


// THE TITLE-LINE RULE (Lars, 2026-09-09): a divided title never puts one
// word alone on a line — at least three words a line, balanced in length.
// Measured by character count here (the print engine measures in points).
const TITLE_LINE_CHARS = 24;
export function titleLines(title: string, minWords = 3): string[] {
  const t = title.trim().replace(/\s+/g, " ");
  if (t.length <= TITLE_LINE_CHARS) return [t];
  const ws = t.split(" ");
  let best: string[] | null = null, bestScore = Infinity;
  const parts = (start: number, left: number): string[][][] => {
    if (left === 1) return ws.length - start >= minWords ? [[ws.slice(start)]] : [];
    const out: string[][][] = [];
    for (let n = minWords; n <= ws.length - start - minWords * (left - 1); n++)
      for (const rest of parts(start + n, left - 1)) out.push([ws.slice(start, start + n), ...rest]);
    return out;
  };
  for (let k = 2; k <= 3; k++) {
    if (ws.length < k * minWords) break;
    for (const split of parts(0, k)) {
      const lines = split.map((p) => p.join(" "));
      const lens = lines.map((l) => l.length);
      if (Math.max(...lens) > TITLE_LINE_CHARS + 6) continue;
      const score = k * 100 + (Math.max(...lens) - Math.min(...lens));
      if (score < bestScore) { best = lines; bestScore = score; }
    }
    if (best) return best;
  }
  return [t];                                   // too few words to divide well: one line, scaled down
}
export function titleScale(title: string): number {
  const longest = Math.max(...titleLines(title).map((l) => l.length));
  return longest <= TITLE_LINE_CHARS ? 1 : Math.max(0.6, TITLE_LINE_CHARS / longest);
}

export function pageStyleCSS(): string {
  return `
    .sc-page {
      background: var(--paper, #f6f1e7);
      color: var(--paper-ink, #1c1914);
      position: relative;
      overflow: hidden;
      box-sizing: border-box;
      flex-shrink: 0;
    }
    .sc-page * { box-sizing: border-box; }
    .sc-runhead {
      position: absolute;
      left: 0; right: 0;
      text-align: center;
      font-variant: small-caps;
      letter-spacing: 0.14em;
    }
    .sc-folio {
      position: absolute;
      left: 0; right: 0;
      text-align: center;
    }
    .sc-opener-label {
      letter-spacing: 0.22em;
      text-transform: uppercase;
      opacity: 0.55;
    }
  `;
}

interface PageViewProps {
  page: PageModel;
  pg: Paginated;
  book: ScrptBook;
  ms: Manuscript;
  settings: PublisherSettings;
  onBlockClick?: (blockId: string) => void;
  highlightBlockId?: string | null;
}

export function PageView({
  page, pg, book, ms, settings, onBlockClick, highlightBlockId,
}: PageViewProps) {
  const f = pg.spec;
  const recto = page.side === "recto";
  const padLeft = recto ? f.gutter : f.marginOutside;
  const padRight = recto ? f.marginOutside : f.gutter;
  const basePt = f.fontSizePt;

  const pageStyle: React.CSSProperties = {
    width: `${f.trimW}in`,
    height: `${f.trimH}in`,
    paddingTop: `${f.marginTop}in`,
    paddingBottom: `${f.marginBottom}in`,
    paddingLeft: `${padLeft}in`,
    paddingRight: `${padRight}in`,
    fontFamily: `"${f.fontFamily}", Georgia, serif`,
  };

  const author = (book.data.author_name as string) || "";
  const series = book.data.series;

  return (
    <div className="sc-page" style={pageStyle} data-side={page.side}>
      {/* running head */}
      {page.header && (
        <div className="sc-runhead"
             style={{ top: `${f.marginTop * 0.42}in`, fontSize: `${basePt * 0.82}pt` }}>
          {page.header}
        </div>
      )}
      {/* folio */}
      {page.folio && (
        <div className="sc-folio"
             style={{ bottom: `${f.marginBottom * 0.38}in`, fontSize: `${basePt * 0.9}pt` }}>
          {page.folio.style === "roman" ? romanNumeral(page.folio.n) : page.folio.n}
        </div>
      )}

      {page.kind === "body" && page.body && (
        <BodyWindowView page={page} pg={pg} onBlockClick={onBlockClick}
                        highlightBlockId={highlightBlockId} />
      )}

      {page.kind === "half_title" && (
        <Centered topFrac={0.3}>
          <div style={{ fontSize: `${basePt * 1.7}pt`, letterSpacing: "0.04em" }}>
            {book.title}
          </div>
        </Centered>
      )}

      {page.kind === "also_by" && (
        <Centered topFrac={0.28}>
          <div style={{ fontSize: `${basePt * 0.95}pt`, fontVariant: "small-caps",
                        letterSpacing: "0.14em", opacity: 0.6, marginBottom: "1.2em" }}>
            Also by {author || "the author"}
          </div>
          {(ms.front_matter.also_by || []).map((t, i) => (
            <div key={i} style={{ fontStyle: "italic", fontSize: `${basePt}pt`,
                                  marginTop: "0.5em" }}>{t}</div>
          ))}
        </Centered>
      )}

      {page.kind === "title" && (
        <div style={{ height: "100%", display: "flex", flexDirection: "column",
                      alignItems: "center", textAlign: "center" }}>
          <div style={{ marginTop: `${0.24 * 100}%` }}>
            <div style={{ fontSize: `${basePt * 2.3 * titleScale(book.title)}pt`, lineHeight: 1.15 }}>
              {titleLines(book.title).map((ln, i) => (
                <span key={i} style={{ display: "block", whiteSpace: "nowrap" }}>{ln}</span>
              ))}
            </div>
            {ms.tagline && (
              <div style={{ fontSize: `${basePt * 0.95}pt`, fontStyle: "italic",
                            opacity: 0.7, marginTop: "1.4em" }}>
                {ms.tagline}
              </div>
            )}
            {series?.series_title && (
              <div style={{ fontSize: `${basePt * 0.85}pt`, fontVariant: "small-caps",
                            letterSpacing: "0.16em", opacity: 0.6, marginTop: "1.6em" }}>
                {series.series_title} · Book {series.book_number}
              </div>
            )}
          </div>
          <div style={{ marginTop: "auto" }}>
            <div style={{ fontSize: `${basePt * 1.15}pt`, letterSpacing: "0.06em" }}>
              {author}
            </div>
            {/* the house mark: the TigerWorks lockup, never small (Lars, 2026-09-08/09);
                the lockup carries its own wordmark, so no text beside it */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/brand/tigerworks-black.png" alt="TigerWorks"
                 style={{ width: "0.8in", height: "0.8in", objectFit: "contain", marginTop: "1.4em",
                          display: "block", marginLeft: "auto", marginRight: "auto" }} />
          </div>
        </div>
      )}

      {page.kind === "copyright" && (
        <div
          style={{ height: "100%", display: "flex", flexDirection: "column",
                   justifyContent: "flex-end", fontSize: `${basePt * 0.72}pt`,
                   lineHeight: 1.5 }}
          dangerouslySetInnerHTML={{
            __html: `<style>.sc-cp p{margin:0 0 0.7em 0;}</style><div class="sc-cp">${
              buildCopyrightHTML(book, ms, settings)}</div>`,
          }}
        />
      )}

      {page.kind === "dedication" && (
        <Centered topFrac={0.3}>
          <div style={{ fontStyle: "italic", fontSize: `${basePt}pt`,
                        maxWidth: "70%", margin: "0 auto", lineHeight: 1.7 }}
               dangerouslySetInnerHTML={{ __html: inline(ms.front_matter.dedication) }} />
        </Centered>
      )}

      {page.kind === "epigraph" && (
        <Centered topFrac={0.3}>
          <div style={{ fontStyle: "italic", fontSize: `${basePt}pt`,
                        maxWidth: "75%", margin: "0 auto", lineHeight: 1.7 }}
               dangerouslySetInnerHTML={{ __html: inline(ms.front_matter.epigraph) }} />
          {ms.front_matter.epigraph_source && (
            <div style={{ fontSize: `${basePt * 0.85}pt`, opacity: 0.65,
                          marginTop: "1.2em" }}>
              — {ms.front_matter.epigraph_source}
            </div>
          )}
        </Centered>
      )}

      {page.kind === "toc" && page.tocEntries && (
        <div style={{ height: "100%" }}>
          <div style={{ textAlign: "center", fontSize: `${basePt * 1.4}pt`,
                        letterSpacing: "0.08em", margin: "0.4in 0 0.5in" }}>
            Contents
          </div>
          <div style={{ fontSize: `${basePt * 0.95}pt` }}>
            {page.tocEntries.map((e, i) => (
              <div key={i} style={{ display: "flex", alignItems: "baseline",
                                    margin: "0.55em 0" }}>
                <span style={{ opacity: 0.55, minWidth: "2.2em" }}>{e.label}</span>
                <span>{e.title}</span>
                <span style={{ flex: 1, borderBottom: "1px dotted rgba(28,25,20,0.35)",
                               margin: "0 0.5em", transform: "translateY(-0.25em)" }} />
                <span>{e.page}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Centered({ topFrac, children }: { topFrac: number; children: React.ReactNode }) {
  return (
    <div style={{ height: "100%", textAlign: "center" }}>
      <div style={{ paddingTop: `${topFrac * 100}%` }}>{children}</div>
    </div>
  );
}

function BodyWindowView({ page, pg, onBlockClick, highlightBlockId }: {
  page: PageModel; pg: Paginated;
  onBlockClick?: (blockId: string) => void;
  highlightBlockId?: string | null;
}) {
  const f = pg.spec;
  const b = page.body!;
  const windowH = b.endPx - b.startPx;
  const flowHTML = pg.flows[b.flowKey] || "";

  const handleClick = onBlockClick
    ? (e: React.MouseEvent) => {
        const el = (e.target as HTMLElement).closest("[data-bid]");
        if (el) onBlockClick(el.getAttribute("data-bid")!);
      }
    : undefined;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {b.opener && (
        <div style={{ height: pg.sinkPx, display: "flex", flexDirection: "column",
                      justifyContent: "flex-end", paddingBottom: `${f.fontSizePt * 1.8}pt`,
                      textAlign: "center" }}>
          {b.openerLabel ? (
            <div className="sc-opener-label"
                 style={{ fontSize: `${f.fontSizePt * 0.8}pt` }}>
              {b.openerLabel}
            </div>
          ) : null}
          {b.openerTitle ? (
            <div style={{ fontSize: `${f.fontSizePt * 1.6}pt`, lineHeight: 1.2,
                          marginTop: "0.5em" }}>
              {b.openerTitle}
            </div>
          ) : null}
          <div style={{ width: "18%", margin: "1.1em auto 0",
                        borderBottom: "0.75pt solid rgba(28,25,20,0.5)" }} />
        </div>
      )}
      <div style={{ height: windowH, overflow: "hidden", position: "relative" }}
           onClick={handleClick}>
        <div
          className="sc-flow"
          style={{ width: pg.bodyWidthPx, transform: `translateY(${-b.startPx}px)`,
                   cursor: onBlockClick ? "text" : undefined }}
          dangerouslySetInnerHTML={{
            __html: highlightBlockId
              ? flowHTML.replace(
                  `data-bid="${highlightBlockId}"`,
                  `data-bid="${highlightBlockId}" style="background:rgba(201,164,92,0.18)"`)
              : flowHTML,
          }}
        />
      </div>
    </div>
  );
}
