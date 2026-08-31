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
