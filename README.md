# SCRPT — Write. Publish. Sell.

The AI book studio. SCRPT plots, writes, and typesets professional books —
thrillers, romance, self-help, business — formats them precisely for Amazon
KDP, narrates the audiobook, and tracks every royalty.

**scrpt.ai** · dark-study UI · adult fiction & non-fiction · print + ebook + audiobook

## Architecture

```
frontend/   Next.js app (Vercel-deployable) — HQ, Work Order, Bookshelf,
            Formatting Studio, Analytics. Auth via Supabase.
engine/     Local FastAPI companion (this machine) — Claude writing pipeline,
            pagination-true PDF export (Playwright), cover spec engine,
            ElevenLabs audiobook mastering, KDP report import. SQLite storage.
supabase/   Auth + account schema.
docs/       KDP_INTERIOR_SPEC.md — verified formatting rules the engine enforces.
output/     One folder per catalog number (SC-xxx): interior.pdf, cover files,
            audiobook masters, designer packages.
```

The cloud frontend handles accounts and UI; the **companion engine** runs
locally so manuscripts, PDFs, and API keys stay on the publisher's machine.

## Quick start (development)

```bash
./start.sh          # engine :8000 + frontend :3000
```

Or separately:

```bash
PYTHONPATH=. python3 -m uvicorn engine.main:app --port 8000   # engine
cd frontend && npm run dev                                     # frontend
```

## Setup for a new user

1. **Account** — sign up at the frontend (Supabase auth; email confirm).
2. **Companion** — `pip3 install -r engine/requirements.txt`,
   `playwright install chromium`, then `companion/install.sh` to run the
   engine at login.
3. **Keys** — `.env` in the project root: `ANTHROPIC_API_KEY` (writing),
   `OPENAI_API_KEY` (cover artwork). ElevenLabs key + voice go in Settings.
4. **Publisher identity** — Settings → publisher name, pen names, KDP email.

## The pipeline

1. **Work Order** — fiction/non-fiction, genre preset, idea, optional series
   (2–12 books). SCRPT develops three plot directions.
2. **Write** — pick a direction; the engine builds a story/concept bible,
   outlines, drafts chapter-by-chapter with rolling continuity, then writes
   the listing copy. Everything is editable afterwards.
3. **Format** — the Formatting Studio paginates the manuscript with real
   trade-book rules (mirrored margins, KDP gutter tiers, widow/orphan
   control, running heads, front matter). Click any paragraph to edit; the
   book reflows live. Export = vector PDF via the same layout engine.
4. **Cover** — spine width computed from the real page count. Either the AI
   path or a designer package (spec sheet + template PDF) with upload
   validation.
5. **Audiobook** — ElevenLabs narration per chapter, mastered to retail spec
   (192 kbps CBR, loudness-normalized), retail sample included.
6. **Publish** — manual KDP upload (no API exists; 3 titles/day cap; AI
   disclosure required). Royalties come back via KDP report XLSX import on
   the Analytics page.

## Non-negotiables

- **KDP AI disclosure**: SCRPT books are AI-generated with human editing —
  disclose on upload. The engine bakes this into the publishing checklist.
- **No KDP login automation**: account safety. Uploads are manual; royalty
  sync is file-import.
- **No fabricated citations** in non-fiction: hard rule in the drafting
  prompts + evidence policy in every concept bible.
