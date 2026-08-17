# KDP Interior Formatting & Platform Reference (verified August 2026)

Engineering spec for the SCRPT interior builder. Numbers verified against official KDP help pages August 2026; source links at the bottom.

## 1. Trim sizes

### Paperback (16 supported sizes, US site)

| Trim (in) | mm | Max pages (B&W) |
|---|---|---|
| 5 × 8 | 127 × 203.2 | 828 |
| 5.06 × 7.81 | 128.5 × 198.4 | 828 |
| 5.25 × 8 | 133.4 × 203.2 | 828 |
| 5.5 × 8.5 | 139.7 × 215.9 | 828 |
| **6 × 9** | 152.4 × 228.6 | 828 |
| 6.14 × 9.21 | 156 × 233.9 | 828 |
| 6.69 × 9.61 | 169.9 × 244.1 | 828 |
| 7 × 10 | 177.8 × 254 | 828 |
| 7.44 × 9.69 | 189 × 246.1 | 828 |
| 7.5 × 9.25 | 190.5 × 235 | 828 |
| 8 × 10 | 203.2 × 254 | 828 |
| 8.25 × 6 | 209.6 × 152.4 | 800 |
| 8.25 × 8.25 | 209.6 × 209.6 | 800 |
| 8.5 × 8.5 | 215.9 × 215.9 | 590 |
| 8.5 × 11 | 215.9 × 279.4 | 590 |
| 8.27 × 11.69 (A4) | 210 × 297 | 780 |

- "Standard" vs "large": anything wider than 6.12" or taller than 9" counts as **large trim** (raises printing cost ~20–30%). 6×9 is standard; 6.14×9.21 is large.
- Most common: **6×9** (nonfiction/trade default), **5×8, 5.25×8, 5.5×8.5** (fiction), **8.5×11** (workbooks/low-content), **8.5×8.5** (square, children's).
- Custom trim allowed within 4×6" to 8.5×11.69", but custom sizes lose Expanded Distribution.

### Hardcover (5 sizes only)

5.5×8.5, 6×9, 6.14×9.21, 7×10, 8.25×11 — all **75–550 pages**. No groundwood, no standard color for hardcover.

### Ink/paper options

| Option | Paper | Page range (paperback) |
|---|---|---|
| Black ink, white paper | 50–61 lb (74–90 GSM) | 24–828 |
| Black ink, cream paper | 50–61 lb (74–90 GSM) | 24–776 |
| Black ink, groundwood | 45 lb (60 GSM) | 24–812 (US-only, cheaper) |
| Standard color, white | 50–61 lb | **72–600** |
| Premium color, white | 60–71 lb (88–105 GSM) | 24–828 |

Cream is the fiction convention; white for nonfiction/anything with images.

## 2. Margins (the critical table)

**Inside (gutter) margin — function of TOTAL page count, applies with or without bleed:**

| Page count | Minimum gutter |
|---|---|
| 24–150 | 0.375" (9.6 mm) |
| 151–300 | 0.5" (12.7 mm) |
| 301–500 | 0.625" (15.9 mm) |
| 501–700 | 0.75" (19.1 mm) |
| 701–828 | 0.875" (22.3 mm) |

**Outside/top/bottom minimums:** 0.25" (6.4 mm) without bleed; **0.375" (9.6 mm) with bleed**. These are hard minimums — real books use more (typically 0.5–1"). Same table applies to hardcover.

**Bleed:** bleed elements must extend 0.125" (3.2 mm) past trim. A PDF with bleed is sized **trim width + 0.125"** (bleed on outside edge only — never the gutter) × **trim height + 0.25"** (0.125" top + 0.125" bottom). E.g. 6×9 with bleed → PDF page = **6.125 × 9.25"**. No-bleed PDF page = exactly trim size.

## 3. Page counts & spine width

- Min pages: paperback **24**, hardcover **75**. Page count = PDF pages (each side counts); KDP pads to even.
- **Paperback spine width:**
  - White paper: pages × **0.002252"** (0.0572 mm)
  - Cream paper: pages × **0.0025"** (0.0635 mm)
  - Premium color: pages × **0.002347"** (0.0596 mm)
  - Standard color: pages × 0.002252"
  - Spine text allowed only at 79+ pages (needs ≥0.0625"/1.6 mm clearance from spine edges; fold-line variance 0.0625").
- Hardcover spine is **not** a simple multiplier: stepped internal table (page block + ~0.189" board allowance); case-wrap covers extend **0.51" (15 mm)** past board edges, **0.4" (10 mm)** hinge gap between spine and cover safe area. Use KDP's official calculator table: https://kdp.amazon.com/cover-calculator. For SCRPT: compute paperback spines ourselves; replicate KDP's table for hardcover.

## 4. Interior PDF requirements

- **PDF required** if the interior has bleed (DOC/DOCX/RTF/HTML/TXT otherwise accepted, but PDF is the only true-to-print path).
- **Single pages, not spreads.**
- **All fonts embedded**; flatten transparencies and layers.
- **No crop/trim marks, bookmarks, comments, annotations, invisible objects, placeholder text, or metadata.**
- Images: **300 DPI minimum**, ≤600 DPI recommended; grayscale for B&W interiors; sRGB or CMYK for color (KDP converts — expect slight shifts).
- **Minimum font size 7 pt.** Line thickness ≥ 0.75 pt (thin hairlines drop out).
- **Max file size 650 MB.** Sequential page order.
- Page size must exactly equal trim (no bleed) or trim + bleed allowance (with bleed) — the renderer must enforce this.

## 5. Typography conventions (trade-book standards, not KDP rules)

Professional conventions (Chicago Manual of Style / Bringhurst) — KDP only enforces the numbers above.

- **Body fonts:** old-style/transitional serifs — Garamond, Caslon, Minion Pro, Baskerville, Palatino, Sabon, Bembo, Janson, Dante. Bookerly is Amazon's Kindle *screen* font (not for print). Free print-safe picks: **EB Garamond, Crimson Pro, Libre Caslon, Source Serif, Literata.**
- **Size/leading:** body 10–12 pt (fiction typically 10.5–11.5 pt); leading 120–145% of size (e.g. 11/14.5 or 11/15). Line length target 60–70 characters.
- **Justified** with **hyphenation on** (max 2–3 consecutive hyphens).
- **Widows/orphans:** no widow at top of page; avoid orphans at bottom; facing pages bottom-align (vertical justification) or run short in pairs.
- **Paragraphs:** first-line indent 1–1.5 em, **no space between paragraphs** (space-between = nonfiction/manuals only; never both). **First paragraph after any heading/chapter opening: no indent.** Scene breaks: blank line or ornament (***); use an ornament when a scene break falls at a page break.
- **Chapter openings:** new page; **sink of ~1/3 page**; optional drop cap (2–3 lines) or small caps for first 3–5 words; no running header on chapter openers.
- **Running headers:** verso = author or book title; recto = book title or chapter title. Suppressed on chapter openers, blanks, and front-matter display pages.
- **Page numbers:** front matter lowercase roman (often suppressed on display pages); body restarts at **arabic 1** on chapter 1's first page. Verso = even, recto = odd — hard invariant.

## 6. Front/back matter — canonical order

(* = must begin recto)

1. Half title* (title only) — i
2. Frontispiece or "Also by" — verso of half title
3. Title page* (title, subtitle, author, imprint) — iii
4. **Copyright page** (verso of title) — iv
5. Dedication* — v
6. Epigraph*
7. Table of contents* (print fiction usually omits)
8. Foreword* (by someone else), Preface* (by author), Acknowledgments
9. Introduction* (if setup rather than argument)
10. Second half title (optional) → **Body** (chapter 1 starts recto, arabic p.1)
11. Back matter: Appendix, Notes, Glossary, Bibliography, Index (nonfiction); Acknowledgments, About the Author, "Also by", newsletter/review ask (fiction, order flexible)

**Copyright page for a self-published KDP book:** © line; "All rights reserved." + no-reproduction clause; fiction disclaimer; ISBN(s) — one per format; edition line ("First edition 2026"); credits; optional imprint + contact. **KDP mandates almost none of this** — only that title/author match metadata and a printed ISBN match the assigned one. Free KDP ISBN → publisher listed as "Independently published", Amazon-only; own ISBN (Bowker) → own imprint name + wide distribution. KDP auto-adds a cover barcode if missing.

## 7. Kindle eBook side (brief)

- Upload formats: **EPUB, DOCX/DOC, KPF**. MOBI fully discontinued March 18, 2025.
- Reflowable EPUB 3 with clean CSS is the export target; don't depend on embedded fonts (Kindle overrides with Bookerly); relative sizes; semantic nav doc; cover ≥1600×2560 recommended.
- QA gate: epubcheck + **Kindle Previewer** desktop app.

## 8. Platform/back-office data

- **KDP Reports** (kdpreports.amazon.com): Dashboard, Combined Sales, per-format Royalty tabs, Orders, **KENP Read** (~$0.004–0.0045/page from monthly fund), Month-to-Date, Prior Months, Payments. Columns: Royalty Date, Title, ASIN/ISBN, Marketplace, Royalty Type, Transaction Type, Units/Net Units, Avg List Price. **XLSX/CSV export.**
- **No public KDP API — confirmed (Aug 2026).** SP-API has no KDP data. Third-party tools scrape the logged-in dashboard or import report files. **SCRPT: build on report XLSX/CSV import** — matches the DistroKid statement-import pattern, no login-automation risk.
- **Print royalty** (since June 10, 2025): royalty = rate × list price − printing cost. **60%** at/above threshold ($9.99 US / £7.99 / €9.99 / $13.99 CAD/AUD / ¥1,000), **50%** below. Expanded Distribution 40% − printing cost.
- **Printing cost (US):** paperback B&W: 24–110 pp flat **$2.30**; 110–828 pp = **$1.00 + $0.012/page**. Premium color: 24–40 pp flat $3.60; 42+ = $1.00 + **$0.065/page**. Standard color (72–600 pp): $1.00 + **$0.0255/page**. Large trim ~20–30% higher; groundwood ~5% cheaper. Hardcover B&W: **$5.65 + $0.012/page** (75–108 pp flat $5.65). Max list price $250.
- **eBook royalty:** 70% requires $2.99–$9.99 US list minus delivery fee (**$0.15/MB**); 35% otherwise. (One unverified 2026 report says the 70% band expands to $12.99 on July 7, 2026 — check https://kdp.amazon.com/en_US/help/topic/G200634500 before hardcoding.)

## Engineering notes (deltas that will bite the renderer)

1. **Gutter depends on final pagination** — a reflow crossing 150/300/500/700 pages must retrigger margin recompute (iterate to fixed point).
2. **Bleed is asymmetric**: outside edge only, never the gutter — verso and recto pages have mirrored geometry.
3. Standard color's floor is 72 pages (not 24); cream tops out at 776.
4. Even/odd invariant (recto = odd) + "chapter 1 = arabic 1 on recto" forces inserted blanks — model blank-page insertion explicitly.
5. Export both variants: no-bleed (page = trim) and bleed (trim +0.125" w / +0.25" h) — never crop marks.

## Sources

- Trim/margins/bleed: https://kdp.amazon.com/en_US/help/topic/GVBQ3CMEQW3W2VL6
- Print options/paper: https://kdp.amazon.com/en_US/help/topic/G201834180
- Submission guidelines/PDF: https://kdp.amazon.com/en_US/help/topic/G201857950
- Paperback spine formulas: https://kdp.amazon.com/en_US/help/topic/G201953020
- Hardcover cover: https://kdp.amazon.com/en_US/help/topic/GDTKFJPNQCBTMRV6
- Paperback printing cost: https://kdp.amazon.com/en_US/help/topic/G201834340
- Hardcover printing cost: https://kdp.amazon.com/en_US/help/topic/GHT976ZKSKUXBB6H
- Print royalties: https://kdp.amazon.com/en_US/help/topic/G201834330
- eBook royalties: https://kdp.amazon.com/en_US/help/topic/G200644210
- Reports: https://kdp.amazon.com/en_US/help/topic/G201488550
- Cover calculator: https://kdp.amazon.com/cover-calculator
