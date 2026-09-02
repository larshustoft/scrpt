# STARTING A UNIVERSE — the one-time gate

Everything here is done ONCE per universe. Nothing may be drawn for an
episode until all of it passes. This exists because Episode 1 of Princess
the Unicorn was drawn for weeks from a character plate that contradicted
its own written bible, and every still in the film inherited it.

    1. THE WRITTEN BIBLE      characters, places, palette, standing laws
    2. THE CHARACTER PLATES   one per character, drawn FROM the bible text
    3. ► VERIFY THE PLATES ◄  a vision model reads each plate back against
                              its written specification and lists every
                              contradiction. THE GATE: nothing else is
                              drawn until this passes.
                              `engine/trailer/verify.py`
    4. THE SCALE PLATE        the whole cast together, true relative sizes
    5. THE LOCATION PLATES    every place the series visits, drawn once
    6. THE VOICE CAST         a voice and a standing direction per character
    7. THE FURNITURE          theme, opening continuation, lullaby, intro,
                              ending, credits — the locked elements
    8. THE FORMAT             episode structure, season map, story chain

A universe that has passed this gate produces episodes; a universe that
has not produces expensive mistakes.

---

# WHAT IS CHECKED ON EVERY EPISODE, FOREVER

Every fault we have found is now a check that runs by itself. None of
these depend on anyone remembering them.

**At the desk, before a credit is spent** (`continuity.check_board`)
- two shots in a row that read the same, or share a framing
- an event shown twice
- a character on screen, or NAMED IN THE PROSE, before the story meets them
- a thing the story says is absent (water in a dry creek) named in a shot
- a mouth moving, in a film with no lip sync
- the storybook look outside the closing summary
- a human being in a world that has none

**In the pictures**
- every still drawn with the scale plate and the cast plates in front of it
- the location plate for the place, reused across the season
- the continuity state written into every prompt, positively and negatively

**At the camera**
- the prompt carries the MOTION only — never the scene description
- everyone stays in frame; every mouth stays closed
- a take is identified by everything the camera receives, so a fix always
  produces a new take instead of a silent cache hit
- a shot that will not pass moderation degrades to its own frame instead
  of killing the shoot

**After the shoot** (`dailies.review_shots`)
- a vision pass reads every filmed shot back against its own description
  and the state of the world
- consecutive shots compared for repetition

**At the end** (`episode_line.quality_sheet`)
- desk check clean, loudness −15.5…−12.5 LUFS, running time under 13 min
- the sales end card can never appear on a film: it is decided by what is
  being made, not by a label
