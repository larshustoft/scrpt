/**
 * SCRPT typesetting geometry — KDP-exact page math.
 * All figures verified against docs/KDP_INTERIOR_SPEC.md.
 *
 * CSS resolves 1in = 96px and 1pt = 96/72px in Chromium, so measuring at
 * CSS-pixel scale and printing at inch scale is exact — the preview IS the
 * print file.
 */

export const PPI = 96; // CSS pixels per inch

export const TRIM_SIZES: Record<string, { w: number; h: number }> = {
  "5x8": { w: 5, h: 8 },
  "5.06x7.81": { w: 5.06, h: 7.81 },
  "5.25x8": { w: 5.25, h: 8 },
  "5.5x8.5": { w: 5.5, h: 8.5 },
  "6x9": { w: 6, h: 9 },
  "6.14x9.21": { w: 6.14, h: 9.21 },
  "6.69x9.61": { w: 6.69, h: 9.61 },
  "7x10": { w: 7, h: 10 },
  "7.44x9.69": { w: 7.44, h: 9.69 },
  "7.5x9.25": { w: 7.5, h: 9.25 },
  "8x10": { w: 8, h: 10 },
  "8.5x8.5": { w: 8.5, h: 8.5 },
  "8.5x11": { w: 8.5, h: 11 },
};

/** KDP minimum inside (gutter) margin by total page count. */
export function kdpMinGutter(pageCount: number): number {
  if (pageCount <= 150) return 0.375;
  if (pageCount <= 300) return 0.5;
  if (pageCount <= 500) return 0.625;
  if (pageCount <= 700) return 0.75;
  return 0.875;
}

export interface FontPreset {
  label: string;
  family: string;
  sizePt: number;
  leading: number; // unitless line-height
}

export const FONT_PRESETS: Record<string, FontPreset> = {
  garamond: { label: "EB Garamond", family: "EB Garamond", sizePt: 11.5, leading: 1.35 },
  ebgaramond_lg: { label: "EB Garamond Large", family: "EB Garamond", sizePt: 12.5, leading: 1.42 },
  crimson: { label: "Crimson Pro", family: "Crimson Pro", sizePt: 11.5, leading: 1.38 },
  literata: { label: "Literata", family: "Literata", sizePt: 10.5, leading: 1.45 },
  sourceserif: { label: "Source Serif 4", family: "Source Serif 4", sizePt: 10.5, leading: 1.45 },
};

export interface FormatSpec {
  trimKey: string;
  trimW: number;          // inches
  trimH: number;
  paperType: string;
  fontFamily: string;
  fontSizePt: number;
  leading: number;
  justify: boolean;
  paragraphStyle: "indent" | "spaced";
  chapterSink: number;    // fraction of body height
  dropCaps: boolean;
  headerVerso: "author" | "title" | "none";
  headerRecto: "title" | "chapter" | "none";
  sceneBreakGlyph: string;
  marginTop: number;      // inches
  marginBottom: number;
  marginOutside: number;
  gutter: number;         // inches — resolved for the current page count
  gutterExtra: number;
}

import type { FormatConfig } from "@/lib/scrpt";

/** Resolve a book's FormatConfig into concrete geometry for a page count. */
export function resolveFormat(cfg: FormatConfig, pageCountEstimate: number): FormatSpec {
  const trim = TRIM_SIZES[cfg.trim_size] || TRIM_SIZES["5.5x8.5"];
  const preset = FONT_PRESETS[cfg.font_preset] || FONT_PRESETS.garamond;
  return {
    trimKey: cfg.trim_size,
    trimW: trim.w,
    trimH: trim.h,
    paperType: cfg.paper_type,
    fontFamily: preset.family,
    fontSizePt: cfg.font_size_pt || preset.sizePt,
    leading: cfg.leading || preset.leading,
    justify: cfg.justify,
    paragraphStyle: cfg.paragraph_style,
    chapterSink: cfg.chapter_sink,
    dropCaps: cfg.drop_caps,
    headerVerso: cfg.running_header_verso,
    headerRecto: cfg.running_header_recto,
    sceneBreakGlyph: cfg.scene_break_glyph || "* * *",
    marginTop: cfg.margin_top,
    marginBottom: cfg.margin_bottom,
    marginOutside: cfg.margin_outside,
    gutter: kdpMinGutter(pageCountEstimate) + (cfg.gutter_extra || 0),
    gutterExtra: cfg.gutter_extra || 0,
  };
}

/** Text block width in CSS px (same for recto and verso — margins mirror). */
export function textWidthPx(f: FormatSpec): number {
  return (f.trimW - f.gutter - f.marginOutside) * PPI;
}

/** Text block height in CSS px (excludes header/folio bands — they live in the margins). */
export function textHeightPx(f: FormatSpec): number {
  return (f.trimH - f.marginTop - f.marginBottom) * PPI;
}

export function romanNumeral(n: number): string {
  const table: [number, string][] = [
    [1000, "m"], [900, "cm"], [500, "d"], [400, "cd"], [100, "c"], [90, "xc"],
    [50, "l"], [40, "xl"], [10, "x"], [9, "ix"], [5, "v"], [4, "iv"], [1, "i"],
  ];
  let out = "";
  for (const [v, s] of table) {
    while (n >= v) { out += s; n -= v; }
  }
  return out;
}

/** Rough page estimate from word count, used to seed the gutter iteration. */
export function estimatePages(words: number, f: { trimW: number; trimH: number; fontSizePt: number; leading: number; marginTop: number; marginBottom: number; marginOutside: number }): number {
  const lineHeightIn = (f.fontSizePt * f.leading) / 72;
  const linesPerPage = (f.trimH - f.marginTop - f.marginBottom) / lineHeightIn;
  const charsPerLine = ((f.trimW - f.marginOutside - 0.55) * 72) / (f.fontSizePt * 0.5);
  const wordsPerPage = (linesPerPage * charsPerLine) / 5.7;
  return Math.max(24, Math.ceil(words / Math.max(80, wordsPerPage)) + 12);
}
