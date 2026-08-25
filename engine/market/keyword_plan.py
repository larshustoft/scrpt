"""
The keyword plan: SCRPT's seven KDP slots, chosen from what readers search.

Three layers, in order:
  1. DATA        Amazon autosuggest (demand, in Amazon's own ranking) and
                 search-result counts (competition) across the Books and
                 Kindle stores — engine/market/keywords.py.
  2. COMPLIANCE  Nothing KDP forbids: other authors/series/brands, program
                 names, sales claims, format words, false claims ("large
                 print"). Also no words already in the title/subtitle
                 (KDP indexes those anyway — a slot spent there is wasted).
  3. TRUTH       A fast model reads the book's blurb and keeps only phrases
                 that honestly describe THIS book — a searched phrase that
                 misdescribes the book buys clicks and returns, not sales.

The result is stored on the book (`keyword_research`) with every candidate,
its numbers, and why it was kept or dropped — so the choice is auditable —
and optionally applied to the seven slots.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Optional

from ..database import get_book_by_catalog, update_book
from ..prose.models import GENRE_PRESETS
from ..writing.client import complete, extract_json, mechanical_model, set_model_override
from .keywords import research, kdp_slots, BOOKS_ALIAS, KINDLE_ALIAS
from .launch_gate import BANNED_KEYWORD_TERMS

FORMAT_WORDS = {"book", "books", "ebook", "ebooks", "kindle", "paperback", "paperbacks",
                "hardcover", "audiobook", "print", "sets", "set", "boxset", "anthology",
                "collection", "new", "releases", "2024", "2025", "2026"}

GENRE_SEEDS = {
    "historical_romance": ["regency romance", "historical romance", "regency romance series",
                           "historical romance series", "regency romance enemies to lovers",
                           "slow burn historical romance", "victorian romance"],
    "romance": ["romance novels", "romance series", "enemies to lovers romance", "slow burn romance"],
    "action_thriller": ["action thriller", "thriller series", "action adventure thriller",
                        "survival thriller", "conspiracy thriller", "suspense thriller"],
    "thriller": ["thriller", "thriller series", "suspense thriller", "psychological thriller"],
}


def _seeds(d: dict) -> list[str]:
    genre = d.get("genre_preset") or ""
    seeds = []
    for key, lst in GENRE_SEEDS.items():
        if key in genre:
            seeds += lst
            break
    if not seeds:
        label = (GENRE_PRESETS.get(genre) or {}).get("label") or genre.replace("_", " ")
        seeds = [label.lower(), f"{label.lower()} series"]
    # the book's own existing phrases, scrubbed, as extra seeds
    for k in (d.get("keywords") or [])[:4]:
        k = k.lower().strip()
        if k and not any(b in k for b in BANNED_KEYWORD_TERMS) and k not in seeds:
            seeds.append(k)
    return seeds[:9]


def _compliant(phrase: str, title_words: set) -> Optional[str]:
    p = phrase.lower().strip()
    if any(b in p for b in BANNED_KEYWORD_TERMS):
        return "banned term"
    words = p.split()
    if any(w in FORMAT_WORDS for w in words):
        return "format word"
    if len(p) > 50:
        return "over 50 chars"
    if all(w in title_words for w in words):
        return "already in title"
    return None


async def keyword_plan(catalog: str, apply: bool = False) -> dict:
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = book["data"]
    title_words = set(re.findall(r"[a-z']+", (book["title"] + " " + (d.get("subtitle") or "")).lower()))
    seeds = _seeds(d)

    # 0. seed discovery — what would a reader of THIS book type? tropes,
    #    setting, character types, mood. Researched against real data next.
    blurb0 = (d.get("description") or d.get("back_cover_blurb") or "")[:1500]
    bible0 = (d.get("manuscript") or {}).get("story_bible") or {}
    try:
        set_model_override(mechanical_model())
        raw = await complete(
            "You know exactly how romance and thriller readers search Amazon.",
            f"TITLE: {book['title']}\nGENRE: {d.get('genre_preset')}\n"
            f"LOGLINE: {bible0.get('logline','')}\nBLURB:\n{blurb0}\n\n"
            "List 10 short search phrases (2-5 words, lower case) a shopper "
            "would type on Amazon to find a book like this: tropes, setting, "
            "era, character types, mood. No author names, no other books or "
            "brands, no format words (book, kindle, paperback). "
            'Return JSON: {"seeds": ["...", ...]}',
            max_tokens=400)
        extra = [x.lower().strip() for x in (extract_json(raw) or {}).get("seeds", []) if isinstance(x, str)]
        for x in extra:
            if x and x not in seeds and not any(b in x for b in BANNED_KEYWORD_TERMS):
                seeds.append(x)
    except Exception:
        pass
    finally:
        set_model_override(None)
    seeds = seeds[:16]

    # 1. data — both stores
    rows: dict[str, dict] = {}
    for seed in seeds:
        for alias in (BOOKS_ALIAS, KINDLE_ALIAS):
            try:
                r = await research(seed, alias=alias, top_n=14)
            except Exception:
                continue
            for k in r.get("keywords", []):
                ph = k["phrase"].lower().strip()
                cur = rows.get(ph)
                if not cur or (k.get("opportunity") or 0) > (cur.get("opportunity") or 0):
                    rows[ph] = {**k, "phrase": ph, "store": alias, "seed": seed}
    candidates = sorted(rows.values(), key=lambda x: -(x.get("opportunity") or 0))

    # 2. compliance
    kept, dropped = [], []
    for c in candidates:
        why = _compliant(c["phrase"], title_words)
        if why:
            dropped.append({**c, "dropped": why})
        else:
            kept.append(c)
    kept = kept[:45]

    # 3. truth — only phrases that honestly describe this book
    blurb = (d.get("description") or d.get("back_cover_blurb") or "")[:1500]
    bible = (d.get("manuscript") or {}).get("story_bible") or {}
    brief = (f"TITLE: {book['title']}\nGENRE: {d.get('genre_preset')}\n"
             f"LOGLINE: {bible.get('logline','')}\nTHEMES: {', '.join(bible.get('themes') or [])}\n"
             f"BLURB:\n{blurb}")
    truthful = kept
    if kept:
        prompt = (
            f"{brief}\n\nCANDIDATE SEARCH PHRASES (what Amazon shoppers type):\n"
            + "\n".join(f"- {c['phrase']}" for c in kept)
            + "\n\nKeep ONLY phrases that honestly describe THIS book — its genre, "
              "era, tropes, tone, setting, series-ness. Drop anything that names "
              "a person, another book or brand, a trope the book does not have, "
              "or a sub-genre it is not. Return JSON: {\"keep\": [\"phrase\", ...]}"
        )
        try:
            set_model_override(mechanical_model())
            raw = await complete("You are a meticulous bookseller who refuses to mislabel a book.",
                                 prompt, max_tokens=800)
            keep = {p.lower().strip() for p in (extract_json(raw) or {}).get("keep", [])}
            truthful = [c for c in kept if c["phrase"] in keep]
            for c in kept:
                if c["phrase"] not in keep:
                    dropped.append({**c, "dropped": "does not describe this book"})
        except Exception:
            truthful = kept
        finally:
            set_model_override(None)

    chosen = kdp_slots(truthful) if truthful else []
    if isinstance(chosen, dict):
        chosen = chosen.get("slots") or chosen.get("keywords") or []
    chosen = [c if isinstance(c, str) else c.get("phrase") for c in chosen][:7]

    record = {
        "at": dt.datetime.now().isoformat(timespec="minutes"),
        "seeds": seeds,
        "chosen": chosen,
        "candidates": [{k: v for k, v in c.items() if k in ("phrase", "demand", "competing_titles", "opportunity", "store")}
                       for c in truthful[:30]],
        "dropped": [{"phrase": c["phrase"], "why": c["dropped"]} for c in dropped[:40]],
        "applied": bool(apply and chosen),
    }
    fresh = get_book_by_catalog(catalog)
    data = dict(fresh["data"])
    data["keyword_research"] = record
    if apply and chosen:
        data["keywords"] = chosen
    update_book(fresh["id"], data)
    return record
