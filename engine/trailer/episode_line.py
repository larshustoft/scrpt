"""The episode line: one command, stages overlapped, quality gated.

Before this, an episode ran in single file — board, then stills, then
voices, then score, then shoot, then mix — about four and a half hours,
most of it spent waiting for a stage that did not depend on the one
before it. Nothing about the voices depends on the pictures. The score
depends only on the score plan. So they run together.

WHAT NEVER MOVES: the two places a person looks. The acted read of the
script, and the animatic of the whole film. Speed comes from the machine
doing things at once, never from skipping a look.

    stage 1  board  ‖  voices (script only)      — parallel
    stage 2  desk check + repair                 — free, must pass
    stage 3  stills ‖ score chapters             — parallel
    GATE     animatic — a person watches
    stage 4  shoot from the approved stills
    stage 5  cut, dailies, bookends, master, archive, audiobook
    REPORT   the quality sheet: chain, desk, dailies, length, loudness
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from ..config import OUTPUT_DIR


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


async def prewarm_voices(catalog: str, board: dict, genre: str = "childrens"):
    """Record every line before a picture exists. The takes are cached, so
    the shoot later finds them already done."""
    from .producer import _record_line, _h, _storyteller_direction
    panels = board.get("panels") or []
    sd = _storyteller_direction(catalog)
    done = 0
    for pn in panels:
        vo = (pn.get("vo") or "").strip()
        if vo:
            d = (pn.get("vo_direction") or sd).strip()
            await _record_line(catalog, vo, genre, f"vo-sb-{_h(vo + d)}-0.95",
                               f"vo-sb-{_h(vo + d)}-0.95.mp3", 0.95, "", d)
            done += 1
        ln = pn.get("line") or {}
        txt = (ln.get("text") or "").strip()
        if txt:
            v, sp = (ln.get("voice") or ""), float(ln.get("speed") or 1.0)
            dr = (ln.get("direction") or "").strip()
            await _record_line(catalog, txt, genre, f"line-sb-{_h(txt + v + dr)}-{sp}",
                               f"line-sb-{_h(txt + v + dr)}-{sp}.mp3", sp, v, dr)
            done += 1
    _log(f"voices ready: {done} takes")
    return done


async def prewarm_score(catalog: str, board: dict, label: str = "film"):
    """Compose the chapters while the stills are still drawing."""
    from .producer import _record_music, _h
    plan = board.get("score_plan") or []
    panels = board.get("panels") or []
    total = sum(float(p.get("dur") or 4) for p in panels)
    span = max(20.0, total / max(1, len(plan)))
    got = 0
    for k, ch in enumerate(plan):
        mood = (ch.get("mood") or "").strip()
        if not mood:
            continue
        if await _record_music(catalog, mood, min(span + 4, 85),
                               f"{label}-ch{k}-{_h(mood)[:6]}"):
            got += 1
    _log(f"score ready: {got} chapters")
    return got


async def draw_and_check_stills(catalog: str, board: dict, profile: dict,
                                rounds: int = 2):
    """Draw every shot, then READ THE DRAWINGS BACK and repair the failures.

    The check used to exist and was never called (2026-09-01): the function
    was named "draw_and_check" and only drew. Caves, boulders and a close-up
    that came back as a landscape all went through to the camera and then to
    a delivered film. A picture now has to pass before it can be filmed, and
    a picture that fails is drawn again — up to `rounds` times — before the
    episode stops and names it.
    """
    from .shotstills import draw_shot_stills
    from .verify import verify_stills
    r = await draw_shot_stills(catalog, board, profile)
    n = len(r.get("stills") or {})
    _log(f"stills ready: {n} of {len(board.get('panels') or [])}")

    flagged = {}
    redrawn = None            # None = the first pass reads every picture
    for rd in range(rounds + 1):
        # ONLY WHAT CHANGED GETS READ AGAIN (2026-09-02). Every round used
        # to re-read all 146 pictures when only the redrawn ones could have
        # changed — three minutes and hundreds of vision calls a round.
        chk = await verify_stills(catalog, board, only=redrawn)
        all_flags = {k: v for k, v in (chk.get("flagged") or {}).items() if v}
        # UNCHECKED IS NOT REJECTED (Lars, 2026-09-01: "this is taking very
        # long"). A picture the checker could not read is not a bad picture,
        # and redrawing it cannot make the checker work. When the vision
        # account died, every one of 146 pictures came back "could not be
        # checked", was treated as a failure, and was redrawn — twice, for
        # nothing. A checker that cannot run stops the line immediately and
        # says why; only pictures it actually judged and rejected are redrawn.
        unchecked = {k: v for k, v in all_flags.items()
                     if any(str(x).startswith("could not be checked") for x in v)}
        if unchecked:
            raise RuntimeError(
                f"the picture checker could not read {len(unchecked)} of "
                f"{chk.get('checked')} pictures, so nothing can be judged or "
                f"redrawn: {list(unchecked.values())[0][0]}")
        flagged = all_flags
        # EVERY REJECTION TEACHES THE UNIVERSE (Lars, 2026-09-02: "build a
        # system that will make future films automatic on the first try").
        # Recorded here, read back into every future drawing prompt once a
        # mistake has recurred — see lessons.py.
        if flagged:
            from .lessons import record as _learn
            _learn(profile, catalog, flagged, rd)
        if rd == 0:
            board["first_pass_yield"] = round(
                1 - len(flagged) / max(1, chk.get("checked") or 1), 3)
            _log(f"first-pass yield: {int(board['first_pass_yield']*100)}% "
                 f"of pictures right the first time")
        if not flagged:
            _log(f"stills checked: all {chk.get('checked')} pass the world rules")
            break
        _log(f"stills checked: {len(flagged)} of {chk.get('checked')} rejected — "
             + "; ".join(f"{k}: {v[0][:60]}" for k, v in list(flagged.items())[:6])
             + (" …" if len(flagged) > 6 else ""))
        if rd == rounds:
            break
        _log(f"redrawing {len(flagged)} rejected pictures (round {rd + 1})")
        await draw_shot_stills(catalog, board, profile, only=set(flagged))
        redrawn = set(flagged)
    if flagged:
        raise RuntimeError(
            f"{len(flagged)} pictures still break the world rules after "
            f"{rounds} redraws and the episode will not be filmed from them: "
            + ", ".join(sorted(flagged)) )
    return n


def quality_sheet(catalog: str, board: dict, film: Path = None,
                  dailies_notes: list = None, board_check: dict = None) -> dict:
    """One sheet, every gate. Speed is never allowed to hide a failure."""
    import re
    import subprocess
    import imageio_ffmpeg
    from .continuity import check_board
    sheet = {"desk_check": check_board(board),
             "dailies": dailies_notes or [],
             # Did every shot in this film open on the picture that was
             # approved? The one question that would have caught a film
             # cut from a week-old cache.
             "board_check": board_check or {},
             "shots": len(board.get("panels") or [])}
    if film and film.exists():
        FF = imageio_ffmpeg.get_ffmpeg_exe()
        pr = subprocess.run([FF, "-i", str(film), "-f", "null", "-"],
                            capture_output=True, text=True)
        ts = re.findall(r"time=(\d+):(\d+):([\d.]+)", pr.stderr)
        if ts:
            h, m, s = ts[-1]
            sheet["seconds"] = int(h) * 3600 + int(m) * 60 + float(s)
        an = subprocess.run([FF, "-i", str(film), "-af",
                             "loudnorm=I=-14:TP=-1.5:print_format=json",
                             "-f", "null", "-"], capture_output=True, text=True)
        m2 = re.search(r"\{[^{}]*input_i[^{}]*\}", an.stderr, re.S)
        if m2:
            d = json.loads(m2.group(0))
            sheet["lufs"] = float(d["input_i"])
            sheet["true_peak"] = float(d["input_tp"])
    sheet["passes"] = (not sheet["desk_check"]
                       and not (sheet["board_check"] or {}).get("off_board")
                       and (sheet.get("lufs") is None or -15.5 < sheet["lufs"] < -12.5)
                       and (sheet.get("seconds") is None or sheet["seconds"] < 13 * 60))
    return sheet


async def establish_world(catalog: str, board: dict, profile: dict) -> dict:
    """Characters, places and objects are drawn and checked BEFORE any shot.

    Every picture in an episode is drawn from these plates, so a mistake in
    one of them is a mistake in a hundred and forty-six drawings. They are
    made first, read back against the written bible, and the episode does
    not proceed on a plate that contradicts it.
    """
    from .plates import draw_cast_plates
    from .locations import draw_location_plates
    from .props import draw_prop_plates
    from .verify import verify_plates

    style = board.get("style") or ""
    cre = (profile.get("creatives") or {})

    cast = (await draw_cast_plates(catalog)).get("plates") or {}
    board["characters"] = {**(board.get("characters") or {}), **cast}
    _log(f"cast plates: {len(cast)}")

    # THE CHARACTER BIBLE'S PICTURES ARE THE PLATES (Lars, 2026-09-02: "it
    # looks to me like you haven't used the character bible we created").
    # The approved portraits were replaced by freshly drawn reference
    # sheets an hour after he signed them off, and a whole film was drawn
    # from characters he had never seen. A universe now names its canonical
    # plates by content hash; an episode's plates must BE those files, byte
    # for byte, or the episode stops before a single picture is drawn.
    import hashlib as _hl
    _udir = Path(profile.get("profile_path") or ".").parent
    _bdir = Path(OUTPUT_DIR) / catalog / "trailer" / "bible"
    _wrong = []
    for _name, _c in (((profile.get("world") or {}).get("plates") or {}).items()):
        _rel, _md5 = _c.get("file"), _c.get("md5")
        if not (_rel and _md5):
            continue
        _canon = _udir / _rel
        _mine = _bdir / f"{_name.lower()}.png"
        if not _canon.exists():
            _wrong.append(f"{_name}: canonical plate missing at {_rel}")
            continue
        if not _mine.exists() or _hl.md5(_mine.read_bytes()).hexdigest() != _md5:
            _mine.parent.mkdir(parents=True, exist_ok=True)
            _mine.write_bytes(_canon.read_bytes())          # the canon wins, always
            _log(f"{_name}: plate restored from the universe's canonical picture")
    if _wrong:
        raise RuntimeError("the universe's canonical character plates are missing: "
                           + "; ".join(_wrong))
    _log("cast plates are the Character Bible's pictures (verified by hash)")

    chk = await verify_plates(catalog)
    bad = {k: v for k, v in (chk.get("by_character") or {}).items() if v}
    if bad:
        # THE PLATE IS THE LAW, SO THE PLATE MUST OBEY THE BIBLE. Glitter was
        # drawn for weeks with a floor-length mane her bible never gave her.
        raise RuntimeError(
            "these character plates contradict the bible and the episode will "
            "not be drawn from them: "
            + "; ".join(f"{k}: {v[0]}" for k, v in bad.items()))
    _log("cast plates agree with the bible")

    # `place_briefs` describes a place in words; `locations` records the
    # plate that was drawn from it. Keeping them apart is what lets a place
    # be drawn once and then reused for the whole season — and it is what
    # was missing when eleven plates sat on disk unregistered, so every
    # shot in those places was invented again from a sentence.
    # A NEW UNIVERSE WRITES ITS OWN WORLD RULES (2026-09-02). Princess's
    # rules — no caves, one stone — were written by hand after a film had
    # already gone wrong without them. A universe that has none gets them
    # drafted from its own bible and story, saved to the profile, and used
    # from the first drawing; they are reviewed, not invented per shot.
    if not (cre.get("world_rules") or []):
        from ..writing.client import complete
        from ..database import get_book_by_catalog as _gb
        _bk = _gb(catalog)
        _bib = (_bk["data"].get("childrens") or {}).get("bible") or {}
        _world = json.dumps({k: _bib.get(k) for k in ("world", "setting", "places", "rules", "tone")
                             if _bib.get(k)}, ensure_ascii=False)[:4000]
        _shots = "\n".join(f"- {p.get('shot','')[:160]}" for p in (board.get("panels") or [])[:40])
        try:
            txt = await complete(
                "You write the standing visual rules for a children's animated universe. "
                "JSON only.",
                f"THE WORLD, from the bible:\n{_world}\n\nSOME SHOTS:\n{_shots}\n\n"
                "Write 4 to 6 STANDING RULES a picture of this world must always obey — "
                "things that must never appear (kinds of place, object, creature, weather "
                "the story does not have), and things that exist exactly once. Each rule "
                "one sentence, plain words, in CAPITALS for the first clause. "
                'Return {"rules": ["..."]}', max_tokens=800)
            from ..writing.client import extract_json
            rules = [str(r)[:300] for r in ((extract_json(txt) or {}).get("rules") or [])][:6]
        except Exception as e:
            raise RuntimeError(f"this universe has no world rules and they could not be "
                               f"drafted: {e}")
        if rules:
            cre["world_rules"] = rules
            try:
                pp = Path(profile.get("profile_path") or "")
                _prof = json.loads(pp.read_text())
                _prof.setdefault("creatives", {})["world_rules"] = rules
                pp.write_text(json.dumps(_prof, indent=1, ensure_ascii=False))
            except Exception as e:
                _log(f"could not save the drafted world rules: {e}")
            _log(f"world rules drafted for this universe ({len(rules)}) — review them in "
                 f"the profile: " + " | ".join(r[:60] for r in rules[:3]))

    briefs = dict(cre.get("place_briefs") or {})
    udir = Path(profile.get("profile_path") or ".").parent

    # EVERY PLACE THE BOARD USES MUST BE ESTABLISHED BEFORE IT IS DRAWN
    # (Lars, 2026-09-01: "establish what every scene in the universe looks
    # like, and THEN create the images"). The set of places comes from the
    # panels themselves — the only field the drawing stage actually reads —
    # not from a summary written alongside them, which can disagree.
    # A place nobody wrote a brief for used to produce a warning in a log
    # nobody reads, and then every shot set there invented its own version
    # of it. The line writes the missing brief itself, from the shots that
    # happen there, so a new episode establishes its new places without a
    # person in the loop. The brief is saved to the universe, so it is
    # written once and reused for the whole season.
    used = sorted({str(p.get("place") or "").strip().lower()
                   for p in (board.get("panels") or []) if p.get("place")})
    unbriefed = [k for k in used if k not in briefs]
    if unbriefed:
        from ..writing.client import complete
        _log(f"{len(unbriefed)} places have never been established: "
             f"{', '.join(unbriefed)} — writing their briefs")
        for key in unbriefed:
            lines = [str(p.get("shot") or "") for p in board["panels"]
                     if str(p.get("place") or "").strip().lower() == key][:12]
            try:
                txt = await complete(
                    "You write location briefs for a children's animated series. "
                    "One paragraph, plain words, no characters in it.",
                    f"These shots all happen in the same place, called "
                    f"\"{key}\":\n\n" + "\n".join(f"- {l}" for l in lines) +
                    "\n\nDescribe THE PLACE ITSELF in one paragraph of about 60 "
                    "words: the ground, what grows there, the rock and water, "
                    "what stands around it, and the light. No characters, no "
                    "action, no camera. It will be drawn once and every shot "
                    "set there will be drawn from it, so describe what never "
                    "changes.", max_tokens=400)
                briefs[key] = " ".join(str(txt).split())[:900]
            except Exception as e:
                raise RuntimeError(
                    f"the place '{key}' could not be established and every shot "
                    f"there would drift: {e}")
        cre["place_briefs"] = briefs
        # written back to the universe so the season pays for this once
        try:
            pp = Path(profile.get("profile_path") or "")
            if pp.exists():
                _prof = json.loads(pp.read_text())
                _prof.setdefault("creatives", {})["place_briefs"] = briefs
                pp.write_text(json.dumps(_prof, indent=1, ensure_ascii=False))
        except Exception as e:
            _log(f"could not save the new place briefs to the universe: {e}")

    if briefs:
        # A LOG THAT MISCOUNTS IS A LOG THAT MISLEADS (2026-09-01). This said
        # "10 new" every run when it meant "10 established, 1 actually drawn",
        # which reads as the whole world being redrawn each time — the exact
        # drift plates exist to prevent. Count what was really drawn.
        _before = {k for k in (cre.get("locations") or {})
                   if (udir / "locations" / f"{k}.png").exists()}
        made = await draw_location_plates(udir, profile, briefs, style)
        got = made.get("plates") or made or {}
        if got:
            cre.setdefault("locations", {}).update(
                {k: f"locations/{k}.png" for k in got})
        _new = sorted(set(got) - _before)
        _log(f"location plates: {len(cre.get('locations') or {})} places "
             f"established"
             + (f", {len(_new)} newly drawn ({', '.join(_new)})" if _new
                else ", none needed drawing"))
    places = cre.get("locations") or {}
    # A WARNING IS NOT A GATE (2026-09-01). This used to log that places had
    # no plate and carry on drawing them anyway, which is the whole failure
    # it was written to prevent.
    missing = [k for k in used if k not in places]
    if missing:
        raise RuntimeError(
            "these places have no plate and every shot set in them would look "
            "different: " + ", ".join(sorted(missing)))

    # THE PLATE IS DRAWN ONCE AND INHERITED FORTY TIMES, SO THE PLATE IS
    # CHECKED (Lars, 2026-09-01: "why is that rock appearing all over the
    # place"). The spring plate carried a large pale boulder; every picture
    # of the spring came back with one, and redrawing those shots could
    # never have removed it. A plate that breaks the world's rules is torn
    # up and drawn again from its brief, once, and then the episode stops
    # rather than inherit it.
    from .verify import verify_locations
    for attempt in range(2):
        chk = await verify_locations(udir, profile)
        bad = chk.get("flagged") or {}
        # A PLATE IS TORN UP ONLY ON TWO INDEPENDENT READS (2026-09-02). The
        # restored-spring plate passed three checks in a morning, failed a
        # fourth on the pale cliff, was thrown away and redrawn — and the
        # replacement had a ring of boulders. One reader's doubt is not a
        # verdict on a picture forty shots already depend on; the doubt is
        # put to a second read, and only a plate that fails both is redrawn.
        if bad:
            again = (await verify_locations(udir, profile)).get("flagged") or {}
            bad = {k: v for k, v in bad.items() if k in again}
            if not bad:
                _log("a location plate was doubted on one read and cleared "
                     "on the second — kept")
        if not bad:
            _log(f"location plates obey the world rules ({chk.get('checked')} checked)")
            break
        _log("these plates break the world rules: "
             + "; ".join(f"{k}: {', '.join(v)}" for k, v in bad.items()))
        if attempt:
            raise RuntimeError(
                "these places are drawn wrong and every shot set in them would "
                "inherit it: "
                + "; ".join(f"{k} ({', '.join(v)})" for k, v in bad.items()))
        for k in bad:
            f = udir / "locations" / f"{k}.png"
            if f.exists():
                f.rename(f.with_suffix(".rejected.png"))
        _log(f"redrawing {len(bad)} location plates")
        await draw_location_plates(udir, profile,
                                   {k: briefs[k] for k in bad if k in briefs}, style)

    props = cre.get("props") or {}
    if props:
        made = await draw_prop_plates(catalog, props, style)
        _log(f"object plates: {len(made.get('plates') or made or {})} of {len(props)}")

    return {"cast": len(cast), "places": len(places), "props": len(props)}


async def run_episode(catalog: str, profile: dict, stop_at_animatic: bool = True,
                      genre: str = "childrens") -> dict:
    """The line, from an approved board to a finished episode."""
    from .. import database as db
    from .animatic import build_animatic

    from .selftest import check_gates
    _gates = check_gates()
    if _gates:
        raise RuntimeError("the film's safety checks are not in place: "
                           + "; ".join(_gates))
    t0 = time.time()
    book = db.get_book_by_catalog(catalog)
    board = json.loads(json.dumps(book["data"]["movie"]["storyboard"]))
    vc = (book["data"]["movie"].get("voice_cast") or {})
    for pn in board["panels"]:
        ln = pn.get("line")
        if isinstance(ln, dict) and ln.get("speaker") in vc:
            ln["voice"] = vc[ln["speaker"]]["id"]

    # THE BOARD IS MADE TO AGREE WITH ITSELF FIRST (2026-09-01). Eighteen
    # shots of episode one were reconciled by hand — a camera set to close
    # while the words said wide, a mother in the sentence and not in the
    # cast list. That is now a stage, so the next episode does not need a
    # person for it.
    from .continuity import check_board, repair_board
    mended = repair_board(board)
    if mended:
        _log(f"board repaired before drawing: {len(mended)} shots — "
             + "; ".join(mended[:4]) + (" …" if len(mended) > 4 else ""))
    desk = check_board(board)
    if desk:
        return {"stopped": "desk check", "problems": desk[:20]}

    # ── STAGE 0: ESTABLISH THE WORLD, THEN DRAW IT (Lars, 2026-09-01:
    # "establish what every scene in the universe/map and the story looks
    # like, and then create the images based on that"). The plate builders
    # and the plate checker all existed and NONE of them were called by the
    # line — the plates for episode one were drawn by hand, once, which is
    # why nothing would have been established for episode two or for a new
    # universe. The law is a stage now.
    await establish_world(catalog, board, profile)

    _log(f"{catalog}: {len(board['panels'])} shots — voices, score and stills together")
    stills, voices, score = await asyncio.gather(
        draw_and_check_stills(catalog, board, profile),
        prewarm_voices(catalog, board, genre),
        prewarm_score(catalog, board),
        return_exceptions=True)
    # A GATHERED EXCEPTION IS STILL A FAILURE (2026-09-01). These three run
    # together for speed, and `return_exceptions` turned a refused picture
    # into a value that read as success. The pictures are the one stage the
    # rest of the episode is built on: if they did not pass, nothing after
    # this line may run.
    if isinstance(stills, BaseException):
        raise stills
    for _name, _r in (("voices", voices), ("score", score)):
        if isinstance(_r, BaseException):
            _log(f"{_name} failed and will be made during the shoot: {_r}")

    fresh = db.get_book_by_catalog(catalog)
    d = dict(fresh["data"]); mv = dict(d["movie"]); mv["storyboard"] = board
    d["movie"] = mv; db.update_book(fresh["id"], d)

    animatic = build_animatic(catalog, board)
    _log(f"animatic: {animatic}  ({(time.time()-t0)/60:.0f} min so far)")
    if stop_at_animatic:
        return {"animatic": str(animatic), "stills": stills, "voices": voices,
                "score": score, "minutes": round((time.time() - t0) / 60, 1),
                "next": "approve the animatic, then run with stop_at_animatic=False"}
    return await finish_episode(catalog, board, profile, t0)


async def finish_episode(catalog: str, board: dict, profile: dict, t0=None) -> dict:
    """Shoot the approved stills and finish the episode."""
    from .selftest import check_gates
    # THE GATES ARE CHECKED BEFORE THE MONEY IS SPENT. Every protection in
    # this line was written after a film was delivered that did not match
    # its board; a later change that quietly removes one looks exactly like
    # a gate that never fires. This costs nothing and runs every time.
    _gates = check_gates()
    if _gates:
        raise RuntimeError("the film's safety checks are not in place: "
                           + "; ".join(_gates))
    from .producer import produce_storyboard
    from .episode import attach_bookends, archive_film_version, export_audiobook
    from .dailies import review_shots
    from .plates import draw_cast_plates
    t0 = t0 or time.time()
    board = json.loads(json.dumps(board))
    board["characters"] = {**(board.get("characters") or {}),
                           **((await draw_cast_plates(catalog)).get("plates") or {})}
    total_s = sum(float(p.get("dur") or 4) for p in board["panels"])
    r = await produce_storyboard(catalog, board, format_name="wide",
                                 version_label="film",
                                 max_seconds=int(total_s * 1.35) + 30)
    film = Path(OUTPUT_DIR) / catalog / str(r.get("file") or "trailer.mp4")
    _log("shot and cut — running dailies")
    day = await review_shots(catalog, board)
    attach_bookends(catalog, film)
    version = archive_film_version(catalog, film, label="line")
    audiobook = export_audiobook(catalog, film)
    sheet = quality_sheet(catalog, board, film, (day or {}).get("notes"),
                          board_check=r.get("board_check"))
    _log(f"episode done in {(time.time()-t0)/60:.0f} min · quality "
         f"{'PASS' if sheet['passes'] else 'NEEDS WORK'}")
    return {"film": str(film), "audiobook": str(audiobook or ""),
            "version": version, "quality": sheet,
            "minutes": round((time.time() - t0) / 60, 1)}
