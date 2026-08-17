# Audiobook Distribution — platform strategy (researched 2026-08-17)

## The one fact that shapes everything
The biggest store (Audible, ~60-70% of retail) is CLOSED to third-party AI
audio; the fastest-growing one (Spotify) is wide open to ElevenLabs. The only
Audible path for AI is Amazon's own Virtual Voice (their voice, from your KDP
ebook, US-only, 40%, $3.99-14.99).

## The stack, in rollout order
1. **Spotify for Authors** (direct): free, unlimited, non-exclusive,
   explicitly ElevenLabs-friendly; 50% on a-la-carte + Premium listening pool;
   live in ~72h. First priority — the streaming pool rewards catalog volume.
2. **Google Play Books Partner Center** (direct): upload own audio, ~52%
   share class, most permissive specs, no ISBN (assigns GGKEY).
3. **Kobo Writing Life** (direct): 45% list / 32% Kobo Plus; narrator listed
   as "Synthesized Voice"; strong international reach.
4. **KDP Virtual Voice**: the Amazon/Audible play — join beta if not invited;
   requires the KDP ebook to exist (SCRPT produces it anyway).
5. **Voices by INaudio** (aggregator; Findaway's successor after Findaway
   closed Aug 2025): Apple Books (aggregator-only!), B&N, Chirp, Storytel,
   OverDrive/Hoopla libraries, Libro.fm; ~80% of net; ElevenLabs is on its
   approved-AI list. At scale, consider PublishDrive ($19.99/mo flat, keep
   100% of net) once aggregator revenue > ~$100/month. Never double-list one
   title to the same store via two routes.

## Delivery specs (SCRPT's audio pipeline already matches)
- Audio: per-chapter MP3, 192 kbps CBR, 44.1 kHz, RMS -23..-18 dB, peak
  <= -3 dB, opening/closing credits, retail sample — EXACTLY what
  engine/audio/pipeline.py masters. ✔
- Cover: SQUARE 1:1, 3000x3000 recommended (2400+ min) — now auto-produced
  as output/<catalog>/audiobook-cover.jpg on every cover install. ✔
- Narrator credit: use the platform's digital-voice flag; Kobo string =
  "Synthesized Voice". NEVER a fictitious human narrator name — the
  misrepresentation, not the AI, is the takedown trigger.
- ISBN: not required anywhere in the stack (free identifiers assigned).
- Tax: W-8BEN-E (non-US entity) in each portal; Spotify pays via Tipalti.

## Economics (calibrated ranges, not forecasts)
- Shares: Spotify 50% a-la-carte + pool; Google ~52%; Kobo 45%; Virtual
  Voice 40%; aggregated stores ~25-45% after cuts.
- Pricing norm 6-12h indie audiobooks: $9.99-19.99 (Virtual Voice caps 14.99).
- Per-title/year, AI-narrated at ~zero marginal narration cost:
  conservative $0-50, realistic $50-300, stretch $500-2,000+. This is a
  PORTFOLIO business: at catalog scale even modest per-title averages are
  real revenue because production cost is near zero.
- One real datapoint: ≈$2-3 per full-book-equivalent streamed on Spotify.

## Watch
Spotify's ElevenLabs-powered in-platform creation tool (invite beta since
June 2026, non-exclusive, 100% of Premium-listening royalties on Spotify) —
worth joining when open; may become the best-paying route for Spotify itself.
