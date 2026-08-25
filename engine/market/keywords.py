"""
Keyword & category research — SCRPT's Publisher Rocket.

Two real data sources, no guessing:
  1. Amazon's own autosuggest (what shoppers actually type, ranked by Amazon)
  2. Amazon search result pages (how many books compete for that phrase, and
     what the top sellers charge)

Score model, plainly: DEMAND is how prominently and how often Amazon suggests a
phrase; COMPETITION is how many titles chase it. OPPORTUNITY rewards phrases
readers search for and few books target — the ones worth putting in the seven
KDP keyword slots and in the title/subtitle.
"""

import asyncio
import json
import re
import string
import urllib.parse
from typing import Iterable, Optional

import httpx

SUGGEST_URL = "https://completion.amazon.com/api/2017/suggestions"
KINDLE_ALIAS = "digital-text"
BOOKS_ALIAS = "stripbooks"
AUDIBLE_ALIAS = "audible"


async def suggest(prefix: str, alias: str = KINDLE_ALIAS,
                  limit: int = 11) -> list[str]:
    """Amazon's live autosuggest for a prefix, in search-store `alias`."""
    params = {
        "session-id": "000-0000000-0000000", "customer-id": "",
        "request-id": "SCRPT", "page-type": "Search", "lop": "en_US",
        "site-variant": "desktop", "client-info": "amazon-search-ui",
        "mid": "ATVPDKIKX0DER", "alias": alias, "b2b": "0", "fresh": "0",
        "ks": "76", "prefix": prefix, "event": "onKeyPress",
        "limit": str(limit), "fb": "1", "suggestion-type": "KEYWORD",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(SUGGEST_URL, params=params,
                             headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except ValueError:
        return []
    return [s.get("value", "") for s in data.get("suggestions", []) if s.get("value")]


async def expand(seed: str, alias: str = KINDLE_ALIAS,
                 depth_letters: bool = True) -> dict[str, float]:
    """Mine the suggestion tree around a seed.

    Returns {phrase: demand_score}. Demand rewards a phrase that Amazon offers
    early (high in the list) and offers again for several different prefixes —
    exactly the signal a shopper's own typing produces.
    """
    prefixes = [seed]
    if depth_letters:
        prefixes += [f"{seed} {c}" for c in string.ascii_lowercase]
    scores: dict[str, float] = {}
    sem = asyncio.Semaphore(6)   # be a polite client

    async def one(p: str):
        async with sem:
            for i, phrase in enumerate(await suggest(p, alias)):
                phrase = phrase.strip().lower()
                if not phrase or phrase == seed.lower():
                    continue
                # position 0 is Amazon's strongest suggestion for that prefix
                scores[phrase] = scores.get(phrase, 0.0) + (11 - min(i, 10)) / 11

    await asyncio.gather(*(one(p) for p in prefixes))
    return scores


_COUNT_RE = re.compile(r"(?:over\s+)?([\d,]+)\s*results", re.I)
_PRICE_RE = re.compile(r"\$(\d+\.\d{2})")


async def competition(phrase: str, alias: str = KINDLE_ALIAS) -> dict:
    """How crowded is this phrase, and what do the leaders look like?"""
    from .browser import Page
    url = ("https://www.amazon.com/s?" + urllib.parse.urlencode(
        {"k": phrase, "i": alias}))
    out = {"phrase": phrase, "competing_titles": None, "avg_price": None,
           "top_titles": []}
    try:
        async with Page() as page:
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            html = await page.content()
            m = _COUNT_RE.search(html)
            if m:
                out["competing_titles"] = int(m.group(1).replace(",", ""))
            try:
                titles = await page.locator(
                    "div[data-component-type='s-search-result'] h2").all_inner_texts()
                out["top_titles"] = [t.strip() for t in titles[:10] if t.strip()]
            except Exception:
                pass
            prices = [float(x) for x in _PRICE_RE.findall(html)[:40]]
            ebook_prices = [p for p in prices if 0.99 <= p <= 24.99]
            if ebook_prices:
                out["avg_price"] = round(sum(ebook_prices) / len(ebook_prices), 2)
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


def opportunity(demand: float, competing: Optional[int]) -> float:
    """0-100. High demand against few competing titles scores highest."""
    if competing is None:
        return round(min(100.0, demand * 12), 1)
    # log-ish compression: 1k competitors is crowded, 50k is a wall
    import math
    crowd = math.log10(max(competing, 10))          # 1 .. ~5.7
    raw = (demand * 12) / max(crowd - 1.0, 0.35)    # reward thin niches
    return round(max(0.0, min(100.0, raw)), 1)


async def research(seed: str, alias: str = KINDLE_ALIAS, top_n: int = 25,
                   check_competition: int = 12, on_progress=None) -> dict:
    """Full keyword study for a niche: mine, rank, then measure the leaders."""
    if on_progress:
        on_progress(0.1, f"Mining what readers type around \"{seed}\"")
    demand = await expand(seed, alias)
    ranked = sorted(demand.items(), key=lambda kv: -kv[1])[:top_n]

    if on_progress:
        on_progress(0.45, f"Sizing the competition for {min(check_competition, len(ranked))} phrases")
    checked: dict[str, dict] = {}
    sem = asyncio.Semaphore(3)

    async def measure(p: str):
        async with sem:
            checked[p] = await competition(p, alias)

    await asyncio.gather(*(measure(p) for p, _ in ranked[:check_competition]))

    rows = []
    for phrase, d in ranked:
        comp = checked.get(phrase, {})
        rows.append({
            "phrase": phrase,
            "demand": round(d, 2),
            "competing_titles": comp.get("competing_titles"),
            "avg_price": comp.get("avg_price"),
            "opportunity": opportunity(d, comp.get("competing_titles")),
            "top_titles": comp.get("top_titles", [])[:3],
        })
    rows.sort(key=lambda r: -r["opportunity"])
    if on_progress:
        on_progress(1.0, "Keyword study complete")
    return {"seed": seed, "store": alias, "keywords": rows}


def kdp_slots(rows: list[dict], max_chars: int = 50,
              paid_book: bool = True) -> list[str]:
    """Pack the best phrases into KDP's seven 50-character keyword slots.

    Amazon indexes every word in the boxes, so slots earn their place by
    covering NEW search ground. For a paid book, "free ..." phrases are
    dropped: they pull shoppers hunting for freebies, who do not convert.
    """
    BAD = ("free",) if paid_book else ()
    pool = [r for r in rows
            if len(r["phrase"]) <= max_chars
            and not any(b in r["phrase"].split() for b in BAD)]

    slots: list[str] = []
    used: set[str] = set()

    def take(row, require_new: int):
        words = set(row["phrase"].split())
        if len(words - used) < require_new:
            return False
        slots.append(row["phrase"])
        used.update(words)
        return True

    # pass 1: every slot must add at least two unseen words
    for r in pool:
        if len(slots) >= 7:
            break
        take(r, 2)
    # pass 2: relax to one new word, then to anything, until seven are filled
    for require in (1, 0):
        for r in pool:
            if len(slots) >= 7:
                break
            if r["phrase"] in slots:
                continue
            take(r, require)
    return slots[:7]
