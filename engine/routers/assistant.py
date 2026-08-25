"""
The SCRPT Assistant — the voice of the front office.

Chat grounded in live production context (catalog, jobs, royalties), spoken
replies via ElevenLabs (browser speech-synthesis fallback client-side), and
local speech-to-text via faster-whisper so the desktop app can listen without
any cloud speech service.
"""

import io
from pathlib import Path
from typing import Optional

import re

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from .. import database as db
from ..jobs import list_jobs
from ..writing.client import complete_chat

router = APIRouter(prefix="/api/scrpt/assistant", tags=["assistant"])

DEFAULT_VOICE = "cgSgspJ2msm6clMCkdW9"  # "Jessica" — young, warm, conversational

# The assistant's voice is a colleague's voice, not a narrator's: young and
# conversational rather than cinematic. These are the house choices offered
# in Settings; each one is already in the account, so switching costs nothing.
ASSISTANT_VOICES = [
    {"id": "cgSgspJ2msm6clMCkdW9", "name": "Jessica", "blurb": "Young, bright and warm — the house default"},
    {"id": "uYXf8XasLslADfZ2MB4u", "name": "Hope", "blurb": "Young American, easy and chatty"},
    {"id": "c1uwEpPUcC16tq1udqxk", "name": "Harper", "blurb": "Young American, confident and cool"},
    {"id": "rChSWFjetDOEAE1elP8k", "name": "Asher", "blurb": "Young British, sincere and real"},
    {"id": "UgBBYS2sOqTuMpoF3BR0", "name": "Mark", "blurb": "Young American man, natural conversation"},
    {"id": "bIHbv24MWmeRgasZH58o", "name": "Will", "blurb": "Young American man, relaxed optimist"},
    {"id": "IKne3meq5aSn9XLyUdCD", "name": "Charlie", "blurb": "Young Australian man, confident and energetic"},
    {"id": "FGY2WhTYpPnrIDTdsKH5", "name": "Laura", "blurb": "Young American, quirky and enthusiastic"},
]


# ── credentials ──────────────────────────────────────────────────

def elevenlabs_key() -> str:
    """Settings first, then key files (SCRPT's own, then STCKR's — same machine)."""
    key = db.get_setting("elevenlabs_api_key", "")
    if key:
        return key
    for p in (Path.home() / ".scrpt" / "elevenlabs-key.txt",
              Path.home() / ".stckr" / "elevenlabs-key.txt"):
        try:
            if p.exists():
                return p.read_text().strip()
        except OSError:
            continue
    return ""


# ── live production context ──────────────────────────────────────

def build_context() -> str:
    lines: list[str] = []
    try:
        books = db.list_books(per_page=100)["books"]
        prose = [b for b in books if b["data"].get("manuscript")]
        lines.append(f"CATALOG ({len(prose)} titles):")
        for b in prose[:20]:
            ms = b["data"]["manuscript"]
            series = b["data"].get("series") or {}
            series_txt = (f" [series: {series['series_title']} #{series.get('book_number')}]"
                          if series.get("series_title") else "")
            lines.append(
                f"  - {b['catalog_number']} \"{b['title']}\" — {ms.get('kind','?')}, "
                f"{ms.get('word_count',0):,} words, status {b['status']}, "
                f"manuscript {ms.get('status','?')}{series_txt}, "
                f"pen name {b['data'].get('author_name') or 'unset'}"
            )
            interior = b["data"].get("interior") or {}
            if interior.get("page_count"):
                v = (interior.get("validation") or {}).get("passed")
                lines.append(f"      interior: {interior['page_count']} pages, "
                             f"KDP validation {'passed' if v else 'FAILED'}")
            cover = b["data"].get("cover") or {}
            if cover.get("status") and cover["status"] != "none":
                lines.append(f"      cover: {cover['status']}")
            audio = b["data"].get("audio") or {}
            if audio.get("status") and audio["status"] != "none":
                lines.append(f"      audiobook: {audio['status']}")
    except Exception as e:
        lines.append(f"(catalog unavailable: {e})")

    try:
        active = list_jobs(active_only=True)
        if active:
            lines.append("RUNNING NOW:")
            for j in active:
                lines.append(f"  - {j['kind']} on {j.get('book_catalog') or '—'}: "
                             f"{j.get('detail') or j.get('stage')} ({round((j.get('progress') or 0)*100)}%)")
        else:
            lines.append("RUNNING NOW: nothing — the production line is idle.")
    except Exception:
        pass

    try:
        from ..reports.importer import summary
        totals = summary().get("totals") or {}
        if totals.get("royalty"):
            lines.append(
                f"ROYALTIES (lifetime, imported reports): ${totals['royalty']:.2f} "
                f"across {totals.get('titles', 0)} earning titles, "
                f"{int(totals.get('units') or 0)} units, "
                f"{int(totals.get('kenp_pages') or 0)} KENP pages.")
        else:
            lines.append("ROYALTIES: no KDP reports imported yet.")
    except Exception:
        pass

    return "\n".join(lines)


SYSTEM_PROMPT = """You are the Assistant of SCRPT, an AI publishing house — you sit in the \
front office as its head of production. You speak with quiet professional confidence: \
concise, warm, direct. Publishing language, never corporate filler.

You are spoken aloud, so keep answers short — two or three sentences unless asked for \
detail. Lead with the answer, never with a preamble. "SCRPT" is pronounced "Script": \
never spell it out letter by letter.

You are a full partner in this business, not a help desk. Talk about anything the \
publisher raises — market strategy, series planning, pricing, competitors, ads, \
cover trends, contracts, craft, what other publishers are doing, or something with \
nothing to do with books at all. Bring your own judgement and your own opinions. \
When the publisher asks "how many books should the series be" or "what sells right \
now", answer with a real recommendation and the reasoning behind it, not a list of \
considerations. Have a view. Argue for it. Disagree when you think they are wrong: \
your value is being the sharpest person in the room, not the most agreeable.

You can SEARCH THE WEB. Use it whenever current fact beats memory — comparable \
series and how long they run, what is charting in a genre, current KDP or Amazon \
Ads mechanics, what a competitor is charging, reader complaints in reviews. Do it \
without being asked and without announcing it; just come back with the finding and \
say where it came from. Never tell the publisher you cannot research something — \
you can. If a search comes back thin, say what you found and what you would infer, \
then move on.

Your job is to make this house smarter and more profitable. Volunteer the thing they \
did not think to ask: a gap in the catalog, a series that should be longer, a price \
that is wrong, a genre worth entering.

You know the house's live state (below). Give real numbers from the context when asked.

What the user can do in SCRPT (guide them to the right place, you cannot press buttons \
yourself): commission books via New Work Order (fiction/non-fiction, series supported); \
review plot directions and chapters in a book's workspace on the Bookshelf; edit and \
typeset in the Formatting Studio (true-to-print pages, exports KDP-validated PDF); \
generate the cover designer package or upload a finished cover; narrate audiobooks \
(ElevenLabs); import KDP royalty reports in Analytics. Uploads to KDP itself are manual \
by design — 3 titles/day cap and Amazon's AI-disclosure requirement apply.

KDP ECONOMICS (authoritative — use these, not memory; always say whether you mean \
print or ebook): Paperback royalty = 60% of list price minus printing cost when list \
is at or above $9.99 US, 50% minus printing below that. US B&W printing cost: flat \
$2.30 up to about 110 pages, then $1.00 plus 1.2 cents per page. Ebook royalty: 70% \
of list minus a small delivery fee when priced $2.99 to $9.99, otherwise 35%. Kindle \
Unlimited pays roughly $0.004 to $0.0045 per KENP page read (about 212 words per \
page); a fully-read novel of 60,000 words earns about $1.15 to $1.45 per borrow.

Keep replies short enough to be spoken aloud — two to four sentences unless the user \
asks for detail or the question genuinely needs the working shown. Never use markdown, \
bullets, or emoji: plain spoken prose.

LIVE STATE:
{context}"""


# ── chat ─────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str          # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


# A conversation is not a manuscript: the assistant answers on a fast model,
# so a spoken reply starts in well under a second instead of five. The
# writing models stay where they belong — on the books.
ASSISTANT_MODEL_DEFAULT = "claude-haiku-4-5"

# The assistant researches for real: Anthropic runs the search server-side,
# so it can check what a series like this one actually runs to, what a genre
# is charging, what reviewers are complaining about — live, mid-conversation.
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 6}


def assistant_model() -> str:
    return db.get_setting("assistant_model", "") or ASSISTANT_MODEL_DEFAULT


@router.post("/chat")
async def chat(req: ChatRequest):
    if not req.messages:
        raise HTTPException(400, "No messages")
    messages = [{"role": m.role, "content": m.content}
                for m in req.messages[-16:] if m.role in ("user", "assistant")]
    system = SYSTEM_PROMPT.format(context=build_context())
    from ..writing.client import client as _client
    resp = await _client().messages.create(
        model=assistant_model(), max_tokens=1600, system=system,
        messages=messages, tools=[WEB_SEARCH_TOOL])
    reply = "".join(b.text for b in resp.content if b.type == "text")
    return {"reply": reply.strip()}


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """The reply as it is written, sentence by sentence, so the voice can
    start speaking the first sentence while the rest is still being thought.
    Server-sent events: {"delta": "..."} then {"sentence": "..."} then
    {"done": "<full reply>"}."""
    if not req.messages:
        raise HTTPException(400, "No messages")
    messages = [{"role": m.role, "content": m.content}
                for m in req.messages[-16:] if m.role in ("user", "assistant")]
    system = SYSTEM_PROMPT.format(context=build_context())
    model = assistant_model()

    async def events():
        from ..writing.client import client as _client
        import json as _json
        full, pending = "", ""
        try:
            async with _client().messages.stream(
                    model=model, max_tokens=1600, system=system, messages=messages,
                    tools=[WEB_SEARCH_TOOL]) as stream:
                async for delta in stream.text_stream:
                    full += delta
                    pending += delta
                    yield f"data: {_json.dumps({'delta': delta})}\n\n"
                    # hand whole sentences to the voice as soon as they close
                    while True:
                        m = re.search(r"[.!?…](?=\s|$)", pending)
                        if not m:
                            break
                        cut = m.end()
                        sentence = pending[:cut].strip()
                        pending = pending[cut:]
                        if len(sentence) > 1:
                            yield f"data: {_json.dumps({'sentence': sentence})}\n\n"
            tail = pending.strip()
            if tail:
                yield f"data: {_json.dumps({'sentence': tail})}\n\n"
            yield f"data: {_json.dumps({'done': full.strip()})}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'error': str(e)[:300]})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── voice out (ElevenLabs) ───────────────────────────────────────

class SpeakRequest(BaseModel):
    text: str
    voice_id: str = ""          # set only to audition a voice in Settings


@router.get("/voice-options")
async def voice_options():
    """The house shortlist for the assistant's voice, plus what's chosen."""
    current = (db.get_setting("assistant_voice_id", "")
               or db.get_setting("elevenlabs_voice_id", "")
               or DEFAULT_VOICE)
    return {"voices": ASSISTANT_VOICES, "current": current, "default": DEFAULT_VOICE}


class VoiceChoice(BaseModel):
    voice_id: str


@router.post("/voice")
async def set_voice(req: VoiceChoice):
    if not req.voice_id.strip():
        raise HTTPException(400, "No voice")
    db.set_setting("assistant_voice_id", req.voice_id.strip())
    return {"ok": True, "voice_id": req.voice_id.strip()}


def say_it_right(text: str) -> str:
    """House pronunciation for the speech engine. SCRPT is said "Script",
    never spelled out — the letters would be read S-C-R-P-T aloud."""
    return re.sub(r"\bSCRPT\b", "Script", text)


@router.post("/speak")
async def speak(req: SpeakRequest):
    key = elevenlabs_key()
    if not key:
        raise HTTPException(424, "No ElevenLabs key configured")
    voice = (req.voice_id.strip()
             or db.get_setting("assistant_voice_id", "")
             or db.get_setting("elevenlabs_voice_id", "")
             or DEFAULT_VOICE)
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream"
            "?output_format=mp3_44100_128&optimize_streaming_latency=3",
            headers={"xi-api-key": key},
            json={"text": say_it_right(req.text)[:2500],
                  "model_id": db.get_setting("elevenlabs_model_id", "eleven_multilingual_v2"),
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75,
                                     "style": 0.3, "use_speaker_boost": True}},
            timeout=60,
        )
    if r.status_code != 200:
        raise HTTPException(502, f"ElevenLabs error {r.status_code}: {r.text[:200]}")
    return Response(content=r.content, media_type="audio/mpeg")


@router.get("/voices")
async def voices():
    key = elevenlabs_key()
    if not key:
        return {"voices": [], "configured": False}
    async with httpx.AsyncClient() as client:
        r = await client.get("https://api.elevenlabs.io/v1/voices",
                             headers={"xi-api-key": key}, timeout=20)
    if r.status_code != 200:
        return {"voices": [], "configured": False}
    data = r.json()
    return {"configured": True, "voices": [
        {"id": v["voice_id"], "name": v["name"], "category": v.get("category", "")}
        for v in data.get("voices", [])
    ]}


# ── voice in (faster-whisper) ────────────────────────────────────

_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


@router.post("/listen")
async def listen(file: UploadFile = File(...)):
    try:
        model = _get_whisper()
    except ImportError:
        raise HTTPException(501, "Speech-to-text not available (faster-whisper missing)")
    audio = await file.read()
    if len(audio) < 1000:
        return {"text": ""}
    try:
        segments, _info = model.transcribe(io.BytesIO(audio), language=None,
                                           vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        return {"text": text}
    except Exception as e:
        raise HTTPException(422, f"Could not transcribe: {e}")
