# Princess the Unicorn — Episode Format

The strict format every episode follows (Lars, 2026-08-30). This document
is LAW for the storyboard, the storytelling and the dialogue: the board
builder injects the FORMAT RULES section into its prompts verbatim, and
the fixed bookends are attached mechanically by the pipeline. The goal is
a system that makes 100 episodes simple: everything episodic is template,
so only the story of the day is new work.

## The fixed skeleton

| # | Segment | Length | Source |
|---|---------|--------|--------|
| 1 | Show intro — sung theme, logo hop + blink | ~20s | `show-intro-v8.mp4`, never re-made per episode |
| 2 | Valley opening — widest view of Rainbow Forest, camera drifts in; theme continuation enters INSIDE the intro's white fade (no dead air) | ~10s | shot per episode from the valley rule |
| 3 | Storyteller opening — "Every morning in Rainbow Forest…" register, then the tease of today's story, BEFORE any dialogue | ~15s | written per episode |
| 4 | The story — the adventure of the day | ~5–6min | per episode |
| 5 | Bedtime ending — Glitter tucks Princess in and sings The Unicorn Lullaby (short); Princess falls asleep on the last note | ~26s | a small rotating set of lullaby animations (to be made — a few variants, reused across episodes) |
| 6 | End card — TigerWorks, thin Futura, white on black | 2s | `endcard-tigerworks.mp4` |

Music slots: sung theme (intro) → instrumental theme continuation (opening,
bows out as first dialogue lands) → mood score as the story needs →
The Unicorn Lullaby (ending). The lullaby is ALWAYS the ending.

## FORMAT RULES (injected into the board builder's prompts)

RULES OF THE SERIES — every episode of Princess the Unicorn obeys these:

S1. THE SHAPE OF A DAY: every episode is one day in Rainbow Forest —
    it begins in the morning ("Every morning in Rainbow Forest…" is the
    storyteller's home key) and ends at bedtime. The final scene is always
    Princess being tucked into her moss bed — write toward bedtime.
S2. THE STORYTELLER opens the episode: first the world (morning, warm,
    safe), then the tease of today's adventure, concrete and story-true
    ("Today, Princess would… and learn…"). No dialogue before her beat.
    She may return for at most one short bridge mid-story and one warm
    line at the close; otherwise the characters carry everything.
S3. ONE ADVENTURE, ONE LESSON: each episode has exactly one small
    adventure and one gentle lesson a 3–6-year-old can say out loud
    (listen for the bell; ask for help; try again). The lesson is LIVED,
    then named once — by a character or the storyteller — near the end.
S4. THE ARC: ordinary morning → the wonder or the wobble (something
    magical to explore, or a small thing goes wrong) → three tries or
    three steps (kids count in threes) → it comes right through the
    lesson → home, calmer than we left → bedtime.
S5. STAKES stay small and warm: nothing scary, nothing cruel, no
    villains — only mishaps, weather, distances and misunderstandings.
    Peril is "a wobbly bridge", never danger of harm.
S6. DIALOGUE for small ears: short lines (a breath each), concrete words,
    feelings said plainly ("I miss Mama"). Characters use each other's
    names warmly and often. Questions invite the viewer ("Can YOU hear
    it?" register) at most once per episode.
S7. THE MOTIFS repeat in every episode: Glitter's silver bell (safety and
    home — "Stay near my bell, little one"), Princess's "Ring, ring,
    ring!" delight, the sparkle that marks magic. Use at least one motif
    at the start and one at the resolution; motifs are how children feel
    at home.
S8. THE CAST is the cast: Princess, Glitter, Pip, Moss, the Fireflies.
    A new friend may visit for one episode, but the family solves the
    day. Never a new main character.
S9. EVERY SHOT obeys the house camera rules: the film's first story shot
    is the widest view of the valley drifting in (no character close in
    shot 1); faces visible, front or three-quarter; storybook painted
    style, never photoreal.
S10. BEDTIME IS SACRED: the last story beat settles everything. No
    cliffhangers, no open questions — the day is complete, Princess is
    safe, the forest holds her near.

## Production notes (for the pipeline, not the prompts)

- Storyteller voice: universe profile `voice_cast.Storyteller` (Sarah).
- Character voices: universe profile `voice_cast`, book-level overrides win.
- Faces: cast plates + drawn board frame travel with EVERY shot. No frame,
  no shoot.
- Bookends are attached by `movie_produce` from the universe profile
  (`show_intro`, `show_outro`); the lullaby ending variants live in the
  profile once made (`lullaby_endings`, rotate per episode).
- Sixty-ish shots is wrong for 8 minutes of this register: ~10 scenes /
  ~36 shots at 4–8s is the proven shape (SC-039).
- Episode premises beyond the books: the Movie tab premise field; the
  format holds whether the story comes from a book or a premise.
