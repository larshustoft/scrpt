"""The season line: keep every stage busy, never race the quality gates.

A season run serially is the sum of its episodes. Run as a line, it is
the length of its slowest stage — because episode two's stills draw while
episode one is shooting, and episode three's voices record while two
draws. The only thing that never overlaps is a person's judgement: the
acted read and the animatic are approved one at a time, in order.

    ep1  ─ draw ─┐─ shoot ─┐─ finish ─┐
    ep2      ─ draw ─┐─ shoot ─┐─ finish ─┐
    ep3          ─ draw ─┐─ shoot ─┐─ finish ─┐

Two workers, one for drawing (images) and one for filming (video),
because they queue on different services and never contend.
"""
from __future__ import annotations

import asyncio
import json
import time

from .episode_line import run_episode, finish_episode, quality_sheet, _log


async def run_season(catalogs: list, profile: dict, approve=None,
                     genre: str = "childrens") -> list:
    """`approve(catalog, animatic_path)` returns True to shoot.

    Default is to STOP at every animatic: a season may not shoot itself
    unwatched. Pass an approver that returns True only after a person has
    said so — never a function that always returns True."""
    draw_q: asyncio.Queue = asyncio.Queue()
    shoot_q: asyncio.Queue = asyncio.Queue()
    results, done = [], []

    async def drawer():
        while True:
            cat = await draw_q.get()
            if cat is None:
                draw_q.task_done(); break
            try:
                r = await run_episode(cat, profile, stop_at_animatic=True, genre=genre)
                _log(f"{cat}: animatic ready — {r.get('animatic')}")
                await shoot_q.put((cat, r))
            except Exception as e:
                _log(f"{cat}: drawing failed — {str(e)[:200]}")
                results.append({"catalog": cat, "error": str(e)[:300]})
            draw_q.task_done()

    async def shooter():
        while True:
            item = await shoot_q.get()
            if item is None:
                shoot_q.task_done(); break
            cat, drawn = item
            try:
                ok = True if approve is None else bool(approve(cat, drawn.get("animatic")))
                if not ok:
                    _log(f"{cat}: waiting for approval — not shot")
                    results.append({"catalog": cat, "waiting_for_approval": True,
                                    **drawn})
                else:
                    from .. import database as db
                    board = db.get_book_by_catalog(cat)["data"]["movie"]["storyboard"]
                    r = await finish_episode(cat, board, profile)
                    q = r.get("quality") or {}
                    _log(f"{cat}: finished — quality "
                         f"{'PASS' if q.get('passes') else 'NEEDS WORK'}")
                    results.append({"catalog": cat, **r})
            except Exception as e:
                _log(f"{cat}: finishing failed — {str(e)[:200]}")
                results.append({"catalog": cat, "error": str(e)[:300]})
            done.append(cat)
            shoot_q.task_done()

    for c in catalogs:
        draw_q.put_nowait(c)
    workers = [asyncio.create_task(drawer()), asyncio.create_task(shooter())]
    await draw_q.join()
    await shoot_q.join()
    for _ in workers:
        draw_q.put_nowait(None); shoot_q.put_nowait(None)
    await asyncio.gather(*workers, return_exceptions=True)
    return results
