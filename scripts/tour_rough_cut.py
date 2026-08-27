"""Phase 1 rough cut: every department scene + narration + score, no guide
scenes yet (gate/stage/white room are Phase 2). Order: 1,3,4,5,6,7,9,10(+11
insert on the shipping line's tail),12, end card. Score: big Hollywood theme
from FRAME ONE (Lars's law), marimba under the working floors, orchestra back
for editing, striding through the dock, thinning to the door.
Output: ~/Desktop/SCRPT-TOUR-ROUGHCUT-v1.mp4
"""
import sys, os, re, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
BASE = Path(__file__).resolve().parent.parent / "output" / "SC-033" / "film"
DESK = Path.home() / "Desktop" / "SCRPT-TOUR-ROUGHCUT-v1.mp4"

def run(args, what):
    r = subprocess.run([FF, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{what}: {r.stderr[-500:]}")

def secs(p):
    r = subprocess.run([FF, "-i", str(p)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))

# wait out any running producer
me = os.getpid()
while True:
    r = subprocess.run(["pgrep", "-f", "produce_scene"], capture_output=True, text=True)
    skip = {me, os.getppid()}
    others = [p for p in r.stdout.split() if p.strip() and int(p) not in skip]
    if not others:
        break
    print(f"waiting for producer {others}...", flush=True)
    time.sleep(45)

s10 = BASE / "scene-10/scene.mp4"
s11 = BASE / "scene-11/scene.mp4"
s10x = BASE / "scene-10/scene-with-insert.mp4"
if s10.exists() and s11.exists():
    d10, d11 = secs(s10), secs(s11)
    tc = max(2.0, d10 - (d11 + 1.0))
    run(["-y", "-i", str(s10), "-i", str(s11), "-filter_complex",
         f"[1:v]scale=1280:720,setpts=PTS+{tc:.3f}/TB[ins];"
         f"[0:v][ins]overlay=enable='between(t,{tc:.3f},{tc + d11 - 0.1:.3f})':eof_action=pass[v];"
         f"[1:a]adelay={int(tc*1000)}|{int(tc*1000)},volume=0.35[ia];"
         f"[0:a][ia]amix=inputs=2:duration=first:dropout_transition=0[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast",
         "-crf", "18", "-c:a", "aac", "-ar", "48000", str(s10x)], "insert overlay")
    print("insert overlaid", flush=True)

order = []
for n in (1, 3, 4, 5, 6, 7, 9, 10, 12):
    p = s10x if (n == 10 and s10x.exists()) else BASE / f"scene-{n:02d}/scene.mp4"
    if p.exists():
        order.append(p)
    else:
        print(f"missing scene {n}", flush=True)
ecard = BASE / "endcard.mp4"
if ecard.exists():
    order.append(ecard)

lst = BASE / "rough-list.txt"
lst.write_text("".join(f"file '{p.resolve()}'\n" for p in order))
joined = BASE / "rough-joined.mp4"
run(["-y", "-f", "concat", "-safe", "0", "-i", str(lst),
     "-vf", "scale=1280:720,fps=24,format=yuv420p",
     "-c:v", "libx264", "-preset", "fast", "-crf", "18",
     "-c:a", "aac", "-ar", "48000", "-ac", "2", str(joined)], "concat")

durs = [secs(p) for p in order]
starts, t = [], 0.0
for d in durs:
    starts.append(t); t += d
total = t
def start_of(scene_n, default):
    p = s10x if (scene_n == 10 and s10x.exists()) else BASE / f"scene-{scene_n:02d}/scene.mp4"
    return starts[order.index(p)] if p in order else default
t3 = start_of(3, 10)            # marimba enters at the office
t9 = start_of(9, total * .55)   # orchestra returns at the editing wing
t12 = start_of(12, total * .85) # thinning at the door
te = starts[-1] if ecard.exists() else total
ms3, ms9, mste = int(t3*1000), int(t9*1000), int(te*1000)
fc = (
    # FRAME ONE DOWNBEAT: the theme opens at full confidence, no slow fade
    f"[1:a]atrim=0:{t3+2:.2f},afade=t=out:st={t3-0.6:.2f}:d=2.4,volume=0.9[orchA];"
    f"[2:a]atrim=0:{t9-t3+2:.2f},afade=t=in:d=1.2,afade=t=out:st={t9-t3-0.5:.2f}:d=2.0,volume=0.5,adelay={ms3}|{ms3}[marA];"
    f"[3:a]atrim=0:{t12-t9+2:.2f},afade=t=in:d=1.0,afade=t=out:st={t12-t9-0.5:.2f}:d=2.5,volume=0.7,adelay={ms9}|{ms9}[orchB];"
    f"[4:a]atrim=0:{total-te:.2f},afade=t=in:d=1.0,volume=0.6,adelay={mste}|{mste}[orchE];"
    f"[orchA][marA][orchB][orchE]amix=inputs=4:duration=longest:dropout_transition=0:normalize=0,atrim=0:{total:.2f}[bus];"
    f"[bus][0:a]sidechaincompress=threshold=0.02:ratio=10:attack=30:release=500[duck];"
    f"[0:a][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0:weights=1 0.9[mix]"
)
run(["-y", "-i", str(joined),
     "-i", "/tmp/score-orch.mp3", "-stream_loop", "6", "-i", "/tmp/score-mar.mp3",
     "-i", "/tmp/score-orch.mp3", "-i", "/tmp/score-orch.mp3",
     "-filter_complex", fc, "-map", "0:v", "-map", "[mix]",
     "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(DESK)], "score mix")
print(f"ROUGH CUT: {DESK} ({total:.1f}s)", flush=True)
