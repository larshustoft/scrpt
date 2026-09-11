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
import re
from pathlib import Path
import uuid
from datetime import datetime

from ..database import get_connection, get_setting, list_books
from ..config import OUTPUT_DIR, PROJECT_ROOT as _PR
PROJECT_ROOT_UNIVERSE = _PR / "universe"
from ..prose.models import GENRE_PRESETS, CHILDRENS_PRESETS

# what the 5 September 2026 research established (live Amazon ranks + Circana +
# K-lytics + Written Word Media); refreshed by each research run's web search
BANNED_PEN_NAMES = {"lily tiger"}
HOUSE_PEN_NAMES = {"princess-the-unicorn": "Poppy Marsh", "freddie-the-farmer": "Hattie Meadows", "rex-the-dinosaur": "Bennie Clay"}


def _pen_name_for(kind) -> str:
    import random
    firsts = ["Clara", "Nell", "Josie", "Wren", "Harriet", "Tessa", "Ada", "Iris", "Rowan", "Elliot", "Sam", "Jude"]
    lasts = ["Ashby", "Marlow", "Fenwick", "Hale", "Whitlock", "Calder", "Pryor", "Lindqvist", "Sorrell", "Blythe"]
    return f"{random.choice(firsts)} {random.choice(lasts)}"

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



LENSES = [
    "what parents buy in the run-up to Christmas", "gift books and boxed-set bait", "what is rising this month, not what is established",
    "under-served readers: boys 6-9, grandparents, ESL adults, teens who hate reading", "non-fiction a person buys to solve one problem this week",
    "formats: journals, planners, puzzle books, workbooks, large print", "sub-genres with fewer than 2,000 competing titles",
    "seasonal: autumn, Halloween, back-to-school, winter holidays", "series fiction in genres the house has never touched",
    "learning books by subject and age: reading, maths, science, geography, history",
]


def _explored_niches() -> list:
    """Every niche phrase the house has measured or built a suggestion on."""
    out = []
    try:
        conn = get_connection()
        for (seed,) in conn.execute("SELECT seed FROM niche_data ORDER BY measured_at DESC LIMIT 60").fetchall():
            out.append(seed)
    except Exception:
        pass
    for r in _rows()[:120]:
        n = (r.get("niche") or "").strip().lower()
        if n and n not in out:
            out.append(n)
    return out[:80]


def _used_cover_concepts() -> str:
    seen = []
    for r in _rows()[:40]:
        cd = " ".join(str(r.get("cover_direction") or "").split())[:110]
        if cd:
            seen.append(f"- {cd}")
    return "\n".join(seen[:30]) or "none"


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


class _Scaled:
    """A job handle whose 0..1 progress is mapped into [lo, hi] of the parent's."""
    def __init__(self, handle, lo: float, hi: float):
        self.h, self.lo, self.hi = handle, lo, hi
    def progress(self, fraction: float, stage: str = "", detail: str = ""):
        if self.h:
            self.h.progress(self.lo + (self.hi - self.lo) * max(0.0, min(1.0, fraction)), stage, detail)
    def cancelled(self) -> bool:
        return bool(self.h and self.h.cancelled())


async def research(n: int = 8, notes: str = "", handle=None) -> dict:
    """Write n new suggestions. Uses live web search on top of the memo.
    Progress: reading the market fills 0.05→0.3, the covers 0.3→0.97."""
    from ..writing.client import complete, extract_json
    _init()
    if handle:
        handle.progress(0.05, "research", "Reading the market")
    existing = _rows()
    taken = [f"{r.get('title')} ({r.get('series_title') or 'standalone'}) — {r['status']}" for r in existing[:60]]
    presets = {k: v.get("label") for k, v in GENRE_PRESETS.items()}
    kids = {k: v.get("label") for k, v in CHILDRENS_PRESETS.items()}
    # ── THE MEASURED MARKET (Lars, 2026-09-09: "books that sell... the same
    # method Bookbeam is using"). First the editor names candidate niches as
    # Amazon search phrases; each is MEASURED on the live store (first-page
    # titles, BSR per book, sales curve); only measured niches can be proposed.
    from .niche import measure_many, brief as niche_brief
    from ..writing.client import utility_model
    # EVERY ROUND LOOKED THE SAME (Lars, 2026-09-11): the editor named the
    # same eight phrases from the same memo each time and the measurement
    # step silently failed, so the memo alone drove every round. Now the
    # explored niches and earlier premises are on the table as "not these",
    # a rotating lens changes the angle of attack, and the measurement runs.
    explored = _explored_niches()
    import random as _rnd
    lens = _rnd.choice(LENSES)
    cand_raw = await complete(
        "You are a data-driven acquisitions editor. JSON only.",
        f"{MARKET_MEMO}\n\nTHE HOUSE'S SHELF TODAY:\n{_shelf_brief()}\n\n"
        f"NICHES ALREADY EXPLORED (name DIFFERENT ones — at most two of your eight may be from this list):\n{', '.join(explored) or 'none'}\n\n"
        f"THIS ROUND'S LENS: {lens}\n\n"
        + (f"PUBLISHER'S NOTES: {notes}\n\n" if notes else "")
        + "Name 8 niches worth measuring on Amazon right now for a house that can produce fiction series, non-fiction and "
        "children's picture/activity books — each as the exact phrase a buyer types into the Amazon Books search box "
        "(e.g. 'cozy mystery series', 'hockey romance', 'unicorn activity book for kids', 'dinosaur coloring book ages 4-8'). "
        "Eight DIFFERENT genres or audiences — never two phrases in the same genre. Include at least two children's niches "
        "and at least two series-fiction niches, and at least three niches the house has never touched. "
        "Return JSON only: {\"niches\": [\"phrase\", ...]}", max_tokens=600, mechanical=True, model=utility_model())
    cand = (extract_json(cand_raw) or {}).get("niches") or []
    cand = [str(c).strip() for c in cand if str(c).strip()][:8]
    if handle:
        handle.progress(0.08, "measuring", f"Measuring {len(cand)} niches on Amazon")
    measured = {}
    for i, seed in enumerate(cand):
        try:
            measured[seed] = (await measure_many([seed]))[seed]
        except Exception as e:
            measured[seed] = {"seed": seed, "error": str(e)[:100]}
        if handle:
            handle.progress(0.08 + 0.17 * (i + 1) / max(1, len(cand)), "measuring", f"Measured: {seed}")
    prompt = (
        f"{MARKET_MEMO}\n\n{niche_brief(measured)}\n\nTHE HOUSE'S SHELF TODAY:\n{_shelf_brief()}\n\n"
        f"ALREADY SUGGESTED (do not repeat these titles, premises, settings or hooks):\n" + ("\n".join(taken) or "none") + "\n\n"
        f"COVER CONCEPTS ALREADY USED (every new cover_direction must differ in subject, composition AND palette):\n{_used_cover_concepts()}\n\n"
        f"THIS ROUND'S LENS: {lens}\n\n"
        + (f"PUBLISHER'S NOTES: {notes}\n\n" if notes else "")
        + "RULES OF THE ROUND: no two proposals share a genre preset; at least half the proposals sit in genres the house "
        "has not suggested before; a series continuation for an existing universe or series is allowed only once per round. "
        "You are the acquisitions editor of an automated publishing house that writes, edits, designs and uploads books "
        "to Amazon KDP by itself (fiction to ~100k words, non-fiction, and illustrated children's books incl. activity "
        "books). Web-search the live Amazon market now to confirm or update the memo (bestseller lists, what indie "
        "titles at #20–#100 in a category look like, prices, page counts, what is trending this month), then propose "
        f"{n} SPECIFIC books the house should produce next, EACH INSIDE ONE OF THE MEASURED NICHES ABOVE (name it in "
        "\"niche\"); a niche that measured badly (few units, or hundreds of thousands of competing titles) is not proposed. "
        "Favour series with read-through, KU-native genres, "
        "growing print segments, and seasonal timing (it is early September). Vary pen names sensibly (one pen name "
        "per genre; reuse the house's existing pen names where the genre matches). Every suggestion must be concrete "
        "enough to commission today. NEVER use the pen name 'Lily Tiger' (it is a real name); invent or reuse other pen names.\n\n"
        f"Fiction/non-fiction genre presets (use exactly one key): {json.dumps(presets)}\n"
        f"Children's presets: {json.dumps(kids)}\n\n"
        "Return JSON only: {\"suggestions\": [{"
        "\"title\": \"...\", \"niche\": \"the measured niche phrase\", \"kind\": \"fiction|nonfiction|childrens\", \"line\": \"story|workbook (workbook = any activity, colouring, tracing, maze, counting or drawing book: 8.5x11 pages drawn one by one)\", \"genre_preset\": \"key\", "
        "\"series_title\": \"... or empty\", \"series_books\": N, \"pen_name\": \"...\", "
        "\"pitch\": \"2-3 sentences: the book, the hook, the reader\", "
        "\"why\": \"the market evidence in numbers (ranks, units/day, growth, prices)\", "
        "\"comparables\": [\"title by author (rank/price)\", ...], "
        "\"target_words\": N, \"price_kindle\": 4.99, \"price_paperback\": 12.99, "
        "\"cover_direction\": \"one sentence for the cover artist\", "
        "\"estimate_monthly_usd\": {\"conservative\": N, \"realistic\": N, \"stretch\": N}  "
        "(DERIVED FROM THE MEASURED NICHE: the new-title units/month (cons/real/stretch) × the book's royalty per unit "
        "(Kindle ≈ 70% of price; paperback ≈ 60% of price minus ~$3 print) — show the arithmetic in \"why\"; "
        "CALIBRATED for a NEW pen name with no readers, no reviews and a $5/day ad test — conservative = what most such "
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
            # the measured evidence rides on the suggestion, so the card shows numbers read off Amazon
            nd = measured.get(str(it.get("niche") or "")) or next((v for k, v in measured.items() if k.lower() in str(it.get("niche") or "").lower()), None)
            if nd and not nd.get("error"):
                it["niche_data"] = {k: nd.get(k) for k in ("seed", "competing_titles", "measured", "units_month_top", "median_units_month",
                                                           "avg_price", "revenue_month_top", "new_book_units_month", "measured_at")}
                it["niche_data"]["leaders"] = [{"title": x["title"], "bsr": x["bsr"], "price": x["price"]} for x in nd.get("top", [])[:3] if x.get("bsr")]
            from ..writing.workbook import detect_universe
            it["universe"] = it.get("universe") or detect_universe(it.get("title"), it.get("pitch"), it.get("series_title"))
            if it["universe"] and HOUSE_PEN_NAMES.get(it["universe"]):
                it["pen_name"] = HOUSE_PEN_NAMES[it["universe"]]
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
    if handle:
        handle.progress(0.3, "covers", f"Designing {len(added)} covers")
    cv = await covers([a["id"] for a in added], handle=_Scaled(handle, 0.3, 0.97) if handle else None)
    conn = get_connection()
    try:
        for sid in cv.get("done", []):
            conn.execute("UPDATE suggestions SET status='new' WHERE id=? AND status='drafting'", (sid,))
        conn.commit()
    finally:
        conn.close()
    return {"added": added, "count": len(cv.get("done", [])), "without_cover": cv.get("failed", [])}



WORKBOOK_WORDS = re.compile(r"activity|workbook|colou?ring|maze|dot[ -]to[ -]dot|trac(e|ing)|cut (and|&) paste|draw with|how to draw|"
                            r"sticker|puzzle|count(ing)?\b|count to|letters|numbers|alphabet|\babc\b|shapes|handwriting|learn to|"
                            r"practi[cs]e|(&|and) play\b|tell the time|opposites|first words", re.I)


def _is_workbook_suggestion(r: dict) -> bool:
    """Activity books are the workbook line — 8.5x11, drawn page by page —
    never the square picture-book path (Lars, 2026-09-10: "the workbooks/
    activity books come up in square format… this has happened a couple of
    times"). The line is declared by research when it can be, and read off
    the title and pitch otherwise."""
    if (r.get("line") or "") == "workbook" or (r.get("book_type") or "") == "workbook":
        return True
    if (r.get("line") or "") == "story":
        return False
    if (r.get("kind") or "") != "childrens":
        return False
    return bool(WORKBOOK_WORDS.search((r.get("title") or "") + " " + (r.get("pitch") or "")[:200]))


def _series_titles(series_title: str) -> str:
    from ..database import list_books
    out = []
    for b in list_books(per_page=1000).get("books", []):
        sr = (b.get("data") or {}).get("series") or {}
        if b.get("status") not in ("cancelled", "deleted", "archived") and (sr.get("series_title") or "").strip().lower() == series_title.strip().lower():
            out.append(f"#{sr.get('book_number')} {b.get('title')}")
    return "; ".join(sorted(out)) or "none"


def _universe_workbook_titles(slug: str) -> str:
    from ..database import list_books
    out = []
    for b in list_books(per_page=1000).get("books", []):
        d = b.get("data") or {}
        if b.get("status") in ("cancelled", "deleted", "archived"):
            continue
        if ((d.get("workbook") or {}).get("universe") or d.get("universe")) == slug and ((d.get("book_type") or "") == "workbook" or (d.get("workbook") or {})):
            out.append(str(b.get("title")))
    return "; ".join(sorted(set(out))) or "none"


def _series_offset(series_title: str) -> tuple[int, str]:
    """Books already in a series of that name: (highest number, series_id) —
    a new batch continues the numbering instead of starting a second book 1
    (Princess the Unicorn Activity Books had 1-6 when 7 more were approved)."""
    from ..database import list_books
    hi, sid = 0, ""
    for b in list_books(per_page=1000).get("books", []):
        if b.get("status") in ("cancelled", "deleted", "archived"):
            continue
        sr = (b.get("data") or {}).get("series") or {}
        if (sr.get("series_title") or "").strip().lower() == series_title.strip().lower() and sr.get("book_number"):
            if int(sr["book_number"]) > hi:
                hi, sid = int(sr["book_number"]), sr.get("series_id") or sid
    return hi, sid


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
            if _is_workbook_suggestion(r):
                try:
                    n_wb = int(r.get("series_books") or 1) if (r.get("series_title") or "").strip() else 1
                    if commission_all and n_wb > 1:
                        cat, job_id = await _commission_workbook_series(r, n_wb)
                    else:
                        cat, job_id = _commission_workbook(r)
                    conn.execute("UPDATE suggestions SET status='approved', catalog=?, decided_at=? WHERE id=?",
                                 (cat, datetime.now().isoformat(timespec="minutes"), sid))
                    results.append({"id": sid, "ok": True, "catalog": cat, "job_id": job_id, "line": "workbook"})
                except Exception as e:
                    results.append({"id": sid, "ok": False, "reason": str(e)[:200]})
                continue
            kind = BookKind(r.get("kind") or "fiction")
            series_title = (r.get("series_title") or "").strip()
            pen = (r.get("pen_name") or "").strip()
            if pen.lower() in BANNED_PEN_NAMES:          # never Lily Tiger on a suggested book (Lars, 2026-09-08)
                pen = HOUSE_PEN_NAMES.get(r.get("universe") or "", "") or _pen_name_for(kind)
                r["pen_name"] = pen
            sug_cover = Path(OUTPUT_DIR) / "suggestions" / f"{sid}.png"
            n_books = int(r.get("series_books") or 1) if series_title else 1
            idea = (f"{r.get('pitch') or ''}\n\nMARKET EVIDENCE: {r.get('why') or ''}\n\nCOMPARABLES: "
                    f"{', '.join(r.get('comparables') or [])}")
            if r.get("publisher_notes"):
                idea += f"\n\nPUBLISHER'S INSTRUCTIONS (binding): {r['publisher_notes']}"
            req = WorkOrderRequest(
                kind=kind, genre_preset=r["genre_preset"], idea=idea, title=r.get("title") or "",
                pen_name=pen, series_title=series_title, series_books=max(1, n_books),
                commission_books=(0 if commission_all else 1), cover_direction=r.get("cover_direction") or "",
                covers_uploaded=([1] if sug_cover.exists() else []),   # the approved cover IS the cover: no variants job
                target_words=int(r["target_words"]) if r.get("target_words") else None,
                generate_plot_options=False, auto_draft=True)
            try:
                res = await create_workorder(req)
                cat = (res.get("books") or [{}])[0].get("catalog_number")
                # the cover Lars approved goes onto the book the moment it exists,
                # so the shelf shows the book he said yes to (2026-09-08)
                if cat and sug_cover.exists():
                    try:
                        from ..cover.front_cover import _install_cover
                        _install_cover(cat, sug_cover.read_bytes(), brief=f"Approved on the Suggested Books page. Direction: {r.get('cover_direction') or ''}")
                    except Exception as e:
                        results.append({"id": sid, "ok": True, "note": f"cover not carried over: {str(e)[:120]}"})
                # the suggested prices ride along to the release desk; a series
                # approved in full is flagged so the series line writes the
                # later books one after another ([[series_line]])
                from ..database import get_book_by_catalog, update_book
                for made in (res.get("books") or []):
                    b = get_book_by_catalog(made.get("catalog_number"))
                    if not b:
                        continue
                    d = dict(b["data"]); d["list_price"] = float(r.get("price_paperback") or d.get("list_price") or 12.99)
                    d["ebook_price"] = float(r.get("price_kindle") or 4.99); d["suggestion_id"] = sid
                    if commission_all and n_books > 1 and d.get("series"):
                        d["series"] = {**d["series"], "auto_advance": True}
                    update_book(b["id"], d)
                conn.execute("UPDATE suggestions SET status='approved', catalog=?, decided_at=? WHERE id=?",
                             (cat, datetime.now().isoformat(timespec="minutes"), sid))
                results.append({"id": sid, "ok": True, "catalog": cat, "job_id": res.get("job_id"),
                                "scope": "series" if (commission_all and n_books > 1) else "first",
                                "books": len(res.get("books") or [])})
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
        "NOT like these, which are already on the shelf — a different subject, composition and palette from every one of them: "
        + "; ".join(x.lstrip("- ") for x in _used_cover_concepts().split("\n")[:12] if x and x != "none"),
    ]
    return "\n".join(l for l in lines if l)


async def covers(ids: list[str], handle=None) -> dict:
    """One high-quality front cover per suggestion, saved under output/suggestions/."""
    import httpx
    from ..cover.front_cover import _generate_one
    _init()
    rows = {r["id"]: r for r in _rows()}
    import asyncio
    from ..writing.workbook import UNIVERSE_CAST, UNIVERSE_DISPLAY, _plate_png
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
                    from ..writing.workbook import detect_universe
                    slug = r.get("universe") or detect_universe(r.get("title"), r.get("pitch"), r.get("series_title"))
                    if slug and not r.get("universe"):
                        r["universe"] = slug
                    uni = UNIVERSE_CAST.get(slug, {})
                    if uni:
                        names = list((uni.get("plates") or {}).keys())
                        lead = names[0] if names else ""
                        brief += (f"\nThis book belongs to the {UNIVERSE_DISPLAY.get(slug, slug)} universe. {lead.upper()} IS THE LEAD: "
                                  f"large, front and centre, the first thing seen, exactly as in the reference. The characters: {uni['look']} "
                                  f"{uni.get('cast', '')} The attached pictures are the references, in this order: {', '.join(names)} — "
                                  "friendly full-colour cartoon style, faithful to the references.")
                        plate = [png for png in (_plate_png(slug, rel) for rel in (uni.get("plates") or {}).values()) if png] or None
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


def _commission_workbook(r: dict, draw_now: bool = True, series_id: str = "", book_number: int = 1, total: int = 1, ages: str = "") -> tuple[str, str]:
    """A workbook is born as a book record with a page plan to come, joins its
    universe, and the workbook line draws it at once."""
    from ..database import create_book
    from ..jobs import start_job
    from ..writing.workbook import write_workbook, UNIVERSE_CAST, UNIVERSE_DISPLAY
    from ..writing.workbook import detect_universe
    slug = r.get("universe") or detect_universe(r.get("title") or "", r.get("pitch") or "", r.get("series_title") or "")
    uni = UNIVERSE_CAST.get(slug, {})
    series_title = (r.get("series_title") or "").strip()
    # a universe book carries the universe's pen name, whatever the suggestion said
    pen = HOUSE_PEN_NAMES.get(slug) or uni.get("author") or r.get("pen_name") or ""
    if series_title and not series_id:
        hi, sid = _series_offset(series_title)
        if hi:
            book_number, series_id, total = hi + book_number, sid or series_id, max(total, hi + max(total, 1))
    data = {
        "kind": "childrens", "book_type": "workbook", "authorship": "house", "genre_preset": "picture_book",
        "author_name": pen, "universe": slug or None, "print_only": True,
        "trim_size": "8.5x11", "paper_type": "white_bw", "page_count": 0,
        "list_price": max(9.99, float(r.get("price_paperback") or 9.99)),   # KDP pays 60% from $9.99, 50% below
        "description": (r.get("pitch") or ""), "cover_direction": r.get("cover_direction") or "",
        # the print tree has no default for children's activity books: plan the
        # categories at birth so the stager never lands them in General
        "kdp": {"print_categories_plan": (
            # KDP's PRINT tree (read off the picker, 2026-09-08): Activities, Crafts &
            # Games has only General / Interactive Adventures / Spies & Spying;
            # Early Learning > Basic Concepts has Alphabet, Counting, Colors, General…
            [["Children's Books", "Arts, Music & Photography", "Art", "General"],
             ["Children's Books", "Activities, Crafts & Games", "General"]]
            if "draw" in (r.get("title") or "").lower() else
            [["Children's Books", "Activities, Crafts & Games", "General"],
             ["Children's Books", "Early Learning", "Basic Concepts", "General"]])},
        "workbook": {"universe": slug, "pitch": (r.get("pitch") or "") + (f" PUBLISHER'S INSTRUCTIONS (binding): {r['publisher_notes']}" if r.get("publisher_notes") else ""), "ages": "3-5" if "letters" in (r.get("title") or "").lower() or "cut" in (r.get("title") or "").lower() else "4-8",
                      "pages_target": 48, "suggestion_id": r.get("id")},
        "manuscript": {"kind": "childrens", "genre_preset": "picture_book", "idea": r.get("pitch") or "", "status": "idea", "chapters": []},
        "interior": {}, "cover": {}, "audio": {}, "suggestion_id": r.get("id"),
        "series": {"series_id": series_id or uuid.uuid4().hex[:8], "series_title": series_title, "book_number": book_number,
                   "total_planned": max(total, int(r.get("series_books") or 1)), "auto_advance": total > 1} if series_title else {},
    }
    if ages:
        data["workbook"]["ages"] = ages
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
    if not draw_now:
        return cat, None                      # the series line draws it after the one before
    job_id = start_job("workbook", lambda h, c=cat: write_workbook(c, h), book_catalog=cat)
    return cat, job_id


async def _commission_workbook_series(r: dict, n: int) -> tuple[str, str]:
    """A series of workbooks (Lars, 2026-09-09: "a series of 10 workbooks
    teaching kids things"): the editor plans N distinct titles across the
    universe's learning pillars, every record is created with its number,
    book one is drawn now and the series line draws the rest one at a time."""
    from ..database import create_book, get_book_by_catalog, update_book
    from ..writing.client import complete, extract_json
    from ..writing.workbook import UNIVERSE_CAST, UNIVERSE_DISPLAY
    from ..writing.workbook import detect_universe
    slug = r.get("universe") or detect_universe(r.get("title") or "", r.get("pitch") or "", r.get("series_title") or "")
    r = {**r, "universe": slug}
    uni = UNIVERSE_CAST.get(slug, {})
    pillars = ""
    try:
        pj = json.loads((PROJECT_ROOT_UNIVERSE / slug / "profile.json").read_text()) if slug else {}
        pillars = ", ".join(pj.get("learning_pillars") or []); world = pj.get("world") or ""
    except Exception:
        world = ""
    raw = await complete("You plan children's activity-book series. JSON only.",
        f"UNIVERSE: {UNIVERSE_DISPLAY.get(slug, slug) or 'none'}. WORLD: {world}\nLEARNING PILLARS: {pillars or 'counting, letters, shapes, nature, feelings'}\n"
        f"CAST: {uni.get('cast', '')}\nSERIES: {r.get('series_title')}\nBOOKS ALREADY IN THIS SERIES (never repeat their topics): {_series_titles(r.get('series_title') or '')}\nOTHER WORKBOOKS ALREADY IN THIS UNIVERSE (never repeat their topics either): {_universe_workbook_titles(slug)}\nFIRST BOOK (already decided): {r.get('title')} — {r.get('pitch')}\n"
        f"AGES: 4-8. FORMAT: 8.5 x 11 black-and-white activity pages, ~48 pages each.\n\n"
        f"Plan exactly {n} books for this series, book 1 being the first book above. Each book teaches ONE thing a parent "
        "would buy it for (counting to 20, letters and sounds, shapes and patterns, colours, mazes and pencil control, "
        "cut and paste, how to draw the cast, seasons and nature, feelings, telling the time...). Titles are short, "
        "start with the character's name where natural, and never repeat a topic. Return JSON only: "
        "{\"books\": [{\"n\": 1, \"title\": \"...\", \"pitch\": \"2 sentences: what the child does, what it teaches\", \"ages\": \"4-6\"}, ...]}",
        max_tokens=3000, mechanical=True)
    plan = (extract_json(raw) or {}).get("books") or []
    plan = sorted([b for b in plan if isinstance(b, dict) and b.get("title")], key=lambda b: int(b.get("n") or 0))[:n]
    if not plan:
        plan = [{"n": 1, "title": r.get("title"), "pitch": r.get("pitch"), "ages": "4-8"}]
    plan[0]["title"] = r.get("title") or plan[0]["title"]; plan[0]["pitch"] = r.get("pitch") or plan[0]["pitch"]
    hi, sid = _series_offset(r.get("series_title") or "")
    series_id = sid or uuid.uuid4().hex[:8]
    first_cat, first_job = None, None
    for i, b in enumerate(plan, start=1):
        rr = {**r, "title": b["title"], "pitch": b.get("pitch") or r.get("pitch"), "series_books": hi + len(plan)}
        cat, job_id = _commission_workbook(rr, draw_now=(i == 1), series_id=series_id, book_number=hi + i, total=hi + len(plan), ages=b.get("ages"))
        if i == 1:
            first_cat, first_job = cat, job_id
    return first_cat, first_job


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
