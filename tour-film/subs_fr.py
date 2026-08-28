"""French burned-subtitle track for the ALT tour cut.

Same rules as the English track: at most two lines per cue, hard 26-char
lines, one fixed position, nothing on the logo card. The brand is always
written SCRPT.
"""
import json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, ".")
import board
import imageio_ffmpeg

END_DUR = board.END_DUR
FF = imageio_ffmpeg.get_ffmpeg_exe()

TEXT = {
    "vo_hi.mp3": "Bonjour ! Bienvenue aux studios SCRPT !",
    "vo_03.mp3": "Vous allez découvrir toute notre chaîne de production — "
                 "d'une simple idée à chacune de nos créations.",
    "vo_05.mp3": "Commençons ici, au département d'écriture. C'est ici que naissent "
                 "les idées de nouvelles histoires, transformées en livres entiers. "
                 "Chapitre par chapitre.",
    "vo_06.mp3": "Voici le département artistique, où chaque livre reçoit son visage — "
                 "couvertures, illustrations et bible des personnages, pour que chaque "
                 "personnage garde le même visage sur la page, la couverture et à l'écran.",
    "vo_08.mp3": "Nos studios de livres audio — où les livres apprennent à parler. Écoutez…",
    "na_15.mp3": "La montagne avait pris trente et un corps du vivant de Luc Reyer. "
                 "Il les avait tous redescendus.",
    "na_18.mp3": "Et voici la partie que je préfère — les studios de cinéma. C'est ici "
                 "que les histoires deviennent des films, sur ce plateau même.",
    "vo_13.mp3": "Voici l'aile du montage — chaque scène y est montée, mise en musique "
                 "et mixée. C'est aussi là que nous créons les bandes-annonces et tous "
                 "les visuels marketing.",
    "vo_14.mp3": "Et voici notre centre de distribution. D'ici, tout part vers les "
                 "plateformes — les livres chez Amazon et Apple Books, les livres audio "
                 "chez Audible et Spotify, et nos films sur Amazon Prime et YouTube — "
                 "prêts à rencontrer leur public en produit fini.",
    "na_30.mp3": "Tout ce que vous venez de voir est un monde imaginaire — mais il "
                 "montre quelque chose de réel : ce que SCRPT peut faire pour vous, "
                 "créateur. Les auteurs, les artistes, les studios, les camions — "
                 "c'est notre logiciel, qui accomplit chacun de ces métiers pour vos "
                 "histoires. Livres, livres audio, films — écrits, produits, publiés "
                 "et promus. Et tout le studio est à vous dès votre connexion.",
    # vo_end plays over the logo card — deliberately NOT subtitled
}

CPL = 26
def cues_for(text):
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
SUB_END = film_len - END_DUR - 0.30

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
    pieces = cues_for(txt)
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

Path("subs_fr.ass").write_text(hdr + "\n".join(ev) + "\n")
bad = [ln for e in ev for ln in e.split(",,")[-1].split("\\N") if len(ln) > CPL]
print(f"{len(ev)} cues FR, line-cap violations: {len(bad)}, subs end by {SUB_END:.1f}s")
assert not bad
