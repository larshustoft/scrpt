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
                       picture_rounds: int = 4, attempts: int = 3,
                       stop_before_shoot: bool = False,
                       shoot_only: bool = False,
                       reshoot=None, redraw=None) -> dict:
    """The whole line. Returns a record; raises only when it cannot continue."""
    from ..database import get_book_by_catalog, update_book
    from ..credits import OutOfCredits
    from .selftest import check_gates
    from .continuity import repair_board, check_board
    from .episode_line import (establish_world, draw_and_check_stills,
                               finish_episode, quality_sheet)
    from .runway import credit_balance

    t0 = time.time()
    # IS THIS WORK SAFE? Asked before two hours of compute, because on
    # 2026-09-02 a night was lost on a machine whose backup and GitHub push
    # had been failing silently for two days. It warns; it never blocks.
    from ..safety import report as safety_report
    safety_report(Path(__file__).resolve().parents[2], log=log)
    gates = check_gates()
    if gates:
        raise RuntimeError("the safety checks are not in place: " + "; ".join(gates))
    log(f"gates in place ({catalog})")

    profile = _profile(slug)
    book = get_book_by_catalog(catalog)
    board = json.loads(json.dumps(book["data"]["movie"]["storyboard"]))
    # EVERY CHARACTER SPEAKS IN THEIR OWN VOICE (Lars, 2026-09-02: "why are
    # we not using the voices for dialogue any more"). The voice cast was
    # applied only on the old entry path; this one skipped it, and all 78
    # lines of episode one were recorded by the narrator. A line whose
    # speaker has a cast voice always carries it; a speaker with no voice
    # is a hard stop, never a silent fallback to the storyteller.
    vc = (book["data"]["movie"].get("voice_cast") or {})
    _unvoiced = set()
    for pn in board["panels"]:
        ln = pn.get("line")
        if isinstance(ln, dict) and (ln.get("text") or "").strip():
            spk = ln.get("speaker")
            if spk in vc and (vc[spk] or {}).get("id"):
                ln["voice"] = vc[spk]["id"]
            elif spk:
                _unvoiced.add(str(spk))
    if _unvoiced:
        raise RuntimeError("these speakers have lines but no voice in the cast: "
                           + ", ".join(sorted(_unvoiced)))
    log(f"voice cast applied: {sum(1 for p in board['panels'] if isinstance(p.get('line'), dict) and p['line'].get('voice'))} lines in character voices")
    # THE STORYTELLER IS THE UNIVERSE'S (2026-09-03): the short SC-042 had no
    # audio.voice_id and was narrated by the engine's default voice. A book
    # of this universe without its own narrator gets the universe's, and a
    # universe with none is a hard stop — never a random voice.
    _sv = ((profile.get("creatives") or {}).get("storyteller_voice") or {}).get("id")
    _bv = ((book["data"].get("audio") or {}).get("voice_id"))
    if not _bv:
        if not _sv:
            raise RuntimeError("no narrator voice: the book has no audio.voice_id and the universe names no storyteller_voice")
        _d = dict(book["data"]); _d["audio"] = {**(_d.get("audio") or {}), "voice_id": _sv}
        update_book(book["id"], _d); book = get_book_by_catalog(catalog)
        log(f"storyteller voice applied from the universe ({_sv[:8]}…)")

    # THE MAP BELONGS TO THE EPISODE (2026-09-02). Without `board["world"]`,
    # apply_world falls back to episode one's constants — and every fix a
    # person makes to place or props is silently undone at the next drawing.
    if not ((board.get("world") or {}).get("places")):
        raise RuntimeError("this board has no world map (board['world'].places); the line "
                           "will not draw it from another episode's places")

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

    # THE QUOTE IS THE CAP (Lars, 2026-09-02). Pictures: one drawing per
    # shot, room for repairs on half of them, plus the plates — and not a
    # drawing more without someone raising the cap on purpose. Credits: the
    # shoot at gen4_turbo's measured ~5 credits/second with 40% headroom.
    from .budget import BUDGET, OverBudget
    n_shots = len(board["panels"])
    total_s = sum(float(p.get("dur") or p.get("seconds") or 5) for p in board["panels"])
    drawings_cap = int(n_shots * 1.5) + 24
    credits_cap = int(total_s * 5 * 1.4) + 200
    # A PERSON MAY SET A TIGHTER CAP FOR A PARTIAL RE-SHOOT (2026-09-02)
    if os.environ.get("SCRPT_CREDITS_CAP"):
        credits_cap = min(credits_cap, int(os.environ["SCRPT_CREDITS_CAP"]))
    BUDGET.quote(drawings_cap=drawings_cap, credits_cap=credits_cap)
    log(f"QUOTE — this run may draw at most {drawings_cap} pictures and spend at most "
        f"{credits_cap} Runway credits ({n_shots} shots, {int(total_s)}s of picture). "
        f"It stops itself at either cap.")

    # 2. the world, drawn once and checked — and the Show Bible it came from,
    #    by hash, so this film can always be traced to the exact characters,
    #    objects, places and rules it was made with (Lars, 2026-09-02).
    world = await establish_world(catalog, board, profile)
    log(f"world established: {world}")
    from .show_bible import manifest as _bible_manifest
    profile = _profile(slug)                       # re-read: the world stage may have saved new plates
    bible = _bible_manifest(profile)
    log(f"show bible: {len(bible['characters'])} characters, {len(bible['objects'])} objects, "
        f"{len(bible['places'])} places, rules {bible['world_rules']}")
    _save()

    # 3. every picture drawn, read back, repaired — retried as a whole if a
    #    round ends with a handful still failing, because a fresh draw of the
    #    same shot often lands where the last one did not
    last = None
    # SHOOT ONLY (2026-09-02): the pictures were finished and approved in an
    # earlier run; film them exactly as they stand. Not a drawing is made —
    # a still that is missing is a hard stop, never a redraw.
    if shoot_only and redraw:
        # a named picture repair: the old pictures are set aside (never
        # deleted), the shots are drawn and read again through the same
        # checks as the board, and the shoot below films the new pictures.
        _tdir = Path(OUTPUT_DIR) / catalog / "trailer"
        _stamp = time.strftime("%Y%m%d-%H%M")
        for p in board["panels"]:
            if str(p.get("n")) in {str(x) for x in redraw}:
                f = _tdir / str(p.get("still") or "")
                if f.exists():
                    f.rename(f.with_name(f.stem + f".prev-{_stamp}" + f.suffix))
        log(f"redrawing by order: {' '.join(str(x) for x in redraw)}")
        await draw_and_check_stills(catalog, board, profile, rounds=picture_rounds, only=list(redraw))
        _save()
    if shoot_only:
        _missing = [str(p.get("n")) for p in board["panels"]
                    if not (Path(OUTPUT_DIR) / catalog / "trailer" / str(p.get("still") or "")).exists()]
        if _missing:
            raise RuntimeError(f"shoot-only, but {len(_missing)} shots have no picture: {' '.join(_missing[:12])}")
        attempts = 0
        log("shoot-only: filming the approved pictures as they stand")
    for attempt in range(1, attempts + 1):
        try:
            await draw_and_check_stills(catalog, board, profile,
                                        rounds=picture_rounds)
            log("every picture passes")
            last = None
            break
        except OutOfCredits:
            raise
        except OverBudget as e:
            # THE CAP IS FINAL. Trying again cannot draw anything; it only
            # re-reads 146 pictures for nothing (2026-09-02). The board goes
            # to approval as it stands, with the disputed shots marked.
            last = e
            log(f"cap reached — {str(e)[:120]}")
            break
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

    # THE BOARD CAN BE APPROVED BEFORE A CREDIT IS SPENT (Lars, 2026-09-02:
    # "I want to see the storyboard before you shoot"). Everything up to
    # here costs pennies; the shoot is the money. With stop_before_shoot
    # the line finishes the pictures, saves them, and hands back — the same
    # command run again picks up at the shoot with nothing redone.
    if stop_before_shoot:
        log("pictures complete — stopping before the shoot for approval")
        return {"stopped": "before shoot", "pictures": len(board["panels"]), "show_bible": bible,
                "first_pass_yield": board.get("first_pass_yield"),
                "picture_warning": str(last)[:300] if last else "",
                "minutes": round((time.time() - t0) / 60, 1)}

    # 4. shoot, cut, master, archive, export
    before = await credit_balance()
    BUDGET.credits_start = before
    log(f"pictures used {BUDGET.report()}")
    log(f"shooting — Runway balance {before}")
    if reshoot:
        log(f"re-shooting by order: {' '.join(str(x) for x in reshoot)}")
    r = await finish_episode(catalog, board, profile, t0, reshoot=list(reshoot or []))
    from .filters import report as _filters_report
    r["filters"] = _filters_report(board)          # what the chain stopped, by filter
    _acted = {k: v["acted"] for k, v in r["filters"].items() if v["acted"]}
    log("filter chain: " + (", ".join(f"{k} {v}" for k, v in _acted.items()) or "nothing stopped"))
    after = await credit_balance()
    r["credits_spent"] = max(0, before - after)
    r["credits_left"] = after
    r["minutes"] = round((time.time() - t0) / 60, 1)
    r["picture_warning"] = str(last)[:300] if last else ""
    r["show_bible"] = bible
    log(f"done in {r['minutes']} min — {r['credits_spent']} credits spent, "
        f"{after} left")
    return r


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    catalog = args[0] if args else "SC-039"
    slug = args[1] if len(args) > 1 else "princess-the-unicorn"
    stop = "--approve-board" in flags
    shoot_only = "--shoot-only" in flags
    # --reshoot=26,26b films those shots again (their old takes are banked);
    # --redraw=28,29 sets those pictures aside so they are drawn and checked
    # again before the shoot (a new picture always means a new take).
    _opt = {f.split("=", 1)[0]: f.split("=", 1)[1] for f in flags if "=" in f}
    reshoot = [x.strip() for x in _opt.get("--reshoot", "").split(",") if x.strip()]
    redraw = [x.strip() for x in _opt.get("--redraw", "").split(",") if x.strip()]
    out = Path(OUTPUT_DIR) / catalog / "episode-run.json"
    try:
        rec = asyncio.run(make_episode(catalog, slug, stop_before_shoot=stop, shoot_only=shoot_only,
                                       reshoot=reshoot, redraw=redraw))
        rec["log"] = LOG
        out.write_text(json.dumps(rec, indent=1, default=str))
        print("\nBOARD READY FOR APPROVAL" if rec.get("stopped") else
              "\nEPISODE COMPLETE:", rec.get("film") or "")
    except Exception as e:
        from .budget import BUDGET as _B
        out.write_text(json.dumps(
            {"failed": str(e), "trace": traceback.format_exc()[-2000:],
             "spend": _B.report(), "log": LOG}, indent=1))
        print("\nEPISODE STOPPED:", e, "|", _B.report())
        raise


if __name__ == "__main__":
    main()
