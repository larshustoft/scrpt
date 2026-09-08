"""SUGGESTED BOOKS — the acquisitions desk (Lars, 2026-09-08: "a 'suggested
book' section in SCRPT where you do research on the market, and suggest books
SCRPT can create. I just have to okay them, one by one or in bulk, and they
get produced and uploaded").

research()   reads the market (live web search on top of the house's standing
             market memo and its own shelf) and writes N concrete, ready-to-
             commission suggestions: title, series, genre, pitch, evidence,
             comparables, prices, a calibrated monthly range.
approve()    turns a suggestion into a work order with auto_draft on: the
             writing pipeline takes it (market check → bible → outline →
             chapters → blurb, covers in parallel), the reader's desk readies
             it, the release desk dates and uploads it. Nothing else to do.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from ..database import get_connection, get_setting, list_books
from ..config import PROJECT_ROOT as _PR
PROJECT_ROOT_UNIVERSE = _PR / "universe"
from ..prose.models import GENRE_PRESETS, CHILDRENS_PRESETS

# what the 5 September 2026 research established (live Amazon ranks + Circana +
# K-lytics + Written Word Media); refreshed by each research run's web search
MARKET_MEMO = """
STANDING MARKET MEMO (2026-09-05, live Amazon ranks read that day):
- Kindle rank → units/day (BookBloom Nov-2025 formula): #68 ≈1,200/day, #195 ≈520, #859 ≈165, #1,483 ≈88, #2,852 ≈53, #4,591 ≈37, #38,825 ≈7.
- Cozy mystery (Kindle): 8 of the top 30 are indie series at book 12–38, $4.99–5.99, 218–314 pages; #20 in category = Kindle #1,483. Witch/paranormal, bookshop/library, travel and K-9 cozies own the chart. Best factory fit: long series, one book every 4–6 weeks, all in Kindle Unlimited.
- Sports/hockey romance: #20 in category = Kindle #195 (≈520/day), #80 ≈100/day; TV adaptation lifting the shelf; voice-driven, winners have 50k–200k ratings. Tropes on the chart: small town, grumpy-sunshine, fake dating, single dad, rivals-to-lovers; 300–350 pages.
- Children's activity/learning books (paperback): self-published titles at #153 (Scissor Skills, $3.99) and #210 (How to Draw Anything, $12.99) in ALL of Books; the segment grew +18% in 2025 and +18% again through May 2026 while total print fell 3.1%. Themed (unicorns, farm, dinosaurs, vehicles, space) faces ~1/10 the competition of generic. B&W interiors 60–100 pages, 8.5x11, $7.99–9.99.
- Psychological/domestic thriller: an indie standalone at Kindle #79 (≈1,050/day); suspense rank 34 ≈1,000/day.
- Seasonal romance: a 21-rating title was #3 in Romantic Comedy on 5 Sep (Always Be My Pumpkin); holiday titles by early November chart for small names.
- Music-business non-fiction: dead (every 2026 AI-music KDP title ranks #600k–1M). Avoid: YA (print −28.7%), self-help (−26.3%), generic low-content, romantasy (100k-word worlds vs BookTok names), erotica shorts (policy/brand risk).
- Written Word Media: 44% of authors over $10k/month write romance; cozy and paranormal romance over-index among high earners. KU page rate ≈ $0.0048.
"""


def _init():
    conn = get_connection()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS suggestions (
            id TEXT PRIMARY KEY, created_at TEXT, status TEXT, data JSON, catalog TEXT, decided_at TEXT, note TEXT)""")
        conn.commit()
    finally:
        conn.close()


def _rows(status: str | None = None) -> list[dict]:
    _init()
    conn = get_connection()
    try:
        q = "SELECT id, created_at, status, data, catalog, decided_at, note FROM suggestions"
        args: tuple = ()
        if status:
            q += " WHERE status = ?"; args = (status,)
        q += " ORDER BY created_at DESC"
        out = []
        for r in conn.execute(q, args).fetchall():
            d = json.loads(r[3]) if isinstance(r[3], str) else (r[3] or {})
            out.append({"id": r[0], "created_at": r[1], "status": r[2], **d, "catalog": r[4], "decided_at": r[5], "note": r[6]})
        return out
    finally:
        conn.close()


def list_suggestions() -> dict:
    rows = [r for r in _rows() if r["status"] != "drafting"]
    return {"suggestions": rows, "open": sum(1 for r in rows if r["status"] == "new"),
            "last_research": get_setting("suggest_last_research", "") or ""}


def _shelf_brief() -> str:
    books = list_books(per_page=500).get("books", [])
    lines = []
    for b in books:
        d = b.get("data") or {}
        if not d.get("manuscript") and not d.get("childrens"):
            continue
        s = d.get("series") or {}
        lines.append(f"- {b.get('title')} · {d.get('genre_preset') or d.get('kind')} · {d.get('author_name') or ''}"
                     + (f" · {s.get('series_title')} #{s.get('book_number')}" if s.get("series_title") else "")
                     + (" · LIVE" if (d.get("publishing") or {}).get("asin") else ""))
    return "\n".join(lines[:60])


async def research(n: int = 8, notes: str = "") -> dict:
    """Write n new suggestions. Uses live web search on top of the memo."""
    from ..writing.client import complete, extract_json
    _init()
    existing = _rows()
    taken = [f"{r.get('title')} ({r.get('series_title') or 'standalone'}) — {r['status']}" for r in existing[:60]]
    presets = {k: v.get("label") for k, v in GENRE_PRESETS.items()}
    kids = {k: v.get("label") for k, v in CHILDRENS_PRESETS.items()}
    prompt = (
        f"{MARKET_MEMO}\n\nTHE HOUSE'S SHELF TODAY:\n{_shelf_brief()}\n\n"
        f"ALREADY SUGGESTED (do not repeat):\n" + ("\n".join(taken) or "none") + "\n\n"
        + (f"PUBLISHER'S NOTES: {notes}\n\n" if notes else "")
        + "You are the acquisitions editor of an automated publishing house that writes, edits, designs and uploads books "
        "to Amazon KDP by itself (fiction to ~100k words, non-fiction, and illustrated children's books incl. activity "
        "books). Web-search the live Amazon market now to confirm or update the memo (bestseller lists, what indie "
        "titles at #20–#100 in a category look like, prices, page counts, what is trending this month), then propose "
        f"{n} SPECIFIC books the house should produce next. Favour series with read-through, KU-native genres, "
        "growing print segments, and seasonal timing (it is early September). Vary pen names sensibly (one pen name "
        "per genre; reuse the house's existing pen names where the genre matches). Every suggestion must be concrete "
        "enough to commission today. NEVER use the pen name 'Lily Tiger' (it is a real name); invent or reuse other pen names.\n\n"
        f"Fiction/non-fiction genre presets (use exactly one key): {json.dumps(presets)}\n"
        f"Children's presets: {json.dumps(kids)}\n\n"
        "Return JSON only: {\"suggestions\": [{"
        "\"title\": \"...\", \"kind\": \"fiction|nonfiction|childrens\", \"genre_preset\": \"key\", "
        "\"series_title\": \"... or empty\", \"series_books\": N, \"pen_name\": \"...\", "
        "\"pitch\": \"2-3 sentences: the book, the hook, the reader\", "
        "\"why\": \"the market evidence in numbers (ranks, units/day, growth, prices)\", "
        "\"comparables\": [\"title by author (rank/price)\", ...], "
        "\"target_words\": N, \"price_kindle\": 4.99, \"price_paperback\": 12.99, "
        "\"cover_direction\": \"one sentence for the cover artist\", "
        "\"estimate_monthly_usd\": {\"conservative\": N, \"realistic\": N, \"stretch\": N}  "
        "(CALIBRATED for a NEW pen name with no readers, no reviews and a $5/day ad test — conservative = what most such "
        "books earn (often $0-50), realistic = the median outcome after 3 books are live (typically $100-800 for a "
        "series in KU, $30-300 for a standalone), stretch = a top-decile outcome, not the chart leader's income; "
        "never quote the comparable's own earnings as the estimate), "
        "\"confidence\": \"low|medium|high\", \"season\": \"e.g. holiday 2026 or evergreen\"}]}"
    )
    raw = await complete("You are a data-driven acquisitions editor. Numbers over adjectives. JSON only.",
                         prompt, max_tokens=9000, web_search=8, mechanical=True)
    out = extract_json(raw) or {}
    items = out.get("suggestions") if isinstance(out, dict) else out
    if not isinstance(items, list):
        raise RuntimeError(f"research returned no list: {str(out)[:200]}")
    conn = get_connection(); added = []
    try:
        for it in items[:n]:
            if not isinstance(it, dict) or not it.get("title"):
                continue
            gp = it.get("genre_preset")
            if gp not in GENRE_PRESETS and gp not in CHILDRENS_PRESETS:
                it["genre_preset"] = "picture_book" if it.get("kind") == "childrens" else ("self_help" if it.get("kind") == "nonfiction" else "romance")
            if "lily tiger" in str(it.get("pen_name") or "").lower():
                it["pen_name"] = "Poppy Marsh"
            it["kind"] = "childrens" if it["genre_preset"] in CHILDRENS_PRESETS else ("nonfiction" if GENRE_PRESETS.get(it["genre_preset"], {}).get("kind") == "nonfiction" else "fiction")
            # the web-search model leaves <cite> tags in its prose: strip them everywhere
            import re as _re
            def _clean(v):
                if isinstance(v, str):
                    return _re.sub(r"\s+", " ", _re.sub(r"</?cite[^>]*>", "", v)).strip()
                if isinstance(v, list):
                    return [_clean(x) for x in v]
                if isinstance(v, dict):
                    return {k: _clean(x) for k, x in v.items()}
                return v
            it = _clean(it)
            # "Series: Book One – Title" is a label, not a title
            t = str(it.get("title") or "").strip(); st_ = str(it.get("series_title") or "").strip()
            for sep in (" – ", " — ", ": Book One - ", " - "):
                if sep in t and (t.lower().startswith(st_.lower()) if st_ else "book one" in t.lower()):
                    t = t.split(sep, 1)[1].strip(); break
            it["title"] = t
            sid = uuid.uuid4().hex[:10]
            conn.execute("INSERT INTO suggestions (id, created_at, status, data) VALUES (?,?,?,?)",
                         (sid, datetime.now().isoformat(timespec="minutes"), "drafting", json.dumps(it)))
            added.append({"id": sid, **it})
        conn.commit()
    finally:
        conn.close()
    from ..database import set_setting
    set_setting("suggest_last_research", datetime.now().isoformat(timespec="minutes"))
    # NO SUGGESTION WITHOUT ITS COVER (Lars, 2026-09-08): a suggestion is shown
    # only once its front cover exists; until then it stays 'drafting', unseen.
    cv = await covers([a["id"] for a in added])
    conn = get_connection()
    try:
        for sid in cv.get("done", []):
            conn.execute("UPDATE suggestions SET status='new' WHERE id=? AND status='drafting'", (sid,))
        conn.commit()
    finally:
        conn.close()
    return {"added": added, "count": len(cv.get("done", [])), "without_cover": cv.get("failed", [])}


async def approve(ids: list[str], commission_all: bool = False) -> dict:
    """Approved suggestions become work orders with auto_draft on."""
    from ..routers.scrpt import create_workorder
    from ..prose.models import WorkOrderRequest, BookKind
    _init()
    rows = {r["id"]: r for r in _rows()}
    results = []
    conn = get_connection()
    try:
        for sid in ids:
            r = rows.get(sid)
            if not r or r["status"] != "new":
                results.append({"id": sid, "ok": False, "reason": "not an open suggestion"}); continue
            if (r.get("line") == "workbook") or (r.get("kind") == "childrens" and any(w in (r.get("title") or "").lower() for w in ("workbook", "cut and paste", "draw with", "trace", "activity"))):
                try:
                    cat, job_id = _commission_workbook(r)
                    conn.execute("UPDATE suggestions SET status='approved', catalog=?, decided_at=? WHERE id=?",
                                 (cat, datetime.now().isoformat(timespec="minutes"), sid))
                    results.append({"id": sid, "ok": True, "catalog": cat, "job_id": job_id, "line": "workbook"})
                except Exception as e:
                    results.append({"id": sid, "ok": False, "reason": str(e)[:200]})
                continue
            kind = BookKind(r.get("kind") or "fiction")
            series_title = (r.get("series_title") or "").strip()
            n_books = int(r.get("series_books") or 1) if series_title else 1
            idea = (f"{r.get('pitch') or ''}\n\nMARKET EVIDENCE: {r.get('why') or ''}\n\nCOMPARABLES: "
                    f"{', '.join(r.get('comparables') or [])}")
            if r.get("publisher_notes"):
                idea += f"\n\nPUBLISHER'S INSTRUCTIONS (binding): {r['publisher_notes']}"
            req = WorkOrderRequest(
                kind=kind, genre_preset=r["genre_preset"], idea=idea, title=r.get("title") or "",
                pen_name=r.get("pen_name") or "", series_title=series_title, series_books=max(1, n_books),
                commission_books=(0 if commission_all else 1), cover_direction=r.get("cover_direction") or "",
                target_words=int(r["target_words"]) if r.get("target_words") else None,
                generate_plot_options=False, auto_draft=True)
            try:
                res = await create_workorder(req)
                cat = (res.get("books") or [{}])[0].get("catalog_number")
                # the suggested prices ride along to the release desk
                from ..database import get_book_by_catalog, update_book
                b = get_book_by_catalog(cat)
                if b:
                    d = dict(b["data"]); d["list_price"] = float(r.get("price_paperback") or d.get("list_price") or 12.99)
                    d["ebook_price"] = float(r.get("price_kindle") or 4.99); d["suggestion_id"] = sid; update_book(b["id"], d)
                conn.execute("UPDATE suggestions SET status='approved', catalog=?, decided_at=? WHERE id=?",
                             (cat, datetime.now().isoformat(timespec="minutes"), sid))
                results.append({"id": sid, "ok": True, "catalog": cat, "job_id": res.get("job_id")})
            except Exception as e:
                results.append({"id": sid, "ok": False, "reason": str(e)[:200]})
        conn.commit()
    finally:
        conn.close()
    return {"results": results}


def reject(ids: list[str], note: str = "") -> dict:
    _init()
    conn = get_connection()
    try:
        for sid in ids:
            conn.execute("UPDATE suggestions SET status='rejected', decided_at=?, note=? WHERE id=? AND status='new'",
                         (datetime.now().isoformat(timespec="minutes"), note[:300], sid))
        conn.commit()
    finally:
        conn.close()
    return {"rejected": ids}


# ── covers: see the book before it exists ─────────────────────────────
COVER_DIR_NAME = "suggestions"


def cover_path(sid: str):
    from ..config import OUTPUT_DIR
    return OUTPUT_DIR / COVER_DIR_NAME / f"{sid}.png"


def _cover_brief(r: dict) -> str:
    """The house's proven shape: a flat front cover, the story for the ARTWORK
    only, the title and the author as the only text. One angle, no lists —
    the image engine is the designer (feedback_cover_prompts_simple)."""
    label = (GENRE_PRESETS.get(r.get("genre_preset"), {}) or CHILDRENS_PRESETS.get(r.get("genre_preset"), {})).get("label", "book")
    title = str(r.get("title") or "").strip(); author = str(r.get("pen_name") or "").strip()
    about = " ".join(str(r.get("pitch") or "").split())[:500]
    direction = " ".join(str(r.get("cover_direction") or "").split())[:200]
    kids = r.get("kind") == "childrens"
    lines = [
        f"Create a paperback front book cover for a {label.lower()} called: {title}",
        f"What the book is about (for the ARTWORK only — do not write any of this on the cover): {about}",
        (f"Direction: {direction}" if direction else ""),
        f'The ONLY text anywhere on the cover is the title "{title}"' + (f' and the author name "{author}"' if author else "") + ". No blurb, no tagline, no sentences.",
        "Output the FLAT COVER ARTWORK ITSELF — one flat rectangle filled edge to edge, exactly as it would be printed. "
        "Not a photograph of a book, not a 3D mockup, no spine, no shadow, no desk, no hands.",
        "It must look like a bestseller in its category on Amazon today: professional typography, a single strong image, "
        "the title readable at thumbnail size." + (" Bright, friendly, child-safe illustration." if kids else ""),
        f"Author: {author}" if author else "",
        "Book size: " + ("8.5″ × 11″" if kids else "5.5″ × 8.5″"),
    ]
    return "\n".join(l for l in lines if l)


async def covers(ids: list[str], handle=None) -> dict:
    """One high-quality front cover per suggestion, saved under output/suggestions/."""
    import httpx
    from ..cover.front_cover import _generate_one
    _init()
    rows = {r["id"]: r for r in _rows()}
    import asyncio
    from ..writing.workbook import UNIVERSE_CAST, _plate_png
    done, failed = [], []
    sem = asyncio.Semaphore(3)
    async with httpx.AsyncClient() as client:
        async def one(i, sid):
            r = rows.get(sid)
            if not r:
                failed.append((sid, "unknown")); return
            async with sem:
                if handle:
                    handle.progress(0.05 + 0.9 * i / max(1, len(ids)), "cover", f"Designing: {r.get('title')}")
                try:
                    brief = _cover_brief(r)
                    plate = None
                    uni = UNIVERSE_CAST.get(r.get("universe") or "", {})
                    if uni:
                        brief += (f"\nThe characters: {uni['look']} {uni.get('cast', '')} The attached pictures are the "
                                  "references, in this order: Princess, Glitter, Pip, Moss — friendly full-colour cartoon style.")
                        plate = [png for png in (_plate_png(r["universe"], rel) for rel in (uni.get("plates") or {}).values()) if png] or None
                    png = await _generate_one(client, brief, reference_png=plate, gen_size="1024x1536")
                    pth = cover_path(sid); pth.parent.mkdir(parents=True, exist_ok=True); pth.write_bytes(png)
                    d = {k: v for k, v in r.items() if k not in ("id", "created_at", "status", "catalog", "decided_at", "note")}
                    d["cover"] = str(pth); d["cover_at"] = datetime.now().isoformat(timespec="minutes")
                    conn = get_connection()
                    try:
                        conn.execute("UPDATE suggestions SET data=? WHERE id=?", (json.dumps(d), sid)); conn.commit()
                    finally:
                        conn.close()
                    done.append(sid)
                except Exception as e:
                    failed.append((sid, str(e)[:120]))
        await asyncio.gather(*[one(i, sid) for i, sid in enumerate(ids)])
    return {"done": done, "failed": failed}


def _commission_workbook(r: dict) -> tuple[str, str]:
    """A workbook is born as a book record with a page plan to come, joins its
    universe, and the workbook line draws it at once."""
    from ..database import create_book
    from ..jobs import start_job
    from ..writing.workbook import write_workbook, UNIVERSE_CAST
    slug = r.get("universe") or ""
    uni = UNIVERSE_CAST.get(slug, {})
    series_title = (r.get("series_title") or "").strip()
    data = {
        "kind": "childrens", "book_type": "workbook", "authorship": "house", "genre_preset": "picture_book",
        "author_name": r.get("pen_name") or uni.get("author") or "", "universe": slug or None, "print_only": True,
        "trim_size": "8.5x11", "paper_type": "white_bw", "page_count": 0,
        "list_price": float(r.get("price_paperback") or 8.99),
        "description": (r.get("pitch") or ""), "cover_direction": r.get("cover_direction") or "",
        "workbook": {"universe": slug, "pitch": (r.get("pitch") or "") + (f" PUBLISHER'S INSTRUCTIONS (binding): {r['publisher_notes']}" if r.get("publisher_notes") else ""), "ages": "3-5" if "letters" in (r.get("title") or "").lower() or "cut" in (r.get("title") or "").lower() else "4-8",
                      "pages_target": 48, "suggestion_id": r.get("id")},
        "manuscript": {"kind": "childrens", "genre_preset": "picture_book", "idea": r.get("pitch") or "", "status": "idea", "chapters": []},
        "interior": {}, "cover": {}, "audio": {}, "suggestion_id": r.get("id"),
        "series": {"series_id": uuid.uuid4().hex[:8], "series_title": series_title, "book_number": 1,
                   "total_planned": int(r.get("series_books") or 1)} if series_title else {},
    }
    book = create_book(r.get("title") or "Untitled workbook", data)
    cat = book["catalog_number"]
    if slug:
        try:
            pp = PROJECT_ROOT_UNIVERSE / slug / "profile.json"
            pj = json.loads(pp.read_text()); mem = pj.setdefault("members", [])
            if cat not in mem:
                mem.append(cat); pp.write_text(json.dumps(pj, indent=1, ensure_ascii=False))
        except Exception:
            pass
    job_id = start_job("workbook", lambda h, c=cat: write_workbook(c, h), book_catalog=cat)
    return cat, job_id


def set_notes(sid: str, notes: str) -> dict:
    """The publisher's instructions for the finished book, kept on the
    suggestion and carried into the work order when it is approved."""
    _init()
    conn = get_connection()
    try:
        row = conn.execute("SELECT data FROM suggestions WHERE id=?", (sid,)).fetchone()
        if not row:
            raise ValueError("unknown suggestion")
        d = json.loads(row[0]); d["publisher_notes"] = str(notes or "")[:4000]
        conn.execute("UPDATE suggestions SET data=? WHERE id=?", (json.dumps(d), sid)); conn.commit()
        return {"id": sid, "publisher_notes": d["publisher_notes"]}
    finally:
        conn.close()
