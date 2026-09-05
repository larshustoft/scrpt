"""
The Kindle eBook stager — learned from the publisher's first pass
(2026-08-22, SC-006) and written to run unattended for the next books.

Flow: Bookshelf → "+ Create Kindle eBook" on the paperback (carries title,
subtitle, author, series, description, keywords) → categories (cascade +
placement boxes) → Save and Continue → Content: DRM off, EPUB upload,
cover JPG, AI questionnaire (custom radios + real selects), the post-upload
confirmation box, Save and Continue → Pricing: KDP Select, 70%, list price,
Save as Draft — and Publish only when asked.

House rules: never types credentials; never presses Publish without the
launch gate and an explicit instruction; a dated publish (the paperback's
release day) is run by the scheduler.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from ..config import OUTPUT_DIR
from ..database import get_book_by_catalog, update_book
from .browser import PROFILE_DIR, _ARGS, _STEALTH, context_kwargs
from .kdp_paperback import AI_DEFAULTS, BANNED
from .launch_gate import launch_gate

KINDLE_CATEGORY_DEFAULTS = {
    # genre preset -> [[cascade..., leaf], ...]  (Kindle Books tree)
    "historical_romance": [["Romance", "Historical Romance", "Regency"],
                           ["Romance", "Historical Romance", "General"],
                           ["Romance", "Enemies to Lovers"]],
    "romance": [["Romance", "Contemporary"], ["Romance", "Enemies to Lovers"]],
    "action_thriller": [["Mystery, Thriller & Suspense", "Thrillers & Suspense", "Suspense"],
                        ["Mystery, Thriller & Suspense", "Thrillers & Suspense", "Technothrillers"],
                        ["Literature & Fiction", "Action & Adventure", "Men's Adventure"]],
    "thriller": [["Mystery, Thriller & Suspense", "Thrillers & Suspense", "Suspense"],
                 ["Mystery, Thriller & Suspense", "Thrillers & Suspense", "Psychological Thrillers"]],
    "superhero": [["Science Fiction & Fantasy", "Fantasy", "Superhero"],
                  ["Science Fiction & Fantasy", "Science Fiction", "Superhero"]],
}
EBOOK_PRICE_DEFAULT = 4.99


def ebook_cover_jpg(catalog: str) -> Path:
    """Kindle wants a tall JPG (ideally 1600×2560): from the print-resolution front."""
    from PIL import Image
    from ..trailer.producer import front_cover_hires
    dest = OUTPUT_DIR / catalog / "ebook-cover.jpg"
    src = None
    try:
        src = front_cover_hires(catalog)
    except Exception:
        src = None
    if not src or not Path(src).exists():
        src = OUTPUT_DIR / catalog / "cover-front.png"
    im = Image.open(src).convert("RGB")
    h = 2560
    w = round(im.size[0] * h / im.size[1])
    im.resize((w, h), Image.LANCZOS).save(dest, "JPEG", quality=92, optimize=True)
    return dest


class KindleStager:
    def __init__(self, catalog: str, publish: bool = False,
                 force_interior: bool = False):
        self.catalog = catalog
        self.publish = publish
        # force_interior: re-upload the EPUB even if the page says one is
        # already there — the antidote to a draft contaminated with another
        # book's interior (the Lake Como/Villa Bellariva id mixup, 2026-08-27).
        self.force_interior = force_interior
        self.book = get_book_by_catalog(catalog)
        self.d = self.book["data"]
        self.log: list[str] = []
        self.shots = OUTPUT_DIR / catalog / "kdp-ebook"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.n = 0
        self.page = None

    def note(self, m):
        self.log.append(m)

    async def shot(self, label, full=False):
        self.n += 1
        try:
            await self.page.screenshot(path=str(self.shots / f"{self.n:02d}-{label}.png"), full_page=full)
        except Exception:
            pass

    def _remember(self, patch: dict):
        fresh = get_book_by_catalog(self.catalog)
        data = dict(fresh["data"])
        prev = data.get("kdp") or {}
        data["kdp"] = {**prev, **patch}
        update_book(fresh["id"], data)
        # see the paperback note: a new title id spends one of the ten
        # creations KDP allows per format each week, success or not
        new_id = patch.get("kindle_id")
        if new_id and prev.get("kindle_id") != new_id:
            try:
                from .kdp_quota import record_creation
                record_creation(self.catalog, "kindle", new_id)
            except Exception:
                pass

    async def signed_in(self) -> bool:
        from .kdp_signin import _is_signin_url
        if not _is_signin_url(self.page.url):
            return True
        # SIGNS ITSELF IN (2026-09-05): the password lives in the keychain, put
        # there through Settings → Amazon KDP; a sign-in page is no longer a stop.
        from .kdp_signin import auto_signin
        r = await auto_signin(self.page, self.note)
        return r in ("signed_in", "signed_in_after")

    # ── details ──────────────────────────────────────────────────
    async def details(self) -> str:
        p = self.page
        kdp = self.d.get("kdp") or {}
        kid = kdp.get("kindle_id")
        pid = kdp.get("paperback_id")
        if kid:
            await p.goto(f"https://kdp.amazon.com/en_US/title-setup/kindle/{kid}/details", timeout=60000, wait_until="domcontentloaded")
        elif pid:
            await p.goto("https://kdp.amazon.com/en_US/bookshelf", timeout=60000, wait_until="domcontentloaded")
            await p.wait_for_timeout(6000)
            if not await self.signed_in():
                return "needs_signin"
            await p.locator(f"#zme-indie-bookshelf-dual-digital-missing_print-add-digital-format-{pid}-action-button-announce").click(timeout=15000)
        else:
            await p.goto("https://kdp.amazon.com/en_US/title-setup/kindle/new/details", timeout=60000, wait_until="domcontentloaded")
        await p.wait_for_timeout(8000)
        # Claim the id before any of the work below can fail. KDP has already
        # created the title by this point and already spent one of the ten
        # Kindle creations it allows per week; writing the id down only after
        # Save and Continue meant a failure in between stranded the draft and
        # the next run minted a second title for the same book.
        for _ in range(4):
            _m = re.search(r"/title-setup/kindle/([A-Za-z0-9]{6,})/", p.url)
            if _m and _m.group(1).lower() != "new":
                if (self.d.get("kdp") or {}).get("kindle_id") != _m.group(1):
                    self._remember({"kindle_id": _m.group(1)})
                    self.note(f"kindle draft {_m.group(1)} — later runs will resume it")
                break
            await p.wait_for_timeout(1500)
        if not await self.signed_in():
            return "needs_signin"
        # the paperback carries title, subtitle, author, series, description, keywords.
        # keep the keywords in sync with the record (compliant, 7)
        kws = [k for k in (self.d.get("keywords") or []) if not any(t in k.lower() for t in BANNED)][:7]
        for i, kw in enumerate(kws):
            try:
                await p.locator(f"#data-keywords-{i}").fill(kw, timeout=4000)
            except Exception:
                pass
        # categories
        text = await p.evaluate("() => document.body.innerText")
        if "Your title's current categories" in text and "Edit categories" in text:
            self.note("categories already set — kept")
        else:
            cats = kdp.get("kindle_categories_plan") or KINDLE_CATEGORY_DEFAULTS.get(self.d.get("genre_preset") or "", [])
            cats = [c.split(" > ") if isinstance(c, str) else c for c in cats]
            placed = await self._place_categories(cats)
            self.note(f"categories placed: {placed}")
        await self.shot("details", full=True)
        await p.locator("#save-and-continue-announce").click(timeout=10000)
        await p.wait_for_timeout(9000)
        m = re.search(r"/title-setup/kindle/([A-Z0-9]+)/", p.url)
        if m and m.group(1) != "new":
            self._remember({"kindle_id": m.group(1)})
            self.note(f"kindle id {m.group(1)}")
        if "/content" not in p.url:
            await self.shot("details-blocked", full=True)
            return "blocked"
        return "ok"

    async def _place_categories(self, cats: list) -> int:
        """Same picker as the paperback's: cascading selects, placement
        checkboxes, exact match first and containment second (2026-09-05:
        the Kindle tree also says "Thrillers & Suspense" now, and an exact
        "Thrillers" placed nothing, which KDP refuses). A book that matches
        nothing gets "General" under its first resolvable path."""
        p = self.page
        SEL = """(t) => {
            const ss = [...document.querySelectorAll('select')].filter(s => s.offsetParent !== null && /react-aui/.test(s.name || s.id));
            const s = ss[ss.length - 1]; if (!s) return 'noselect';
            const opts = [...s.options].filter(o => o.text.trim() !== 'Select one');
            const norm = x => x.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
            const w = norm(t); const first = w.split(' ')[0];
            let o = opts.find(o => norm(o.text) === w) || opts.find(o => norm(o.text).includes(w)) || opts.find(o => w.includes(norm(o.text)))
                 || opts.find(o => norm(o.text).split(' ').includes(first));
            if (!o) return 'nooption:' + opts.map(o => o.text.trim()).join(';');
            s.value = o.value; s.dispatchEvent(new Event('change', {bubbles: true})); return 'ok:' + o.text.trim(); }"""
        LEAF = """(t) => {
            const labels = [...document.querySelectorAll('[role=dialog] label, [aria-modal=true] label')].filter(l => l.offsetParent !== null);
            const norm = x => x.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
            const w = norm(t); const first = w.split(' ')[0];
            let l = labels.find(l => norm(l.innerText) === w) || labels.find(l => norm(l.innerText).includes(w)) || labels.find(l => w.includes(norm(l.innerText)) && norm(l.innerText).length > 3)
                 || labels.find(l => norm(l.innerText).split(' ').includes(first) && first.length > 3);
            if (!l) return 'noleaf:' + labels.map(l => l.innerText.trim()).join(';');
            const box = l.querySelector('input[type=checkbox]') || document.getElementById(l.htmlFor || '');
            if (box && box.checked) return 'already:' + l.innerText.trim();
            l.click(); return 'ok:' + l.innerText.trim(); }"""
        COUNT = """() => { const m = document.body.innerText.match(/(\\d) out of 3 category placements/); return m ? +m[1] : -1; }"""
        btn = p.locator("#categories-modal-button")
        for _ in range(20):
            try:
                if await btn.is_enabled():
                    break
            except Exception:
                pass
            await p.wait_for_timeout(1500)
        else:
            self.note("categories button never became enabled — categories left as they are")
            return 0
        await btn.click(timeout=10000)
        await p.wait_for_timeout(2500)
        placed = 0
        first_group = True
        chains = [list(c) for c in cats[:3]]
        for attempt_general in (False, True):
            for chain in chains:
                if placed >= 3:
                    break
                path, leaf = chain[:-1], (chain[-1] if not attempt_general else "General")
                if not first_group:
                    try:
                        await p.get_by_role("button", name="Add another category").click(timeout=6000)
                        await p.wait_for_timeout(1500)
                    except Exception:
                        pass
                first_group = False
                ok = True
                for level in path:
                    r = await p.evaluate(SEL, level)
                    await p.wait_for_timeout(1500)
                    if not r.startswith("ok"):
                        self.note(f"category level '{level}' not in the Kindle tree ({r[:90]})")
                        ok = False; break
                if not ok:
                    continue
                r = await p.evaluate(LEAF, leaf)
                await p.wait_for_timeout(900)
                if r.startswith("ok") or r.startswith("already"):
                    n = await p.evaluate(COUNT)
                    placed = n if n >= 0 else placed + 1
                    self.note(f"category placed: {' > '.join(path)} > {r.split(':', 1)[1]}")
                else:
                    self.note(f"category leaf '{leaf}' not under {' > '.join(path)} ({r[:80]})")
            if placed:
                break
            self.note("no planned category exists in the Kindle tree — placing General")
        await p.get_by_role("button", name="Save categories").click(timeout=8000)
        await p.wait_for_timeout(2500)
        return placed

    # ── content ──────────────────────────────────────────────────
    async def content(self) -> str:
        p = self.page
        kid = (get_book_by_catalog(self.catalog)["data"].get("kdp") or {}).get("kindle_id")
        await p.goto(f"https://kdp.amazon.com/en_US/title-setup/kindle/{kid}/content", timeout=60000, wait_until="domcontentloaded")
        await p.wait_for_timeout(8000)
        if not await self.signed_in():
            return "needs_signin"
        await p.evaluate("""() => { const r=[...document.querySelectorAll('input[name="data[is_drm]-radio"]')].find(x=>x.value==='false'); r && r.click(); }""")
        # Any file chooser the page manages to open gets answered in-process —
        # a NATIVE macOS picker froze a run dead (2026-08-27): automation
        # cannot see OS dialogs, so one stray click hangs the line forever.
        cover_jpg = str(ebook_cover_jpg(self.catalog))
        epub = OUTPUT_DIR / self.catalog / "ebook.epub"
        async def _answer_chooser(fc):
            try:
                name = ((await fc.element.get_attribute("id")) or "").lower()
                await fc.set_files(str(epub) if "interior" in name else cover_jpg)
                self.note(f"file chooser intercepted ({name or 'unknown input'})")
            except Exception:
                pass
        p.on("filechooser", _answer_chooser)
        body = await p.evaluate("() => document.body.innerText")
        if self.force_interior or "uploaded successfully" not in body.split("Kindle eBook Cover")[0]:
            await p.locator("#data-assets-interior-file-upload-AjaxInput").set_input_files(str(epub))
            await p.wait_for_timeout(15000)
            self.note("EPUB uploaded" + (" (forced re-upload)" if self.force_interior else ""))
        # RE-READ the page before deciding about the cover: the first body
        # snapshot goes stale the moment the EPUB upload rewrites the page,
        # and acting on it made us re-click an upload control that was
        # already done ("Cover uploaded successfully" was on screen).
        body = await p.evaluate("() => document.body.innerText")
        if "Cover uploaded successfully" not in body:
            await p.locator("#data-assets-cover-file-upload-AjaxInput").set_input_files(cover_jpg)
            await p.wait_for_timeout(15000)
            body = await p.evaluate("() => document.body.innerText")
            if "Cover uploaded successfully" not in body:
                await p.evaluate("""() => { const el=[...document.querySelectorAll('label, span, div')].find(e => e.children.length<4 && /Upload a cover you already have/i.test(e.innerText||'') && e.offsetParent!==null && (e.innerText||'').length<120); const inp=el && (el.querySelector('input')||el.closest('label')?.querySelector('input')); (inp||el) && (inp||el).click(); }""")
                await p.wait_for_timeout(1500)
                await p.locator("#data-assets-cover-file-upload-AjaxInput").set_input_files(cover_jpg)
                await p.wait_for_timeout(15000)
            self.note("cover uploaded")
        # AI questionnaire: custom radios, real selects
        q = p.locator(".ditto-questionnaire").first
        yes = q.get_by_role("radio", name="Yes").first
        if (await yes.get_attribute("aria-checked")) != "true":
            await yes.click(timeout=8000)
            await p.wait_for_timeout(2000)
        await p.select_option("#generative-ai-questionnaire-text", label=AI_DEFAULTS["texts"])
        await p.select_option("#generative-ai-questionnaire-images", label=AI_DEFAULTS["images"])
        await p.select_option("#generative-ai-questionnaire-translations", label=AI_DEFAULTS["translations"])
        await p.wait_for_timeout(1000)
        for ph, val in (('input[placeholder="e.g. ChatGPT"]', AI_DEFAULTS["texts_tool"]),
                        ('input[placeholder="e.g. DALL-E"]', AI_DEFAULTS["images_tool"])):
            loc = p.locator(f".ditto-questionnaire {ph}").first
            if await loc.count():
                await loc.fill("")
                await loc.type(val, delay=20)
        self.note("AI disclosure set")
        # wait for KDP's processing, then the post-upload confirmation
        for _ in range(90):
            body = await p.evaluate("() => document.body.innerText")
            if "Processing your file" not in body and "processing" not in body.lower()[:2000]:
                break
            await p.wait_for_timeout(10000)
        # A re-uploaded manuscript makes KDP demand the "I confirm that my
        # answers are accurate" box in EVERY section that shows one (AI +
        # Accessibility at least). Tick the actual checkboxes, all of them —
        # clicking the label text toggled nothing and blocked the page.
        async def _tick_confirms():
            # 2026-09-05: the box is no longer an <input>. KDP draws it as
            # <div role="checkbox" aria-checked="false"> inside the label, so
            # both shapes are ticked — anything unticked whose label reads
            # "I confirm that my answers are accurate".
            return await p.evaluate("""() => {
                let n = 0;
                const re = /confirm that my answers are accurate/i;
                for (const box of document.querySelectorAll('input[type=checkbox]')) {
                    const wrap = box.closest('div, label, section');
                    const t = wrap ? (wrap.innerText || '') : '';
                    if (re.test(t) && !box.checked) { box.click(); n++; }
                }
                for (const box of document.querySelectorAll('[role=checkbox]')) {
                    if (box.getAttribute('aria-checked') === 'true' || box.offsetParent === null) continue;
                    const wrap = box.closest('label') || box.parentElement;
                    const t = wrap ? (wrap.innerText || '') : '';
                    if (re.test(t)) { box.click(); n++; }
                }
                return n;
            }""")
        n = await _tick_confirms()
        if n:
            self.note(f"confirmation boxes ticked: {n}")
            await p.wait_for_timeout(1200)
        await self.shot("content", full=True)
        await p.locator("#save-and-continue-announce").first.click(timeout=10000)
        await p.wait_for_timeout(10000)
        if "/pricing" not in p.url:
            n = await _tick_confirms()
            if n:
                self.note(f"confirmation boxes ticked (second pass): {n}")
                await p.wait_for_timeout(1200)
                await p.locator("#save-and-continue-announce").first.click(timeout=10000)
                await p.wait_for_timeout(10000)
        if "/pricing" not in p.url:
            await self.shot("content-blocked", full=True)
            diag = await p.evaluate("""() => [...document.querySelectorAll('[role=alert], .a-alert-error, [aria-invalid="true"]')].filter(e=>e.offsetParent!==null).map(e=>(e.innerText||'').trim().slice(0,160))""")
            self.note("content blocked: " + json.dumps(diag)[:400])
            return "blocked"
        return "ok"

    # ── pricing ──────────────────────────────────────────────────
    async def pricing(self) -> str:
        p = self.page
        kid = (get_book_by_catalog(self.catalog)["data"].get("kdp") or {}).get("kindle_id")
        await p.goto(f"https://kdp.amazon.com/en_US/title-setup/kindle/{kid}/pricing", timeout=60000, wait_until="domcontentloaded")
        await p.wait_for_timeout(8000)
        if not await self.signed_in():
            return "needs_signin"
        sel = p.locator("#data-is-select")
        if await sel.count() and not await sel.is_checked():
            await sel.check(timeout=5000)
            await p.wait_for_timeout(1500)
        await p.evaluate("""() => { const r=[...document.querySelectorAll('input[name="data[digital][royalty_rate]-radio"]')].find(x=>x.value==='70_PERCENT'); r && r.click(); }""")
        await p.wait_for_timeout(1500)
        price = float((self.d.get("kdp") or {}).get("ebook_price") or EBOOK_PRICE_DEFAULT)
        # Amazon pays the 70% rate only from $2.99 to $9.99. Above that the
        # tier selected below is not on offer and the book quietly earns 35%,
        # so the price has to stay inside the band the royalty assumes.
        price = min(9.99, max(2.99, price))
        us = p.locator('input[name="data[digital][channels][amazon][US][price_vat_inclusive]"]').first
        await us.click()
        await us.fill("")
        await us.type(f"{price:.2f}", delay=40)
        await us.press("Tab")
        await p.wait_for_timeout(4000)
        self.note(f"KDP Select on · 70% · ${price:.2f}")
        await self.shot("pricing", full=True)
        if self.publish:
            # KDP renders sixteen copies of this id; strict mode refuses to
            # pick — the first visible one is the real button
            await p.locator("#save-and-publish-announce").first.click(timeout=10000)
            await p.wait_for_timeout(8000)
            await self.shot("published")
            self.note("PUBLISH pressed")
            self._remember({"kindle_status": "submitted_for_publishing",
                            "kindle_submitted_at": dt.datetime.now().isoformat(timespec="minutes")})
        else:
            await p.locator("#save-announce").first.click(timeout=10000)
            await p.wait_for_timeout(6000)
            self._remember({"kindle_status": "draft_complete_awaiting_publish", "ebook_price": price})
            self.note("saved as draft")
        return "ok"

    async def run(self) -> dict:
        gate = launch_gate(self.catalog)
        if not gate["ready"] and self.publish:
            return {"ok": False, "stopped_at": "gate", "blocking": gate["blocking_failures"],
                    "message": "The launch gate is not clear — nothing was published."}
        from playwright.async_api import async_playwright
        from . import kdp_paperback as _pb
        try:
            if _pb._OPEN:
                await _pb._OPEN[0].close()
                await _pb._OPEN[1].stop()
        except Exception:
            pass
        _pb._OPEN = None
        pw = await async_playwright().start()
        ctx = await pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False,  # HEADFUL, deliberately: the first headless STAGING run got the
            # session signed out mid-flight (2026-08-27) — Amazon re-challenges heavy
            # flows in headless. Reads/scans may run headless; uploads keep a window.
            args=_ARGS,
            **context_kwargs(viewport={"width": 1400, "height": 900}))
        await ctx.add_init_script(_STEALTH)
        _pb._OPEN = (ctx, pw)
        self.page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        result = {"catalog": self.catalog, "gate": gate["ready"]}
        try:
            for step, fn in (("details", self.details), ("content", self.content), ("pricing", self.pricing)):
                r = await fn()
                result[step] = r
                if r == "needs_signin":
                    result.update(ok=False, stopped_at=step, message="Amazon asked for the password — sign in in the open window, then run again.")
                    return result
                if r == "blocked":
                    result.update(ok=False, stopped_at=step, message=f"KDP did not accept the {step} page — see the screenshots.")
                    return result
            result["ok"] = True
            result["published"] = self.publish
        except Exception as e:
            result.update(ok=False, error=str(e)[:300])
            await self.shot("error", full=True)
        finally:
            result["log"] = self.log
        return result


async def stage_kindle(catalog: str, publish: bool = False,
                       force_interior: bool = False) -> dict:
    from .launch_gate import assert_publishable
    assert_publishable(catalog)
    return await KindleStager(catalog, publish=publish,
                              force_interior=force_interior).run()


async def publish_kindle_only(catalog: str) -> dict:
    """The dated press: the draft is complete; open Pricing and publish."""
    from .launch_gate import assert_publishable
    assert_publishable(catalog)
    return await KindleStager(catalog, publish=True).run()
