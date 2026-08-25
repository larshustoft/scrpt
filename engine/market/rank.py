"""
Rank tracking — the Book Report half of the growth engine.

Reads a live Amazon product page for each published book: Best Sellers Rank,
category ranks, price, rating and review count, stored daily so a series'
trajectory (and an ad campaign's effect on it) is visible over time.
"""

import re
from typing import Optional

from ..database import get_connection, list_books
from .browser import Page
from .store import init as _init

_BSR_RE = re.compile(r"#([\d,]+)\s+in\s+(?:Kindle Store|Books)", re.I)
_CAT_RE = re.compile(r"#([\d,]+)\s+in\s+([A-Za-z0-9 &',\-]+)")
_PRICE_RE = re.compile(r'"price"\s*:\s*"?\$?([\d.]+)', re.I)
_RATING_RE = re.compile(r"([\d.]+)\s+out of 5 stars", re.I)
_REVIEWS_RE = re.compile(r"([\d,]+)\s+ratings", re.I)


async def snapshot(asin: str) -> dict:
    """One live reading of a book's Amazon listing."""
    out = {"asin": asin, "bsr": None, "category_ranks": [], "price": None,
           "rating": None, "reviews": None}
    async with Page() as page:
        await page.goto(f"https://www.amazon.com/dp/{asin}",
                        timeout=45000, wait_until="domcontentloaded")
        # BSR and price live below the fold and load lazily — scroll to force it
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1800)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
            await page.wait_for_timeout(700)
        except Exception:
            pass
        # Everything is read from the BOOK'S OWN page sections — never a
        # page-wide search, which would scoop numbers out of the
        # "customers also bought" carousels (a different book entirely).
        try:
            dom = await page.evaluate("""() => {
                const price = document.querySelector('#kindle-price, #price, #tmm-grid-swatch-KINDLE .a-color-price, #corePrice_feature_div .a-price .a-offscreen');
                const rc = document.querySelector('#acrCustomerReviewText');
                const rt = document.querySelector('#acrPopover');
                const detail = document.querySelector('#detailBulletsWrapper_feature_div, #productDetails_detailBullets_sections1, #detailBullets_feature_div, #productDetailsTable');
                return {
                    price: price ? price.innerText.trim() : null,
                    reviews: rc ? rc.innerText.trim() : null,
                    rating: rt ? (rt.getAttribute('title') || rt.innerText || '') : null,
                    detail: detail ? detail.innerText : null,
                    title: (document.querySelector('#productTitle')||{}).innerText || null,
                };
            }""")
        except Exception:
            dom = {}
        dom_price = (dom or {}).get("price")
        html = ""   # no page-wide parsing; DOM sections only
    if not (dom or {}).get("title"):
        # the product page did not render for this read — record NOTHING rather
        # than a guess, and flag it so the caller knows this snapshot is empty
        out["error"] = "page_not_rendered"
        return out
    detail = (dom or {}).get("detail") or ""
    m = _BSR_RE.search(detail)                      # book's own detail block only
    if m:
        out["bsr"] = int(m.group(1).replace(",", ""))
    seen = set()
    for num, cat in _CAT_RE.findall(detail)[:12]:
        cat = cat.strip()
        if cat.lower() in ("kindle store", "books") or cat in seen:
            continue
        seen.add(cat)
        out["category_ranks"].append({"category": cat,
                                      "rank": int(num.replace(",", ""))})
    dom_rating = (dom or {}).get("rating") or ""
    rm = _RATING_RE.search(dom_rating)
    if rm:
        try:
            out["rating"] = float(rm.group(1))
        except ValueError:
            pass
    if dom_price:
        pm = re.search(r"([\d.]+)", dom_price.replace(",", ""))
        if pm:
            try:
                out["price"] = float(pm.group(1))
            except ValueError:
                pass
    if out["price"] is None:
        m = _PRICE_RE.search(html)
        if m:
            try:
                out["price"] = float(m.group(1))
            except ValueError:
                pass
    dom_reviews = (dom or {}).get("reviews")
    if dom_reviews:
        rm = re.search(r"([\d,]+)", dom_reviews.replace(",", ","))
        if rm:
            try:
                out["reviews"] = int(rm.group(1).replace(",", ""))
            except ValueError:
                pass
    return out


def _published_books() -> list[dict]:
    """Books that carry an ASIN — i.e. actually live on Amazon."""
    out = []
    for b in list_books(per_page=500)["books"]:
        asin = ((b["data"].get("publishing") or {}).get("asin")
                or b["data"].get("asin"))
        if asin:
            out.append({"catalog": b["catalog_number"], "title": b["title"],
                        "asin": asin})
    return out


async def track_all(on_progress=None) -> dict:
    """Daily rank sweep over every published book."""
    _init()
    books = _published_books()
    captured, errors = [], []
    for i, b in enumerate(books):
        if on_progress:
            on_progress(i / max(1, len(books)), f"Reading {b['title'][:32]}")
        try:
            snap = await snapshot(b["asin"])
        except Exception as e:
            errors.append({"catalog": b["catalog"], "error": str(e)[:150]})
            continue
        if snap.get("error"):
            errors.append({"catalog": b["catalog"], "error": snap["error"]})
            continue
        conn = get_connection()
        try:
            import json as _json
            conn.execute(
                "INSERT INTO rank_history (catalog, asin, bsr, category_ranks, "
                "price, reviews, rating) VALUES (?,?,?,?,?,?,?)",
                (b["catalog"], b["asin"], snap["bsr"],
                 _json.dumps(snap["category_ranks"]), snap["price"],
                 snap["reviews"], snap["rating"]))
            conn.commit()
        finally:
            conn.close()
        captured.append({**b, **snap})
    return {"tracked": len(captured), "errors": errors, "books": captured}


def history(catalog: str, days: int = 30) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT bsr, price, reviews, rating, captured_at FROM rank_history "
            "WHERE catalog = ? AND captured_at >= datetime('now', ?) "
            "ORDER BY captured_at", (catalog, f"-{days} days")).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
