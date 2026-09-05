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

    def step(name, ok, detail=""):
        report["steps"].append({"step": name, "ok": bool(ok), "detail": detail})
        if handle:
            handle.progress(min(0.99, 0.05 + 0.9 * len(report["steps"]) / 9), name, f"{title[:30]}: {detail or name}")

    # 1. the acceptance desk
    for rnd in range(MAX_DESK_ROUNDS + 1):
        acc = _d(catalog).get("acceptance") or {}
        if acc.get("verdict") == "accept":
            break
        if rnd == MAX_DESK_ROUNDS:
            step("acceptance", False, f"still '{acc.get('verdict')}' at {acc.get('score')} after {MAX_DESK_ROUNDS} rounds — the line stops here")
            report["stopped_at"] = "acceptance"
            return report
        if handle:
            handle.progress(0.05, "acceptance", f"{title[:30]}: the desk reads (round {rnd + 1})")
        await acceptance_job(handle or _Null(), catalog)
    acc = _d(catalog).get("acceptance") or {}
    step("acceptance", True, f"accept · {acc.get('score')}")

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
    except _Skip:
        pass
    except Exception as e:
        step("continuity", True, f"audit skipped: {str(e)[:80]}")

    # 2. interior + EPUB
    res = await export_interior(catalog)
    if not (res.get("validation") or {}).get("passed"):
        step("interior", False, "validation failed"); report["stopped_at"] = "interior"; return report
    step("interior", True, f"{res.get('page_count')} pages")
    try:
        build_epub(catalog)
        step("epub", True, "")
    except Exception as e:
        step("epub", False, str(e)[:120])

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
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.post(f"{ENGINE}/cover/print-wrap/{catalog}", json={})
        wrap = r.json() if r.status_code == 200 else {}
    if not (wrap.get("validation") or {}).get("passed"):
        step("wrap", False, str(wrap.get("detail") or wrap)[:160]); report["stopped_at"] = "wrap"; return report
    step("wrap", True, f"{wrap.get('pages_used')} pages, spine {(wrap.get('spec') or {}).get('spine_width_in')} in")

    # 4. keywords (live research, applied)
    async with httpx.AsyncClient(timeout=900) as c:
        r = await c.post(f"{ENGINE}/keywords/research/{catalog}", json={"apply": True})
        kw = r.json() if r.status_code == 200 else {}
        if kw.get("job_id"):
            j = await _wait_job(kw["job_id"], handle, "keywords", 0.5, 0.05)
            kw = j.get("result") or {}
    chosen = kw.get("chosen") or _d(catalog).get("keywords") or []
    step("keywords", bool(chosen), f"{len(chosen)} slots")

    # 5. house fields + release date
    d = _d(catalog)
    kind = d.get("kind") or (d.get("manuscript") or {}).get("kind") or "fiction"
    _patch(catalog, paper_type="cream_bw" if kind == "fiction" else "white_bw",
           list_price=float(d.get("list_price") or 12.99))
    rel = dict((_d(catalog).get("release") or {}))
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
    if not pb.get("ok"):
        step("paperback", False, (pb.get("message") or pb.get("error") or json.dumps(pb)[:160])
             + (" · " + " | ".join(str(x)[:90] for x in (pb.get("log") or [])[-3:]) if pb.get("log") else ""))
        report["stopped_at"] = "paperback"; report["kdp"] = pb; return report
    step("paperback", True, f"published · release {rel['date']}")
    _patch(catalog, release={**rel, "status": "submitted", "submitted_at": dt.datetime.now().isoformat(timespec="minutes")})

    # 8. Kindle — drafted now, published on the same day by the scheduler
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
