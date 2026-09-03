"""A film is BORN THROUGH SCRPT (Lars, 2026-09-03: "everything we do here
should run through our SCRPT system — that is where we save the voices and
other creative choices").

    python3 -m engine.trailer.new_film <universe-slug> <manuscript.md> [--minutes 4]

From one manuscript in the house format this: creates the book inside the
universe (member, data.universe, the universe's voices, style, bibles), parses
the manuscript with wrapped paragraphs joined (the short SC-042 lost the end of
every sentence to a line-by-line parser), declares the story's object set and
places from the manuscript header, builds the board from the locked scenes,
applies the world map, and leaves the book ready for

    python3 -m engine.trailer.make_episode <catalog> <universe-slug> --approve-board
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from ..config import PROJECT_ROOT
from .. import database as db

UNIVERSES = PROJECT_ROOT / "universe"


def parse_manuscript(text: str) -> dict:
    """{title, object_set: {key: [states]}, places: [...], scenes: [{n,title,setting,action,script}]}"""
    title = ""
    m = re.search(r"^# (.+)$", text, re.M)
    if m:
        raw = m.group(1).strip()
        if raw.isupper():
            small = {"and", "the", "of", "a", "an", "in", "on", "at", "to", "for"}
            ws = raw.lower().split()
            title = " ".join(w if (i and w in small) else w.capitalize() for i, w in enumerate(ws))
        else:
            title = raw
    objects, places = {}, []
    m = re.search(r"\*\*Object set\*\*\s*—\s*(.+?)(?:\n\s*\n|\*\*Places)", text, re.S)
    if m:
        for part in re.split(r"\s*·\s*", " ".join(m.group(1).split())):
            mm = re.match(r"`([a-z0-9-]+)`\s*\(states:\s*([^)]+)\)", part.strip())
            if mm:
                objects[mm.group(1)] = [s.strip() for s in mm.group(2).split("/") if s.strip()]
    m = re.search(r"\*\*Places[^*]*\*\*\s*—\s*(.+?)(?:\n\s*\n|---)", text, re.S)
    if m:
        places = [p.strip().rstrip(".") for p in re.split(r"\s*·\s*", " ".join(m.group(1).split())) if p.strip().rstrip(".")]
    scenes, cur = [], None
    for para in re.split(r"\n\s*\n", text):
        para = " ".join(l.strip() for l in para.strip().splitlines())
        mh = re.match(r"^## (\d+) · (.+)$", para)
        if mh:
            cur = {"n": int(mh.group(1)), "title": mh.group(2).strip(), "setting": "", "action": "", "script": []}
            scenes.append(cur); continue
        if cur is None:
            continue
        ml = re.match(r"^\*\*([A-Z]+)\*\* \*\(([^)]*)\)\*: (.+)$", para)
        if ml:
            who, direction, line = ml.group(1), ml.group(2), ml.group(3).strip()
            cur["script"].append({"type": "vo" if who == "STORYTELLER" else "line",
                                  "speaker": "Storyteller" if who == "STORYTELLER" else who.capitalize(),
                                  "text": line, "direction": direction})
        elif para.startswith("*") and para.endswith("*") and cur["script"]:
            cur["script"].append({"type": "sound", "text": para.strip("*").strip()})
        elif para.startswith("[") and para.endswith("]"):
            cur["setting"] = para.strip("[]").strip()
    return {"title": title, "object_set": objects, "places": places, "scenes": scenes}


def _profile(slug: str) -> dict:
    return json.loads((UNIVERSES / slug / "profile.json").read_text())


async def new_film(slug: str, manuscript: Path, minutes: int = 4, kind: str = "short") -> str:
    from .bible import build_film_board
    from .world import apply_world
    from .continuity import check_board, repair_board
    prof = _profile(slug)
    ms = parse_manuscript(manuscript.read_text())
    if not ms["scenes"]:
        raise RuntimeError("the manuscript has no '## n · TITLE' scenes")
    title = ms["title"] or manuscript.stem
    # the parent book of the universe lends its bibles and style — the universe's creative choices
    parent = None
    for cat in (prof.get("members") or []):
        parent = db.get_book_by_catalog(cat)
        if parent:
            break
    pd = (parent or {}).get("data") or {}
    data = {k: pd[k] for k in ("bibles", "childrens", "series", "genre", "kind", "style", "author", "audience", "age_range") if k in pd}
    data.update({"title": title, "universe": slug, "short": kind == "short",
                 "movie": {"kind": kind, "voice_cast": dict(prof.get("voice_cast") or {}),
                           "script_file": str(manuscript.relative_to(PROJECT_ROOT)) if str(manuscript).startswith(str(PROJECT_ROOT)) else str(manuscript),
                           "script_scenes": ms["scenes"], "object_set": ms["object_set"], "places": ms["places"]},
                 "summary": " ".join(s["text"] for sc in ms["scenes"][:1] for s in sc["script"] if s["type"] == "vo")[:400]})
    book = db.create_book(title, data)
    catalog = book.get("catalog_number") or book["data"].get("catalog_number")
    # membership: the universe owns this film (voices, bookends, storyteller)
    pp = UNIVERSES / slug / "profile.json"; pj = json.loads(pp.read_text())
    mem = pj.setdefault("members", [])
    if catalog not in mem:
        mem.append(catalog); pp.write_text(json.dumps(pj, indent=1, ensure_ascii=False))
    print(f"[new_film] {catalog} '{title}' born in {slug}: {len(ms['scenes'])} scenes, objects {list(ms['object_set'])}, places {ms['places']}", flush=True)
    # object states must exist before the board is drawn; missing ones are a hard stop
    reg = (pj.get("world") or {}).get("props_plates") or {}
    missing = [f"{k}--{s}" for k, states in ms["object_set"].items() for s in states if f"{k}--{s}" not in reg]
    if missing:
        raise RuntimeError("the object set is not drawn yet — run foundation.draw_object_set for: " + ", ".join(missing))
    locs = (pj.get("creatives") or {}).get("locations") or {}
    missing_places = [p for p in ms["places"] if p not in locs]
    if missing_places:
        raise RuntimeError("these places have no plate in the atlas: " + ", ".join(missing_places))
    premise = (f"A {minutes}-minute {kind} in the {prof.get('name') or slug} universe. Board it as SHORT shots: no shot may need more than "
               f"5 seconds of picture; a long narration beat becomes two shots. No lip sync. Places: {', '.join(ms['places'])}. "
               f"Objects: " + "; ".join(f"{k} (states {' / '.join(v)})" for k, v in ms["object_set"].items()))
    await build_film_board(catalog, minutes=minutes, format_kind="childrens", premise=premise, locked_scenes=ms["scenes"])
    # the world map: places by scene setting, objects by state named in the words
    b = db.get_book_by_catalog(catalog); d = dict(b["data"]); bd = d["movie"]["storyboard"]
    scene_place = {}
    for sc in ms["scenes"]:
        scene_place[str(sc["n"])] = sc["setting"] if sc["setting"] in locs else (ms["places"][min(len(ms["places"]) - 1, sc["n"] - 1)] if ms["places"] else "")
    words = {}
    for k, states in ms["object_set"].items():
        for st in states:
            words[f"{k}--{st}"] = [k.replace("-", " "), f"{k.replace('-', ' ')} {st.replace('-', ' ')}"]
    bd["world"] = {"places": scene_place, "shot_places": {}, "props": words, "shot_props": {}}
    apply_world(bd); repair_board(bd)
    bd["desk_check"] = check_board(bd)
    db.update_book(b["id"], d)
    print(f"[new_film] board: {len(bd['panels'])} shots, desk check {'clean' if not bd['desk_check'] else bd['desk_check'][:3]}", flush=True)
    print(f"next: python3 -m engine.trailer.make_episode {catalog} {slug} --approve-board", flush=True)
    return catalog


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    if len(args) < 2:
        print(__doc__); sys.exit(2)
    asyncio.run(new_film(args[0], Path(args[1]).resolve(), minutes=int(opts.get("--minutes", 4))))


if __name__ == "__main__":
    main()
