"""Overnight build: the complete SCRPT Lot Tour film, beats 0-11.

Waits for any running scene job, stages scenes 4-13 from the shooting draft,
shoots every missing scene (one at a time, true-face frames leading), then
assembles the full film with the three-costume score plan, the marketing
insert overlaid on the dock line's tail, the white room, and the end card
with Brian's close. Output: ~/Desktop/SCRPT-TOUR-FULL-v1.mp4
"""
import sys, os, time, json, asyncio, subprocess, shutil, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
import imageio_ffmpeg

from engine.database import get_book_by_catalog, update_book
from engine.film.scenes import produce_scene
from engine.film.screenplay import _film, _save_film
from engine.trailer import runway
from engine.trailer.producer import _record_line

FF = imageio_ffmpeg.get_ffmpeg_exe()
BASE = Path(__file__).resolve().parent.parent / "output" / "SC-033" / "film"
HOUSE = Path.home() / ".scrpt" / "house"
DESK = Path.home() / "Desktop" / "SCRPT-TOUR-FULL-v1.mp4"
BRIAN = "nPczCjzI2devNBz1zQrb"
CREDIT_FLOOR = 2000

def run(args, what):
    r = subprocess.run([FF, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{what}: {r.stderr[-600:]}")

def secs(p):
    r = subprocess.run([FF, "-i", str(p)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))

GUIDE = ["The Guide"]
NARR_STAGE = ("The narrator behind the glass, a man in his fifties seen through "
              "the booth window absorbed in his read, speaks into the microphone:")
NARR_VOICE = "a deep, warm, measured male narrator voice"

SCENES = {
 "4": dict(amb="a soft rain of keyboards, pages shuffling, chairs rolling, low murmured talk in a busy writers room",
   shots=[dict(k=1, seconds=13, characters=GUIDE,
     framing="Interior single continuous take, she walks the centre aisle toward camera, no cuts",
     action="On the lamplit writers' floor, The Guide walks the centre aisle toward the camera between occupied desks — laptops beside stacked manuscripts, writers working (faces incidental) — face to camera the whole take, warm and smiling.",
     sound="keyboards pattering, a page turning",
     line=dict(speaker="The Guide", text="One floor down is our writing department. This is where the writers take the plan and turn it into pages. Every book is written here — start to finish, chapter by chapter."))]),
 "5": dict(amb="quiet modern design studio: pen taps on a display tablet, a large print sliding from a printer, soft studio playback",
   shots=[dict(k=1, seconds=15, characters=GUIDE,
     framing="Interior single continuous take, she faces camera among the designers' desks, no cuts",
     action="In the bright modern art department — white walls, light oak desks, Fracture Point cover designs glowing on a row of Macs, a wall gridded with character portraits, a proof on an easel — The Guide stands facing the camera, gesturing easily toward the cover wall, designers at work around her (faces incidental).",
     sound="a pen tapping a tablet, a print sliding out",
     line=dict(speaker="The Guide", text="This is the art department — where every book gets its face. Covers, artwork — and the character bible: every person in every story, so they look the same on the page, on the cover, and on screen."))]),
 "6": dict(amb="busy studio lot exterior: footsteps, golf carts humming past, crew chatter, birds in palm trees, light wind",
   shots=[dict(k=1, seconds=8, characters=GUIDE,
     framing="Exterior single continuous walking take, she walks toward camera down the west lane",
     action="The Guide walks toward the camera down the sunlit west lane — the plaza opening behind her, the water tower ahead, golf carts passing, crew crossing (faces incidental) — talking to us as she walks, face to camera.",
     sound="footsteps on asphalt, a golf cart passing",
     line=dict(speaker="The Guide", text="This way — just across the lane."))]),
 "7": dict(amb="near-silent recording studio room tone, a console fader click, the hush of acoustic panels",
   shots=[dict(k=1, seconds=12, characters=GUIDE,
     framing="Interior single continuous take in the control room, she faces camera, no cuts",
     action="In the windowless audiobook control room — console glow, the red recording lamp burning, the narrator behind glass, the engineer at the desk (faces incidental) — The Guide faces the camera, warm and hushed, and at the end of her line lifts one finger: listen.",
     sound="room tone, a fader click",
     line=dict(speaker="The Guide", text="Welcome to our audiobook studios. In here, the books learn to speak. Narration, mastering — the whole audiobook, recorded under this little red lamp.")),
    dict(k=2, seconds=9, characters=[],
     framing="Through the booth glass, close on the narrator at the microphone",
     action="Through the booth glass: the audiobook narrator at the microphone, headphones on, absorbed in the read, the red lamp glowing — recording Fracture Point.",
     sound="the narration clean and close through studio monitors",
     speech_stage=NARR_STAGE, voice_desc=NARR_VOICE,
     line=dict(speaker="Audiobook Narrator", text="The mountain had taken thirty-one bodies in Luc Reyer's lifetime. He had carried down every one of them. He had promised himself he was done counting."))]),
 "8": dict(amb="vast sound stage cavern acoustics: snow machines hissing, a crane motor, a walkie squawk, distant calls of rolling",
   shots=[dict(k=1, seconds=8, characters=[],
     framing="Aerial drone rise off the moving golf cart, sweeping toward Stage 1",
     action="The camera lifts off the moving golf cart mid-plaza and rises — the white cart shrinking below, the whole studio lot spreading out in soft 2pm light, sweeping toward Stage 1's open elephant doors.",
     sound="the cart's electric whirr fading, wind lifting with altitude, the lot humming below"),
    dict(k=2, seconds=12, characters=GUIDE,
     framing="Interior single continuous take just inside the sound stage, she faces camera, no cuts",
     action="Just inside the vast sound stage, mid-take on a Fracture Point action scene — a stunt performer in a red-and-black rescue jacket on ropes over the crevasse set, snow machines blowing, the LED mountain wall storm-lit, film crew at work (faces incidental) — The Guide faces the camera, delighted, gesturing back at the shoot.",
     sound="snow machines hissing, a crane moving, 'rolling!' far off",
     line=dict(speaker="The Guide", text="And this is the part I love — the film studios. The stories become films here — full scenes, real sound, shot right on this stage."))]),
 "9": dict(amb="dark editing suite: the film's own mountain wind bleeding from monitors, a scrub-wheel rewind, soft keys",
   shots=[dict(k=1, seconds=16, characters=GUIDE,
     framing="Interior single continuous take in the editing suite, she faces camera, no cuts",
     action="In the dark editing wing, lit by the glowing edit screens — the Fracture Point film playing on the big monitor, an editor at the console (face incidental) — The Guide faces the camera, relaxed and warm.",
     sound="a scrub-wheel rewind, the film's wind from the monitors",
     line=dict(speaker="The Guide", text="This is the editing wing — every scene is cut, scored and mixed in here. It's also where we make the trailers, and all the marketing creatives — every ad and promo you'll see out there. And if a scene isn't right, we shoot it again — just that scene."))]),
 "10": dict(amb="working loading dock: hand-truck wheels on concrete, cartons landing, tape guns, a truck liftgate whine",
   shots=[dict(k=1, seconds=26, characters=GUIDE,
     framing="Exterior single continuous take on the distribution platform, she faces camera, no cuts",
     action="On the distribution centre's loading platform — six platform trucks at the bays, dock workers loading boxes (faces incidental) — The Guide faces the camera, easy and proud, gesturing along the line of trucks.",
     sound="cartons landing, a liftgate whine",
     line=dict(speaker="The Guide", text="And this is our distribution centre. When all of this is done, we ship it over to the different platforms — the books to Amazon and Apple Books, the audiobooks to Audible and Spotify, and our films to Amazon Prime and YouTube — so that what started as an idea in our publisher's office, is now ready to meet the audience as a finished product. As a book, an audiobook, or as a full film. And that's when our marketing department starts working, adding fuel to the fire."))]),
 "11": dict(amb="a dozen dashboards quietly refreshing, soft keyboard clicks, a gentle chime as a campaign goes live",
   shots=[dict(k=1, seconds=6, characters=[],
     framing="Interior insert, the marketing department at work",
     action="The bright, busy marketing department: the display wall running the Fracture Point campaign — its snowy cover as ad creatives in several sizes, its trailer playing, performance curves climbing — a dozen marketers at work, a group at the campaign wall (all faces incidental).",
     sound="dashboards refreshing, a soft chime")]),
 "12": dict(amb="the dock noise falling away behind her: distant cartons, wind, her footsteps on concrete growing alone",
   shots=[dict(k=1, seconds=9, characters=GUIDE,
     framing="Exterior single continuous walking take along the platform, she walks toward camera",
     action="The Guide walks unhurried toward the camera along the distribution platform, past the trucks being loaded, trailing a hand along a stack of crates, a small knowing smile — the plain door visible at the platform's end behind her.",
     sound="her footsteps on concrete, the dock quieting",
     line=dict(speaker="The Guide", text="Of course — this lot doesn't exist. Not in brick and palm trees, anyway.")),
    dict(k=2, seconds=6, characters=GUIDE,
     framing="At the platform's end: the plain door",
     action="At the end of the platform The Guide reaches a plain grey door in the warehouse wall, opens it — pure white light spills out through the doorway — and she steps through into the white, a natural turn of movement.",
     sound="the door handle, a low white hush swelling through the gap")]),
 "13": dict(amb="total white silence, only her footsteps and voice in a boundless void",
   shots=[dict(k=1, seconds=27, characters=GUIDE,
     framing="Single continuous take in the white void, she walks toward camera from small to full height, no cuts",
     action="A boundless pure-white room — no walls, no shadows, only the small dark doorway far behind her. The Guide walks steadily toward the camera, growing from small in the white to full height in frame, near and personal, always in motion, speaking the whole way.",
     sound="her footsteps soft in the void",
     line=dict(speaker="The Guide", text="Everything you've just seen is an imagined world, of course — but it shows you something real: what SCRPT can do for you as a creative. The writers, the artists, the studios, the trucks — that's our software, doing every one of those jobs for your stories. Books, audiobooks, films — written, produced, published and promoted. And the whole studio is yours the moment you sign in."))]),
}

FRAME_SRC = {  # (scene, shot) -> staging frame with her true face already in it
 ("4", 1): "tour-sb-03.png", ("5", 1): "tour-sb-04.png", ("6", 1): "tour-sb-05.png",
 ("7", 1): "tour-sb-06.png", ("7", 2): "tour-sb-06.png",
 ("8", 1): "scrpt-lot-photo.png", ("8", 2): "tour-sb-07.png",
 ("9", 1): "tour-sb-08.png", ("10", 1): "tour-sb-09.png", ("11", 1): "tour-sb-09b.png",
 ("12", 1): "tour-sb-10.png", ("12", 2): "tour-sb-10.png", ("13", 1): "tour-sb-11.png",
}

def wait_for_running_job():
    """Never shoot beside another producer — wait out any running scene job."""
    me = os.getpid()
    while True:
        r = subprocess.run(["pgrep", "-f", "produce_scene|SCRPT-TOUR-PILOT"],
                           capture_output=True, text=True)
        pids = [p for p in r.stdout.split() if p.strip() and int(p) != me]
        others = []
        for p in pids:
            c = subprocess.run(["ps", "-p", p, "-o", "command="],
                               capture_output=True, text=True).stdout
            if "python3" in c and str(me) not in p:
                others.append(p)
        if not others:
            return
        print(f"waiting for running job(s) {others} ...", flush=True)
        time.sleep(60)

OFFICE_LINE = ("This is where we hatch out the frameworks and seeds for new "
               "stories, that eventually can become books, audiobooks, movie "
               "trailers and full films.")

async def main():
    wait_for_running_job()

    book = get_book_by_catalog("SC-033")
    film = _film(book)

    # Lars cut the office line's first sentence (it repeated the gate's
    # "where every idea starts"). If scene 3 was shot with the longer line,
    # the take is outdated — clear it so it re-shoots with the final text.
    sc3 = film.setdefault("scenes", {}).setdefault("3", {})
    sh3 = (sc3.get("shots") or [{}])[0]
    if ((sh3.get("line") or {}).get("text") or "") != OFFICE_LINE:
        sh3.setdefault("line", {})["text"] = OFFICE_LINE
        sh3["line"]["speaker"] = "The Guide"
        for f in (BASE / "scene-03").glob("*.mp4"):
            f.unlink()
        print("scene 3: line shortened — old take cleared for re-shoot", flush=True)

    for n, sc in SCENES.items():
        cur = film.setdefault("scenes", {}).setdefault(n, {})
        cur["ambience"] = sc["amb"]
        cur["shots"] = sc["shots"]
    _save_film("SC-033", film)
    print("scenes 4-13 staged", flush=True)

    for (n, k), src in FRAME_SRC.items():
        d = BASE / f"scene-{int(n):02d}"
        d.mkdir(parents=True, exist_ok=True)
        dest = d / f"frame-{k:02d}.png"
        if not dest.exists():
            shutil.copy2(HOUSE / src, dest)
    print("true-face frames installed", flush=True)

    failed = []
    for n in range(2, 14):
        out = BASE / f"scene-{n:02d}" / "scene.mp4"
        if out.exists() and out.stat().st_size > 300_000:
            print(f"scene {n}: already produced, keeping", flush=True)
            continue
        bal = await runway.credit_balance()
        if bal < CREDIT_FLOOR:
            print(f"CREDIT FLOOR: {bal} left — stopping shoots", flush=True)
            failed.append(n)
            continue
        try:
            rec = await produce_scene("SC-033", n)
            print(f"scene {n}: {json.dumps(rec)}", flush=True)
        except Exception as e:
            print(f"scene {n} FAILED: {e}", flush=True)
            failed.append(n)

    # ---- the marketing insert rides on the dock line's tail ----
    s10 = BASE / "scene-10/scene.mp4"
    s11 = BASE / "scene-11/scene.mp4"
    s10x = BASE / "scene-10/scene-with-insert.mp4"
    use_insert_cut = False
    if s10.exists() and s11.exists():
        try:
            d10, d11 = secs(s10), secs(s11)
            tc = max(2.0, d10 - (d11 + 1.0))   # insert ends 1 s before her take ends
            run(["-y", "-i", str(s10), "-i", str(s11), "-filter_complex",
                 f"[1:v]scale=1280:720,setpts=PTS+{tc:.3f}/TB[ins];"
                 f"[0:v][ins]overlay=enable='between(t,{tc:.3f},{tc + d11 - 0.1:.3f})':eof_action=pass[v];"
                 f"[1:a]adelay={int(tc*1000)}|{int(tc*1000)},volume=0.35[ia];"
                 f"[0:a][ia]amix=inputs=2:duration=first:dropout_transition=0[a]",
                 "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast",
                 "-crf", "18", "-c:a", "aac", "-ar", "48000", str(s10x)], "insert overlay")
            print("marketing insert overlaid on dock tail", flush=True)
        except Exception as e:
            print(f"insert overlay failed ({e}) — falling back to straight cut", flush=True)
            use_insert_cut = True
    else:
        use_insert_cut = s11.exists()

    # ---- end card: white, the mark, Brian's line ----
    card = BASE / "endcard.png"
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (1280, 720), (250, 249, 247))
    dr = ImageDraw.Draw(im)
    def font(size):
        for f in ("/System/Library/Fonts/Supplemental/Didot.ttc",
                  "/System/Library/Fonts/Supplemental/Times New Roman.ttf"):
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
        return ImageFont.load_default()
    f1, f2 = font(120), font(30)
    def centred(txt, f, y, tracking=0, fill=(35, 33, 30)):
        w = dr.textlength(txt, font=f) + tracking * max(0, len(txt) - 1)
        x = (1280 - w) / 2
        for ch in txt:
            dr.text((x, y), ch, font=f, fill=fill)
            x += dr.textlength(ch, font=f) + tracking
    centred("S C R P T", f1, 250)
    centred("ONE IDEA. EVERY FORMAT.", f2, 420, tracking=6, fill=(110, 100, 85))
    im.save(card)

    genre = (book["data"].get("genre_preset") or "")
    brian = await _record_line("SC-033", "Script — One Idea. Every Format.", genre,
                               "tour-brian-close", "tour-brian-close.mp3",
                               speed=0.95, voice_override=BRIAN)
    ecard = BASE / "endcard.mp4"
    binp = ["-i", str(brian)] if brian else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    run(["-y", "-loop", "1", "-i", str(card), *binp,
         "-filter_complex",
         "[0:v]fade=t=in:st=0.5:d=1.4:color=white,format=yuv420p,fps=24[v];"
         "[1:a]adelay=1800|1800,apad[a]",
         "-map", "[v]", "-map", "[a]", "-t", "8",
         "-c:v", "libx264", "-preset", "fast", "-crf", "18",
         "-c:a", "aac", "-ar", "48000", "-ac", "2", str(ecard)], "end card")
    print("end card built", flush=True)

    # ---- assembly order ----
    order = []
    for n in range(1, 14):
        if n == 10 and s10x.exists():
            order.append(s10x); continue
        if n == 11 and not use_insert_cut:
            continue                     # insert already lives inside scene 10
        p = BASE / f"scene-{n:02d}/scene.mp4"
        if p.exists():
            order.append(p)
        else:
            print(f"assembly: scene {n} missing, skipped", flush=True)
    order.append(ecard)

    lst = BASE / "full-list.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in order))
    joined = BASE / "full-joined.mp4"
    run(["-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-vf", "scale=1280:720,fps=24,format=yuv420p",
         "-c:v", "libx264", "-preset", "fast", "-crf", "18",
         "-c:a", "aac", "-ar", "48000", "-ac", "2", str(joined)], "full concat")

    # ---- the score in its three costumes ----
    durs = [secs(p) for p in order]
    starts, t = [], 0.0
    for d in durs:
        starts.append(t); t += d
    total = t
    idx = {p: i for i, p in enumerate(order)}
    def start_of(scene_n, default):
        p = s10x if (scene_n == 10 and s10x.exists()) else BASE / f"scene-{scene_n:02d}/scene.mp4"
        return starts[idx[p]] if p in idx else default
    t3 = start_of(3, 27)          # marimba enters at the office
    t8 = start_of(8, total * .5)  # orchestra returns at the stage ride
    t10 = start_of(10, total * .7)
    t13 = start_of(13, total - durs[-1] - 27)
    te = starts[-1]               # end card
    ms3, ms8, ms10, mste = (int(x * 1000) for x in (t3, t8, t10, te))
    fc = (
        f"[1:a]atrim=0:{t3+2:.2f},afade=t=in:d=0.8,afade=t=out:st={t3-0.6:.2f}:d=2.4,volume=0.85[orchA];"
        f"[2:a]atrim=0:{t8-t3+2:.2f},afade=t=in:d=1.5,afade=t=out:st={t8-t3-0.5:.2f}:d=2.0,volume=0.5,adelay={ms3}|{ms3}[marA];"
        f"[3:a]atrim=0:{t10-t8+2:.2f},afade=t=in:d=1.0,afade=t=out:st={t10-t8-0.5:.2f}:d=2.0,volume=0.75,adelay={ms8}|{ms8}[orchB];"
        f"[4:a]atrim=0:{t13-t10+1:.2f},afade=t=in:d=1.2,afade=t=out:st={t13-t10-3.0:.2f}:d=3.0,volume=0.45,adelay={ms10}|{ms10}[orchC];"
        f"[5:a]atrim=0:{total-te:.2f},afade=t=in:d=1.2,volume=0.6,adelay={mste}|{mste}[orchE];"
        f"[orchA][marA][orchB][orchC][orchE]amix=inputs=5:duration=longest:dropout_transition=0:normalize=0,atrim=0:{total:.2f}[bus];"
        f"[bus][0:a]sidechaincompress=threshold=0.02:ratio=10:attack=30:release=500[duck];"
        f"[0:a][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0:weights=1 0.9[mix]"
    )
    run(["-y", "-i", str(joined),
         "-i", "/tmp/score-orch.mp3", "-stream_loop", "6", "-i", "/tmp/score-mar.mp3",
         "-i", "/tmp/score-orch.mp3", "-i", "/tmp/score-orch.mp3", "-i", "/tmp/score-orch.mp3",
         "-filter_complex", fc, "-map", "0:v", "-map", "[mix]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(DESK)], "score mix")
    print(f"FULL FILM: {DESK} ({total:.1f}s)", flush=True)
    if failed:
        print(f"NOTE — scenes with problems: {failed}", flush=True)
    print("credits left:", await runway.credit_balance(), flush=True)

asyncio.run(main())
