import asyncio, os, sys, subprocess, difflib, re
from pathlib import Path
BOOKR = Path("/Users/tiger/Desktop/CATALOG ENGINE/bookr")
for line in (BOOKR / ".env").read_text().splitlines():
    if line.strip() and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
sys.path.insert(0, str(BOOKR)); sys.path.insert(0, str(Path(__file__).parent))
import imageio_ffmpeg
from engine.trailer import runway
from board import takes, FRAMES, CANON_GUIDE, CANON_LOT, STYLE

OUT = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
GATE = None
CREDIT_FLOOR = 2000

def crop16x9(src: Path, dest: Path) -> Path:
    from PIL import Image
    im = Image.open(src).convert("RGB")
    w, h = im.size
    want = w * 9 // 16
    if h > want:
        top = (h - want) // 2; im = im.crop((0, top, w, top + want))
    elif h < want:
        ww = h * 16 // 9; left = (w - ww) // 2; im = im.crop((left, 0, left + ww, h))
    im.save(dest); return dest

def build_prompt(tk):
    head = []
    if "g" in tk.get("canon", ""): head.append(CANON_GUIDE)
    if "l" in tk.get("canon", ""): head.append(CANON_LOT)
    body = f"SHOT: {tk['shot']}"
    if tk.get("line"):
        voice = tk.get("voice") or ("a warm, friendly, professional female voice, "
                                    "bright and young, clear American English")
        if tk.get("speech"):
            body += (f"\n\n{tk['speech']} (accurate natural lip sync, {voice}; he "
                     f"reads EXACTLY these words, slowly): \"{tk['line']}\"")
        else:
            # A friendly host, not a recital: her own conversational words are
            # welcome — the CONTENT is what must land (Lars's direction).
            body += (f"\n\nTHE GUIDE speaks warmly and naturally straight to the "
                     f"camera, like a friendly host welcoming visitors and showing "
                     f"them around — conversational, relaxed, genuinely delighted, "
                     f"accurate natural lip sync, {voice}. In her own friendly "
                     f"words she conveys exactly this, in clear English, and "
                     f"nothing else: \"{tk['line']}\"")
    return "\n\n".join(head) + "\n\n" + body + f"\n\nSTYLE: {STYLE}" + tk.get("text", "")

def transcript_ok(clip: Path, expect: str) -> bool:
    """Reject mumble takes: the audio must transcribe to (close to) the line."""
    wav = clip.with_suffix(".wav")
    subprocess.run([FF, "-y", "-v", "error", "-i", str(clip), "-vn", "-ar", "16000",
                    "-ac", "1", str(wav)], capture_output=True)
    try:
        import httpx
        with open(wav, "rb") as fh:
            r = httpx.post("https://api.openai.com/v1/audio/transcriptions",
                           headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                           files={"file": ("a.wav", fh, "audio/wav")},
                           data={"model": "whisper-1", "language": "en"}, timeout=180)
        got = (r.json().get("text") or "") if r.status_code == 200 else ""
    except Exception:
        got = ""
    finally:
        wav.unlink(missing_ok=True)
    if not got.strip():
        print("    transcript EMPTY", flush=True)
        return False
    # Lars's standard: not her exact words — the same meaning and content,
    # conversational and friendly. A judge answers that; string-diff cannot.
    try:
        import httpx
        jr = httpx.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                     "anthropic-version": "2023-06-01"},
            json={"model": "claude-haiku-4-5", "max_tokens": 10,
                  "messages": [{"role": "user", "content":
                    "A friendly studio tour host was asked to convey this content "
                    f"in her own words:\n---\n{expect}\n---\nShe said:\n---\n{got}\n---\n"
                    "Answer PASS if what she said is clear English, friendly and "
                    "conversational, and carries the same meaning and content "
                    "(her own phrasing is fine; nothing important missing, nothing "
                    "off-message added). Also FAIL if she spells out S-C-R-P-T "
                    "letter by letter instead of saying the word Script, or if "
                    "she describes the studio as being only about filmmaking. "
                    "Otherwise answer PASS. One word only."}]},
            timeout=60)
        verdict = jr.json()["content"][0]["text"].strip().upper() if jr.status_code == 200 else ""
    except Exception:
        verdict = ""
    if not verdict:
        a = re.sub(r"[^a-z ]", "", expect.lower())
        b = re.sub(r"[^a-z ]", "", got.lower())
        verdict = "PASS" if difflib.SequenceMatcher(None, a, b).ratio() >= 0.35 else "FAIL"
    print(f"    transcript [{verdict}]: {got[:90]!r}", flush=True)
    return verdict.startswith("PASS")

async def shoot(tk):
    key = tk["key"]
    dest = OUT / f"shot_{key}.mp4"
    if dest.exists() and dest.stat().st_size > 200_000:
        print(f"[{key}] have", flush=True); return True
    prompt = build_prompt(tk)
    speak = bool(tk.get("line"))
    frame_uri = None
    if tk.get("frame"):
        cropped = crop16x9(FRAMES[tk["frame"]], OUT / f"first_{key}.png")
        frame_uri = await runway.upload_file(cropped)
    qc_rolls = 0
    for a in range(12):
        async with GATE:
            try:
                if tk["cam"] == "veo":
                    t = await runway.generate_shot(prompt, frame_uri or "",
                                                   seconds=8, ratio="1920:1080",
                                                   model="veo3.1", audio=speak)
                else:
                    secs = max(4, min(30, tk["dur"]))   # Seedance holds 30s single takes
                    t = await runway.generate_seedance(prompt, [], seconds=secs,
                                                       ratio="1920:1080",
                                                       model="seedance2_5",
                                                       audio=speak)
                r = await runway.wait_for(t["id"], timeout_s=1800)
                if r.get("status") == "SUCCEEDED" and (r.get("output") or [None])[0]:
                    await runway.download(r["output"][0], dest)
                    if speak and not transcript_ok(dest, tk["line"]):
                        dest.unlink(missing_ok=True)
                        qc_rolls += 1
                        if qc_rolls > 3:
                            print(f"[{key}] transcript QC gave up", flush=True)
                            return False
                        print(f"[{key}] re-roll (speech QC)", flush=True)
                        continue
                    print(f"[{key}] shot ok", flush=True)
                    return True
                fail = f"{r.get('failure')} / {r.get('failureCode')}"
            except Exception as e:
                fail = str(e)[:140]
        print(f"[{key}] try{a} {fail}", flush=True)
        await asyncio.sleep(min(8, 2 + a))
    print(f"[{key}] GAVE UP", flush=True)
    return False

async def main():
    global GATE
    GATE = asyncio.Semaphore(4)
    tks = takes()
    bal = await runway.credit_balance()
    print(f"start credits {bal} · {len(tks)} takes", flush=True)
    res = []
    async def guarded(t):
        if await runway.credit_balance() < CREDIT_FLOOR:
            print(f"[{t['key']}] CREDIT FLOOR — skipped", flush=True); return False
        return await shoot(t)
    res = await asyncio.gather(*(guarded(t) for t in tks))
    print(f"DONE {sum(res)}/{len(tks)} credits {await runway.credit_balance()}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
