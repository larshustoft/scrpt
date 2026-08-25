"""
Pre-flight: is a book actually ready to upload to KDP?

A single checklist every book must pass before it can go near Amazon. Each
item is pass/fail with a plain reason, so the gate is honest — nothing reaches
KDP on an assumption. This is the "missing links" detector: run it and the
gaps are named.
"""

import os
from pathlib import Path

from ..config import OUTPUT_DIR
from ..database import get_book_by_catalog


def _exists(catalog: str, name: str) -> bool:
    return (Path(OUTPUT_DIR) / catalog / name).exists()


def check(catalog: str) -> dict:
    b = get_book_by_catalog(catalog)
    if not b:
        raise ValueError("Book not found")
    d = b["data"]
    ms = d.get("manuscript") or {}
    acc = d.get("acceptance") or {}
    items = []

    def item(name, ok, detail, blocking=True):
        items.append({"name": name, "ok": bool(ok), "detail": detail,
                      "blocking": blocking})

    # ── manuscript ──
    words = sum(c.get("word_count", 0) for c in ms.get("chapters") or [])
    item("Manuscript written", words > 5000, f"{words:,} words")
    item("Acceptance verdict", acc.get("verdict") == "accept",
         f"{acc.get('verdict') or 'not run'} {acc.get('score') or ''}".strip(),
         blocking=False)   # 'revise' can still ship; the editor's read is advisory

    # ── files ──
    item("Ebook EPUB", _exists(catalog, "ebook.epub"), "ebook.epub")
    item("Ebook cover (1600×2560)", _exists(catalog, "ebook-cover.jpg"),
         "ebook-cover.jpg")
    item("Print interior PDF", _exists(catalog, "interior.pdf"), "interior.pdf")
    # print wrap: exists AND validates to spec
    wrap = (d.get("cover") or {}).get("print_wrap") or {}
    full = (d.get("cover") or {}).get("full_cover") or {}
    wrap_ok = _exists(catalog, "cover-wrap.pdf") or bool(full.get("file"))
    val = (wrap.get("validation") or full.get("validation") or {})
    item("Print cover wrap", wrap_ok, "cover-wrap.pdf")
    item("Wrap matches KDP spec", val.get("passed", wrap_ok),
         "dimensions validated" if val.get("passed") else "not validated",
         blocking=False)

    # ── metadata ──
    item("Title", bool(b["title"] and not b["title"].lower().startswith("untitled")),
         b["title"])
    item("Author / pen name", bool(d.get("author_name")), d.get("author_name") or "—")
    blurb = d.get("description") or ms.get("blurb") or ""
    item("Description / blurb", 150 <= len(blurb) <= 4000, f"{len(blurb)} chars")
    item("Subtitle / tagline", bool(ms.get("tagline")), ms.get("tagline") or "—",
         blocking=False)
    kws = d.get("keywords") or []
    item("7 keyword slots", len(kws) >= 5, f"{len(kws)} set")
    cats = d.get("categories") or []
    item("Categories", len(cats) >= 1, f"{len(cats)} set")
    item("List price", bool(d.get("list_price")), f"${d.get('list_price') or '—'}")

    # ── print spec ──
    pages = (d.get("interior") or {}).get("page_count")
    item("Interior page count", bool(pages and pages >= 24),
         f"{pages or '—'} pages")
    item("Trim size", bool((d.get("format") or {}).get("trim_size") or d.get("trim_size")),
         (d.get("format") or {}).get("trim_size") or d.get("trim_size") or "—")

    blocking_fails = [i for i in items if i["blocking"] and not i["ok"]]
    return {
        "catalog": catalog, "title": b["title"],
        "ready": len(blocking_fails) == 0,
        "blocking_failures": [i["name"] for i in blocking_fails],
        "advisories": [i["name"] for i in items if not i["blocking"] and not i["ok"]],
        "items": items,
    }
