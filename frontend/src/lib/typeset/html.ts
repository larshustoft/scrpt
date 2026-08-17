/**
 * Block -> HTML. ONE generator used by both the measuring pass and the page
 * renderer, so measured geometry always matches rendered geometry exactly.
 */

import type { Block } from "@/lib/scrpt";
import type { FormatSpec } from "./geometry";

function esc(s: string): string {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/** *italic* -> <em>italic</em> (the only inline markup in the dialect) */
export function inline(s: string): string {
  return esc(s).replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

/**
 * Chapter body flow styles. Font size in pt (CSS pt = 1/72in, exact in
 * Chromium); indents in em; everything else derives from the format spec.
 */
export function flowCSS(f: FormatSpec): string {
  const paraSpacing = f.paragraphStyle === "spaced";
  return `
    .sc-flow {
      font-family: "${f.fontFamily}", Georgia, serif;
      font-size: ${f.fontSizePt}pt;
      line-height: ${f.leading};
      color: var(--paper-ink, #1c1914);
      text-align: ${f.justify ? "justify" : "left"};
      hyphens: auto;
      -webkit-hyphens: auto;
      hyphenate-limit-chars: 6 3 3;
      font-kerning: normal;
      font-variant-ligatures: common-ligatures;
      overflow-wrap: break-word;
    }
    .sc-flow p {
      margin: 0;
      text-indent: ${paraSpacing ? "0" : "1.3em"};
      orphans: 1; widows: 1; /* we do our own control */
    }
    .sc-flow p.sc-noindent { text-indent: 0; }
    ${paraSpacing ? ".sc-flow p + p { margin-top: 0.55em; }" : ""}
    .sc-flow h2 {
      font-size: ${(f.fontSizePt * 1.18).toFixed(2)}pt;
      font-weight: 600;
      margin: 1.5em 0 0.6em 0;
      text-align: left;
      line-height: 1.25;
      page-break-after: avoid;
    }
    .sc-flow h3 {
      font-size: ${(f.fontSizePt * 1.02).toFixed(2)}pt;
      font-weight: 600;
      font-style: italic;
      margin: 1.2em 0 0.4em 0;
      text-align: left;
      line-height: 1.25;
    }
    .sc-flow .sc-scenebreak {
      text-align: center;
      margin: ${(f.leading * 0.9).toFixed(2)}em 0;
      letter-spacing: 0.4em;
      text-indent: 0.4em; /* visually recenters spaced glyphs */
    }
    .sc-flow blockquote {
      margin: 0.8em 1.6em;
      font-style: italic;
      text-align: left;
    }
    .sc-flow ul, .sc-flow ol {
      margin: 0.6em 0 0.6em 1.5em;
      padding: 0;
      text-align: left;
    }
    .sc-flow li { margin: 0.2em 0; }
    .sc-flow .sc-box {
      border: 0.75pt solid #1c1914;
      padding: 0.7em 0.9em;
      margin: 0.9em 0;
      text-align: left;
      page-break-inside: avoid;
    }
    .sc-flow .sc-box .sc-box-title {
      font-weight: 600;
      font-size: ${(f.fontSizePt * 0.82).toFixed(2)}pt;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-bottom: 0.4em;
    }
    .sc-flow .sc-box p { text-indent: 0; margin-top: 0.35em; }
    .sc-flow .sc-dropcap::first-letter {
      font-size: 3.1em;
      float: left;
      line-height: 0.82;
      padding: 0.04em 0.06em 0 0;
      font-weight: 500;
    }
  `;
}

/**
 * Render one block to HTML.
 * data-bid carries the block id for click-to-edit hit testing.
 */
export function blockHTML(b: Block, opts: { noindent?: boolean; dropcap?: boolean } = {}): string {
  const cls = [
    opts.noindent ? "sc-noindent" : "",
    opts.dropcap ? "sc-dropcap sc-noindent" : "",
  ].filter(Boolean).join(" ");
  switch (b.type) {
    case "paragraph":
      return `<p data-bid="${b.id}"${cls ? ` class="${cls}"` : ""}>${inline(b.text)}</p>`;
    case "heading":
      return b.level === 3
        ? `<h3 data-bid="${b.id}">${inline(b.text)}</h3>`
        : `<h2 data-bid="${b.id}">${inline(b.text)}</h2>`;
    case "scene_break":
      return `<div data-bid="${b.id}" class="sc-scenebreak" data-atomic="1">${esc("* * *")}</div>`;
    case "blockquote":
      return `<blockquote data-bid="${b.id}">${inline(b.text)}</blockquote>`;
    case "bullet_list":
      return `<ul data-bid="${b.id}">${(b.items || []).map((i) => `<li>${inline(i)}</li>`).join("")}</ul>`;
    case "numbered_list":
      return `<ol data-bid="${b.id}">${(b.items || []).map((i) => `<li>${inline(i)}</li>`).join("")}</ol>`;
    case "callout":
    case "exercise":
      return `<div data-bid="${b.id}" class="sc-box" data-atomic="1">${
        b.title ? `<div class="sc-box-title">${inline(b.title)}</div>` : ""
      }${(b.text || "").split(/\n\n+/).map((p) => `<p>${inline(p)}</p>`).join("")}</div>`;
    default:
      return "";
  }
}

/**
 * A chapter's full flow HTML. First paragraph after the opening (and after
 * scene breaks / headings) gets no indent, per trade convention.
 */
export function chapterFlowHTML(blocks: Block[], f: FormatSpec): string {
  const out: string[] = [];
  let noindentNext = true;
  blocks.forEach((b, i) => {
    if (b.type === "paragraph") {
      const dropcap = f.dropCaps && i === 0;
      out.push(blockHTML(b, { noindent: noindentNext, dropcap }));
      noindentNext = false;
    } else {
      out.push(blockHTML(b));
      if (b.type === "scene_break" || b.type === "heading") noindentNext = true;
    }
  });
  return out.join("\n");
}
