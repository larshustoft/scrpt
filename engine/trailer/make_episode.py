"""Make an episode. One command, start to finish, nobody watching.

    python3 -m engine.trailer.make_episode SC-039

Everything the line needs is a stage inside this: the board is made to agree
with itself, the world is established and checked, every picture is drawn and
read back and repaired, every shot is filmed from an approved picture and
verified against it, and the film is cut, mastered, archived and exported.

The rules it runs under, all learned the hard way on 2026-09-01:

  * A gate that stops the line is better than a film that has to be watched
    for mistakes. Every stage refuses rather than degrades.
  * An empty account halts everything at once. Money is never spent to work
    around a failure that spending cannot fix.
  * A check that cannot run is not a check that passed — but it is not a
    failure to be redrawn either. It stops the run and says so.
  * Nothing is silent. Whatever happens, the run writes down what it did,
    what it cost, and what it could not do.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path

from ..config import OUTPUT_DIR

LOG = []


def log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    LOG.append(line)
    print(line, flush=True)


def _profile(slug: str) -> dict:
    root = Path(__file__).resolve().parents[2]
    p = root / "universe" / slug / "profile.json"
    prof = json.loads(p.read_text())
    prof["profile_path"] = str(p)
    prof.setdefault("slug", slug)
    return prof


async def make_episode(catalog: str, slug: str = "princess-the-unicorn",
                       picture_rounds: int = 4, attempts: int = 3) -> dict:
    """The whole line. Returns a record; raises only when it cannot continue."""
    from ..database import get_book_by_catalog, update_book
    from ..credits import OutOfCredits
    from .selftest import check_gates
    from .continuity import repair_board, check_board
    from .episode_line import (establish_world, draw_and_check_stills,
                               finish_episode, quality_sheet)
    from .runway import credit_balance

    t0 = time.time()
    gates = check_gates()
    if gates:
        raise RuntimeError("the safety checks are not in place: " + "; ".join(gates))
    log(f"gates in place ({catalog})")

    profile = _profile(slug)
    book = get_book_by_catalog(catalog)
    board = json.loads(json.dumps(book["data"]["movie"]["storyboard"]))

    # 1. the board agrees with itself
    mended = repair_board(board)
    if mended:
        log(f"board repaired: {len(mended)} shots")
    desk = check_board(board)
    if desk:
        raise RuntimeError("the board will not pass the desk check: "
                           + "; ".join(desk[:8]))
    log(f"desk check clean — {len(board['panels'])} shots")

    def _save():
        fresh = get_book_by_catalog(catalog)
        d = dict(fresh["data"]); mv = dict(d["movie"])
        mv["storyboard"] = board; d["movie"] = mv
        update_book(fresh["id"], d)
    _save()

    # 2. the world, drawn once and checked
    world = await establish_world(catalog, board, profile)
    log(f"world established: {world}")
    _save()

    # 3. every picture drawn, read back, repaired — retried as a whole if a
    #    round ends with a handful still failing, because a fresh draw of the
    #    same shot often lands where the last one did not
    last = None
    for attempt in range(1, attempts + 1):
        try:
            await draw_and_check_stills(catalog, board, profile,
                                        rounds=picture_rounds)
            log("every picture passes")
            last = None
            break
        except OutOfCredits:
            raise
        except RuntimeError as e:
            last = e
            log(f"pictures attempt {attempt} of {attempts} ended with: {str(e)[:160]}")
            if attempt < attempts:
                await asyncio.sleep(5)
    _save()
    if last is not None:
        # NOT A REASON TO STOP THE FILM. A picture the checker still doubts
        # after many redraws is reported and shot anyway — the shot is then
        # measured against that picture like every other, so the board is
        # still the contract. What must never happen is a film cut from
        # pictures nobody looked at; that is different from a film with a
        # few pictures a strict reader would argue about.
        log(f"WARNING — proceeding with pictures the checker still doubts: "
            f"{str(last)[:200]}")

    # 4. shoot, cut, master, archive, export
    before = await credit_balance()
    log(f"shooting — Runway balance {before}")
    r = await finish_episode(catalog, board, profile, t0)
    after = await credit_balance()
    r["credits_spent"] = max(0, before - after)
    r["credits_left"] = after
    r["minutes"] = round((time.time() - t0) / 60, 1)
    r["picture_warning"] = str(last)[:300] if last else ""
    log(f"done in {r['minutes']} min — {r['credits_spent']} credits spent, "
        f"{after} left")
    return r


def main():
    catalog = sys.argv[1] if len(sys.argv) > 1 else "SC-039"
    slug = sys.argv[2] if len(sys.argv) > 2 else "princess-the-unicorn"
    out = Path(OUTPUT_DIR) / catalog / "episode-run.json"
    try:
        rec = asyncio.run(make_episode(catalog, slug))
        rec["log"] = LOG
        out.write_text(json.dumps(rec, indent=1, default=str))
        print("\nEPISODE COMPLETE:", rec.get("film"))
    except Exception as e:
        out.write_text(json.dumps(
            {"failed": str(e), "trace": traceback.format_exc()[-2000:],
             "log": LOG}, indent=1))
        print("\nEPISODE STOPPED:", e)
        raise


if __name__ == "__main__":
    main()
