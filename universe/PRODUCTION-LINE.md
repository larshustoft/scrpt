# The TigerWorks Animation Production Line

The method, as it now stands (2026-08-31). It is universe-agnostic: any
new series follows these stages in this order. Every stage before the
shoot is cheap and revisable; the shoot is the one irreversible spend.

## The stages

**1 · THE SCRIPT — the film is the script.**
Written to work with the eyes closed: a listener who never sees a
picture follows the whole story. The storyteller is the spine (marks
every move, cause, place-change and feeling); dialogue does character,
jokes and the songs. One voice per beat, never overlapping.
*Gate: Lars reads it as text and approves before anything is drawn.*

**2 · THE BEATS.**
The approved script is parsed into ordered beats (`vo` / `line`), then
grouped into shots — at most two beats and ~26 words per shot, so the
words always lead. A shot's length is `words / 2.2 + 1.6s`, floor 4s.

**3 · THE BOARD — illustration, never rewriting.**
For each shot the model is given the LOCKED words and asked only:
what picture best serves what the audience is hearing right now?
House camera rules apply (first shot the widest view; faces visible;
painted style; no lettering). One frame drawn per shot: the frames are
the STYLE ANCHOR the camera needs — no frame, no shoot.
*Gate: the board is reviewable as pictures + words before any spend.*

**4 · THE SHOOT.**
Each shot goes to the camera with its cast plates (identity) and its
board frame (composition + style), audio OFF — audio-on doubles the
price (75 cr/s vs ~28). Takes are cached by prompt hash, so re-cuts and
re-records are free forever after.
*Gate: quoted in credits and explicitly approved. Shoot in acts, not
all at once, so the first act can be judged before the rest is bought.*

**5 · THE MIX.**
Voices recorded per character voice (cast in the universe profile,
with per-voice performance settings); each panel holds its own speech —
the picture stretches and holds rather than letting words spill into
the next shot. Score in emotional chapters, sound cue per shot, then
the whole episode mastered to −14 LUFS / −1.5 dBTP.

**6 · THE BOOKENDS.**
Attached mechanically from the universe profile: sung intro at the
front; at the end the lullaby scene and the 10-second credits (names,
then the TigerWorks mark, over a locked living scene, one steady dim,
music ending on its own final chord).

## What is made once per universe (never per episode)

Theme song and sung intro · the lullaby (short + full) · the credits
scene and card · character plates and sprite sheets · the world's map
and hero art · the format doc and voice cast. Everything else is the
story of the day.

## Learned the hard way (do not repeat)

- Board-then-write makes the story disappear. Script first, always.
- Segments carry picture only; audio filters on them fail silently.
- A still PNG overlay needs `-loop 1` or it paints one frame.
- Green screen keys cleanly; white backgrounds leave dark halos.
- Fades stack: set one dim before the first frame and leave it.
- Music should end on its own last chord, not be faded out.
- Measure loudness; a lullaby 15 dB under the story disappears.

### The opening beat is never composed

Beat 2 — the music that carries the film out of the intro, under the
storyteller's wide-world introduction — is the universe's own theme
continuation, held in the profile as `creatives.theme_continuation`. The
score builder now leads with that file and lets the first written chapter
pick up underneath it once it has bowed out. It must never generate a cue
for this beat: the whole point of an opening theme is that a child knows
the show before a word is spoken, and a chaptered score quietly replaced
it with a new piece of music (2026-08-31). A new universe therefore needs
its theme continuation recorded before its first film is cut.

### Every universe gets its own folder on the hard drive

The repo is where the studio works; `~/TigerWorks/` is where a person
looks. Each universe has the same nine shelves — `01 Scripts & notes`,
`02 Books`, `03 Logos`, `04 Characters`, `05 Music`, `06 Voices`,
`07 Films`, `08 Website`, `09 For Lars` — in the order the line uses
them, and the other brands keep their marks under `~/TigerWorks/Brands/`.
`python3 tools/house_folders.py` builds the shelves for every registered
universe and writes the path back into its profile as `desktop_mirror`.
Anything waiting on Lars' own hands (a cutout, a signature, a listen)
goes on shelf 09 and nowhere else.

### Read the script aloud before anything is shot

Every manuscript is recorded as a plain read — the real cast, no
pictures, no music — and listened to end to end before a single frame is
drawn. It costs voice characters and no video credits, and it is the only
honest test of the first law. It also measures the film: the read's
running time IS the episode's running time, give or take the breathing.
`scratchpad/read_script.py` is the pattern (parse the manuscript, one
recording per beat in the cast voice, concat with a 0.3s gap, master).

### The board: one anchor per SCENE, not one frame per shot

Drawing a frame for every shot is the slowest step in the line and most
of what it buys is redundant: inside one scene the place, the light and
the palette do not change. So each SCENE gets one drawn anchor, and every
shot in that scene carries its scene's anchor plus the cast plates. The
anchor holds style, place and light; the plates hold the faces; the shot's
own words decide the framing. Thirteen drawings instead of a hundred, and
the continuity that actually matters is the continuity that is kept.

**State the hour and the light in every anchor prompt.** The first pass
for Episode 1 came back with nine of thirteen anchors under a moon — the
universe's style is dreamy, and nothing in the prompt said "morning". Had
that gone to camera, 122 shots would have inherited it and the film would
have contradicted its own script from the first line. Write it out:
"EARLY MORNING, bright warm sunrise light, blue sky" — and say plainly
where dark IS correct (inside the cave, and nowhere else).

### The gate: shoot three shots and stop

Before committing a five-figure shoot, shoot the first three shots and
look at them. It costs about 900 credits and it is the difference between
losing 900 and losing 24,000. Check three things only: is it painterly or
has it drifted photoreal, do the characters match their plates, and is the
light the light the script says it is.

---

# THE LINE (2026-09-01) — how an episode is actually made

Nothing below is optional, and the order is the point. Stages that do not
depend on each other run at the same time; the two stages where a person
looks never move.

```
  script  ──► the acted read              ◄── A PERSON LISTENS
     │
     ├─ board (locked script, never re-adapted)
     │     └─ desk check  ── repeat until zero problems (free)
     │
     ├─ stills  ‖  voices  ‖  score        (three at once)
     │
     └─ animatic ─────────────────────────◄── A PERSON WATCHES
           │
           ├─ shoot: gen4-turbo animates each approved still (~5 cr/s)
           ├─ dailies: a vision pass reads every shot back
           └─ cut · bookends · master · archive · audiobook
                 └─ quality sheet: desk, dailies, length, loudness
```

**Speed comes from parallelism, never from skipping a look.** Voices do
not depend on pictures. The score depends only on the score plan. Drawing
and filming queue on different services and never contend — so across a
season, episode two draws while episode one shoots.

`engine/trailer/episode_line.py` runs one episode. `season_line.py` runs
a season as a line, with one drawing worker and one filming worker, and
an `approve()` that must be a person's decision — a season may never
shoot itself unwatched.

**Lanes** (env-overridable): stills 8, voices 4, shoots 6, vision 6.
Measured before: stills 1.4/min at three lanes — 100 minutes an episode.

**Made once per universe, never per episode:** the theme, the lullaby,
the intro, the ending, the credits, the voice cast and their directions,
the scale plate, the style, and the **location plates** — every place the
series visits, drawn once and used as the base of every still set there.

**The quality sheet is the gate at the end**, and it fails an episode on:
any desk-check problem, loudness outside −15.5…−12.5 LUFS, or a running
time past 13 minutes. Fast is only fast if the thing at the end is right.

### When you animate a still, send the MOTION and nothing else

The picture already holds the characters, their colours, their sizes, the
place and the light. Sending the scene description with it makes the model
choose between the two — and it will blend them. On Episode 1's first
section (2026-09-01) a still of two unicorns went to the camera together
with a paragraph that mentioned a bird, and the shot came back as a blue
bird with a unicorn horn. The same still, same model, same 25 credits,
with a one-sentence motion prompt, came back identical to the still with
the characters walking. The rule: **image-to-video prompts describe
movement only.** Everything else belongs in the still.

---

# THE CONSISTENCY LAWS (2026-09-01)

Learned shot by shot on Episode 1, watching Lars read a 146-shot board.
Every one of these is now enforced in code, not remembered.

**1. One place, one look.** Every shot carries a `place`. The first shot in
a place is its MASTER, and every other shot there is drawn with the
master's picture as a reference: same ground, same plants, same light,
same props, in the same positions. Ten places in Episode 1; 121 of its 146
shots inherit one. Without this, a rope bridge is a different bridge in
every shot of the same crossing.

**2. One prop, one prop.** A thing the story keeps returning to — a fallen
branch, the stone that blocks the water — is a prop with its own master
shot, and every shot showing it inherits that shot too. A shot may inherit
BOTH its place and its prop. Without this, "the stone" in the cave is a
different rock from the one that fell off the cliff.

**3. Nothing appears before the story finds it.** Characters have a
`first_appearance` scene; places and objects have a scene from which they
may be seen. The cave is not visible before they discover it. Checked in
the cast list AND in the prose of every shot description.

**4. Nothing the world does not have.** A universe carries `world_rules` —
no humans in an animal world, nothing blocking an opening unless the story
put it there. Written into every still prompt and checked afterwards by a
vision pass over every picture.

**5. The style must not point at another picture.** "In the style of the
cover" imported the cover's framing habits — dark tree hollows at the
edges — into all 146 shots. A film's style DESCRIBES the look; it never
references an image.

**6. The bible is the source of the plates, and the plates are checked
against it.** A plate that disagrees with the written bible silently
becomes the truth. Verified once per universe, before anything is drawn.

**7. Two checks over every picture, before a credit is spent.**
`verify_stills` — the world's rules. `verify_story` — does this picture
show its own beat, with the right characters, matching the words heard
over it. Both cheap, both automatic, both run until clean.

**8. A long stage owns only its own output.** A drawing run that saves the
whole board at the end throws away every note made while it ran. Stages
re-read the live board and write only their own fields.

---

## What 1 September taught us — the delivery laws

Laws 1–8 are about drawing. These are about what happens *after* the
pictures are right, and every one of them comes from a film that was
delivered looking nothing like the board it was made from.

**9. A take's identity is the picture it was shot from, not that
picture's filename.** Every still we repaired kept its name, so the cache
called it a hit and served footage shot days earlier — some from before
stills existed at all. 80 of 135 shots in a delivered film were not the
approved pictures. A cached take is now keyed on the still's *bytes*, and
is compared to that still before it is reused.

**10. The board is a contract, and the film is measured against it.**
Before a single frame is cut, the first frame of every take is compared
to the still it was approved from. A film that does not match its board
is not cut; the shots are named instead. Nothing about this is inferred
from timestamps or cache bookkeeping — the pixels are compared.

**11. A check that is never called is not a check.** `verify_stills`,
`verify_story` and `verify_plates` all existed, all worked, and none of
them were wired into the line. So did the location-plate and prop-plate
builders: the plates for episode one were drawn by hand, once, which
meant nothing at all would have been established for episode two. Every
check and every builder is a stage in `episode_line`, or it does not
exist.

**12. A gate must be able to stop the line.** A refused picture that
comes back through `asyncio.gather(..., return_exceptions=True)` reads as
success. A vision check that throws must reject, not pass. A stage that
fails must raise where the caller will feel it.

**13. A check that cries wolf gets ignored, and costs money.** Asked
without the cast, the picture checker reported "this shows a unicorn, not
a Princess" for 92 correct shots. Every check is given the context it
needs to judge fairly before it is allowed to reject anything.

**14. The map belongs to the episode.** Places, objects and the shots
that override them are carried on the board, not written into the code.
Episode one's map lived in `world.py` as module constants — episode two
would have been shot in episode one's places.

*Laws 1–14 are the children's-book and animation line. The grown-up
non-fiction book and film processes do not use them.*
