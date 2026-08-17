# Book Length Norms — SCRPT Calibration Reference

Researched 2026-08-17 (sources at bottom; [S] = well-sourced, [E] = estimate).
These numbers drive GENRE_PRESETS in engine/prose/models.py and the length
warnings in the Publishing checklist.

## The one-line rule

**Estimate printed pages as words ÷ 275** (use ÷250 for airy fiction at small
trims, ÷300 for dense 6x9 nonfiction), then add ~12 pages of front/back matter.

## Fiction

| Genre | Floor | Sweet spot | Ceiling | Chapters | Words/ch | Trim | Pages @ sweet |
|---|---|---|---|---|---|---|---|
| Action thriller | 70k | **95k–110k** | 120k | 40–60 | 1,800–2,800 | 5.5x8.5 / 6x9 | ~360–420 |
| Legal thriller | 80k | **95k–115k** | 130k | 30–40 | 3,000–4,500 | 5.5x8.5 / 6x9 | ~370–440 |
| Conspiracy thriller | 90k | **100k–120k** | 140k | **90–110** | **1,000–1,500** | 5.5x8.5 | ~390–460 |
| Contemporary romance (KU/indie) | 45k | **55k–70k** | 85k | 20–25 | ~3,000 | 5x8 / 5.25x8 | ~220–280 |
| Contemporary romance (trad print) | 50k | 70k–80k | 90k | 24–28 | ~3,000 | 5.25x8 | ~280–320 |
| Historical romance | 75k | **85k–95k** | 110k | 28–32 | ~3,000 | 5.25x8 | ~330–380 |

Structure signatures:
- **Action thriller** (Baldacci teaches 3–5 page chapters): short scene-chapters,
  alternating hero/antagonist POV, cliffhanger outs.
- **Legal thriller** (Grisham): longer procedural chapters, less POV-hopping.
- **Conspiracy** (The Da Vinci Code: 105 chapters, ~1,300–1,800 words each [S]):
  2–5 page chapters, every chapter ends on a micro-reveal, 3+ POV threads,
  24–48h story clock. The chapter rhythm IS the genre.
- **Romance**: dual alternating POV, HEA mandatory, epilogue near-mandatory.
  KU economics favor 55–70k rapid-release series over single long books.

Calibration warnings: don't imitate the classics' lengths — Bourne Identity
~183k, Killing Floor ~144–178k, A Time to Kill ~169k [all E] are pre-modern-market
outliers. Today's acquisition band is 90–110k.

## Non-fiction

| Genre | Floor | Sweet spot | Ceiling | Chapters | Words/ch | Trim | Pages @ sweet |
|---|---|---|---|---|---|---|---|
| Self-help | 35k | **45k–60k** | 75k | 12–16 | ~3,500 | 6x9 | ~180–230 |
| Business/productivity | 45k | **55k–70k** | 80k | 10–15 | ~4,000 | 6x9 | ~210–260 |
| Mindfulness/spirituality | 30k | **40k–55k** | 65k | 10–12 | ~3,800 | 5.5x8.5 | ~170–220 |

Comps: Atomic Habits ~75k [E], 320pp, 20 chapters in 6 parts, chapter-end
summary boxes [S]. The Power of Now ~59k [E], 236pp, 10 chapters. Deep Work
~74k [E], 296pp. E-Myth ~67k [E], 268pp. (7 Habits at ~105k is a pre-90s
outlier — don't calibrate to it.)

## KDP practicalities

- **79-page minimum for spine text** on the cover [S].
- **Perceived value**: ~200pp is the credibility floor for a $12.99+ novel;
  sub-150pp fiction reads "thin" at premium prices. Nonfiction tolerates
  150–250pp fine.
- **Printing cost** scales with pages: 300pp ≈ $4.60; at $12.99/60% that's
  ~$3.19/copy royalty. Longer ≠ better margin — every 25 pages ≈ $0.30 cost.
- **KU/KENP**: KENP ≠ print pages. KENPC v2 ≈ ~212 words per KENP page
  (community-measured, 174–215 observed). A fully-read 60k romance ≈ 280–320
  KENP ≈ $1.15–1.45/borrow at current rates. Compute per title; don't hardcode.

## Sources

Reedsy, Manuscript Academy 2026, Kindlepreneur (genre word counts & chapter
lengths); UEA Lee Child archive (Killing Floor chapters); Novel Word Count /
WordsRated (Grisham, Baldacci); Literature & Latte (Da Vinci Code chapter
analysis); Yael's Library (romance subgenre guidelines); Reading Length +
Wikipedia + PRH (nonfiction comps); KDPEasy (words-per-page divisors);
kboards / Just Publishing Advice (KENPC history); KDP official help
(spine/printing/royalty). Classic-title word counts are third-party estimates
— treat with ±15% error bars.

## Indie/KU thriller band (added from competitor reference, 2026-08-17)

Real-world KDP competitor example: "The Capitol Contract" (Patriot Files #3,
indie, Aug 2025): **215 pages ≈ 55-65k words** — far below the trad band,
mirroring the KU romance pattern. The indie-velocity position: 55-70k words,
~200-250 pages, rapid series release, KU-first, comp-author targeting
("for fans of Vince Flynn / Jack Carr / Patterson") directly in the subtitle.
Two viable strategies per series: trad-length (95-110k, print credibility,
higher cost/slower) vs indie-velocity (55-70k, faster testing, thinner).
SCRPT default stays trad-length; test velocity-band series via the Work
Order's target-length override and let read-through decide.

## HOUSE FORMATS (codified 2026-08-17 — research-validated defaults per genre)

| Genre | Trim | Paper | Evidence |
|---|---|---|---|
| Action/legal/conspiracy thriller | **5.5 × 8.5″** | cream | Dark State (#1 indie, Financial) exactly 5.5×8.5/452pp; Terminal List mass pb 5.31×8.25; indie standard |
| Romance (contemporary + historical) | **5.25 × 8″** | cream | Researched band 5–5.5″ × 8–8.5″; 5.25×8 in-band with better print economics than 5×8 |
| Self-help / business | **6 × 9″** | white | Dominant non-fiction trade standard (multiple sources) |
| Mindfulness | **5.5 × 8.5″** | cream | Intimate trim, fiction-adjacent feel |

These ARE the GENRE_PRESETS defaults — the Work Order applies them
automatically; override per book only with reason. Top-chart empirical word
counts: winning indie thrillers are FULL LENGTH (Dark State 452pp ≈ 110k;
Terminal List 432pp ≈ 105-115k) — the 215pp mid-tail book is not the model.
