"""
The Launch Gate — the one check a book must clear before the line moves it
toward KDP. It folds every quality signal the house has into a single
verdict with named failures, so the automatic line can never pass a weak
product forward, and the publisher sees exactly why something stalled.

Blocking = the line stops. Advisory = the line continues, the report notes it.
"""

from __future__ import annotations

import datetime as dt
import re

from ..config import OUTPUT_DIR
from ..database import get_book_by_catalog, list_books
from .preflight import check as preflight

LEAD_DAYS = 10
# program names, sales claims, and — per KDP metadata rules — other authors,
# other books/series and brands the house doesn't own
BANNED_KEYWORD_TERMS = ("kindle unlimited", "bestseller", "best seller", "free", "#1", "amazon",
                        "bridgerton", "jane austen", "austen", "julia quinn", "georgette heyer",
                        "netflix", "for fans of", "prime reading", "kindle", "audible")


def launch_gate(catalog: str) -> dict:
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    d = book["data"]
    items: list[dict] = []

    def item(name, ok, detail="", blocking=True):
        items.append({"name": name, "ok": bool(ok), "detail": detail, "blocking": blocking})

    # ── 1. metadata preflight (existing 9 checks) ──
    pf = preflight(catalog)
    for c in pf.get("checks", []):
        item(f"Metadata · {c['name']}", c["ok"], c.get("detail", ""), c.get("blocking", True))

    # ── 2. the acceptance desk ──
    acc = d.get("acceptance") or {}
    verdict = acc.get("verdict")
    item("Acceptance desk verdict", verdict == "accept",
         f"{verdict or 'not run'}" + (f" · {acc.get('score')}/10" if acc.get("score") else ""))
    rd = acc.get("readability") or {}
    if rd:
        target = rd.get("house_target", "")
        ok_read = bool(rd.get("meets_target")) if "meets_target" in rd else (
            rd.get("avg_sentence_words", 99) <= 16 and rd.get("long_sentence_share", 1) <= 0.12
            and rd.get("dialogue_paragraph_share", 0) >= 0.20)
        item("Readability (easy read, plain words)", ok_read,
             f"avg {rd.get('avg_sentence_words')} words · long {round(100*rd.get('long_sentence_share',0))}% · "
             f"dialogue {round(100*rd.get('dialogue_paragraph_share',0))}% · "
             f"hard words {round(100*rd.get('hard_word_share',0))}% (target: {target})")
    else:
        item("Readability", False, "not measured")
    cont = acc.get("continuity") or []
    item("Continuity audit", len(cont) == 0, f"{len(cont)} open issue(s)" if cont else "clean")
    length = acc.get("length") or {}
    if length:
        item("Length in commercial band", bool(length.get("ok")),
             f"{length.get('total_words', 0):,} words (band {length.get('floor', 0):,}–{length.get('ceiling', 0):,})")

    # ── 3. files and print package ──
    out = OUTPUT_DIR / catalog
    interior = d.get("interior") or {}
    item("Interior PDF validated", bool((interior.get("validation") or {}).get("passed")) and (out / "interior.pdf").exists(),
         f"{interior.get('page_count', 0)} pages" if interior else "not exported")
    wrap = ((d.get("cover") or {}).get("print_wrap") or {})
    wv = wrap.get("validation") or {}
    item("Cover wrap validated (KDP spec)", bool(wv.get("passed")) and (out / "cover-wrap.pdf").exists(),
         "; ".join(c.get("detail", "") for c in wv.get("checks", [])[:2]) if wv else "no wrap")
    item("Front cover present", (out / "cover-front.png").exists(), "", True)
    item("Ebook (EPUB) built", (out / "ebook.epub").exists(), "", False)

    # ── 4. house rules ──
    paper = d.get("paper_type") or ""
    kind = (d.get("kind") or (d.get("manuscript") or {}).get("kind") or "fiction")
    want = "cream_bw" if kind == "fiction" else "white_bw"
    item("Paper matches house rule", paper == want, f"{paper or '—'} (fiction→cream, non-fiction→white)")
    kws = [k.lower() for k in (d.get("keywords") or [])]
    bad = [k for k in kws if any(t in k for t in BANNED_KEYWORD_TERMS)]
    lp = [k for k in kws if "large print" in k]
    item("Keywords compliant", not bad and not lp,
         ("banned: " + ", ".join(bad) if bad else "") + ("; 'large print' claimed" if lp else "") or "clean")
    kr = d.get("keyword_research") or {}
    fresh_kr = False
    if kr.get("at"):
        try:
            fresh_kr = (dt.datetime.now() - dt.datetime.fromisoformat(kr["at"])).days <= 60
        except ValueError:
            fresh_kr = False
    item("Keyword research (live Amazon data)", fresh_kr and bool(kr.get("applied")),
         (f"researched {kr.get('at','')[:10]}, {'applied' if kr.get('applied') else 'NOT applied'}" if kr else "never run"))
    sub = (d.get("subtitle") or "").strip()
    item("Subtitle is cover-safe", True,
         "KDP requires the subtitle to appear on the cover — SCRPT's stored tagline usually does NOT; "
         "use the cover's descriptor line or leave blank" if sub else "none stored", False)
    price = float(d.get("list_price") or 0)
    item("Price in 60% royalty tier", price >= 9.99, f"${price:.2f}" if price else "—")

    # ── 5. launch plan ──
    rel = d.get("release") or {}
    today = dt.date.today()
    if rel.get("date"):
        try:
            rd_ = dt.date.fromisoformat(rel["date"])
            item("Release date set ≥ 10 days out", (rd_ - today).days >= LEAD_DAYS or rel.get("status") == "released",
                 rel["date"])
        except ValueError:
            item("Release date set ≥ 10 days out", False, "invalid date")
    else:
        item("Release date set ≥ 10 days out", False, "no date — run the planner")
    series = d.get("series") or {}
    if series.get("series_title") and int(series.get("book_number") or 1) > 1:
        prev_ok = False
        prev_detail = "previous book not found"
        for b in list_books(per_page=500).get("books", []):
            s2 = (b.get("data") or {}).get("series") or {}
            if s2.get("series_title") == series["series_title"] and int(s2.get("book_number") or 0) == int(series["book_number"]) - 1:
                pr = (b.get("data") or {}).get("release") or {}
                pub = (b.get("data") or {}).get("publishing") or {}
                prev_ok = bool(pub.get("asin") or pr.get("date") and rel.get("date") and pr["date"] <= rel["date"])
                prev_detail = f"#{int(series['book_number'])-1} {'released' if pub.get('asin') else 'planned ' + str(pr.get('date'))}"
                break
        item("Series order respected", prev_ok, prev_detail)
    item("Trailer produced", (out / "trailer.mp4").exists(), "", False)
    ai = (d.get("kdp") or {}).get("ai_disclosure")
    item("AI disclosure prepared", True, "house default: Yes · texts extensive editing (Claude) · images one-or-few (GPT Image)", False)

    blocking = [i for i in items if i["blocking"] and not i["ok"]]
    advisory = [i for i in items if not i["blocking"] and not i["ok"]]
    return {
        "catalog": catalog, "title": book["title"],
        "ready": not blocking,
        "blocking_failures": [i["name"] for i in blocking],
        "advisories": [i["name"] for i in advisory],
        "checks": items,
        "release_date": rel.get("date"),
    }


def line_status() -> dict:
    """Every title's gate verdict — the factory line at a glance."""
    rows = []
    for b in list_books(per_page=500).get("books", []):
        d = b.get("data") or {}
        if (d.get("publishing") or {}).get("asin") or d.get("external"):
            rows.append({"catalog": b["catalog_number"], "title": b["title"], "stage": "live", "ready": True,
                         "blocking_failures": [], "release_date": (d.get("release") or {}).get("date")})
            continue
        try:
            g = launch_gate(b["catalog_number"])
        except Exception as e:
            rows.append({"catalog": b["catalog_number"], "title": b["title"], "stage": "error", "ready": False,
                         "blocking_failures": [str(e)[:80]], "release_date": None})
            continue
        ms = d.get("manuscript") or {}
        chapters = ms.get("chapters") or []
        written = bool(chapters) and all(c.get("blocks") for c in chapters)
        stage = ("gate passed" if g["ready"] else
                 "packaging" if written and (d.get("acceptance") or {}).get("verdict") == "accept" else
                 "acceptance" if written else "writing")
        rows.append({"catalog": b["catalog_number"], "title": b["title"], "stage": stage, "ready": g["ready"],
                     "blocking_failures": g["blocking_failures"], "release_date": g["release_date"]})
    return {"line": rows}

def assert_publishable(catalog: str) -> None:
    """A book marked never_publish is a test or an internal project: it must
    never reach Amazon, whatever calls in — the line, the scheduler, autopilot
    or a stray endpoint. Raising here is the last gate before KDP."""
    from ..database import get_book_by_catalog
    b = get_book_by_catalog(catalog)
    if b and (b["data"] or {}).get("never_publish"):
        reason = (b["data"] or {}).get("never_publish_reason") or "marked never-publish"
        raise RuntimeError(f"{catalog} is marked never-publish ({reason}) — refusing to send it to KDP")
