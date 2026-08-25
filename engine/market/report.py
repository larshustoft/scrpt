"""
The publisher's daily report.

One page answering the four questions the controller of this business asks:
what did we write, what went out, what did we promote and at what cost, and
what did we earn.
"""

from datetime import date, timedelta

from ..database import get_connection, list_books
from .store import init as _init


def _writing_today(day: str) -> dict:
    conn = get_connection()
    try:
        jobs = conn.execute(
            "SELECT book_catalog, kind, status FROM jobs "
            "WHERE date(updated_at) = ?", (day,)).fetchall()
    finally:
        conn.close()
    books, written = [], 0
    for b in list_books(per_page=300)["books"]:
        ms = b["data"].get("manuscript") or {}
        chapters = ms.get("chapters") or []
        words = sum(c.get("word_count", 0) for c in chapters)
        drafted = sum(1 for c in chapters if c.get("blocks"))
        touched = any(j["book_catalog"] == b["catalog_number"] for j in jobs)
        if touched:
            acc = b["data"].get("acceptance") or {}
            books.append({
                "catalog": b["catalog_number"], "title": b["title"],
                "chapters": f"{drafted}/{len(chapters)}", "words": words,
                "status": ms.get("status"),
                "verdict": acc.get("verdict"), "score": acc.get("score"),
            })
            written += words
    return {"books": books, "jobs_run": len(jobs), "words_in_progress": written}


def _released(day: str) -> list[dict]:
    out = []
    for b in list_books(per_page=300)["books"]:
        pub = b["data"].get("publishing") or {}
        if (pub.get("released_at") or "")[:10] == day:
            out.append({"catalog": b["catalog_number"], "title": b["title"],
                        "asin": pub.get("asin"),
                        "channels": pub.get("channels") or []})
    return out


def _promoted(day: str) -> dict:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT campaign, catalog, spend, sales, clicks, impressions "
            "FROM ad_spend WHERE day = ?", (day,)).fetchall()
        planned = conn.execute(
            "SELECT catalog, daily_budget FROM ad_plans WHERE status='active'"
        ).fetchall()
    finally:
        conn.close()
    spend = sum(r[2] or 0 for r in rows)
    sales = sum(r[3] or 0 for r in rows)
    return {
        "campaigns": [{"campaign": r[0], "catalog": r[1],
                       "spend": round(r[2] or 0, 2), "sales": round(r[3] or 0, 2),
                       "clicks": r[4], "impressions": r[5]} for r in rows],
        "spend": round(spend, 2), "attributed_sales": round(sales, 2),
        "acos": round(spend / sales, 2) if sales else None,
        "budgeted_daily": round(sum(r[1] or 0 for r in planned), 2),
    }


def _earned(day: str) -> dict:
    conn = get_connection()
    try:
        def window(since: str) -> dict:
            r = conn.execute(
                "SELECT COALESCE(SUM(royalty),0), COALESCE(SUM(units),0), "
                "COALESCE(SUM(kenp),0) FROM sales_rows WHERE day >= ?",
                (since,)).fetchone()
            return {"royalty": round(r[0] or 0, 2), "units": r[1] or 0,
                    "kenp": r[2] or 0}
        today = conn.execute(
            "SELECT COALESCE(SUM(royalty),0), COALESCE(SUM(units),0), "
            "COALESCE(SUM(kenp),0) FROM sales_rows WHERE day = ?",
            (day,)).fetchone()
        d = date.fromisoformat(day)
        return {
            "today": {"royalty": round(today[0] or 0, 2), "units": today[1] or 0,
                      "kenp": today[2] or 0},
            "last_7": window((d - timedelta(days=7)).isoformat()),
            "last_30": window((d - timedelta(days=30)).isoformat()),
        }
    finally:
        conn.close()


def _rank_moves(day: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT catalog, bsr, captured_at FROM rank_history "
            "WHERE captured_at >= datetime('now','-2 days') ORDER BY captured_at"
        ).fetchall()
    finally:
        conn.close()
    latest, first = {}, {}
    for catalog, bsr, _ts in rows:
        if bsr is None:
            continue
        first.setdefault(catalog, bsr)
        latest[catalog] = bsr
    return [{"catalog": c, "bsr": latest[c], "change": first[c] - latest[c]}
            for c in latest]


def daily(day: str = "") -> dict:
    """Assemble the report. `change` on rank is positive when a book climbs."""
    _init()
    day = day or date.today().isoformat()
    money = _earned(day)
    promo = _promoted(day)
    profit = round(money["today"]["royalty"] - promo["spend"], 2)
    return {
        "date": day,
        "written": _writing_today(day),
        "released": _released(day),
        # VERIFIED — from Amazon's own report files
        "promoted": {**promo, "source": "amazon_ads_report"},
        "earned": {**money, "source": "kdp_sales_report"},
        "net_today": profit,
        "data_trust": "Money figures are from Amazon report files (verified). "
                      "Rank/BSR below is scraped and best-effort — never used "
                      "for spend decisions.",
        # UNVERIFIED — scraped, shown for context only
        "ranks_unverified": _rank_moves(day),
    }


def as_text(rep: dict) -> str:
    """The report as a plain digest — email, terminal, or push notification."""
    L = [f"SCRPT — daily report, {rep['date']}", ""]
    w = rep["written"]
    L.append(f"WRITTEN   {len(w['books'])} book(s) worked on, {w['jobs_run']} job(s)")
    for b in w["books"][:8]:
        verdict = f" — {b['verdict']} {b['score']}" if b.get("verdict") else ""
        L.append(f"          {b['title'][:38]:38} {b['chapters']:>7} "
                 f"{b['words']:>7,}w{verdict}")
    rel = rep["released"]
    L.append(f"RELEASED  {len(rel) or 'nothing today'}")
    for r in rel:
        L.append(f"          {r['title'][:40]} ({r.get('asin') or 'no ASIN'})")
    p = rep["promoted"]
    L.append(f"PROMOTED  ${p['spend']:.2f} spent"
             + (f", ACOS {int(p['acos']*100)}%" if p.get("acos") else "")
             + f" (budgeted ${p['budgeted_daily']:.2f}/day)")
    e = rep["earned"]
    L.append(f"EARNED    ${e['today']['royalty']:.2f} today  |  "
             f"7d ${e['last_7']['royalty']:.2f}  |  30d ${e['last_30']['royalty']:.2f}")
    L.append(f"NET       ${rep['net_today']:.2f} today (royalties minus ad spend)")
    ranks = rep.get("ranks_unverified") or []
    if ranks:
        best = sorted(ranks, key=lambda r: -(r["change"] or 0))[:3]
        L.append("RANK*     " + ", ".join(
            f"{r['catalog']} #{r['bsr']:,} ({r['change']:+,})" for r in best))
        L.append("          * scraped, best-effort — not used for spend decisions")
    L.append("")
    L.append("All money figures above are from Amazon's own report files.")
    return "\n".join(L)
