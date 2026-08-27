"""Tour rebuild, Phase 1: every guide-less scene, on Seedance, with Jessica VO.

The locked narration script (~/.scrpt/house/tour-vo-script.md) drives the
lines. The guide appears on camera only in scenes 2 (gate), 8 shot 2 (stage)
and 13 (white room) — those are Phase 2 (veo, with speech-transcript QC) and
are NOT shot here. Scene 1 (drone) and scene 11 (marketing insert) keep their
approved takes.
"""
import sys, os, json, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path

from engine.database import get_book_by_catalog, update_book
from engine.film.scenes import produce_scene
from engine.film.screenplay import _film, _save_film
from engine.trailer import runway

BASE = Path(__file__).resolve().parent.parent / "output" / "SC-033" / "film"
CREDIT_FLOOR = 2000

G = "The Guide"
STYLE_LOT = ("Photorealistic, lifelike, cinematic 35mm with natural film grain and "
             "shallow depth of field, present-day 2026, a working heritage movie "
             "studio lot in Burbank, soft Californian 2pm light on every exterior "
             "and through every window.")

def vo_shot(k, seconds, framing, action, sound, line=None, extra=None):
    sh = dict(k=k, seconds=seconds, framing=framing, action=action, sound=sound,
              characters=[], vo=True, no_refs=True)
    sh.pop("camera", None)
    if line:
        sh["line"] = dict(speaker=G, text=line)
    if extra:
        sh.update(extra)
    return sh

SCENES = {
 "3": dict(amb="quiet high corner office room tone: a clock, pages turning, the studio lot's murmur far below through glass",
   shots=[vo_shot(1, 12,
     "Interior, slow push-in across the empty publisher's office",
     "The publisher's corner office, nobody in frame, the feeling of just-left: a warm desk lamp over an open notebook, a coffee still steaming, the brass quill-and-book mark on the dark charcoal wall, tall windows with the busy sunlit studio lot far below — golf carts and crew crossing the plaza. The camera pushes in slowly toward the window.",
     "a clock ticking, a page settling",
     line="This is where we hatch out the frameworks and seeds for new stories, that eventually can become books, audiobooks, movie trailers and full films.")]),
 "4": dict(amb="a soft rain of keyboards, pages shuffling, chairs rolling, low murmured talk in a busy writers room",
   shots=[vo_shot(1, 13,
     "Interior, slow dolly down the writers' floor centre aisle",
     "The writers' floor at full work: writers at warm lamplit wooden desks, laptops beside stacked manuscripts, one leaning back reading pages, another typing fast, a third pinning a story card to a big corkboard. Slow dolly down the centre aisle. No face in focus — everyone absorbed, turned or in soft focus.",
     "keyboards pattering, a page turning",
     line="One floor down is our writing department. This is where the writers take the idea and turn it into pages. Every book is written here — start to finish, chapter by chapter.")]),
 "5": dict(amb="quiet modern design studio: pen taps on a display tablet, a large print sliding from a printer, soft studio playback",
   shots=[vo_shot(1, 15,
     "Interior, slow lateral glide through the art department",
     "A bright modern design studio inside the heritage building: designers at a row of Macs with dramatic snowy-mountain book cover designs glowing on the screens, one drawing on a pen display, a wall gridded with painted character portraits, a large cover proof on an easel. Slow lateral camera glide. No face in focus — the team absorbed in the work.",
     "a pen tapping a tablet, a print sliding out",
     line="This is the art department, where every book gets its face. Covers, artwork and the character bible. We decide the look of every person in your story, so they look the same on the page, on the cover, and on screen.")]),
 "6": dict(amb="busy studio lot exterior: golf carts humming past, distant crew chatter, birds in palm trees, light wind",
   shots=[vo_shot(1, 6,
     "Exterior, steadicam walk down the west lane",
     "A steadicam glide down a sunlit studio-lot lane between cream heritage buildings: golf carts passing, crew crossing with a props cart, palms swaying, the white water tower ahead, a small cream building with a glowing red lamp over its door at the lane's end. Nobody addresses the camera.",
     "footsteps on asphalt, a golf cart passing",
     line="Just across the lane now.")]),
 "7": dict(amb="near-silent recording studio room tone, the hush of acoustic panels",
   shots=[vo_shot(1, 11,
     "Interior, slow push toward the booth glass in the audiobook control room",
     "A windowless audiobook control room: an engineer at a large console in warm low light, the red RECORDING lamp burning, snowy-mountain artwork on the screens, and behind the booth glass a silver-haired narrator at a large microphone, headphones on, absorbed in his read. The camera pushes slowly toward the glass. No voice audible yet.",
     "room tone, a console fader click",
     line="Our audiobook studios. In here, the books learn to speak. Narration, mastering — the whole audiobook, recorded under this little red lamp. Listen—"),
    dict(k=2, seconds=9, characters=[], no_refs=True,
     framing="Through the booth glass, close on the narrator at the microphone",
     action="Through the booth glass: a silver-haired narrator in his fifties at a large studio microphone, headphones on, warm lamp light, the red lamp glowing — recording an audiobook, absorbed, speaking into the microphone.",
     sound="his narration clean and close through the studio monitors",
     speech_stage=("The narrator behind the glass, seen through the booth window "
                   "absorbed in his read, speaks slowly into the microphone:"),
     voice_desc="a deep, warm, measured male narrator voice, speaking clear unhurried American English",
     line=dict(speaker="Audiobook Narrator",
               text="The mountain had taken thirty-one bodies in Luc Reyer's lifetime. He had carried down every one of them. He had promised himself he was done counting."))]),
 "8": dict(amb="vast sound stage cavern acoustics: snow machines hissing, a crane motor, a walkie squawk",
   shots=[vo_shot(1, 8,
     "Aerial drone rise off the moving golf cart, sweeping toward Stage 1",
     "The camera lifts off a moving white golf cart mid-plaza and rises: the cart shrinking below on the busy lot, palms and the white water tower sweeping past, heritage stages spreading out in soft 2pm light, gliding toward the huge open elephant doors of Stage 1.",
     "the cart's electric whirr fading, wind lifting with altitude",
     line="Come on — we'll take the cart from here.")]),
 "9": dict(amb="dark editing suite: the film's own mountain wind bleeding from monitors, a scrub-wheel rewind, soft keys",
   shots=[vo_shot(1, 16,
     "Interior, slow push across the editing suite",
     "A dark editing wing lit by glowing screens: an editor at a console scrubbing a snowy-mountain action film on the big monitor, timelines and waveforms on the side displays, a second suite visible beyond. The camera pushes in slowly past racks of gear. The editor absorbed, face away or in shadow.",
     "a scrub-wheel rewind, the film's wind from the monitors",
     line="This is the editing wing — every scene is cut, scored and mixed in here. It's also where we make the trailers, and all the marketing creatives — every ad and promo you'll see out there. And if a scene isn't right, we shoot it again — just that scene.")]),
 "10": dict(amb="working loading dock: hand-truck wheels on concrete, cartons landing, tape guns, a truck liftgate whine",
   shots=[vo_shot(1, 27,
     "Exterior, slow tracking shot along the distribution platform",
     "A working distribution centre in soft 2pm sun: six white platform trucks backed to the loading bays, dock workers rolling hand trucks of boxed books and sealed cartons up the ramps, a forklift crossing, the sawtooth warehouse roofline above. The trucks' trailer sides carry the platform logos: an Amazon truck, an Audible truck, an Apple Books truck, a Spotify truck, an Amazon Prime Video truck and a YouTube truck. Slow tracking shot along the platform, workers' faces incidental.",
     "cartons landing, a liftgate whine, tape guns",
     line="And this is our distribution centre. When all of this is done, we ship it over to the different platforms — the books to Amazon and Apple Books, the audiobooks to Audible and Spotify, and our films to Amazon Prime and YouTube — so that what started as an idea in our publisher's office, is now ready to meet the audience as a finished product. As a book, an audiobook, or as a full film. And that's when our marketing department starts working, adding fuel to the fire.")]),
 "12": dict(amb="the dock noise falling away: distant cartons, wind, a low white hush",
   shots=[vo_shot(1, 10,
     "Exterior, slow drift toward the plain door at the platform's end",
     "The quiet end of the distribution platform: stacked black road cases and crates, the last truck bays behind, and in the warehouse wall a plain grey service door standing slightly ajar — PURE WHITE LIGHT pouring through the gap, casting a long bright wedge across the concrete, unnaturally clean, clearly not daylight. The camera drifts slowly toward the door. Nobody in frame.",
     "wind, the dock quieting, a low white hush through the gap",
     line="Of course — this lot doesn't exist. Not in brick and palm trees, anyway.")]),
}

async def main():
    book = get_book_by_catalog("SC-033")
    film = _film(book)

    # restage: departments are Seedance text-only + VO under the locked script
    for n, sc in SCENES.items():
        cur = film.setdefault("scenes", {}).setdefault(n, {})
        cur["ambience"] = sc["amb"]
        cur["shots"] = sc["shots"]
        for sh in cur["shots"]:
            sh.pop("camera", None)
        cur.pop("produced", None)
        d = BASE / f"scene-{int(n):02d}"
        if d.exists():
            for f in d.glob("*.mp4"):
                f.unlink()

    # Phase 2 scenes: update her lines to the locked script, mark, do not shoot
    g2 = film["scenes"].get("2", {})
    for sh in g2.get("shots") or []:
        if (sh.get("line") or {}).get("text"):
            sh["line"]["text"] = ("Hi! And welcome to SCRPT! Let me take you for a "
                                  "little tour, so you can get to know how it all works "
                                  "and what we do here. So first — let's begin at the "
                                  "publisher's office, where every idea starts.")
    _save_film("SC-033", film)
    print("restaged: departments on Seedance+VO; her scenes held for Phase 2", flush=True)

    world = book["data"].setdefault("bibles", {}).setdefault("world", {})
    if not world.get("style"):
        world["style"] = STYLE_LOT
        update_book(book["id"], book["data"])

    failed = []
    for n in (3, 4, 5, 6, 7, 9, 10, 12):
        bal = await runway.credit_balance()
        if bal < CREDIT_FLOOR:
            print(f"CREDIT FLOOR: {bal} — stopping", flush=True)
            failed.append(n); break
        try:
            rec = await produce_scene("SC-033", n)
            print(f"scene {n}: {json.dumps(rec)}", flush=True)
        except Exception as e:
            print(f"scene {n} FAILED: {e}", flush=True)
            failed.append(n)

    print("PHASE 1 DONE. problems:", failed or "none", flush=True)
    print("credits left:", await runway.credit_balance(), flush=True)

asyncio.run(main())
