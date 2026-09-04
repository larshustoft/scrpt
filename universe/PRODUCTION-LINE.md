# THE WORK PROCESS — starting point from 2026-09-04

Saved on Lars's instruction after the first Seedance short (*Princess and the
Lost Bell*, SC-042): "much better; not yet publishable; stick to Seedance for
all clips; save this work process and make it our starting point." Every film
begins here. The laws below are the detail; this is the order of work.

1. **Foundation first** (`engine/trailer/foundation.py`). The universe owns,
   approved once in FOUNDATION.html: canonical character plates, a pose sheet
   per character (angles, expressions, movements, identity-verified), the
   atlas of wide places drawn in one palette, and for every story an object
   set with ONE picture per state. Nothing is drawn from text alone.
2. **The manuscript** in the house format (STORYTELLER / character lines with
   direction, `[place: …]` per scene, header naming the object set and
   places). Wrapped paragraphs are read whole; every word ships.
3. **Born through the line**: `python3 -m engine.trailer.new_film <universe>
   <manuscript.md>` creates the book inside the universe — member, voices,
   bibles, style, object set, places — and builds the board.
4. **The board**: one shot per beat, no shot over 5 s of picture (longer
   beats become two shots, the second one closer), framing/motion/cast/place/
   object state on every shot, desk check clean, world map applied.
   Storyboard published for Lars's approval before any take is bought.
5. **Pictures**: drawn from the foundation references (pose first, then plate,
   object states, place plate), checked by the world rules, redrawn only
   where refused; scenery inherited from an approved master. First-pass yield
   is logged.
6. **The camera**: every shot, wide or close, is a Seedance 2.5 take with the
   cast plates, the closest pose, the object states and the storyboard frame
   attached; 5 seconds, judged by identity against the plates; refused twice
   → third try; refused three times → the run stops and names the shot. No
   drifts, no held pictures, no other camera. Takes are banked and reused by
   an exact camera-aware map; a take is judged once.
7. **The cut**: the join is measured against its parts, no freeze-frames,
   sound cues that turn into voices are thrown away, the score follows the
   universe's music direction, the universe's intro and outro are attached
   untouched, −14 LUFS; narration and lines in the universe's voices.
8. **Scans before delivery**: clip lengths, frozen tails, a cast-aware
   stranger check on every shot, and a frame sheet looked at by eye.
9. **Delivery** to `~/Movies/<universe>/…` (never iCloud), with a written
   report: what was spent against the cap, what the checks found, what to
   look at.

**Money**: every run is quoted with the camera's real price (150 cr per
Seedance take) and stops itself at the cap; nothing is spent past what Lars
was told; a creative downgrade to save money is asked, never defaulted.

**Known next lever**: story logic between clips (Lars will send notes) — a
desk check for staging and consequence before pictures are drawn.

---

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

## Laws 15–22 — learned finishing Episode 1 (2 September 2026)

*Children's books and animation films only.*

15. **First-pass yield is the economics.** Every rejected picture is a redraw and ten minutes. The line logs `first_pass_yield` on the first check of every episode; compare episodes by that number, not by feel. (Episode 1: 32% before the fixes, 78% after.)
16. **A universe remembers its mistakes.** Every rejection is recorded in `universe/<slug>/lessons.json`. A kind of mistake seen three times becomes a standing rule in every future drawing prompt for that universe. The second film starts where the first one finished.
17. **Only a wide shot gets the wide reference.** Close, detail and medium shots draw from identity alone — faces and props. A location plate handed to a close-up comes back as a landscape.
18. **Faces first in the reference list.** Identity is the one thing that may never drift; whoever is in the shot leads the list and is never the one dropped.
19. **A shot line describes a picture; it gives no orders.** "No loose boulders" belongs in the world rules or the place brief, once. Pasted into a line it confuses the drawer and the checker. The repair stage strips them and reports it.
20. **Exemptions match plurals.** A rule that cannot be satisfied — "stones" never matching "stone" — spends money in a loop and never converges.
21. **A prop reference is the object, not an instruction to add one.** The plate shows the thing on a plain background; told nothing else, the model places a second copy on the ground.
22. **An empty account halts everything, and "could not be checked" is never "rejected."** Money is never spent to work around a failure spending cannot fix. A dead checker stops the line; it does not start a redraw loop.
23. **A tight shot keeps tight continuity.** Withholding *every* reference from close shots cured the landscapes and broke the objects — the one round stone became a different stone in a different hole between two consecutive close-ups. Only a *wide* predecessor is withheld from a tight shot; a close still cannot pull the camera wide and is the best reference there is for the same thing seen again. (Lars, 2 Sep 2026: "this doesn't look like the same stone")
24. **The Character Bible's pictures ARE the plates.** The four portraits Lars approved are stored in the universe (`plates/`) with their content hash in the profile; every episode copies them in and verifies them byte for byte before drawing. No stage may draw a "fresh reference sheet." On 1 September the approved portraits were replaced by newly drawn cartoon plates an hour after sign-off, and a whole film was drawn from characters nobody had approved. Changing a character is a decision made in the bible and the plate files together, on purpose. (Lars, 2 Sep 2026: "it looks to me like you haven't used the character bible we created")
25. **The bible text follows the approved picture, not the other way round.** When text and approved picture disagree, the picture Lars signed off is canon and the words are corrected — never the plate redrawn to fit a sentence.
26. **The quote is the cap.** Every episode logs, before it spends, the most pictures it may draw and the most credits it may spend. The drawing stage counts every call and refuses the one past the cap; the shoot reads its balance every ten takes and launches nothing past its cap. Hitting a cap ends the run with the numbers. Raising a cap is a decision a person makes, on purpose. (Lars, 2 Sep 2026: "this film is ending up at an exceptional high cost")
27. **One source for a character.** The Character Bible document is generated from the canonical plates (`python3 -m engine.trailer.character_bible`), never made separately. What is signed off and what is drawn from are the same bytes.
28. **A new universe writes its world rules before its first picture.** If a universe has none, they are drafted from its bible and saved to the profile for review — never left empty, never invented shot by shot.
29. **Stills are drawn at medium quality.** Measured on 2 Sep 2026 (a close, a wide, a detail, side by side): at the film's 1280×720 frame, medium is indistinguishable from high, at roughly half the price and 2.5× the speed. Quality is a setting (`SCRPT_STILL_QUALITY`), and a change to it is a measured decision, not a default.
30. **A worn prop is on its wearer's plate.** A prop marked `worn_by` is never handed over as its own reference when the wearer is in the shot — doing so put a second bell on the ground six times. (Lars, 2 Sep 2026)
31. **A built structure is a prop.** A bridge, a gate, a well: anything the world builds once is a prop with its own plate, in every shot that shows it, regardless of framing — so a medium shot cannot re-invent it as a stone arch.
32. **A smile is not speech.** The mouths-closed rule exists because lip-sync was removed and a mouth mid-word flaps in video. A character whose approved plate smiles open-mouthed is not talking, and the checker asks about talking, not smiling.
33. **The map belongs to the episode, on the board.** `board["world"]` holds the scene→place map, per-shot places, the prop vocabulary and per-shot props. `apply_world` rebuilds from it before every drawing — never from another episode's constants — and props are a union, never a replacement. On 2 Sep 2026 a hard-coded scene 11 = "inside-the-cave" silently undid every fix to the board each time a picture was drawn; the line now refuses a board that has no world map of its own.
34. **Rules are said positively.** A drawing model draws what it is told about: "no caves" put caves in a dozen shots, and "the round white stone exists once" put the stone on the forest path, at the bridge and in the closing pages. World rules and earned lessons describe what IS there — "the cliff face is solid rock", "the ground is grass and small flat pebbles" — and the plot's objects attach to shots only through the board's per-shot map, never through a stray word or a stale list. (Lars, 2 Sep 2026: "why is that rock appearing all over the place")
35. **A size line travels only with its object, and the whole prompt reaches the model.** "The white stone in the cave is about as tall as Princess" rode in all 146 prompts as part of the size chart, and drew a stone and a cave into shots that had neither. Object sizes are stated only in shots that carry the object. And prompts that ran to 5,000 characters were being cut at 3,800, so the closing camera line and the earned rules never arrived — the cap is 6,000 now and the desk check should flag any prompt that would exceed it.
36. **A plate is looked at before it is used.** Two new prop entries were registered by copying the stone's template, inherited its `look`, and were drawn as stones — then handed to every bridge and spring-opening shot as the reference for a bridge and a hole. A plate that has never been looked at is not a reference; it is a rumour. The world stage shows its plates on a sheet, and a person looks at that sheet once per universe.
37. **The Show Bible is the source, and it is one thing.** Characters, objects, places and the world's rules live in the universe as canonical plates with content hashes (`world.plates`, `world.props_plates`, `creatives.locations`) plus their words. Every episode copies them in and verifies them before drawing; a newly drawn object is saved back to the universe once and never redrawn. The Show Bible document (`python3 -m engine.trailer.show_bible`) is generated from those same files, and every run records the bible manifest it was drawn from. The bell is a universe object: Glitter's on lilac, Princess's the same bell a little smaller on sky blue. (Lars, 2 Sep 2026)
38. **A take is judged on its whole length.** Every take opens on its approved picture because the model is forced to; what it does in seconds two to five is where a human girl, a yellow bear or a cartoon pony arrives. A take is read at five points: frame 0 must be the still, later frames must keep its structure, and the middle and the end are shown to a reader beside the still — same characters, nobody new, nobody human, no mouth mid-word. A take that barely moves is a photograph on screen and is rejected too. (Lars, 2 Sep 2026: "I'm starting to wonder if you actually have a functioning filtering process")
39. **Names summon strangers.** A motion line never carries a character's name. "Princess turns her head" drew a human princess; "Pip pulls the vine" summoned a bear to pull it. The line is sent with every name replaced by what the picture shows: the small unicorn foal, the tall mother unicorn, the little teal dragon, the small blue bird.
40. **The cap reserves before it launches.** A balance read lags the API by minutes; a cap judged on it let a 1,200-credit pass spend 3,150. Every take now reserves its cost before launch and a launch that would pass the cap is refused — no read, nothing in flight can slip past. (2 Sep 2026)
41. **A shot with a picture is never filmed from a sentence.** A failed still upload retries three times, then the shot holds on its picture with a slow push-in. The silent text-to-video fallback is gone; four such takes reached a cut before the board gate refused them.
42. **Three refused takes → hold on the picture.** The third try asks only for breath and light; if that is refused too, the shot holds on its approved still and is reported by name. A quiet true picture beats a lively wrong one; the film is never stopped by a shot the model cannot hold and never shipped with one it invented.
43. **One reference per object.** A built thing that already exists in a location plate — the bridge — gets its object plate CUT from that plate, never drawn from a sentence. Two references for one object gave the film two bridges. (Lars, 2 Sep 2026: "a few different bridges in this scene")
44. **A take is as long as its words.** A shot whose line needs more than 5.5 seconds gets a 10-second take; the whole-length judge guards it. A 5-second take stretched and frozen to cover the words is a still on screen. The fireflies are a small cloud of tiny soft lights, never a blaze; the branch is a branch a foal can lift, never a log.
45. **Sound cues are concrete.** Water over stones, hoofsteps, leaves, a bell. Never wind, whisper, murmur, hum, sigh, echo or "distant" — the sound generator turns those into a voice under the picture. (Lars, 2 Sep 2026: "a strange voice in the background at 7:45")
47. **Every character speaks in their own voice, on every path.** A line whose speaker has a cast voice carries it; a speaker with no voice stops the line. All 78 lines of episode one were recorded by the narrator because one entry path skipped the cast. (Lars, 2 Sep 2026: "why are we not using the voices for dialogue any more")
48. **A plate satisfies both the approved look and the words.** Glitter's approved portrait had a realistic muzzle; the bible text said "stylised-cute, not realistic-equine" — the text was right and the picture read as a horse in every tender scene. When picture and words disagree, candidates are drawn and a person chooses; the winner becomes the plate on purpose. (Lars, 2 Sep 2026: "Glitter looked better before — what changed?")

49. **No freeze-frames, ever.** When a take is shorter than its words, the cut stretches it (≤1.5×) and then bounces the tail (backwards, forwards) until the line ends. `tpad=clone` is banned from the episode cut (gate 25). v6 had 26 shots ending on a frozen frame; nobody noticed until Lars did.
50. **Strangers are counted, not argued.** The take judge counts unicorns/dragons/birds in the still and in the later frame; more in the frame than in the still = a stranger, the take is refused (gate 26). Yes/no questions let a pink pony and a lion cub through.
51. **A prop lives only in its own shots.** The world map lists the shots a prop belongs to; every other still is checked for it (a stray branch/log fails the picture unless the shot names one — gate 27). After the branch is lifted away there are no more branches; no later shot may continue from a branch shot.
52. **Sound cues are whole phrases of real sounds.** Never a dangling fragment ("fading into dusty", "her echoing softly") — the SFX generator turns those into voices. A cue is checked for dangling words before it is rendered.
53. **After a delivery, the film is scanned, not watched.** Frozen tails (freezedetect), strangers (count at three points), stray props (still check) — the three scans that found today's faults run on every cut before it is called finished.

54. **The filter chain is one visible string** (`engine/trailer/filters.py`, `CHAIN`, gate 29). Desk → picture → pre-flight → take → cut → delivery. Nobody filters a film by hand: a picture that failed its check is never filmed (`still_cleared`), the motion line is linted (names → species, arrivals/reveals dropped, two sentences), a risky action is asked for gently on the FIRST paid take (`gentle_first`), a 5-second take carries up to 8 seconds of words (`take_length`), every take is judged along its length and by character count, the cut scans itself for frozen tails, and a sound effect that transcribes to words is thrown away (`sfx_words`). The run record reports what each filter stopped.
55. **Scenery is inherited from the master.** A shot that continues an approved picture may show what that picture shows (a rock cutting, a cave mouth). The checker asks the master the same scenery question before refusing the continuation, and reports the waiver by name (gate 30). Shot 28 was refused four times for a boulder that shot 17 has.
56. **The workspace lives on local disk, never on iCloud Desktop.** With the disk 93% full, iCloud evicted takes, music, the engine's own source and its git objects mid-run; ffmpeg died with "Operation timed out" after 1,025 credits were spent. Working copy: `~/TigerWorks/SCRPT`. Every ffmpeg input is checked for the placeholder flag and pulled back, or the run stops naming the file (gate 31).
57. **The join is the sum of its parts.** Stretched/bounced segments are encoded on the same clock (24 fps, timescale 12288) as every other segment, and the joined picture is measured against the segment total; a join that lost time stops the run (gate 32). v7 shipped 47 seconds short before this existed.
58. **A take that dies early is trimmed, not held.** The frozen tail of a take is cut off and the live part stretched/bounced to the words (gate 33). Fireflies are points of light, never bugs with faces: the picture checker refuses insect-characters not on the cast list.
59. **An episode carries every shot on its board.** The trailer's house-minute trim never applies to a film, and the join refuses a film that lacks any pictured panel, naming them (gate 37). Episode 1 shipped four times without Pip's directions and Moss's entrance — eleven middle panels dropped by a trailer rule that reported only to a progress bar. A rule that only talks to a progress bar is not a rule.
60. **Money rules learned the hard way today.** A take is keyed by what the camera saw (never the drawing prompt), a take is judged once and remembered, an exact shot→take map is honoured before any guess, an approved place plate is never torn up on one doubt, and the cap is set to 1 credit for any re-cut that should buy nothing. Every one of these stopped a run before it spent.
61. **No clip longer than five seconds** (Lars, 2026-09-03). No video generation longer than 5s, ever; a line that needs more picture is two shots on the board. Gate 38 refuses the launch.
62. **No lip sync** until a model can do it well. Every take is asked for with mouths closed; dialogue is carried by the voice track over acting, not by mouths. Gate 38.
63. **The foundation comes before the first shot** (Lars, 2026-09-03: "build a system that is built on a stronger foundation"). A universe owns, approved once and reused forever: pose sheets for every character (angles, expressions, movements, each verified against the canonical plate), an atlas of wide places drawn in one palette, and for every story an object set with ONE picture per STATE. Shots reference the pose closest to their action, the place plate, and the object state they show — `engine/trailer/foundation.py`, FOUNDATION.html for approval, gate 39.
64. **Two paid takes, then the picture.** The video model invents in about a third of takes (extra unicorns, a dragon, a human — all caught by the judge on the short, 17 of 46). Try one is the action, try two is camera-only, and a shot refused twice holds on its approved picture with a slow drift: on-model, free. A third paid take is a coin toss with someone else's money (gate 40).
65. **A film is born through the line** (Lars, 2026-09-03: "everything we do here should run through SCRPT — that is where we save the voices and other creative choices"). `python3 -m engine.trailer.new_film <universe> <manuscript.md>` creates the book inside the universe (member, voices, bibles, style), parses the manuscript whole (wrapped lines joined — the short lost the end of every sentence to a line-by-line side script), declares the object set and places from the header, and builds the board. The universe's voice cast is the cast of every book in it (gate 42). Side scripts never create a film.
66. **The camera is the intro's camera** (Lars, 2026-09-03). EVERY shot, wide or close, is a Seedance 2.5 take with the cast plates, the closest pose, the object states and the storyboard frame attached, judged by identity against those plates. No drifts, no held pictures, no cheating (Lars): a shot refused three times stops the run and is named for his decision. gen4_turbo is retired for episodes. Gate 43–44. Price: 150 credits per 5-second take.
