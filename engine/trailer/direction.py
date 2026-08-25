"""
The director's chair: SCRPT makes the directorial choices itself.

Before a trailer is written or shot, the director reads the book and
decides — per book, not per genre — the look and feel (palette, light,
lens, camera grammar), the rhythm (shot count, average cut), the narrator
(register, then a real casting from the voice bank), the score (instru-
mentation, tempo, build) and the sound design (the hits, or none). The
genre recipes in producer.py remain the fallback when no brief exists.

The brief lives on the book as `trailer.direction`; a narrator the
publisher cast by hand is never overruled (`trailer.voice.auto` is false).
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx

from ..database import get_book_by_catalog, get_setting, update_book
from ..prose.models import Manuscript
from ..writing.client import complete, extract_json, mechanical_model, set_model_override


def _plot(ms: Manuscript) -> str:
    return "\n".join(f"  Ch{c.index}: {c.outline_summary}" for c in ms.chapters if c.outline_summary)[:3000]


async def write_direction(catalog: str) -> dict:
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = book["data"]
    ms = Manuscript.model_validate(d.get("manuscript") or {})
    b = ms.story_bible
    from .reference import reference_block
    ref = reference_block(d)
    prompt = (
        f"{ref}\nBOOK: \"{book['title']}\"\nGENRE: {d.get('genre_preset','')}\n"
        f"LOGLINE: {getattr(b,'logline','')}\nSETTING: {getattr(b,'setting','')} ({getattr(b,'time_period','')})\n"
        f"TONE: {getattr(b,'tone','')}\nTHEMES: {', '.join(getattr(b,'themes',[]) or [])}\n"
        f"BACK COVER COPY:\n{d.get('back_cover_blurb') or ms.blurb or ''}\n"
        f"PLOT:\n{_plot(ms)}\n\n"
        "You are directing this book's trailer for a theatrical-grade campaign. "
        "Make every directorial choice yourself, specific to THIS story — not a "
        "genre template. Decide:\n"
        "- LOOK: palette, light, lens and film-stock feel, camera grammar "
        "(how the camera moves), weather and time of day that recur. One "
        "paragraph the video model can obey, 50-80 words, concrete.\n"
        "- RHYTHM: total length in seconds (25-45), number of shots (4-10), "
        "how the cut accelerates or holds.\n"
        "- VOICE: the narrator's register — gender, age range, accent, "
        "texture, pace, attitude — and a 3-6 word search query for a voice "
        "library (e.g. 'deep calm british male narrator').\n"
        "- MUSIC: instrumentation, tempo, how it builds, the emotion; 30-60 "
        "words. No band or composer names.\n"
        "- SOUND DESIGN: an opening sound, a per-cut hit (or null if this "
        "trailer should breathe without hits), and a reveal sound for the "
        "final cover card — each as a 10-20 word sound-effect prompt.\n"
        "- END CARD: its mood in a few words.\n"
        'Return JSON only: {"angle": "one line — the trailer\'s idea", '
        '"look": "...", "seconds": 30, "shots": 6, "pacing": "...", '
        '"voice": {"register": "...", "query": "..."}, "music": "...", '
        '"sound": {"intro": "...", "cut_hit": "..." or null, "reveal": "..."}, '
        '"end_card": "..."}'
    )
    raw = await complete(
        "You are an award-winning trailer director. Your choices are specific, "
        "restrained and commercial: they sell the book without explaining it.",
        prompt, max_tokens=1500)
    direction = extract_json(raw) or {}
    direction["at"] = dt.datetime.now().isoformat(timespec="minutes")
    fresh = get_book_by_catalog(catalog)
    data = dict(fresh["data"])
    tr = dict(data.get("trailer") or {})
    tr["direction"] = direction
    data["trailer"] = tr
    update_book(fresh["id"], data)
    return direction


async def _bank(api_key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": api_key})
    if r.status_code != 200:
        return []
    out = []
    for v in r.json().get("voices", []):
        labels = v.get("labels") or {}
        out.append({"id": v["voice_id"], "name": v["name"],
                    "desc": (v.get("description") or "")[:160],
                    "labels": ", ".join(f"{k}: {val}" for k, val in labels.items())})
    return out


async def _library(api_key: str, query: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get("https://api.elevenlabs.io/v1/shared-voices",
                        params={"search": query, "page_size": 12, "use_cases": "narrative_story"},
                        headers={"xi-api-key": api_key})
    if r.status_code != 200:
        return []
    out = []
    for v in r.json().get("voices", []):
        out.append({"id": v["voice_id"], "name": v["name"], "owner": v.get("public_owner_id"),
                    "desc": (v.get("description") or "")[:160],
                    "labels": f"gender: {v.get('gender')}, age: {v.get('age')}, accent: {v.get('accent')}, "
                              f"use: {v.get('use_case')}, uses: {v.get('cloned_by_count')}"})
    return out


async def cast_narrator(catalog: str, direction: dict) -> Optional[dict]:
    """Cast the narrator to the brief: the bank first, the library if the
    bank has no fit. A hand-cast voice is never replaced."""
    book = get_book_by_catalog(catalog)
    d = book["data"]
    current = (d.get("trailer") or {}).get("voice") or {}
    if current.get("id") and current.get("auto") is False:
        return current
    api_key = get_setting("elevenlabs_api_key", "")
    if not api_key:
        return None
    register = (direction.get("voice") or {}).get("register") or ""
    query = (direction.get("voice") or {}).get("query") or "cinematic narrator"
    bank = await _bank(api_key)
    library = await _library(api_key, query)
    pool = [{**v, "source": "bank"} for v in bank] + [{**v, "source": "library"} for v in library]
    if not pool:
        return None
    listing = "\n".join(f"[{i}] {v['name']} ({v['source']}) — {v['labels']} — {v['desc']}" for i, v in enumerate(pool))
    pick = None
    try:
        set_model_override(mechanical_model())
        raw = await complete(
            "You are a casting director for film trailers.",
            f"NARRATOR WANTED: {register}\n\nCANDIDATES:\n{listing}\n\n"
            "Pick the single best fit for a cinematic book-trailer read. Prefer "
            "voices described as narrator/cinematic/trailer over conversational "
            "ones; prefer the bank when two are equal. "
            'Return JSON: {"index": N, "why": "one line"}', max_tokens=120)
        j = extract_json(raw) or {}
        pick = pool[int(j.get("index"))]
        pick["why"] = j.get("why", "")
    except Exception:
        pick = next((v for v in pool if v["source"] == "bank"), pool[0])
    finally:
        set_model_override(None)
    voice_id = pick["id"]
    if pick["source"] == "library":
        # hire it into the bank so recordings can use it
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(f"https://api.elevenlabs.io/v1/voices/add/{pick['owner']}/{pick['id']}",
                                 json={"new_name": pick["name"]}, headers={"xi-api-key": api_key})
            if r.status_code == 200:
                voice_id = r.json().get("voice_id") or voice_id
            else:
                fallback = next((v for v in pool if v["source"] == "bank"), None)
                if fallback:
                    pick, voice_id = fallback, fallback["id"]
        except Exception:
            pass
    cast = {"id": voice_id, "name": pick["name"], "auto": True,
            "why": pick.get("why", ""), "register": register}
    fresh = get_book_by_catalog(catalog)
    data = dict(fresh["data"])
    tr = dict(data.get("trailer") or {})
    tr["voice"] = cast
    data["trailer"] = tr
    update_book(fresh["id"], data)
    return cast


def direction_block(d: dict) -> str:
    """What the script writer reads: the director's choices as rules."""
    dr = (d.get("trailer") or {}).get("direction") or {}
    if not dr:
        return ""
    return (
        f"\nDIRECTOR'S BRIEF (obey it):\nAngle: {dr.get('angle','')}\n"
        f"Look: {dr.get('look','')}\nRhythm: {dr.get('seconds')}s, {dr.get('shots')} shots — {dr.get('pacing','')}\n"
        f"Voice register: {(dr.get('voice') or {}).get('register','')}\nMusic: {dr.get('music','')}\n"
        f"End card: {dr.get('end_card','')}\n"
    )
