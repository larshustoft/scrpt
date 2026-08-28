"""The zero-credit finishing edit — everything from footage already owned.

Fixes cut in: Jessica speaks the brand ("Script") before her on-camera take
enters past the mispronounced word; the fixed audiobook pair; the calm dock;
the longer marketing beat; and the finale as her voice over a reprise montage
of the film's own best moments, landing in the empty white void, then the
card, Brian, and a full fade to black. No generation anywhere.
"""
import subprocess, sys, re, json
from pathlib import Path
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT = Path(__file__).parent
X = 0.55
FINAL = Path.home() / "Desktop" / "SCRPT-TOUR-FINAL.mp4"
SCORE = OUT / "score.mp3"
END_DUR = 7.0

def run(args, label):
    p = subprocess.run([FF, *args], capture_output=True, text=True)
    if p.returncode != 0:
        print(f"!! {label}\n{p.stderr[-1800:]}"); sys.exit(1)

def dur(path):
    s = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", s)
    h, mi, sec = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(sec)

VF = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=24,format=yuv420p"
VF_ZOOM = "scale=2208:1242:force_original_aspect_ratio=increase,crop=1920:1080,fps=24,format=yuv420p"

# (name, src, ss, length, keep_audio, zoom)
SEGS = [
    ("aerial",   "shot_01.mp4",      0.0, 6.0,  False, False),
    ("welcome",  "welcome_block.mp4",2.25,6.30, True,  False),
    ("follow",   "shot_35.mp4",      0.0, 6.2,  False, False),
    ("writersA", "shot_08.mp4",      0.0, 5.0,  False, False),
    ("writersB", "shot_09.mp4",      0.0, 4.6,  False, False),
    ("artA",     "shot_10.mp4",      0.0, 5.2,  False, False),
    ("artB",     "shot_11.mp4",      0.0, 5.2,  False, False),
    ("audioroom","cut_14.mp4",       0.0, 6.0,  False, False),
    ("narrator", "shot_15.mp4",      0.0, 7.85, True,  False),
    ("stageW",   "shot_17.mp4",      0.0, 4.5,  False, False),
    ("stageHer", "shot_18.mp4",      0.0, 7.85, True,  False),
    ("editA",    "shot_20.mp4",      0.0, 5.0,  False, False),
    ("editB",    "shot_21.mp4",      0.0, 4.6,  False, False),
    ("dockA",    "cut_23.mp4",       0.0, 6.3,  False, False),
    ("dockB",    "cut_26.mp4",       0.0, 4.3,  False, False),
    ("mkt",      "shot_27.mp4",      0.0, 6.9,  False, False),
    # ---- the reveal: her voice over the film's own memory ----
    ("void1",    "shot_30.mp4",     22.6, 3.4,  False, True),
    ("m1",       "shot_08.mp4",      1.0, 1.6,  False, False),
    ("m2",       "shot_10.mp4",      1.0, 1.6,  False, False),
    ("m3",       "shot_17.mp4",      0.8, 1.6,  False, False),
    ("m4",       "shot_18.mp4",      2.0, 1.6,  False, False),
    ("m5",       "cut_23.mp4",       1.0, 1.6,  False, False),
    ("m6",       "shot_21.mp4",      1.0, 1.6,  False, False),
    ("m7",       "shot_27.mp4",      1.0, 1.6,  False, False),
    ("m8",       "shot_35.mp4",      1.0, 1.6,  False, False),
    ("void2",    "shot_30.mp4",     24.4, 1.6,  False, True),
]

clips, plan, keepers = [], [], {}
for name, src, ss, ln, keep, zoom in SEGS:
    dst = OUT / f"fin_{name}.mp4"
    vf = VF_ZOOM if zoom else VF
    args = ["-y", "-ss", f"{ss:.3f}", "-i", str(OUT / src), "-t", f"{ln:.3f}",
            "-vf", vf, "-c:v", "libx264", "-crf", "16", "-preset", "medium",
            "-pix_fmt", "yuv420p"]
    args += ["-an"]
    run(args + [str(dst), "-loglevel", "error"], f"seg {name}")
    real = dur(dst)          # trust the file, not the plan — a short source
    if keep:                 # truncated the whole dissolve chain once
        run(["-y", "-ss", f"{ss:.3f}", "-i", str(OUT / src), "-t", f"{real:.3f}",
             "-vn", "-af", "aresample=44100,afade=t=in:d=0.06,afade=t=out:st=" +
             f"{max(0, real-0.25):.3f}:d=0.25",
             str(OUT / f"na_{name}.mp3"), "-loglevel", "error"], f"na {name}")
        keepers[name] = OUT / f"na_{name}.mp3"
    clips.append(dst); plan.append(real)

# the void freeze that carries the last words
last = OUT / "fin_voidhold.png"
run(["-y", "-sseof", "-0.08", "-i", str(OUT / "shot_30.mp4"), "-frames:v", "1",
     "-update", "1", str(last), "-loglevel", "error"], "void frame")
hold = OUT / "fin_voidhold.mp4"
run(["-y", "-loop", "1", "-i", str(last), "-t", "6.5",
     "-vf", "zoompan=z='1.12+0.00035*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=24,format=yuv420p",
     "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
     str(hold), "-loglevel", "error"], "void hold")
clips.append(hold); plan.append(dur(hold))

card = OUT / "endcard.png"
end = OUT / "cut_end_final.mp4"
run(["-y", "-loop", "1", "-i", str(card), "-t", f"{END_DUR:.3f}",
     "-vf", f"fade=t=in:st=0:d=0.9:color=white,fade=t=out:st={END_DUR-1.4:.2f}:d=1.4,fps=24,format=yuv420p",
     "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
     str(end), "-loglevel", "error"], "endcard")
clips.append(end); plan.append(dur(end))

starts, t0 = [], 0.0
for d in plan:
    starts.append(t0); t0 += d - X
total = t0 + X
S = {SEGS[i][0]: starts[i] for i in range(len(SEGS))}
S["voidhold"] = starts[len(SEGS)]
S["end"] = starts[len(SEGS) + 1]

args = ["-y"]
for c in clips:
    args += ["-i", str(c)]
chain, prev, off = [], "0:v", 0.0
for i in range(1, len(clips)):
    off += plan[i - 1] - X
    trans = "fadewhite" if i >= len(clips) - 2 else "fade"
    chain.append(f"[{prev}][{i}:v]xfade=transition={trans}:duration={X}:offset={off:.3f}[v{i}]")
    prev = f"v{i}"
run(args + ["-filter_complex", ";".join(chain), "-map", f"[{prev}]",
            "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
            str(OUT / "picture_final.mp4"), "-loglevel", "error"], "reel")

# ---- voices on the timeline ----
vo_at = [
    (OUT / "vo_hi.mp3",    S["aerial"] + 2.1),
    (OUT / "na_welcome.mp3", S["welcome"]),
    (OUT / "vo_03.mp3",    S["follow"] + 0.35),      # production line
    (OUT / "vo_05.mp3",    S["writersA"] + 0.35),
    (OUT / "vo_06.mp3",    S["artA"] + 0.35),
    (OUT / "vo_08.mp3",    S["audioroom"] + 0.35),
    (OUT / "na_narrator.mp3", S["narrator"]),
    (OUT / "na_stageHer.mp3", S["stageHer"]),
    (OUT / "vo_13.mp3",    S["editA"] + 0.35),
    (OUT / "vo_14.mp3",    S["dockA"] + 0.30),
    (OUT / "vo_15.mp3",    S["mkt"] + 0.35),
    (OUT / "vo_close.mp3", S["void1"] + 0.5),
    (OUT / "vo_end.mp3",   S["end"] + 1.2),
]
vo_at = [(f, at) for f, at in vo_at if f.exists()]
vo_at.sort(key=lambda x: x[1])
guarded, prev_end = [], -10.0
for fpath, at in vo_at:
    at = max(at, prev_end + 0.35)
    guarded.append((fpath, at)); prev_end = at + dur(fpath)
vo_at = guarded

args = ["-y", "-i", str(OUT / "picture_final.mp4")]
for f_, _ in vo_at:
    args += ["-i", str(f_)]
args += ["-i", str(SCORE)]
si = len(vo_at) + 1

fc = []
for i, (_, at) in enumerate(vo_at):
    ms = int(at * 1000)
    fc.append(f"[{i+1}:a]aresample=44100,adelay={ms}|{ms},volume=1.0[n{i}]")
fc.append("".join(f"[n{i}]" for i in range(len(vo_at))) +
          f"amix=inputs={len(vo_at)}:normalize=0:dropout_transition=0[vo]")
fc.append("[vo]asplit=2[vomix][vokey]")

# score: downbeat at zero, calm under first VO, SILENT under the welcome
# segment (its own baked bed carries the same cue), quiet through the film,
# finale at the card, master fade at the end
w0, w1 = S["welcome"] - 0.35, S["welcome"] + 6.30
te = S["end"]
OPEN_V, TALK_V, QUIET_V = 0.42, 0.24, 0.16
vol = (f"if(lt(t,1.6),{OPEN_V},"
       f"if(lt(t,{w0:.2f}),{TALK_V},"
       f"if(lt(t,{w1:.2f}),0,"
       f"if(lt(t,{S['void1']:.2f}),{TALK_V},{QUIET_V}))))")
score_len = dur(SCORE)
fc.append(f"[{si}:a]aresample=44100,atrim=0:{min(score_len, te):.3f},"
          f"volume='{vol}':eval=frame[bedA]")
segsA = ["[bedA]"]
pos, n = min(score_len, te), 0
while pos < te - 1.0:
    take = min(score_len - 12.0, te - pos)
    ms = int(pos * 1000)
    fc.append(f"[{si}:a]aresample=44100,atrim=10:{10+take:.3f},asetpts=PTS-STARTPTS,"
              f"volume={QUIET_V},afade=t=in:d=2.0,adelay={ms}|{ms}[bedQ{n}]")
    segsA.append(f"[bedQ{n}]"); pos += take; n += 1
msE = int(te * 1000)
fc.append(f"[{si}:a]aresample=44100,atrim=0:{END_DUR+1.0:.3f},asetpts=PTS-STARTPTS,"
          f"volume=0.5,afade=t=in:d=0.4,afade=t=out:st={END_DUR-2.2:.2f}:d=2.2,"
          f"adelay={msE}|{msE}[bedF]")
segsA.append("[bedF]")
fc.append("".join(segsA) + f"amix=inputs={len(segsA)}:normalize=0:dropout_transition=0,"
          f"atrim=0:{total:.3f}[bed]")
fc.append("[bed][vokey]sidechaincompress=threshold=0.05:ratio=7:attack=25:release=420[duck]")
fc.append(f"[vomix][duck]amix=inputs=2:normalize=0:dropout_transition=0,"
          f"atrim=0:{total:.3f},loudnorm=I=-14:TP=-1.5:LRA=11,"
          f"afade=t=out:st={max(0, total-1.8):.3f}:d=1.8,"
          f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a]")

run(args + ["-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
            "-ac", "2", "-shortest", str(FINAL), "-loglevel", "error"], "mix")
print(json.dumps({"total_s": round(total, 2), "out": str(FINAL)}, indent=1))
