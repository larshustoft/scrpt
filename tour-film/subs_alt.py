"""Burned-subtitle track for the ALT tour cut.

Rules (Lars): at most two lines per cue, every line hard-capped so libass
can never add a third; one fixed bottom-center position; nothing on the
logo card — its own typography carries the closing words.
"""
import json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, ".")
import board
import imageio_ffmpeg

END_DUR = board.END_DUR
FF = imageio_ffmpeg.get_ffmpeg_exe()

panel_vo = {}
for obj in vars(board).values():
    if isinstance(obj, list):
        for p in obj:
            if isinstance(p, dict) and "vo" in p and "n" in p:
                panel_vo[p["n"]] = p["vo"]
line_by_key = {t["key"]: t.get("line") for t in board.takes() if t.get("line")}

TEXT = {"vo_hi.mp3": "Hi! And welcome to Script Studios!"}
for n, vo in panel_vo.items():
    TEXT[f"vo_{n:02d}.mp3"] = vo
for k, ln in line_by_key.items():
    TEXT[f"na_{k}.mp3"] = ln
# vo_end plays over the logo card — deliberately NOT subtitled

def brand(t):
    return re.sub(r"\bScript\b", "SCRPT", t)

CPL = 26
def cues_for(text):
    """Word-greedy lines of <= CPL chars, paired into cues of at most two."""
    words = " ".join(text.split()).split(" ")
    lines, cur = [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if len(t) <= CPL:
            cur = t
        else:
            if cur:
                lines.append(cur)
            while len(w) > CPL:
                lines.append(w[:CPL]); w = w[CPL:]
            cur = w
    if cur:
        lines.append(cur)
    return ["\\N".join(lines[i:i + 2]) for i in range(0, len(lines), 2)]

def ts(x):
    return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"

r = subprocess.run([FF, "-i", "tour_alt.mp4"], capture_output=True, text=True).stderr
m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r)
film_len = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
SUB_END = film_len - END_DUR - 0.30      # the card is subtitle-free

hdr = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Film,SF Pro Display,56,&H00FFFFFF,&H90000000,&H00000000,0,0,1,0,3,2,360,360,92,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

ev = []
for c in json.load(open("cues_alt.json")):
    txt = TEXT.get(c["file"])
    if not txt:
        continue
    pieces = cues_for(brand(txt))
    span = c["dur"] + 0.35
    total_chars = sum(len(p.replace("\\N", " ")) for p in pieces)
    t0 = c["at"]
    for p in pieces:
        w = len(p.replace("\\N", " ")) / total_chars
        d = max(0.9, span * w)
        s0, s1 = t0, min(t0 + d, c["at"] + span)
        t0 += span * w
        if s0 >= SUB_END:
            continue
        ev.append(f"Dialogue: 0,{ts(s0)},{ts(min(s1, SUB_END))},Film,,0,0,0,,{p}")

Path("subs_alt.ass").write_text(hdr + "\n".join(ev) + "\n")
bad = [ln for e in ev for ln in e.split(",,")[-1].split("\\N") if len(ln) > CPL]
print(f"{len(ev)} cues, max 2 lines each, line-cap violations: {len(bad)}, "
      f"subs end by {SUB_END:.1f}s (card at {film_len - END_DUR:.1f}s)")
assert not bad
