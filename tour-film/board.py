"""THE SCRPT LOT TOUR — shot board, built on the commercial's proven method.

Short takes (4-8s), 1080p. Identity by CANON TEXT repeated verbatim in every
shot (the commercial's mechanism — no image refs). Departments on Seedance
(camera "sd", silent, VO carries the words). The guide's three SPEAKING
moments (gate / stage / white room) on veo3.1 with native lip-synced audio
(camera "veo"), first-frame anchored where a frame exists, split into short
takes so nothing drifts. VO voice: Jessica (the guide/assistant voice),
commercial-tuned. Brian speaks ONLY the end card line.
"""


# ---- REFERENCES: every take anchors on its APPROVED image ----
# Storyboard frames (~/.scrpt/house/tour-sb-*.png) are the shot's FIRST FRAME
# via veo image-to-video — the film matches the board by construction. Location
# plates cover shots the board doesn't. (Lars: "find the storyboard, the
# instructions and references needed".)
from pathlib import Path as _P
_H = _P.home() / ".scrpt" / "house"
_B = _P("/Users/tiger/Desktop/CATALOG ENGINE/bookr/output/SC-033")
FRAMES = {
    "aerial":  _H / "tour-sb-00.png",
    "gate":    _H / "tour-sb-01.png",            # her, at the cart — approved
    "office":  _H / "tour-sb-02.png",
    "writers": _H / "tour-sb-03.png",
    "art":     _H / "tour-sb-04.png",
    "lane":    _H / "tour-sb-05.png",
    "audio":   _H / "tour-sb-06.png",
    "stage":   _H / "tour-sb-07.png",            # her, on the stage — approved
    "stagewide": _H / "loc-stage.png",           # the set without her
    "editing": _H / "tour-sb-08.png",
    "editing2": _H / "loc-editing.png",
    "dock":    _H / "tour-sb-09.png",
    "dock2":   _H / "loc-dock.png",
    "mkt":     _H / "tour-sb-09b.png",
    "dockwalk": _H / "tour-sb-10-withguide-v2.png",  # her walking the platform
    "door":    _H / "tour-sb-10.png",
    "white":   _H / "tour-sb-11.png",
    "white2":  _H / "tour-white-photo.png",            # her, in the void — approved
    "drive":   _B / "film/scene-06/frame-01.png",    # her at the wheel — approved
    "master":  _H / "scrpt-lot-photo.png",
}

CANON_GUIDE = (
    "THE GUIDE: a warm, friendly woman in her early thirties, shoulder-length "
    "softly-waved dark brown hair parted at the side, warm hazel eyes, natural "
    "radiant smile; cream silk long-sleeved shirt with the sleeves rolled once, "
    "a small engraved brass name badge on the chest, dark tailored trousers, "
    "small gold hoop earrings. THE SAME WOMAN in every shot — same face, same "
    "hair, same clothes — always smiling, at ease, genuinely delighted.")

CANON_LOT = (
    "THE LOT — one working heritage movie studio in Burbank, present-day 2026, "
    "identical in every shot: a cream art-deco office tower with a rooftop "
    "SCRPT sign beside an ornate iron gate with a lit marquee arch; a white "
    "steel water tower; two huge curved sound stages; a long sawtooth-roofed "
    "distribution warehouse east; palm trees, white golf carts, busy film crew "
    "everywhere. Soft Californian 2pm sunshine, clear blue sky, short shadows.")

STYLE = (
    "Cinematic commercial photography. BRIGHT, luminous, optimistic: soft "
    "frontal daylight so every face is clearly lit and readable — no "
    "silhouettes, no heavy backlight, no crushed shadows. Warm clean colour "
    "grade, shallow depth of field, 35mm anamorphic, photoreal and lifelike. "
    "Everyone in frame looks genuinely happy and at ease. No text overlays, "
    "no captions, no on-screen writing.")

TEXT_SIGN = ("\n\nTEXT: the ONLY lettering visible anywhere is the rooftop "
             "sign and gate marquee, reading exactly SCRPT. No other words.")
TEXT_BADGE = ("\n\nTEXT: the ONLY lettering visible anywhere is her small "
              "brass name badge, reading exactly SCRPT — spelled S-C-R-P-T. "
              "No other words on screen.")
TEXT_TRUCKS = ("\n\nTEXT: the ONLY lettering visible is the platform logo on "
               "each truck's trailer side — one truck Amazon, one Audible, one "
               "Apple Books, one Spotify, one Prime Video, one YouTube — real "
               "logos, no other words anywhere.")
TEXT_NONE = ""

# g = guide canon in prompt, l = lot canon
# camera: sd (Seedance text, silent) | sdA (Seedance, native audio) | veo (i2v, audio)
# panel groups share one VO line, timed inside the group (commercial rule)
PANELS = [
 # ≤ 2:00 total (Lars). One cart moment. No dock-walk scene. Verbatim where sacred.
 dict(n=1, vo=None, takes=[
   dict(key="01", dur=4, cam="veo", frame="aerial", canon="l", text=TEXT_SIGN,
        shot="High aerial drone over the whole studio lot, slowly descending toward the gate " + "—" + " the deco tower with its rooftop sign, the water tower, the curved stages, trucks at the warehouse, tiny golf carts and crew on the plaza."),
 ]),
 dict(n=2, vo=None, voz="native", takes=[
   dict(key="03", dur=8, cam="veo", frame="gate", canon="gl", text=TEXT_BADGE,
        line="Hi! And welcome to Script! We're so thrilled to have you here " + "—" + " you're about to see our full production line, from one idea to every product we create.",
        shot="Just inside the iron gate by the lit marquee reading MAIN GATE, a white golf cart parked beside her: THE GUIDE stands facing the camera, warm and delighted, welcoming us with easy open gestures. Static camera, calm natural motion only."),
   dict(key="05", dur=8, cam="veo", frame="gate", canon="gl", text=TEXT_BADGE,
        line="So first " + "—" + " let's begin at the publisher's office, where every idea starts.",
        shot="Same framing: THE GUIDE by the cart gestures up toward the deco office tower beside the gate as she speaks to camera, bright and inviting. Static camera."),
 ]),
 dict(n=4, vo="This is the publisher's office. This is where we hatch out the frameworks and seeds for new stories, that eventually can become books, audiobooks, movie trailers and full films.", takes=[
   dict(key="06", dur=6, cam="veo", frame="office", canon="", text=TEXT_NONE,
        shot="A warm corner office high in a heritage tower, empty of people, just-left: slow push across a dark wood desk " + "—" + " brass lamp glowing, an open notebook, a coffee steaming " + "—" + " toward tall windows with the sunlit studio backlot far below. NOBODY in frame."),
   dict(key="07", dur=6, cam="veo", frame="office", canon="l", text=TEXT_NONE,
        shot="From inside the empty office, slow push toward the window: far below, the busy studio lot " + "—" + " golf carts crossing the plaza, the water tower, the curved stages in soft afternoon sun. NOBODY inside the room."),
 ]),
 dict(n=5, vo="One floor down is our writing department " + "—" + " where the writers take the idea and turn it into pages. Every book is written here, chapter by chapter.", takes=[
   dict(key="08", dur=5, cam="veo", frame="writers", canon="", text=TEXT_NONE,
        shot="A grand heritage writers' hall: slow dolly down the centre aisle between warm lamplit wooden desks, writers absorbed at laptops beside stacked manuscripts, one pinning a card to a corkboard. No face in sharp focus."),
   dict(key="09", dur=4, cam="sd", canon="", text=TEXT_NONE,
        shot="Close over a writer's shoulder: hands typing fast on a laptop beside a tall stack of printed manuscript pages, a brass desk lamp warm, dust in the light. Face out of frame."),
 ]),
 dict(n=6, vo="This is the art department, where every book gets its face " + "—" + " covers, artwork and the character bible, so every person in your story looks the same on the page, on the cover, and on screen.", takes=[
   dict(key="10", dur=5, cam="veo", frame="art", canon="", text=TEXT_NONE,
        shot="A bright modern design studio: slow lateral glide along a row of large screens glowing with dramatic snowy-mountain book cover designs, designers working at pen displays, sunlight through tall industrial windows. Faces soft."),
   dict(key="11", dur=5, cam="veo", frame="art", canon="", text=TEXT_NONE,
        shot="Slow push toward a studio wall gridded with painted character portraits of the same few faces from many angles, a large printed cover proof on a wooden easel beside it. Live faces soft."),
 ]),
 dict(n=7, vo=None, takes=[
   dict(key="12", dur=4, cam="veo", frame="drive", canon="gl", text=TEXT_BADGE,
        shot="From the lane's edge: THE GUIDE drives the white golf cart past at an easy pace, eyes on the lane ahead, relaxed small smile, hands on the wheel " + "—" + " palms, crew and the water tower behind her. She does not speak. Simple forward motion, all four wheels on the ground."),
 ]),
 dict(n=8, vo="Our audiobook studios " + "—" + " where the books learn to speak. Listen" + "—", takes=[
   dict(key="14", dur=6, cam="veo", frame="audio", canon="", text=TEXT_NONE,
        shot="A windowless audiobook control room in warm low light: an engineer at a large console, a glowing red RECORDING lamp over the double-glass booth door, and behind the glass a silver-haired narrator at a big microphone, headphones on. Interior only, no daylight."),
 ]),
 dict(n=9, vo=None, takes=[
   dict(key="15", dur=8, cam="sd", canon="", text=TEXT_NONE,
        line="The mountain had taken thirty-one bodies in Luc Reyer's lifetime. He had carried down every one of them.",
        speech=("The narrator, a silver-haired man in his fifties in a padded vocal "
                "booth, absorbed in his read, speaks slowly and warmly into the microphone"),
        voice="a deep, warm, measured male narrator voice, clear unhurried American English",
        shot="Inside the padded vocal booth, close on the silver-haired narrator at the studio microphone with a pop filter, headphones on, warm reading lamp, dark acoustic foam behind him " + "—" + " NO windows, NO glass reflections, no daylight. He is absorbed, reading aloud."),
 ]),
 dict(n=11, vo=None, takes=[
   dict(key="17", dur=4, cam="veo", frame="stagewide", canon="", text=TEXT_NONE,
        shot="Inside a vast sound stage, mid-take on a mountain-rescue action film: a stunt performer in a red-and-black rescue jacket on ropes over a crevasse set of carved ice, snow machines blowing, a huge LED mountain wall storm-lit, film crew working. Faces incidental."),
 ]),
 dict(n=12, vo=None, voz="native", takes=[
   dict(key="18", dur=8, cam="veo", frame="stage", canon="gl", text=TEXT_BADGE,
        line="And this is the part I love " + "—" + " the film studios. The stories become films here, right on this stage.",
        shot="Just inside the sound stage: THE GUIDE faces the camera, delighted, the snowy crevasse set and working film crew behind her. Static camera, calm gestures."),
 ]),
 dict(n=13, vo="This is the editing wing " + "—" + " every scene is cut, scored and mixed in here. It's also where we make the trailers, and all the marketing creatives.", takes=[
   dict(key="20", dur=5, cam="veo", frame="editing", canon="", text=TEXT_NONE,
        shot="A sealed editing suite lit only by its screens: an editor seen from behind at a glowing console, scrubbing a snowy mountain film on a large cinema monitor, timelines and waveforms on side displays. No windows, no daylight, his face away from camera."),
   dict(key="21", dur=4, cam="sd", canon="", text=TEXT_NONE,
        shot="Close on the big edit monitor: a dramatic snowy mountain sequence scrubbing back and forth, a timeline of clips beneath, an editor's hand on a jog wheel in the foreground glow. No readable text on the screens."),
 ]),
 dict(n=14, vo="And this is our distribution centre. From here we ship everything to the platforms " + "—" + " the books to Amazon and Apple Books, the audiobooks to Audible and Spotify, and our films to Amazon Prime and YouTube " + "—" + " ready to meet the audience as a finished product.", takes=[
   dict(key="23", dur=6, cam="veo", frame="dock", canon="l", text=TEXT_TRUCKS,
        shot="Bright midday at the distribution centre: slow tracking shot along the loading platform, six white platform trucks backed to the bays, dock workers rolling hand trucks of boxed books up the ramps. EVERY worker a clearly different person " + "—" + " different ages, builds, skin tones, hair and clothing colours, nobody repeated."),
   dict(key="26", dur=6, cam="veo", frame="dock2", canon="", text=TEXT_TRUCKS,
        shot="The last bays: the Spotify, Prime Video and YouTube trucks in a row, doors open, workers loading, a hand truck rolling past in the foreground, bright midday sun. EVERY worker a clearly different person, nobody repeated."),
 ]),
 dict(n=15, vo="And that's when our marketing department starts working, adding fuel to the fire.", takes=[
   dict(key="27", dur=5, cam="veo", frame="mkt", canon="", text=TEXT_NONE,
        shot="A bright busy marketing floor: a display wall running a snowy-mountain book campaign " + "—" + " cover art as ads in several sizes, a trailer playing, performance curves climbing " + "—" + " a dozen different marketers at work. Faces incidental."),
 ]),
 dict(n=17, vo=None, voz="native", takes=[
   dict(key="30", dur=26, cam="sd", canon="g", text=TEXT_BADGE,
        line="Everything you've just seen is an imagined world " + "—" + " but it shows you something real: what Script can do for you as a creative. The writers, the artists, the studios, the trucks " + "—" + " that's our software, doing every one of those jobs for your stories. Books, audiobooks, films " + "—" + " written, produced, published and promoted. And the whole studio is yours the moment you sign in.",
        shot="ONE SINGLE CONTINUOUS TAKE, static camera, no cuts: a real photography-studio white cyclorama " + "—" + " seamless soft white in every direction, a small dark doorway far behind her. THE GUIDE walks toward the camera from the doorway ONCE, arriving at full height in frame near the camera early in the take " + "—" + " and then STANDS STILL, feet planted, speaking the rest warmly and personally straight to camera with only natural small gestures. When she has finished she gives one last warm smile, then turns and WALKS OUT OF FRAME TO THE RIGHT, leaving the empty white void. Real skin texture, soft even light."),
 ]),
]

END_VO = "Script — One Idea. Every Format."
END_DUR = 7.0

def takes():
    out = []
    for p in PANELS:
        for t in p["takes"]:
            t2 = dict(t)
            t2["panel"] = p["n"]
            out.append(t2)
    return out
