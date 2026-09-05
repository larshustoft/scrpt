"""
KDP automation.

Amazon publishes no KDP API, so SCRPT drives a real browser against a
PERSISTENT profile at ~/.scrpt/browser-profile.

Non-negotiable rules, enforced in code:
  * SCRPT never types a password and never handles credentials. The publisher
    signs in once, by hand, in a visible window (`open_login`).
  * SCRPT never presses Publish. It fills a draft and stops, leaving the
    final submit to the publisher.
  * Every write action is logged in the returned report.
"""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Optional

from ..config import OUTPUT_DIR
from ..database import get_book_by_catalog, get_setting, list_books, update_book
from .browser import Page

BOOKSHELF = "https://kdp.amazon.com/en_US/bookshelf"
REPORTS = "https://kdp.amazon.com/en_US/reports-new"
NEW_TITLE = "https://kdp.amazon.com/en_US/title-setup/kindle/new/details"


async def session_status() -> dict:
    """Is the stored browser session still signed in to KDP?"""
    try:
        async with Page(persistent=True) as page:
            await page.goto(BOOKSHELF, timeout=45000, wait_until="domcontentloaded")
            url = page.url
            from .kdp_signin import auto_signin, _is_signin_url
            signed_in = not _is_signin_url(url)
            signin = ""
            if not signed_in:
                signin = await auto_signin(page)
                signed_in = signin in ("signed_in", "signed_in_after")
                url = page.url
            title = await page.title()
        return {"signed_in": signed_in, "url": url, "title": title, "signin": signin}
    except Exception as e:
        return {"signed_in": False, "error": str(e)[:200]}


async def open_login() -> dict:
    """Open a VISIBLE browser at KDP so the publisher can sign in themselves.

    The window stays open until they close it; the session is then stored in
    the persistent profile for later headless work.
    """
    from playwright.async_api import async_playwright
    from .browser import PROFILE_DIR, _ARGS, _STEALTH, context_kwargs
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    pw = await async_playwright().start()
    ctx = await pw.chromium.launch_persistent_context(
        str(PROFILE_DIR), headless=False, args=_ARGS, **context_kwargs())
    await ctx.add_init_script(_STEALTH)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(BOOKSHELF, timeout=60000)
    # hand the window to the human and let it live independently
    return {"opened": True,
            "instruction": "Sign in to KDP in the window that just opened, then "
                           "close it. SCRPT will reuse that session."}


# The exact words KDP prints under a format. "Release scheduled" is the one
# that matters most and reads least like the others: a book showing it is
# submitted and dated, NOT live and NOT editable as a draft. Matching is by
# prefix, so the longer phrasings have to be listed in their own right or a
# scheduled book goes unrecognised and disappears off our copy of the shelf.
KDP_STATES = ("draft", "in review", "live", "publishing", "release scheduled",
              "scheduled", "blocked", "unpublished", "updates publishing",
              "updates in review", "manuscript ready", "draft incomplete")


def _parse_bookshelf_text(text: str) -> list[dict]:
    """KDP renders the bookshelf as flowing text, not clean rows. Each book
    reads: <title> / "by <author>" / a status / ... / "ASIN: B0XXXXXXXX".

    A title only gets an ASIN once it is LIVE. Binding records to the ASIN
    line therefore made every draft and every scheduled release invisible —
    and a book SCRPT cannot see is a book it will happily upload twice. So
    each title block is recorded whether or not it has an ASIN, carrying
    whatever state KDP shows beside it.
    """
    import re
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    books: list[dict] = []
    cur = None

    def flush():
        """One record per format actually present on the shelf.

        A title is rarely in one state: the same book can be a scheduled
        paperback and a draft ebook at the same time, and collapsing that into
        a single row is what made the shelf unreadable. A format with no
        status was never created — only offered — so it is not recorded.
        """
        if not (cur and cur.get("title")):
            return
        found = cur.get("formats") or {}
        for fmt, slot in found.items():
            if not slot.get("status"):
                continue
            books.append({"title": cur["title"], "author": cur.get("author"),
                          "format": fmt, "status": slot["status"],
                          "asin": slot.get("asin"),
                          "series_status": cur.get("series_status")})
        if not found:
            books.append({"title": cur["title"], "author": cur.get("author"),
                          "format": None, "status": None, "asin": None,
                          "series_status": cur.get("series_status")})

    for i, line in enumerate(lines):
        low = line.lower()
        if low.startswith("by ") and 3 < len(line) < 80:
            prev = lines[i - 1] if i else ""
            if prev and 3 < len(prev) < 120 and not prev.lower().startswith(
                    ("asin", "submitted", "$", "manage", "view", "order", "why")):
                flush()
                cur = {"title": prev, "author": line[3:].strip(),
                       "asin": None, "status": None, "format": None}
            continue
        if not cur:
            continue

        # "Series status: Live" describes the SERIES, not this book. Reading it
        # as the book's state made a paperback that says "Draft" report itself
        # as live — the exact misreading that would let an upload run against a
        # published title.
        if low.startswith("series status"):
            cur["series_status"] = line.split(":", 1)[-1].strip().lower() or None
            continue

        # KDP prints one section per format — "Kindle eBook", "Paperback",
        # "Hardcover" — each with its own status underneath. Everything that
        # follows belongs to the section last opened.
        if low in ("kindle ebook", "kindle edition", "paperback", "hardcover"):
            cur["section"] = "ebook" if low.startswith("kindle") else low
            continue

        sec = cur.get("section")
        if not sec:
            continue

        # "+ Create Kindle eBook" is an offer to make one, not evidence of one.
        # Treating it as evidence labelled every paperback an ebook.
        if low.startswith(("+ create", "create ", "link existing")):
            continue

        slot = cur.setdefault("formats", {}).setdefault(sec, {"status": None, "asin": None})
        if slot["status"] is None:
            for st in KDP_STATES:
                if low == st or low.startswith(st):
                    slot["status"] = st
                    break
        m = re.match(r"ASIN:\s*(B0[A-Z0-9]{8})", line, re.I)
        if m and not slot["asin"]:
            slot["asin"] = m.group(1)
    flush()

    # one record per (title, format); prefer the entry that carries an ASIN
    out: dict = {}
    for b in books:
        key = ((b["title"] or "").strip().lower(), b.get("format") or "")
        if key not in out or (b.get("asin") and not out[key].get("asin")):
            out[key] = b
    return list(out.values())


async def read_bookshelf() -> dict:
    """Everything currently on the KDP bookshelf, so SCRPT's catalogue can be
    reconciled with what is actually live on Amazon."""
    async with Page(persistent=True) as page:
        await page.goto(BOOKSHELF, timeout=60000, wait_until="domcontentloaded")
        if "signin" in page.url:
            return {"signed_in": False, "titles": []}
        await page.wait_for_timeout(6000)
        text = await page.evaluate("() => document.body.innerText")
    titles = _parse_bookshelf_text(text)
    return {"signed_in": True, "titles": titles, "raw_rows": len(titles)}


async def sync_bookshelf() -> dict:
    """Match live KDP titles to SCRPT books and store their ASINs."""
    shelf = await read_bookshelf()
    if not shelf.get("signed_in"):
        return {"signed_in": False, "matched": 0,
                "message": "Sign in to KDP first (open_login)."}
    books = list_books(per_page=300)["books"]
    matched, unknown = [], []
    for row in shelf["titles"]:
        line = (row.get("title") or "").lower()
        hit = next((b for b in books
                    if b["title"] and b["title"].lower()[:28] in line), None)
        if not hit:
            unknown.append(row.get("line"))
            continue
        data = dict(get_book_by_catalog(hit["catalog_number"])["data"])
        pub = dict(data.get("publishing") or {})
        changed = False
        # A title on the shelf is on KDP whether or not it has an ASIN yet —
        # record its presence so nothing tries to upload it a second time.
        if not pub.get("kdp_present"):
            pub["kdp_present"] = True
            changed = True
        if row.get("status") and pub.get("kdp_status") != row["status"]:
            pub["kdp_status"] = row["status"]
            changed = True
        if row.get("asin") and pub.get("asin") != row["asin"]:
            pub["asin"] = row["asin"]
            pub.setdefault("released_at", date.today().isoformat())
            changed = True
        if changed:
            data["publishing"] = pub
            update_book(hit["id"], data)
        matched.append({"catalog": hit["catalog_number"], "title": hit["title"],
                        "asin": row.get("asin"), "status": row.get("status"),
                        "format": row.get("format")})

    # persist the whole live shelf so SCRPT can show the account's catalogue,
    # collapsing ebook + paperback + hardcover of one book into a single entry
    from ..database import set_setting
    grouped: dict = {}
    scrpt_asins = {m["asin"] for m in matched if m.get("asin")}
    for row in shelf["titles"]:
        key = (row.get("title") or "").strip().lower()
        g = grouped.setdefault(key, {"title": row.get("title"),
                                     "author": row.get("author"),
                                     "asins": [], "is_scrpt": False})
        if row["asin"] not in g["asins"]:
            g["asins"].append(row["asin"])
        if row["asin"] in scrpt_asins:
            g["is_scrpt"] = True
    catalogue = sorted(grouped.values(), key=lambda x: (x.get("author") or "", x.get("title") or ""))
    set_setting("kdp_bookshelf", json.dumps({
        "synced_at": date.today().isoformat(),
        "books": catalogue}))

    return {"signed_in": True, "matched": len(matched), "books": matched,
            "catalogue": catalogue,
            "on_kdp_not_in_scrpt": [b["title"] for b in catalogue
                                    if not b["is_scrpt"]][:40]}


def stored_bookshelf() -> dict:
    """The last synced KDP catalogue, for display inside SCRPT."""
    raw = get_setting("kdp_bookshelf", "")
    if not raw:
        return {"synced_at": None, "books": []}
    try:
        return json.loads(raw)
    except ValueError:
        return {"synced_at": None, "books": []}


async def download_reports(out_dir: Optional[str] = None) -> dict:
    """Pull the KDP royalty report file so sales can be imported."""
    target = Path(out_dir or (Path(OUTPUT_DIR).parent / "data" / "kdp-reports"))
    target.mkdir(parents=True, exist_ok=True)
    saved = []
    async with Page(persistent=True) as page:
        await page.goto(REPORTS, timeout=60000, wait_until="domcontentloaded")
        if "signin" in page.url:
            return {"signed_in": False, "files": []}
        await page.wait_for_timeout(4000)
        try:
            async with page.expect_download(timeout=45000) as dl:
                await page.get_by_role(
                    "button", name=lambda n: n and "download" in n.lower()).first.click()
            download = await dl.value
            dest = target / f"kdp-{date.today().isoformat()}-{download.suggested_filename}"
            await download.save_as(str(dest))
            saved.append(str(dest))
        except Exception as e:
            return {"signed_in": True, "files": [], "error": str(e)[:200],
                    "hint": "KDP's report page changed its download control; "
                            "download by hand and import the file."}
    return {"signed_in": True, "files": saved}


async def prepare_draft(catalog: str) -> dict:
    """Fill a new Kindle title's details from SCRPT's upload package.

    Stops at the filled form. SCRPT does NOT press Publish — the window is
    left open for the publisher to review and submit.
    """
    from ..routers.scrpt import upload_package
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    pkg = upload_package(catalog)
    meta = pkg["metadata"]

    from playwright.async_api import async_playwright
    from .browser import PROFILE_DIR, _ARGS, _STEALTH, context_kwargs
    pw = await async_playwright().start()
    ctx = await pw.chromium.launch_persistent_context(
        str(PROFILE_DIR), headless=False, args=_ARGS, **context_kwargs())
    await ctx.add_init_script(_STEALTH)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(NEW_TITLE, timeout=60000, wait_until="domcontentloaded")
    if "signin" in page.url:
        return {"signed_in": False,
                "message": "Sign in to KDP first, then run this again."}

    filled, missed = [], []

    async def fill(selector: str, value: str, label: str):
        if not value:
            return
        try:
            el = page.locator(selector).first
            await el.wait_for(timeout=8000)
            await el.fill(str(value))
            filled.append(label)
        except Exception:
            missed.append(label)

    await fill("#data-print-book-title", meta["title"], "title")
    await fill("#data-print-book-subtitle", meta.get("subtitle") or "", "subtitle")
    await fill("#data-print-book-series-title", meta.get("series_title") or "",
               "series")
    await fill("#data-print-book-contributor-0-first-name",
               (meta.get("author") or "").split(" ")[0], "author first name")
    await fill("#data-print-book-contributor-0-last-name",
               " ".join((meta.get("author") or "").split(" ")[1:]), "author last name")
    await fill("#cke_1_contents textarea, #data-print-book-description",
               meta.get("description") or "", "description")
    for i, kw in enumerate((meta.get("keywords") or [])[:7]):
        await fill(f"#data-print-book-keywords-{i}", kw, f"keyword {i+1}")

    return {
        "signed_in": True,
        "catalog": catalog,
        "filled": filled,
        "needs_manual": missed + ["categories", "AI disclosure", "pricing",
                                  "manuscript upload", "cover upload"],
        "ai_disclosure": meta.get("ai_disclosure"),
        "series_note": meta.get("series_note"),
        "message": ("Draft filled in an open window. SCRPT never presses "
                    "Publish — review, complete the upload steps, and submit "
                    "yourself."),
    }
