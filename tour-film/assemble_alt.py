"""The tour's edit — the commercial's assembler adapted.

Differences from the commercial: the guide's speaking takes carry NATIVE audio
(veo lip sync) — extracted and placed on the timeline exactly where their take
sits; and the score starts on FRAME ONE at full confidence (Lars's law).
"""
import subprocess, sys, json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from board import takes, END_DUR
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT = Path(__file__).parent
X = 0.55         # cross-dissolve
LEAD = 0.35      # VO starts this far into its panel
SCORE = OUT / "score.mp3"
FINAL = Path(__file__).parent / "tour_alt.mp4"   # the ALT cut — separate master

def run(args, label):
    p = subprocess.run([FF, *args], capture_output=True, text=True)
    if p.returncode != 0:
        print(f"!! {label}\n{p.stderr[-2000:]}"); sys.exit(1)

def dur(path):
    s = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", s)
    if not m:
        raise RuntimeError(f"no duration for {path}")
    h, mi, sec = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(sec)

PARTIAL = "--partial" in sys.argv
TK = takes()
# ALT CUT (Lars): no gate welcome, no marketing department — aerial dissolves
# straight into the golf cart; its first 0.5s (a glitch) is trimmed away.
TK = [t for t in TK if t["key"] not in ("03", "27")]
HEADTRIM = {"35": 0.5}
missing = [t["key"] for t in TK if not (OUT / f"shot_{t['key']}.mp4").exists()]
if missing and not PARTIAL:
    print("missing takes:", ", ".join(missing)); sys.exit(2)
if PARTIAL:
    TK = [t for t in TK if (OUT / f"shot_{t['key']}.mp4").exists()]
    print("PARTIAL cut —", len(TK), "takes; missing:", ", ".join(missing))

# ---- 1. per-take screen time. Speaking takes keep their full spoken length;
#         silent panels stretch to fit their VO like the commercial.
by_panel = {}
for t in TK:
    by_panel.setdefault(t["panel"], []).append(t)

plan = []
for t in TK:
    src = OUT / f"shot_{t['key']}.mp4"
    if t.get("line"):                      # native speech: keep the take whole
        plan.append(dur(src) - 0.15)
        continue
    sibs = [x for x in by_panel[t["panel"]] if not x.get("line")]
    v = OUT / f"vo_{t['panel']:02d}.mp3"
    need = (dur(v) + LEAD + 0.45 + X) if v.exists() else 0
    panel_len = max(sum(x["dur"] for x in sibs), need)
    plan.append(panel_len / max(1, len(sibs)))

# ---- 2. cut every take to length
clips = []
for t, d in zip(TK, plan):
    src = OUT / f"shot_{t['key']}.mp4"
    dst = OUT / f"cut_alt_{t['key']}.mp4"
    ht = HEADTRIM.get(t["key"], 0.0)
    have = dur(src) - ht
    vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=24,format=yuv420p"
    if have < d - 0.05:
        vf = f"setpts={d/have:.5f}*PTS," + vf
    run(["-y", "-ss", f"{ht:.3f}", "-i", str(src), "-t", f"{d:.3f}", "-an", "-vf", vf,
         "-c:v", "libx264", "-crf", "16", "-preset", "medium",
         "-pix_fmt", "yuv420p", str(dst), "-loglevel", "error"], f"cut {t['key']}")
    clips.append(dst)
    if t.get("line"):                      # native audio out to the timeline
        run(["-y", "-i", str(src), "-vn", "-t", f"{d:.3f}",
             "-af", "aresample=44100,afade=t=in:d=0.05",
             str(OUT / f"na_{t['key']}.mp3"), "-loglevel", "error"], f"na {t['key']}")

# ---- 3. end card
card = OUT / "endcard.png"
if not card.exists():
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (1920, 1080), (250, 249, 247))
    dr = ImageDraw.Draw(im)
    def font(size):
        for f in ("/System/Library/Fonts/Supplemental/Didot.ttc",
                  "/System/Library/Fonts/Supplemental/Times New Roman.ttf"):
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
        return ImageFont.load_default()
    f1, f2 = font(170), font(44)
    def centred(txt, f, y, tracking=0, fill=(35, 33, 30)):
        w = dr.textlength(txt, font=f) + tracking * max(0, len(txt) - 1)
        x = (1920 - w) / 2
        for ch in txt:
            dr.text((x, y), ch, font=f, fill=fill)
            x += dr.textlength(ch, font=f) + tracking
    centred("S C R P T", f1, 380)
    centred("ONE IDEA. EVERY FORMAT.", f2, 630, tracking=9, fill=(110, 100, 85))
    im.save(card)
end = OUT / "cut_alt_end.mp4"
run(["-y", "-loop", "1", "-i", str(card), "-t", f"{END_DUR:.3f}",
     "-vf", f"fade=t=out:st={END_DUR-1.4:.2f}:d=1.4,fps=24,format=yuv420p",
     "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p",
     str(end), "-loglevel", "error"], "endcard")
clips.append(end); plan.append(END_DUR)

# ---- 4. the reel: dissolves, washing to white at the end
starts, t0 = [], 0.0
for d in plan:
    starts.append(t0); t0 += d - X
total = t0 + X

args = ["-y"]
for c in clips:
    args += ["-i", str(c)]
chain, prev, off = [], "0:v", 0.0
for i in range(1, len(clips)):
    off += plan[i - 1] - X
    trans = "fade"     # her wall and the card share the same white — a plain
    # dissolve is seamless; fadewhite overshot to pure 255 (a bright flash)
    chain.append(f"[{prev}][{i}:v]xfade=transition={trans}:duration={X}:"
                 f"offset={off:.3f}[v{i}]")
    prev = f"v{i}"
run(args + ["-filter_complex", ";".join(chain), "-map", f"[{prev}]",
            "-c:v", "libx264", "-crf", "16", "-preset", "medium",
            "-pix_fmt", "yuv420p", str(OUT / "picture_alt.mp4"), "-loglevel", "error"], "reel")

# ---- 5. voices on the timeline: TTS VO per panel + native take audio, then
#         the score ducked beneath every word, from FRAME ONE.
voiced_panels = set()
vo_at = []
for i, t in enumerate(TK):
    if t.get("line"):
        vo_at.append((OUT / f"na_{t['key']}.mp3", starts[i]))
        continue
    p = t["panel"]
    if p in voiced_panels:
        continue
    v = OUT / f"vo_{p:02d}.mp3"
    if v.exists():
        vo_at.append((v, starts[i] + LEAD))
        voiced_panels.add(p)
vo_at.append((OUT / "vo_end.mp3", starts[len(TK)] + 1.2))
# ALT: the welcome is pure VO over the drone shot — she greets us, then the
# cart panel's line follows as the second sentence
i35 = next(i for i, t in enumerate(TK) if t["key"] == "35")
vo_at.append((OUT / "vo_hi.mp3",
              max(0.4, starts[i35] + LEAD - dur(OUT / "vo_hi.mp3") - 0.35)))
if (OUT / "amb_open.mp3").exists():
    vo_at.append((OUT / "amb_open.mp3", 0.0))
vo_at = [(f, at) for f, at in vo_at if f.exists()]
# no colliding voices (Lars): push any cue that would start before the
# previous one ends, plus a natural breath
vo_at.sort(key=lambda x: x[1])
guarded, prev_end = [], -10.0
for fpath, at in vo_at:
    is_bed = Path(fpath).name == "amb_open.mp3"
    if "na_" in Path(fpath).name or is_bed:
        pass                       # LIP SYNC IS SACRED — never move take audio
    else:
        at = max(at, prev_end + 0.35)
    guarded.append((fpath, at))
    if not is_bed:                 # a bed is not a voice: it must not push cues
        prev_end = at + dur(fpath)
vo_at = guarded

args = ["-y", "-i", str(OUT / "picture_alt.mp4")]
for f, _ in vo_at:
    args += ["-i", str(f)]
args += ["-i", str(SCORE)]
si = len(vo_at) + 1

f = []
for i, (_, at) in enumerate(vo_at):
    ms = int(at * 1000)
    nm = Path(vo_at[i][0]).name
    lvl = 1.22 if nm == "na_03.mp3" else (0.55 if nm == "amb_open.mp3" else 1.0)
    tail = ""
    if nm == "na_03.mp3":      # its baked score bed cut dead at the next clip
        d03 = dur(vo_at[i][0])
        tail = f",afade=t=out:st={max(0, d03-1.2):.2f}:d=1.2"
    f.append(f"[{i+1}:a]aresample=44100{tail},adelay={ms}|{ms},volume={lvl}[n{i}]")
f.append("".join(f"[n{i}]" for i in range(len(vo_at))) +
         f"amix=inputs={len(vo_at)}:normalize=0:dropout_transition=0[vo]")
f.append("[vo]asplit=2[vomix][vokeyraw]");
f.append(f"[vokeyraw]apad=whole_dur={total:.3f}[vokey]")   # self-bounding pad: atrim-after-infinite-apad never EOFs in this split graph
# FRAME ONE DOWNBEAT, then three movements (Lars): the strong opening calms
# into her first words; a quiet continuation carries the film; the FINALE
# returns full at the logo and fades with the black.
OPEN_V, TALK_V, QUIET_V = 0.42, 0.24, 0.15
score_len = dur(SCORE)
t_end = starts[-1]                     # the card appears here
# no baked bed in this cut — one continuous score, settling slowly mid-scene
i35 = next(i for i, t in enumerate(TK) if t["key"] == "35")
s_end = starts[i35] + plan[i35]
vol = (f"if(lt(t,{s_end:.2f}),{OPEN_V},"
       f"if(lt(t,{s_end+6.0:.2f}),{OPEN_V}+({TALK_V}-{OPEN_V})*(t-{s_end:.2f})/6.0,"
       f"{TALK_V}))")
f.append(f"[{si}:a]aresample=44100,atrim=0:{min(score_len, t_end):.3f},"
         f"volume='{vol}':eval=frame[bedA]")
segs = ["[bedA]"]
pos = min(score_len, t_end)
n = 0
while pos < t_end - 1.0:               # quiet middle: the cue's calm interior
    take = min(score_len - 12.0, t_end - pos)
    ms = int(pos * 1000)
    f.append(f"[{si}:a]aresample=44100,atrim=10:{10+take:.3f},asetpts=PTS-STARTPTS,"
             f"volume={QUIET_V},afade=t=in:d=2.0,adelay={ms}|{ms}[bedQ{n}]")
    segs.append(f"[bedQ{n}]"); pos += take; n += 1
msE = int(t_end * 1000)
f.append(f"[{si}:a]aresample=44100,atrim=0:{END_DUR+1.0:.3f},asetpts=PTS-STARTPTS,"
         f"volume=0.55,afade=t=in:d=0.4,afade=t=out:st={END_DUR-5.5:.2f}:d=5.5,"
         f"adelay={msE}|{msE}[bedF]")
segs.append("[bedF]")
f.append("".join(segs) + f"amix=inputs={len(segs)}:normalize=0:dropout_transition=0,"
         f"atrim=0:{total:.3f}[bed]")
f.append("[bed][vokey]sidechaincompress=threshold=0.05:ratio=7:attack=25:release=420[duck]")
f.append(f"[vomix][duck]amix=inputs=2:normalize=0:dropout_transition=0,"
         f"apad=whole_dur={total:.3f},loudnorm=I=-14:TP=-1.5:LRA=11,"
         f"afade=t=out:st={max(0, total-3.2):.3f}:d=3.2,"
         f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a]")

run(args + ["-filter_complex", ";".join(f), "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
            "-ac", "2", str(FINAL), "-loglevel", "error"], "mix")

(OUT / "cues_alt.json").write_text(json.dumps(
    [{"file": Path(f).name, "at": round(at, 3), "dur": round(dur(f), 3)}
     for f, at in vo_at], indent=1))
assert FINAL.exists() and FINAL.stat().st_size > 5_000_000, "mix produced no usable file"
print(json.dumps({"total_s": round(total, 2), "takes": len(TK),
                  "out": str(FINAL)}, indent=1))
