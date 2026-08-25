"""
KDP paperback staging — the upload flow SCRPT learned by doing it by hand.

Drives a real, VISIBLE browser on the persistent signed-in profile through
KDP's three pages (Details → Content → Rights & Pricing) from the book's
SCRPT record, applying the house rules, and stops at a saved draft.
`publish=True` presses Publish — only when the publisher has enabled
auto-publish or asked for it explicitly; the launch gate must pass first.

Rules enforced in code:
  * never types a password — if Amazon re-prompts, the run pauses and
    returns needs_signin so the publisher can sign in in the open window
  * subtitle is only sent if the cover carries it (else the cover's
    descriptor line if known, else blank)
  * keywords are scrubbed of banned terms; paper follows fiction→cream,
    non-fiction→white; free KDP ISBN; no Expanded Distribution; price kept
    in the 60% tier; AI disclosure = house defaults
  * every step is screenshotted into output/<catalog>/kdp/ and logged
"""

from __future__ import annotations

import asyncio
import datetime as dt
import html as _html
import json
from pathlib import Path
from typing import Optional

from ..config import OUTPUT_DIR, delivery_name, write_delivery_copies
from ..database import get_book_by_catalog, update_book
from .launch_gate import launch_gate

BOOKSHELF = "https://kdp.amazon.com/en_US/bookshelf"
CREATE = "https://kdp.amazon.com/en_US/create"
BANNED = ("kindle unlimited", "bestseller", "best seller", "free", "#1", "amazon", "large print")

AI_DEFAULTS = {
    "texts": "Entire work, with extensive editing", "texts_tool": "Claude",
    "images": "One or a few AI-generated images, with minimal or no editing",
    "images_tool": "ChatGPT (GPT Image)", "translations": "None",
}
TRIM_LABEL = {"5x8": "5 x 8 in", "5.25x8": "5.25 x 8 in", "5.5x8.5": "5.5 x 8.5 in", "6x9": "6 x 9 in"}
PAPER_LABEL = {"cream_bw": "Black and white interior with cream paper",
               "white_bw": "Black and white interior with white paper",
               "standard_color": "Standard color interior with white paper",
               "premium_color": "Premium color interior with white paper"}


_OPEN = None          # (context, playwright) of the window left open for review


class Stager:
    def __init__(self, catalog: str, publish: bool = False):
        self.catalog = catalog
        self.publish = publish
        self.book = get_book_by_catalog(catalog)
        if not self.book:
            raise ValueError("Book not found")
        self.d = self.book["data"]
        self.log: list[str] = []
        self.shots = OUTPUT_DIR / catalog / "kdp"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.n = 0
        self.page = None

    # ── plumbing ─────────────────────────────────────────────────
    async def shot(self, label: str, full: bool = False):
        self.n += 1
        p = self.shots / f"{self.n:02d}-{label}.png"
        try:
            await self.page.screenshot(path=str(p), full_page=full)
        except Exception:
            pass
        return str(p)

    def note(self, msg: str):
        self.log.append(msg)

    async def signed_in(self) -> bool:
        return "signin" not in self.page.url and "ap/signin" not in self.page.url

    async def fill(self, selector: str, value: str):
        loc = self.page.locator(selector).first
        await loc.wait_for(timeout=10000)
        await loc.fill(str(value))

    async def click_text(self, text: str, wait_ms: int = 1500):
        p = self.page
        loc = p.get_by_role("button", name=text, exact=False)
        if await loc.count() == 0:
            loc = p.get_by_text(text, exact=False)
        await loc.first.click(timeout=10000)
        await p.wait_for_timeout(wait_ms)

    async def radio_by_label(self, pattern: str):
        return await self.page.evaluate("""(pat) => {
            const re = new RegExp(pat);
            const r = [...document.querySelectorAll('input[type=radio]')].find(x => x.labels && x.labels[0] && re.test(x.labels[0].innerText));
            if (r) { r.click(); return 'radio'; }
            const el = [...document.querySelectorAll('label, span, div')].find(e => e.children.length < 4 && re.test((e.innerText||'').trim()) && e.offsetParent !== null && (e.innerText||'').length < 90);
            if (!el) return 'missing';
            const inp = el.querySelector('input') || el.closest('label')?.querySelector('input');
            (inp || el).click(); return 'label';
        }""", pattern)

    async def _place_categories_picker(self, cats: list) -> int:
        p = self.page
        SEL = """(t) => { const ss=[...document.querySelectorAll('select')].filter(s=>s.offsetParent!==null); const s=ss[ss.length-1]; if(!s) return 'noselect'; const o=[...s.options].find(o=>o.text.trim()===t); if(!o) return 'nooption'; s.value=o.value; s.dispatchEvent(new Event('change',{bubbles:true})); return 'ok'; }"""
        btn = p.locator("#categories-modal-button")
        if await btn.count():
            await btn.click(timeout=10000)
        else:
            await self.click_text("Choose categories", 2000)
        await p.wait_for_timeout(2500)
        groups: dict = {}
        for chain in cats[:3]:
            groups.setdefault(tuple(chain[:-1]), []).append(chain[-1])
        placed = 0
        first = True
        for path, leaves in groups.items():
            if not first:
                await p.get_by_role("button", name="Add another category").click(timeout=8000)
                await p.wait_for_timeout(1500)
            first = False
            ok = True
            for level in path:
                r = await p.evaluate(SEL, level)
                await p.wait_for_timeout(1500)
                if r != "ok":
                    ok = False
                    self.note(f"category level missing: {level}")
                    break
            if not ok:
                continue
            for leaf in leaves:
                try:
                    loc = p.get_by_text(leaf, exact=True)
                    n = await loc.count()
                    await loc.nth(n - 1).click(timeout=5000)
                    await p.wait_for_timeout(800)
                    placed += 1
                except Exception:
                    self.note(f"category leaf missing: {leaf}")
        await p.get_by_role("button", name="Save categories").click(timeout=8000)
        await p.wait_for_timeout(2500)
        return placed

    # ── metadata from the record, house rules applied ────────────
    def metadata(self) -> dict:
        d = self.d
        kws = [k for k in (d.get("keywords") or []) if not any(t in k.lower() for t in BANNED)][:7]
        sub = (d.get("kdp") or {}).get("subtitle_used") or ""
        kind = d.get("kind") or (d.get("manuscript") or {}).get("kind") or "fiction"
        paper = "cream_bw" if kind == "fiction" else "white_bw"
        price = float(d.get("list_price") or 12.99)
        if price < 9.99:
            price = 9.99
        series = d.get("series") or {}
        rel = d.get("release") or {}
        return {
            "title": self.book["title"], "subtitle": sub,
            "author": d.get("author_name") or "", "description": d.get("description") or "",
            "keywords": kws, "categories": d.get("categories") or [],
            "series_title": series.get("series_title"), "book_number": series.get("book_number"),
            "paper": paper, "trim": d.get("trim_size") or "5.25x8", "price": price,
            "release_date": rel.get("date"), "release_mode": rel.get("mode") or "immediate",
            "kdp_series_id": (d.get("kdp") or {}).get("series_id"),
            "paperback_id": (d.get("kdp") or {}).get("paperback_id"),
        }

    # ── pages ────────────────────────────────────────────────────
    async def details(self, m: dict):
        p = self.page
        if m["paperback_id"]:
            await p.goto(f"https://kdp.amazon.com/en_US/title-setup/paperback/{m['paperback_id']}/details",
                         timeout=60000, wait_until="domcontentloaded")
        else:
            await p.goto(CREATE, timeout=60000, wait_until="domcontentloaded")
            await self.click_text("Create paperback", 4000)
        if not await self.signed_in():
            return "needs_signin"
        await self.fill("#data-print-book-title", m["title"])
        if m["subtitle"]:
            await self.fill("#data-print-book-subtitle", m["subtitle"])
        parts = m["author"].split(" ")
        await self.fill("#data-print-book-primary-author-first-name", parts[0])
        await self.fill("#data-print-book-primary-author-last-name", " ".join(parts[1:]))
        paras = [x.strip() for x in m["description"].split("\n\n") if x.strip()]
        body = "".join(f"<p>{'<b>' if i == 0 else ''}{_html.escape(x)}{'</b>' if i == 0 else ''}</p>" for i, x in enumerate(paras))
        # the description editor: CKEditor on the classic page, a contenteditable
        # or textarea on the newer one — and an existing draft may already carry it
        set_desc = await p.evaluate("""(h) => {
            try { if (window.CKEDITOR && Object.keys(CKEDITOR.instances).length) {
                const k = Object.keys(CKEDITOR.instances)[0]; CKEDITOR.instances[k].setData(h); return 'ckeditor'; } } catch (e) {}
            const ta = document.querySelector('#data-print-book-description, textarea[name*="description"]');
            if (ta) { ta.value = h.replace(/<[^>]+>/g, ''); ta.dispatchEvent(new Event('input', {bubbles: true})); ta.dispatchEvent(new Event('change', {bubbles: true})); return 'textarea'; }
            const ce = [...document.querySelectorAll('[contenteditable="true"]')].find(e => e.closest('[class*="description" i], [id*="description" i]') || e.getBoundingClientRect().height > 80);
            if (ce) { ce.focus(); ce.innerHTML = h; ce.dispatchEvent(new Event('input', {bubbles: true})); return 'contenteditable'; }
            return null;
        }""", body)
        if not set_desc:
            if m["paperback_id"]:
                self.note("description editor not found — existing draft keeps its description")
            else:
                raise RuntimeError("Could not find the description editor on the KDP details page")
        else:
            self.note(f"description set via {set_desc}")
        await p.evaluate("() => document.querySelector('#non-public-domain')?.click()")
        await p.evaluate("""() => { const r=[...document.querySelectorAll('input[name="data[print_book][is_adult_content]-radio"]')].find(x=>x.value==='false'); r && r.click(); }""")
        for i, kw in enumerate(m["keywords"]):
            await self.fill(f"#data-print-book-keywords-{i}", kw)
        self.note(f"details filled: {len(m['keywords'])} keywords")

        # categories: "Books > Romance > Historical > Regency" → cascade + placement checkbox.
        # An existing draft that already carries categories shows "Edit categories" — keep them.
        has_cats = None
        for _ in range(12):            # the block renders late; wait for either button
            has_cats = await p.evaluate("""() => { const t=document.body.innerText; if (/Edit categories/i.test(t)) return true; if (/Choose categories/i.test(t)) return false; return null; }""")
            if has_cats is not None:
                break
            await p.wait_for_timeout(2000)
        if has_cats:
            self.note("categories already on the draft — kept")
            cats_todo = []
        else:
            # the same picker as the Kindle page: cascade selects + placement boxes
            from .kdp_ebook import KINDLE_CATEGORY_DEFAULTS
            plan = (self.d.get("kdp") or {}).get("kindle_categories_plan") or KINDLE_CATEGORY_DEFAULTS.get(self.d.get("genre_preset") or "", [])
            plan = [c.split(" > ") if isinstance(c, str) else c for c in plan] or [
                [x.strip() for x in c.replace("Kindle Store > Kindle eBooks > ", "").replace("Books > ", "").split(">")] for c in m["categories"][:3]]
            try:
                placed = await self._place_categories_picker(plan)
                self.note(f"categories placed: {placed}")
            except Exception as e:
                self.note(f"categories: {str(e)[:80]}")
            cats_todo = []
        done = 0
        for cat in cats_todo:
            chain = [c.strip() for c in cat.replace("Kindle Store", "Books").split(">")][1:]
            if done:
                await self.click_text("Add another category", 1500)
            ok = True
            for level in chain[:-1]:
                r = await p.evaluate("""(t) => { const ss=[...document.querySelectorAll('select[name^=react-aui]')].filter(s=>s.offsetParent!==null); const s=ss[ss.length-1]; if(!s) return 'noselect'; const o=[...s.options].find(o=>o.text.trim()===t); if(!o) return 'nooption'; s.value=o.value; s.dispatchEvent(new Event('change',{bubbles:true})); return 'ok'; }""", level)
                await p.wait_for_timeout(1200)
                if r != "ok":
                    ok = False; break
            leaf = chain[-1]
            r2 = await p.evaluate("""(t) => { const l=[...document.querySelectorAll('label, span')].find(e=>e.innerText && e.innerText.trim()===t && e.offsetParent!==null); if(!l) return 'missing'; const box=l.querySelector('input[type=checkbox]')||l.closest('label')?.querySelector('input'); (box||l).click(); return 'ok'; }""", leaf)
            if ok and r2 == "ok":
                done += 1
            else:
                self.note(f"category not placed: {cat}")
        if cats_todo:
            await self.click_text("Save categories", 2000)
            self.note(f"categories placed: {done}")

        # series
        if m["series_title"] and not m["paperback_id"]:
            await self.click_text("Add to series", 3000)
            if m["kdp_series_id"]:
                await self.click_text("Select series", 2500)
                self.note("existing series: select by hand if not auto-matched")
            else:
                await self.click_text("Create series", 2500)
                await self.click_text("Main content", 2500)
                await self.click_text("Go to series setup", 4000)
                await self.fill("#data-series-title", m["series_title"])
                await p.evaluate("""() => { const r=[...document.querySelectorAll('input[name="data[is_series_ordered]"]')].find(x=>x.value==='true'); r && r.click(); }""")
                await self.click_text("Submit updates", 5000)
                sid = p.url.split("/series/")[-1].split("?")[0] if "/series/" in p.url else None
                if sid:
                    self._remember({"series_id": sid})
                await self.shot("series")
                # back to the title
                pid = m["paperback_id"] or (p.url.split("attach_item_id=")[-1].split("&")[0] if "attach_item_id=" in p.url else None)
                if pid:
                    self._remember({"paperback_id": pid})
                    await p.goto(f"https://kdp.amazon.com/en_US/title-setup/paperback/{pid}/details",
                                 timeout=60000, wait_until="domcontentloaded")
        # release
        if m["release_mode"] == "scheduled" and m["release_date"]:
            await self.radio_by_label("Schedule my book")
            await p.wait_for_timeout(800)
            y, mo, da = m["release_date"].split("-")
            await p.evaluate("""(v) => { const i=document.querySelector('#release-date-picker-input'); if(i){ i.value=v; i.dispatchEvent(new Event('input',{bubbles:true})); i.dispatchEvent(new Event('change',{bubbles:true})); } }""",
                             f"{mo}/{da}/{y}")
            self.note(f"release scheduled {m['release_date']}")
        await self.shot("details")
        await self.click_text("Save and Continue", 6000)
        if not await self.signed_in():
            return "needs_signin"
        pid = p.url.split("/paperback/")[-1].split("/")[0]
        if pid and pid != "new":
            self._remember({"paperback_id": pid})
        return "ok"

    async def content(self, m: dict):
        p = self.page
        pid = (get_book_by_catalog(self.catalog)["data"].get("kdp") or {}).get("paperback_id")
        await p.goto(f"https://kdp.amazon.com/en_US/print-setup/paperback/{pid}/content",
                     timeout=60000, wait_until="domcontentloaded")
        await p.wait_for_timeout(2500)
        if not await self.signed_in():
            return "needs_signin"
        txt = await p.inner_text("body")
        if "has been assigned a free KDP ISBN" not in txt:
            # the ISBN block renders late on a fresh title: wait for its options
            for _ in range(20):
                txt = await p.inner_text("body")
                if "free KDP ISBN" in txt or "Assign ISBN" in txt:
                    break
                await p.wait_for_timeout(3000)
            await self.radio_by_label("Get a free KDP ISBN")
            await p.wait_for_timeout(1500)
            clicked = await p.evaluate("""() => { const b=[...document.querySelectorAll('button, [role=button]')].filter(x => x.offsetParent!==null && /assign (me )?(a )?(free )?(kdp )?isbn/i.test(x.innerText||'')); const t=b[b.length-1]; if (t) { t.click(); return t.innerText.trim(); } return null; }""")
            self.note(f"ISBN: clicked {clicked!r}")
            for _ in range(10):
                await p.wait_for_timeout(2000)
                txt = await p.inner_text("body")
                if "has been assigned a free KDP ISBN" in txt:
                    break
        txt = await p.inner_text("body")
        import re
        isbn = re.search(r"ISBN:\s*(\d{13})", txt)
        if isbn:
            self._remember({"isbn": isbn.group(1)})
        await self.radio_by_label("^" + re.escape(PAPER_LABEL[m["paper"]]) + "$")
        await self.radio_by_label("^No Bleed$")
        await self.radio_by_label("^Matte$")
        # trim (custom dropdown)
        cur = await p.evaluate("""() => { const el=[...document.querySelectorAll('*')].find(e=>e.children.length===0 && / x [\\d.]+ in \\(/.test((e.innerText||'').trim()) && e.offsetParent!==null && (e.innerText||'').length<40); return el ? el.innerText.trim() : ''; }""")
        want = TRIM_LABEL.get(m["trim"], m["trim"])
        if want not in cur:
            await p.get_by_text(cur, exact=False).first.click()
            await p.wait_for_timeout(800)
            await p.get_by_text(want, exact=False).first.click()
            await p.wait_for_timeout(1000)
        # files (titled delivery copies) — uploaded only when they changed:
        # a re-upload restarts KDP's multi-minute conversion from zero
        import hashlib as _hl
        write_delivery_copies(self.catalog, self.book["title"])
        out = OUTPUT_DIR / self.catalog
        interior_f = out / delivery_name(self.book["title"], "interior")
        cover_f = out / delivery_name(self.book["title"], "cover")
        digest = _hl.sha1(interior_f.read_bytes() + cover_f.read_bytes()).hexdigest()[:16]
        already = ((get_book_by_catalog(self.catalog)["data"].get("kdp") or {}).get("uploaded_digest"))
        if already == digest:
            self.note("manuscript + cover unchanged since the last upload — not re-uploading")
            uploaded_now = False
        else:
            await p.locator("input[type=file]").nth(0).set_input_files(str(interior_f))
            await p.wait_for_timeout(12000)
            await self.radio_by_label("^Upload a cover you already have")
            await p.locator('input[type=file][accept=".pdf"]').first.set_input_files(str(cover_f))
            await p.wait_for_timeout(12000)
            self._remember({"uploaded_digest": digest})
            self.note("manuscript + cover uploaded")
            uploaded_now = True
        # AI disclosure
        await self.radio_by_label("^Yes$")
        await p.wait_for_timeout(800)
        for field, choice in (("Texts", AI_DEFAULTS["texts"]), ("Images", AI_DEFAULTS["images"]), ("Translations", AI_DEFAULTS["translations"])):
            try:
                await p.locator(f'xpath=//*[normalize-space(text())="{field}"]/following::*[normalize-space(text())="Select"][1]').first.click(timeout=5000)
                await p.wait_for_timeout(600)
                await p.get_by_text(choice, exact=True).first.click(timeout=5000)
                await p.wait_for_timeout(600)
            except Exception as e:
                self.note(f"AI field {field}: {str(e)[:60]}")
        try:
            await self.fill('input[placeholder="e.g. ChatGPT"]', AI_DEFAULTS["texts_tool"])
            await self.fill('input[placeholder="e.g. DALL-E"]', AI_DEFAULTS["images_tool"])
        except Exception:
            pass
        # the new-upload confirmation KDP added ("I confirm that my answers are accurate")
        async def _save_enabled() -> bool:
            return bool(await p.evaluate("""() => { const b=document.querySelector('[data-testid="save-and-continue-button"]'); return !!b && !b.disabled; }"""))

        async def _confirm_box():
            """Tick 'I confirm that my answers are accurate' (a custom control —
            click its label once; judge by whether Save and Continue enables)."""
            try:
                t = p.get_by_text("I confirm that my answers are accurate", exact=False)
                if await t.count() == 0:
                    self.note("upload confirmation: not shown")
                    return
                await t.first.click(timeout=4000)
                await p.wait_for_timeout(1500)
                if await _save_enabled():
                    self.note("upload confirmation ticked")
                    return
                await t.first.click(timeout=4000)        # it was already ticked: restore
                await p.wait_for_timeout(1500)
                self.note("upload confirmation: toggled back" if await _save_enabled() else "upload confirmation: clicked, Save still disabled")
            except Exception as e:
                self.note(f"upload confirmation box: {str(e)[:60]}")
        await _confirm_box()
        await self.shot("content")

        async def _wait_processing(max_s: int = 1800):
            # KDP converts manuscript AND cover ("Checking your … for quality
            # issues…") — several minutes after a new upload. Wait it out.
            waited = 0
            while waited < max_s:
                body = await p.inner_text("body")
                if "Checking your" not in body and "processing your manuscript" not in body.lower():
                    return True
                await p.wait_for_timeout(10000)
                waited += 10
            return False
        await _wait_processing()
        await p.wait_for_timeout(2000)
        await _confirm_box()
        # previewer (required)
        await self.click_text("Launch Previewer", 5000)
        await _wait_processing()
        for _ in range(60):
            if "print-preview" in p.url:
                break
            await p.wait_for_timeout(10000)
        if "print-preview" not in p.url:
            await self.shot("previewer-pending")
            self.note("previewer did not open within the wait — KDP may still be converting; run again later")
            return "preview_issues"
        # the previewer renders the book page by page; wait for its verdict
        for _ in range(30):
            body = await p.inner_text("body")
            if "No Issue" in body or "issue" in body.lower() or "Approve" in body:
                break
            await p.wait_for_timeout(10000)
        await p.wait_for_timeout(3000)
        await self.shot("previewer")
        body = await p.inner_text("body")
        issues = "No Issue Selected" not in body and "No issues" not in body and "issue" in body.lower()
        self.note("previewer: " + ("issues flagged — review" if issues else "no issues"))
        if issues:
            self.note("previewer text: " + " ".join(body.split())[:400])
            return "preview_issues"          # never approve a flagged preview
        await self.click_text("Approve", 6000)
        # back on Content: KDP re-validates before it enables Save and Continue
        await p.wait_for_timeout(4000)
        if not await _save_enabled():
            await _confirm_box()
        for _ in range(24):
            if await _save_enabled():
                break
            await p.wait_for_timeout(5000)
        else:
            await self.shot("content-blocked", full=True)
            diag = await p.evaluate("""() => {
                const bad = [...document.querySelectorAll('[aria-invalid="true"], .error, [class*="error" i], [class*="alert" i]')]
                  .filter(e => e.offsetParent !== null && (e.innerText||'').trim())
                  .map(e => (e.innerText||'').trim().slice(0, 140));
                const warn = [...document.querySelectorAll('*')].filter(e => e.children.length===0 && e.offsetParent!==null && /preview and approve|required|must|please/i.test(e.innerText||''))
                  .map(e => e.innerText.trim().slice(0, 140));
                return {bad: bad.slice(0, 8), warn: [...new Set(warn)].slice(0, 8)};
            }""")
            self.note("Save and Continue stayed disabled: " + json.dumps(diag)[:600])
            return "preview_issues"
        await p.locator('[data-testid="save-and-continue-button"]').first.click(timeout=10000)
        await p.wait_for_timeout(4000)
        return "ok"

    async def pricing(self, m: dict):
        p = self.page
        pid = (get_book_by_catalog(self.catalog)["data"].get("kdp") or {}).get("paperback_id")
        await p.goto(f"https://kdp.amazon.com/en_US/print-setup/paperback/{pid}/pricing",
                     timeout=60000, wait_until="domcontentloaded")
        await p.wait_for_timeout(3000)
        if not await self.signed_in():
            return "needs_signin"
        await self.radio_by_label("All territories")
        await self.fill("#price-input-usd", f"{m['price']:.2f}")
        await p.keyboard.press("Tab")
        await p.wait_for_timeout(3000)
        await self.shot("pricing")
        if self.publish:
            await self.click_text("Publish Your Paperback Book", 8000)
            await self.shot("published")
            self.note("PUBLISH pressed")
            self._remember({"status": "submitted"})
            data = dict(get_book_by_catalog(self.catalog)["data"])
            pub = dict(data.get("publishing") or {})
            pub["uploaded_at"] = dt.datetime.now().isoformat(timespec="minutes")
            data["publishing"] = pub
            update_book(self.book["id"], data)
        else:
            await self.click_text("Save as Draft", 4000)
            self._remember({"status": "draft_complete_awaiting_publish"})
        return "ok"

    def _remember(self, patch: dict):
        fresh = get_book_by_catalog(self.catalog)
        data = dict(fresh["data"])
        data["kdp"] = {**(data.get("kdp") or {}), **patch}
        update_book(fresh["id"], data)

    # ── the run ──────────────────────────────────────────────────
    async def run(self) -> dict:
        gate = launch_gate(self.catalog)
        if not gate["ready"] and self.publish:
            return {"ok": False, "stopped_at": "gate", "blocking": gate["blocking_failures"],
                    "message": "The launch gate is not clear — nothing was published."}
        from playwright.async_api import async_playwright
        from .browser import PROFILE_DIR, UA, _ARGS, _STEALTH
        # one window at a time: the previous run's window (left open for
        # review) holds the profile lock — close it before we open ours
        global _OPEN
        try:
            if _OPEN:
                await _OPEN[0].close()
                await _OPEN[1].stop()
        except Exception:
            pass
        _OPEN = None
        pw = await async_playwright().start()
        ctx = await pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False, args=_ARGS, user_agent=UA,
            viewport={"width": 1400, "height": 900}, locale="en-US")
        await ctx.add_init_script(_STEALTH)
        _OPEN = (ctx, pw)
        self.page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        m = self.metadata()
        result = {"catalog": self.catalog, "gate": gate["ready"], "gate_blocking": gate["blocking_failures"]}
        try:
            for step, fn in (("details", self.details), ("content", self.content), ("pricing", self.pricing)):
                r = await fn(m)
                result[step] = r
                if r == "needs_signin":
                    result.update(ok=False, stopped_at=step,
                                  message="Amazon asked for the password — sign in in the open window, then run again.")
                    return result
                if r == "preview_issues":
                    result.update(ok=False, stopped_at=step,
                                  message="KDP's previewer flagged issues — review them in the open window; nothing was published.")
                    return result
            result["ok"] = True
            result["published"] = self.publish
        except Exception as e:
            result.update(ok=False, error=str(e)[:300])
            await self.shot("error")
        finally:
            result["log"] = self.log
            result["shots"] = str(self.shots)
            # leave the window open for the publisher's review
        return result


async def stage_paperback(catalog: str, publish: bool = False) -> dict:
    from .launch_gate import assert_publishable
    assert_publishable(catalog)
    return await Stager(catalog, publish=publish).run()
