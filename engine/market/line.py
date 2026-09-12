"""
The factory line, end to end: a written book → published on KDP.

    accept → interior (even pages) → EPUB → front cover (generated if the
    book has none; series look kept) → print wrap → keyword research →
    release date (the slate planner) → paperback staged and PUBLISHED with
    the scheduled date → Kindle edition staged as a draft with the dated
    publish on the same day.

Standing order (2026-08-22): publish all the way, paperback and Kindle on
the same day. The line still stops — and says why — when a step fails:
a book the desk will not accept, a gate failure, a KDP sign-in prompt.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path

import httpx

from ..config import OUTPUT_DIR
from ..database import get_book_by_catalog, update_book

ENGINE = "http://127.0.0.1:8000/api/scrpt"
MAX_DESK_ROUNDS = 2


def _d(catalog: str) -> dict:
    return get_book_by_catalog(catalog)["data"]


def _patch(catalog: str, **fields):
    b = get_book_by_catalog(catalog)
    data = dict(b["data"])
    data.update(fields)
    update_book(b["id"], data)


async def _wait_job(job_id: str, handle=None, label: str = "", base: float = 0.0, span: float = 0.1) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        for _ in range(2000):
            r = await c.get(f"{ENGINE}/jobs/{job_id}")
            j = r.json()
            if handle and j.get("detail"):
                handle.progress(base + span * float(j.get("progress") or 0), label, j.get("detail"))
            if j.get("status") in ("done", "error"):
                return j
            await asyncio.sleep(6)
    return {"status": "error", "error": "timed out"}


async def run_line(catalog: str, handle=None, publish: bool = True) -> dict:
    from ..writing.acceptance import acceptance_job
    from ..interior.print_service import export_interior
    from ..interior.epub import build_epub
    from ..cover.front_cover import generate_front_cover
    from .launch_gate import launch_gate
    from .scheduler import suggest_schedule
    from .kdp_paperback import stage_paperback
    from .kdp_ebook import stage_kindle

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    title = book["title"]
    from ..writing.ledger import current_catalog as _cc
    _cc.set(catalog)                 # the ledger books every call to THIS title
    report: dict = {"catalog": catalog, "title": title, "steps": []}

    # A DAILY CAP PER BOOK (2026-09-08): Vector: Zero Point went round the line
    # three times in a day after two engine restarts and cost $15 in re-edits
    # and re-audits. No book may spend more than line_daily_cap_usd (default
    # $12) in one day; past that the line leaves it alone until tomorrow.
    try:
        import sqlite3 as _sq
        from ..config import DATABASE_PATH as _dbp
        from ..database import get_setting as _gs
        cap = float(_gs("line_daily_cap_usd", "12") or 12)
        _c = _sq.connect(str(_dbp))
        spent = _c.execute("select coalesce(sum(usd),0) from token_usage where catalog=? and at like ?",
                           (catalog, dt.date.today().isoformat() + "%")).fetchone()[0]
        _c.close()
        # an accepted book has nothing left to generate: its tail (wrap, keywords,
        # gate, upload) costs cents and is never held by the cap — the cap stops
        # generation, not publishing (three finished workbooks sat on it, 2026-09-08)
        _acc = ((_d(catalog).get("acceptance") or {}).get("verdict") == "accept")
        if spent >= cap and not _acc:
            report["steps"].append({"step": "budget", "ok": False, "detail": f"${spent:.2f} spent on this book today, cap ${cap:.0f} — resumes tomorrow"})
            report["stopped_at"] = "budget"
            return report
        if spent >= cap:
            report["steps"].append({"step": "budget", "ok": True, "detail": f"${spent:.2f} spent today (cap ${cap:.0f}) — accepted, finishing steps only"})
    except Exception:
        pass

    def step(name, ok, detail=""):
        report["steps"].append({"step": name, "ok": bool(ok), "detail": detail})
        if handle:
            handle.progress(min(0.99, 0.05 + 0.9 * len(report["steps"]) / 9), name, f"{title[:30]}: {detail or name}")

    # 0. WORKBOOKS (2026-09-08): pages, not chapters — no reader's desk, no line
    # edit, no continuity, no EPUB, no Kindle. Drawn and checked by the workbook line.
    wb = _d(catalog).get("workbook")
    if wb:
        if not wb.get("done"):
            step("acceptance", False, "the workbook's pages are not drawn yet"); report["stopped_at"] = "acceptance"; return report
        step("acceptance", True, f"workbook line · {len(wb.get('pages') or [])} pages drawn")
        from ..writing.workbook import build_workbook_interior
        res = await asyncio.to_thread(build_workbook_interior, catalog)
        if not (res.get("validation") or {}).get("passed", True):
            step("interior", False, "validation failed"); report["stopped_at"] = "interior"; return report
        step("interior", True, f"{res.get('page_count')} pages")
        step("epub", True, "print-only book — no ebook")
        return await _finish_print_book(catalog, report, step, handle, publish, title)

    # 0b. PICTURE BOOKS (2026-09-08): cover chosen by a vision judge, bible,
    # spreads, interior — then the print tail. No reader's desk, no line edit.
    ch = _d(catalog).get("childrens")
    if ch and (ch.get("spreads") or []):
        from ..writing.childrens_ready import ready_childrens, _art_complete
        if not (_d(catalog).get("childrens_ready") or {}).get("done") or not _art_complete(_d(catalog)):
            if handle:
                handle.progress(0.05, "childrens", f"{title[:30]}: cover, bible, spreads")
            r = await ready_childrens(catalog, handle)
            for st_ in r.get("steps", []):
                step(st_[0], st_[1], st_[2])
            if not r.get("ok"):
                report["stopped_at"] = r.get("stopped_at") or "childrens"; return report
        else:
            step("acceptance", True, "children's line · cover, bible and art complete")
        from ..interior.childrens_interior import build_interior as _ci
        res = await _ci(catalog, handle)
        step("interior", True, f"{res.get('pages')} pages")
        step("epub", True, "picture book — print first")
        _patch(catalog, print_only=True)
        return await _finish_print_book(catalog, report, step, handle, publish, title)

    # 1. THE READER'S DESK (2026-09-07, replaces the score loop): a triage read
    # of the opening, midpoint, climax and ending; targeted fixes only on the
    # chapters the reader named; then accept or shelve. Never a blanket rewrite.
    from ..writing.desk import ready_manuscript, line_edit, manuscript_sig
    acc = _d(catalog).get("acceptance") or {}
    tri = _d(catalog).get("triage") or {}
    if acc.get("verdict") == "accept" and (acc.get("accepted_by") == "reader's desk" or tri.get("sig") == manuscript_sig(_d(catalog))):
        step("acceptance", True, f"accept · reader's desk ({tri.get('verdict') or 'ship'})")
    elif acc.get("verdict") == "accept" and not tri:
        # accepted by the old editor: the reader still reads it once (cheap), and can only confirm or fix
        if handle:
            handle.progress(0.05, "triage", f"{title[:30]}: the reader reads")
        r = await ready_manuscript(catalog, handle or _Null())
        step("acceptance", r["accepted"], f"reader's desk: {r['verdict']} after {r['rounds']} fix round(s)")
        if not r["accepted"]:
            report["stopped_at"] = "acceptance"; return report
    else:
        if handle:
            handle.progress(0.05, "triage", f"{title[:30]}: the reader reads")
        r = await ready_manuscript(catalog, handle or _Null())
        step("acceptance", r["accepted"], f"reader's desk: {r['verdict']} after {r['rounds']} fix round(s)")
        if not r["accepted"]:
            report["stopped_at"] = "acceptance"; return report

    # 1b. THE LINE EDIT — every chapter once per manuscript version
    try:
        if handle:
            handle.progress(0.3, "line-edit", f"{title[:30]}: line edit")
        le = await line_edit(catalog, handle)
        step("line-edit", True, le.get("skipped") or f"{len(le.get('edited') or [])} chapters edited, {len(le.get('kept') or [])} kept")
    except Exception as e:
        step("line-edit", True, f"skipped: {str(e)[:80]}")

    # no rework on a relaunch: if the manuscript is unchanged since the last
    # insurance pass, skip it (every audit and rewrite costs money)
    import hashlib as _hl, json as _json
    ms_now = _d(catalog).get("manuscript") or {}
    ms_sig = _hl.sha1(_json.dumps([c.get("blocks") for c in ms_now.get("chapters", [])], sort_keys=True).encode()).hexdigest()[:16]
    acc_prev = _d(catalog).get("acceptance") or {}
    if acc_prev.get("insurance_sig") == ms_sig:
        step("continuity", True, "unchanged since the last pass — skipped")
    else:
      pass
    # insurance: a fresh continuity audit on the final text, rulings enforced —
    # two rounds, then what remains is advisory (an audit always finds something;
    # the gate must not be a loop the book can never leave)
    try:
        if acc_prev.get("insurance_sig") == ms_sig:
            raise _Skip()
        from ..writing.quality import continuity_audit, revise_chapter
        total_found = fixed = 0
        remaining = []
        for rnd in range(2):
            cont = await continuity_audit(catalog)
            issues = [c for c in cont.get("contradictions", []) if "canon facts list" not in str(c.get("chapters", ""))]
            total_found += len(issues)
            if not issues:
                remaining = []
                break
            for con in issues[:5]:
                chapters = [int("".join(ch for ch in tok if ch.isdigit())) for tok in str(con.get("chapters", "")).replace("ch", "").replace("Ch", "").split(",") if any(ch.isdigit() for ch in tok)]
                ruling = (con.get("fix") or "").strip()
                for idx in chapters[:3]:
                    if ruling:
                        try:
                            await revise_chapter(catalog, idx, [f"CANON RULING (enforce exactly): {ruling} Context: {con.get('problem','')} Change only what the ruling requires."], [])
                            fixed += 1
                        except Exception:
                            pass
            remaining = issues
        if remaining:
            cont = await continuity_audit(catalog)
            remaining = [c for c in cont.get("contradictions", []) if "canon facts list" not in str(c.get("chapters", ""))]
        b_ = get_book_by_catalog(catalog); data_ = dict(b_["data"]); a_ = dict(data_.get("acceptance") or {})
        a_["continuity"] = []
        a_["continuity_advisory"] = remaining
        ms_after = data_.get("manuscript") or {}
        a_["insurance_sig"] = _hl.sha1(_json.dumps([c.get("blocks") for c in ms_after.get("chapters", [])], sort_keys=True).encode()).hexdigest()[:16]
        data_["acceptance"] = a_; update_book(b_["id"], data_)
        step("continuity", True, f"{total_found} found, {fixed} rulings enforced, {len(remaining)} left as advisory")
        if fixed:
            # a ruling rewrote a chapter: line-edit THAT chapter again (facts
            # unchanged, so no second audit), then seal the signature on the final text
            try:
                le2 = await line_edit(catalog, handle)
                b_ = get_book_by_catalog(catalog); data_ = dict(b_["data"]); a_ = dict(data_.get("acceptance") or {})
                a_["insurance_sig"] = manuscript_sig(data_); data_["acceptance"] = a_; update_book(b_["id"], data_)
                step("line-edit", True, f"after rulings: {len(le2.get('edited') or [])} chapter(s) re-edited")
            except Exception as e:
                step("line-edit", True, f"after rulings: skipped ({str(e)[:60]})")
    except _Skip:
        pass
    except Exception as e:
        step("continuity", True, f"audit skipped: {str(e)[:80]}")

    # 2. interior + EPUB — built once per manuscript. A relaunch with the same
    # text (2026-09-05: Fracture Point went through the line six times in a
    # day) spent ~25 minutes re-typesetting before it ever reached KDP.
    out_dir = OUTPUT_DIR / catalog
    built = (_d(catalog).get("line") or {}).get("built") or {}
    have_files = all((out_dir / f).is_file() and (out_dir / f).stat().st_size > 0
                     for f in ("interior.pdf", "ebook.epub"))
    if built.get("sig") == ms_sig and have_files:
        step("interior", True, f"{built.get('pages')} pages — unchanged, kept")
        step("epub", True, "unchanged, kept")
    else:
        res = await export_interior(catalog)
        if not (res.get("validation") or {}).get("passed"):
            step("interior", False, "validation failed"); report["stopped_at"] = "interior"; return report
        step("interior", True, f"{res.get('page_count')} pages")
        try:
            build_epub(catalog)
            step("epub", True, "")
        except Exception as e:
            step("epub", False, str(e)[:120])
        _b = get_book_by_catalog(catalog); _data = dict(_b["data"])
        _data["line"] = {**(_data.get("line") or {}), "built": {"sig": ms_sig, "pages": res.get("page_count"),
                                                                 "at": dt.datetime.now().isoformat(timespec="minutes")}}
        update_book(_b["id"], _data)

    return await _finish_print_book(catalog, report, step, handle, publish, title, ms_sig)


async def _finish_print_book(catalog, report, step, handle, publish, title, ms_sig=None):
    """cover → wrap → keywords → release date → gate → paperback (→ Kindle unless print-only)."""
    from .launch_gate import launch_gate
    from .scheduler import suggest_schedule
    from .kdp_paperback import stage_paperback
    from .kdp_ebook import stage_kindle
    out_dir = OUTPUT_DIR / catalog
    print_only = bool(_d(catalog).get("print_only"))
    # 3. front cover (generate if missing) + print wrap
    front = OUTPUT_DIR / catalog / "cover-front.png"
    if not front.exists():
        if handle:
            handle.progress(0.35, "cover", f"{title[:30]}: designing the front cover")
        await generate_front_cover(catalog)
        if not front.exists():
            step("cover", False, "no front cover produced"); report["stopped_at"] = "cover"; return report
        step("cover", True, "front cover generated")
    else:
        step("cover", True, "front cover present")
    wrap_f = out_dir / "cover-wrap.pdf"
    built = (_d(catalog).get("line") or {}).get("built") or {}
    if ms_sig and built.get("sig") == ms_sig and built.get("wrap") and wrap_f.is_file() and wrap_f.stat().st_mtime >= front.stat().st_mtime:
        step("wrap", True, "unchanged, kept")
    else:
        async with httpx.AsyncClient(timeout=600) as c:
            r = await c.post(f"{ENGINE}/cover/print-wrap/{catalog}", json={})
            wrap = r.json() if r.status_code == 200 else {}
        if not (wrap.get("validation") or {}).get("passed"):
            step("wrap", False, str(wrap.get("detail") or wrap)[:160]); report["stopped_at"] = "wrap"; return report
        step("wrap", True, f"{wrap.get('pages_used')} pages, spine {(wrap.get('spec') or {}).get('spine_width_in')} in")
        _b = get_book_by_catalog(catalog); _data = dict(_b["data"])
        _data["line"] = {**(_data.get("line") or {}), "built": {**((_data.get("line") or {}).get("built") or {}), "wrap": True}}
        update_book(_b["id"], _data)

    # 4. keywords (live research, applied) — once per manuscript as well
    chosen = _d(catalog).get("keywords") or []
    if ms_sig and built.get("sig") == ms_sig and built.get("keywords") and len(chosen) >= 5:
        step("keywords", True, f"{len(chosen)} slots — kept")
    else:
        async with httpx.AsyncClient(timeout=900) as c:
            r = await c.post(f"{ENGINE}/keywords/research/{catalog}", json={"apply": True})
            kw = r.json() if r.status_code == 200 else {}
            if kw.get("job_id"):
                j = await _wait_job(kw["job_id"], handle, "keywords", 0.5, 0.05)
                kw = j.get("result") or {}
        chosen = kw.get("chosen") or _d(catalog).get("keywords") or []
        step("keywords", bool(chosen), f"{len(chosen)} slots")
        if chosen:
            _b = get_book_by_catalog(catalog); _data = dict(_b["data"])
            _data["line"] = {**(_data.get("line") or {}), "built": {**((_data.get("line") or {}).get("built") or {}), "keywords": True}}
            update_book(_b["id"], _data)

    # 5. house fields + release date
    d = _d(catalog)
    kind = d.get("kind") or (d.get("manuscript") or {}).get("kind") or "fiction"
    _patch(catalog, paper_type="cream_bw" if kind == "fiction" else "white_bw",
           list_price=float(d.get("list_price") or 12.99))
    rel = dict((_d(catalog).get("release") or {}))
    # a title KDP already holds keeps its date and its status: re-sending a
    # corrected file must not re-plan it (2026-09-12: two scheduled workbooks
    # were pushed a month out by a failed re-upload)
    _on_kdp = bool((_d(catalog).get("kdp") or {}).get("paperback_id"))
    if _on_kdp and rel.get("date") and rel.get("status") in ("submitted", "released"):
        step("release", True, rel["date"] + " (kept — already on KDP)")
        return await _finish_after_release(catalog, report, step, handle, publish, title, rel, print_only, out_dir)
    if not rel.get("date") or rel["date"] < dt.date.today().isoformat():
        plan = suggest_schedule()
        prop = next((p_ for p_ in plan.get("proposals", []) if p_.get("catalog") == catalog), None)
        if prop:
            rel["date"] = prop["date"]
        else:
            dday = dt.date.today() + dt.timedelta(days=14)
            while dday.weekday() != 1:          # Tuesdays
                dday += dt.timedelta(days=1)
            rel["date"] = dday.isoformat()
    rel.update(mode="scheduled", status="planned", planned_by=rel.get("planned_by") or "factory-line")
    _patch(catalog, release=rel)
    step("release", True, rel["date"])
    return await _finish_after_release(catalog, report, step, handle, publish, title, rel, print_only, out_dir)


async def _finish_after_release(catalog, report, step, handle, publish, title, rel, print_only, out_dir):
    """gate → paperback (→ Kindle) — the part of the line after the release date."""
    from .launch_gate import launch_gate
    from .kdp_paperback import stage_paperback
    from .kdp_ebook import stage_kindle

    # 6. the gate
    gate = launch_gate(catalog)
    if not gate["ready"]:
        step("gate", False, ", ".join(gate["blocking_failures"])); report["stopped_at"] = "gate"; return report
    step("gate", True, "clear")

    if not publish:
        report["ok"] = True
        return report

    # 7. paperback — published with the scheduled date
    if handle:
        handle.progress(0.7, "kdp", f"{title[:30]}: paperback on KDP")
    pb = await stage_paperback(catalog, publish=True)
    # KDP converts a fresh upload for minutes; "still converting" is not a
    # failure. Wait and try the stage again, up to three times, in the same run.
    for _try in range(3):
        if pb.get("ok") or not pb.get("retryable"):
            break
        if handle:
            handle.progress(0.75, "kdp", f"{title[:30]}: KDP is still converting — retry {_try + 1} in 10 min")
        await asyncio.sleep(600)
        pb = await stage_paperback(catalog, publish=True)
    if not pb.get("ok"):
        step("paperback", False, (pb.get("message") or pb.get("error") or json.dumps(pb)[:160])
             + (" · " + " | ".join(str(x)[:90] for x in (pb.get("log") or [])[-3:]) if pb.get("log") else ""))
        report["stopped_at"] = "paperback"; report["kdp"] = pb; return report
    step("paperback", True, f"published · release {rel['date']}")
    _patch(catalog, release={**rel, "status": "submitted", "submitted_at": dt.datetime.now().isoformat(timespec="minutes")})
    try:                                   # a run that died before writing its id down leaves a twin: remove it
        from .kdp_paperback import remove_duplicate_drafts
        dd = await remove_duplicate_drafts(catalog)
        if dd.get("deleted"):
            step("dedupe", True, f"removed {len(dd['deleted'])} duplicate draft(s)")
    except Exception as e:
        step("dedupe", True, f"skipped: {str(e)[:60]}")

    # 8. Kindle — drafted now, published on the same day by the scheduler
    if print_only:
        step("kindle", True, "print-only book — no Kindle edition")
        report["ok"] = True
        return report
    if handle:
        handle.progress(0.85, "kdp", f"{title[:30]}: Kindle edition")
    kb = await stage_kindle(catalog, publish=False)
    if not kb.get("ok"):
        step("kindle", False, kb.get("message") or kb.get("error") or json.dumps(kb)[:160])
        report["stopped_at"] = "kindle"; report["kindle"] = kb; return report
    b = get_book_by_catalog(catalog); data = dict(b["data"])
    data["kdp"] = {**(data.get("kdp") or {}), "kindle_publish_on": rel["date"]}
    update_book(b["id"], data)
    step("kindle", True, f"draft complete · publishes {rel['date']}")
    report["ok"] = True
    return report


class _Skip(Exception):
    pass


class _Null:
    def progress(self, *a, **k):
        pass


async def run_many(catalogs: list, handle=None, publish: bool = True) -> dict:
    """Books one after another — KDP is a single browser session."""
    out = []
    for i, c in enumerate(catalogs):
        if handle:
            handle.progress(i / max(1, len(catalogs)), "line", f"{c}: starting")
        try:
            out.append(await run_line(c, handle, publish=publish))
        except Exception as e:
            out.append({"catalog": c, "ok": False, "error": str(e)[:300]})
        r = out[-1]
        if r.get("stopped_at") in ("paperback", "kindle") and "sign in" in (json.dumps(r)).lower():
            break          # Amazon wants the password — the publisher must act first
    return {"books": out}
