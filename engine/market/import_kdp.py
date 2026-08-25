"""
Import existing KDP books into SCRPT as catalogue records.

For books already live on Amazon (published before SCRPT, or by hand): create a
SCRPT record carrying the ASINs and pen name, download the real cover from the
product page so the bookshelf looks right, and mark them external so the
writing pipeline never touches them.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

import httpx

from ..config import OUTPUT_DIR
from ..database import create_book, get_book_by_catalog, list_books, update_book
from .browser import Page
from .kdp import stored_bookshelf


async def _cover_url(asin: str) -> Optional[str]:
    async with Page() as page:
        await page.goto(f"https://www.amazon.com/dp/{asin}",
                        timeout=45000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        return await page.evaluate("""() => {
            const el = document.querySelector('#imgBlkFront, #ebooksImgBlkFront, #landingImage, img#main-image');
            if (!el) return null;
            const dyn = el.getAttribute('data-a-dynamic-image');
            if (dyn) { try {
                const o = JSON.parse(dyn);
                let best = null, area = 0;
                for (const [u, wh] of Object.entries(o)) {
                    const a = (wh[0]||0) * (wh[1]||0);
                    if (a > area) { area = a; best = u; }
                }
                if (best) return best;
            } catch(e) {} }
            return el.src || el.getAttribute('src');
        }""")


async def _download_cover(asin: str, catalog: str) -> bool:
    """Fetch the real cover and write the front-cover files SCRPT displays."""
    url = await _cover_url(asin)
    if not url:
        return False
    # ask Amazon's CDN for a large render
    url = re.sub(r"\._[^.]+_\.", "._SL1600_.", url)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200 or len(r.content) < 5000:
        return False
    out = Path(OUTPUT_DIR) / catalog
    out.mkdir(parents=True, exist_ok=True)
    raw = r.content
    (out / "cover-art.png").write_bytes(raw)
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.save(out / "cover-front.png")
        # ebook spec render for consistency
        w = 800
        im.resize((w, int(w * im.height / im.width)), Image.LANCZOS).save(
            out / "cover-front.png")
    except Exception:
        (out / "cover-front.png").write_bytes(raw)
    return True


def _guess_kind(title: str) -> str:
    return "nonfiction"      # the existing catalogue is all guides/non-fiction


async def import_existing(on_progress=None) -> dict:
    """Create SCRPT records for every KDP book not already imported."""
    shelf = stored_bookshelf()
    catalogue = shelf.get("books") or []
    if not catalogue:
        return {"imported": 0, "message": "Sync the KDP bookshelf first."}

    # already-imported ASINs (so re-running is safe)
    known = set()
    for b in list_books(per_page=500)["books"]:
        pub = b["data"].get("publishing") or {}
        for a in (pub.get("asins") or ([pub["asin"]] if pub.get("asin") else [])):
            known.add(a)

    imported, covers = [], 0
    for i, book in enumerate(catalogue):
        asins = book.get("asins") or []
        if not asins or all(a in known for a in asins):
            continue
        if on_progress:
            on_progress(i / max(1, len(catalogue)),
                        f"Importing {book['title'][:34]}")
        data = {
            "kind": _guess_kind(book["title"]),
            "book_type": _guess_kind(book["title"]),
            "author_name": book.get("author") or "",
            "external": True,          # not SCRPT-produced; pipeline skips it
            "publishing": {"asin": asins[0], "asins": asins,
                           "channels": ["KDP"], "source": "kdp_import"},
            "manuscript": {}, "cover": {}, "audio": {},
        }
        rec = create_book(title=book["title"], data=data)
        catalog = rec["catalog_number"]
        # give it its real cover
        got = False
        try:
            got = await _download_cover(asins[0], catalog)
        except Exception:
            got = False
        if got:
            fresh = get_book_by_catalog(catalog)
            d = dict(fresh["data"])
            d["cover"] = {"mode": "amazon", "cover_front_png":
                          str(Path(OUTPUT_DIR) / catalog / "cover-front.png")}
            update_book(fresh["id"], d)
            covers += 1
        imported.append({"catalog": catalog, "title": book["title"],
                         "asin": asins[0], "cover": got})
    return {"imported": len(imported), "covers_downloaded": covers,
            "books": imported}
