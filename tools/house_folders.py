#!/usr/bin/env python3
"""Make (or repair) the house folder on the hard drive.

Every universe gets the SAME nine shelves, in the order the production
line uses them, under ~/TigerWorks/Universes/<Name>/. Run it after
registering a universe — it creates what is missing and never touches,
moves or deletes anything that already exists.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HOUSE = Path.home() / "TigerWorks"
SHELVES = ["01 Scripts & notes", "02 Books", "03 Logos", "04 Characters",
           "05 Music", "06 Voices", "07 Films", "08 Website", "09 For Lars"]


def ensure(name: str) -> Path:
    d = HOUSE / "Universes" / name
    for s in SHELVES:
        (d / s).mkdir(parents=True, exist_ok=True)
    readme = d / "README.md"
    if not readme.exists():
        readme.write_text(f"# {name}\n\nNine shelves, the same in every "
                          "universe — see ../../README.md.\n")
    return d


def main():
    from engine import database as db
    root = Path(__file__).resolve().parents[1]
    v = db.get_setting("universes", "")
    reg = v if isinstance(v, dict) else json.loads(v or "{}")
    made = []
    for u in reg.values():
        prof = json.loads((root / u["profile"]).read_text())
        name = prof.get("title") or prof.get("name") or u.get("name") or ""
        if not name:
            continue
        d = ensure(name)
        made.append(str(d))
        # write the shelf back into the profile so the studio knows where
        # a human will look for these files
        cr = prof.setdefault("creatives", {})
        if cr.get("desktop_mirror") != str(d):
            cr["desktop_mirror"] = str(d)
            prof["desktop_mirror"] = str(d)
            (root / u["profile"]).write_text(json.dumps(prof, indent=2, ensure_ascii=False))
    print("\n".join(made) or "no universes registered")


if __name__ == "__main__":
    main()
