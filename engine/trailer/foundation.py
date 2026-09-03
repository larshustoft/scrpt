"""THE FOUNDATION — what a universe must own before a single shot is drawn
(Lars, 2026-09-03: "build a system that is built on a stronger foundation").

Episode 1 was drawn from one portrait per character, one plate per place and
one picture per object, and the model filled every gap by itself: the unicorn
changed from shot to shot, the stone changed shape and place, the stick was
never the same stick. This module draws and registers the three things that
close those gaps:

  * POSE SHEETS  — every character in the same set of angles, expressions and
                   movements, each verified against the canonical plate
                   (world.poses[name][pose] = {file, md5, tags}).
  * THE ATLAS    — the universe defined in wide pictures, drawn in the palette
                   of the approved valley plate (creatives.locations + location_md5).
  * OBJECT SETS  — every story object as ONE picture per STATE
                   (world.props_plates["key--state"], creatives.props["key--state"]).

Everything drawn here is shown to Lars in one gallery (FOUNDATION.html) and
approved once; after that the shot stage only ever reuses these pictures.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import re
from pathlib import Path

from ..config import OPENAI_API_KEY, OUTPUT_DIR, PROJECT_ROOT

UNIVERSES = PROJECT_ROOT / "universe"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _profile(slug: str) -> tuple[Path, dict]:
    pp = UNIVERSES / slug / "profile.json"
    return pp, json.loads(pp.read_text())


def _save_profile(pp: Path, prof: dict) -> None:
    pp.write_text(json.dumps(prof, indent=1, ensure_ascii=False))


# ── identity: is this still the same character? ─────────────────────────────
async def same_character(canonical: Path, candidate: Path, name: str, reads: int = 2) -> tuple[bool, str]:
    """Two independent reads; both must agree it is the same character."""
    from ..writing.client import complete_vision, extract_json
    from PIL import Image
    a = Image.open(canonical).convert("RGB"); b = Image.open(candidate).convert("RGB")
    h = 512
    a = a.resize((int(a.width * h / a.height), h)); b = b.resize((int(b.width * h / b.height), h))
    pair = Image.new("RGB", (a.width + b.width + 16, h), (255, 255, 255))
    pair.paste(a, (0, 0)); pair.paste(b, (a.width + 16, 0))
    buf = io.BytesIO(); pair.save(buf, "PNG")
    why = ""
    for _ in range(reads):
        raw = await complete_vision(
            "You compare two pictures of an animated character. JSON only.",
            f"Left: the approved picture of {name}. Right: a new drawing meant to be the SAME character in a "
            "different pose or expression. Is it the same character — same species, same coat and mane colours, "
            "same horn/wings/markings, same age and proportions, same art style? Ignore pose, expression, "
            'background and camera angle. {"same": true/false, "why": "..."}',
            buf.getvalue())
        d = extract_json(raw) or {}
        why = str(d.get("why") or "")[:120]
        if not d.get("same"):
            return False, why
    return True, why


# ── pose sheets ─────────────────────────────────────────────────────────────
def pose_list(prof: dict, name: str) -> list[dict]:
    """[{slug, text, kind}] for a character: angles + expressions + movements,
    with per-character overrides (a bird flies, a unicorn walks)."""
    sheet = (prof.get("world") or {}).get("pose_sheet") or {}
    ov = ((prof.get("world") or {}).get("pose_sheet_overrides") or {}).get(name.lower()) or {}
    out = []
    for kind in ("angles", "expressions", "movements"):
        for text in (ov.get(kind) or sheet.get(kind) or []):
            out.append({"slug": _slug(text), "text": text, "kind": kind[:-1]})
    return out


async def draw_pose_sheets(slug: str, style: str = "", quality: str = "medium",
                           only: set | None = None, handle=None) -> dict:
    """Draw every missing pose for every canonical character, verify identity
    twice, keep what passes, register by md5. Returns {name: {pose: file}}."""
    import httpx
    from ..cover.front_cover import _best_image_model
    from .plates import _draw_with_refs
    if not OPENAI_API_KEY:
        raise RuntimeError("OpenAI is not configured — the pose sheets need it")
    pp, prof = _profile(slug)
    udir = pp.parent
    plates = (prof.get("world") or {}).get("plates") or {}
    poses = prof.setdefault("world", {}).setdefault("poses", {})
    made, failed = {}, []
    gate = asyncio.Semaphore(int(os.environ.get("SCRPT_STILL_LANES", "6")))

    async def one(client, model, name, canon: Path, pose: dict):
        async with gate:
            dest = udir / "plates" / name / f"{pose['slug']}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            reg = poses.setdefault(name, {})
            if dest.exists() and reg.get(pose["slug"], {}).get("md5") == _md5(dest):
                return name, pose["slug"], str(dest.relative_to(udir))
            prompt = (f"Exactly this character, {name.capitalize()}, and nobody else: {pose['text']}. "
                      "The same species, the same coat, mane and tail colours, the same horn, wings or "
                      "markings, the same proportions and age as in the reference picture — a model sheet "
                      "pose of the SAME character. Full body visible, plain soft pastel background, no "
                      f"scenery, no other characters, no text. {style}")
            for attempt in range(2):
                got = await _draw_with_refs(client, model, prompt, [canon], dest,
                                            size="1024x1024", quality=quality)
                if not got or not dest.exists():
                    continue
                ok, why = await same_character(canon, dest, name.capitalize())
                if ok:
                    reg[pose["slug"]] = {"file": str(dest.relative_to(udir)), "md5": _md5(dest),
                                         "kind": pose["kind"], "text": pose["text"]}
                    if handle:
                        handle.progress(0.4, "poses", f"{name}: {pose['slug']}")
                    return name, pose["slug"], reg[pose["slug"]]["file"]
                dest.rename(dest.with_name(dest.stem + f".rejected{attempt}.png"))
                print(f"[poses] {name} {pose['slug']}: not the same character ({why}) — redrawing", flush=True)
            return None

    jobs = []
    async with httpx.AsyncClient(timeout=260) as client:
        model = await _best_image_model(client)
        for name, rec in plates.items():
            if only and name not in only:
                continue
            canon = udir / (rec["file"] if isinstance(rec, dict) else rec)
            if not canon.exists():
                failed.append(f"{name}: canonical plate missing"); continue
            for pose in pose_list(prof, name):
                jobs.append(one(client, model, name, canon, pose))
        for r in await asyncio.gather(*jobs, return_exceptions=True):
            if isinstance(r, BaseException):
                failed.append(str(r)[:120])
            elif isinstance(r, tuple):
                made.setdefault(r[0], {})[r[1]] = r[2]
    _save_profile(pp, prof)
    if failed:
        print(f"[poses] {len(failed)} pose(s) not kept: " + "; ".join(failed[:6]), flush=True)
    return {"poses": made, "failed": failed}


# ── which pose does a shot want? ────────────────────────────────────────────
_POSE_WORDS = {
    "from behind": ["walks away", "walking away", "from behind", "back to", "walks on down", "walks off"],
    "running": ["run", "runs", "running", "gallop", "races", "dash"],
    "walking": ["walk", "walks", "walking", "step", "steps"],
    "sitting": ["sits", "sitting", "sat"],
    "lying": ["lies", "lying", "lay", "asleep", "sleeping"],
    "head lowered": ["sniff", "picks up", "lowers her head", "lowers his head", "nose to the ground", "in her teeth"],
    "looking back": ["looks back", "over her shoulder", "over his shoulder", "turns her head", "turns his head"],
    "from above": ["from above", "looking up", "looks up"],
    "side profile": ["profile", "from the side", "side view"],
    "sad": ["sad", "worried", "lonely", "tears", "ears down"],
    "scared": ["scared", "afraid", "frightened", "shaking", "trembl"],
    "surprised": ["surprised", "gasp", "wide eyes", "startled"],
    "happy": ["happy", "smiles", "smiling", "laughs", "proud", "joy", "bright"],
    "sleepy": ["sleepy", "yawns", "dozes", "calm", "rest"],
    "flying": ["flies", "flying", "flew", "soars", "swoops"],
    "hovering": ["hovers", "hovering"],
    "perched": ["perch", "lands on", "sits on a branch"],
    "landing": ["lands", "landing"],
    "pointing": ["points", "pointing", "that way"],
    "head tilted": ["listens", "listening", "tilts"],
}


def pose_for(prof: dict, udir: Path, name: str, pn: dict) -> Path | None:
    """The registered pose picture whose tags best match this shot's words;
    None when nothing matches (the canonical plate alone is then used)."""
    reg = ((prof.get("world") or {}).get("poses") or {}).get(name.lower()) or {}
    if not reg or udir is None:
        return None
    text = " ".join([str(pn.get("shot") or ""), str(pn.get("motion") or "")]).lower()
    best, score = None, 0
    for pslug, rec in reg.items():
        ptext = str(rec.get("text") or pslug).lower()
        s = 0
        for key, words in _POSE_WORDS.items():
            if key in ptext and any(w in text for w in words):
                s += 2 if rec.get("kind") == "movement" else 1
        if s > score:
            best, score = rec, s
    if best:
        f = udir / best["file"]
        if f.exists() and _md5(f) == best.get("md5"):
            return f
    return None


# ── the atlas ────────────────────────────────────────────────────────────────
async def draw_atlas(slug: str, style: str = "", quality: str = "high", handle=None) -> dict:
    """Draw every atlas place that has no plate yet, in the palette of the
    approved valley plate, and register it. Verification + location_md5 is
    left to establish_world (it already does both)."""
    from .locations import draw_location_plates
    pp, prof = _profile(slug)
    udir = pp.parent
    atlas = ((prof.get("creatives") or {}).get("atlas") or {}).get("places") or {}
    locs = (prof.get("creatives") or {}).get("locations") or {}
    todo = {k: v for k, v in atlas.items() if k not in locs}
    refs = []
    for anchor in ("rainbow-valley", "valley-from-above"):
        f = udir / str(locs.get(anchor) or "")
        if locs.get(anchor) and f.exists():
            refs.append(f); break
    if not todo:
        return {"drawn": {}, "note": "atlas complete"}
    made = await draw_location_plates(udir, prof, todo, style, handle=handle, refs=refs, quality=quality)
    # briefs are kept next to the plates so the Show Bible can print them
    pp, prof = _profile(slug)
    briefs = prof.setdefault("creatives", {}).setdefault("place_briefs", {})
    for k, v in todo.items():
        briefs.setdefault(k, v)
    # AN ATLAS PLATE IS APPROVED BY LARS, NOT BY THE READER (2026-09-03): the
    # first run after the atlas was drawn tore up three plates on "cave" and
    # "stone" reads (a hollow log's opening, a spring's rocky bowl) and redrew
    # pictures he had already been shown. Every atlas plate is recorded as
    # approved by its bytes the moment it is drawn; the gallery is the review.
    approved = prof["creatives"].setdefault("location_md5", {})
    for k, rel in made.items():
        f = udir / rel
        if f.exists():
            approved[k] = _md5(f)
    _save_profile(pp, prof)
    return {"drawn": made}


# ── object sets: one picture per state ──────────────────────────────────────
async def draw_object_set(slug: str, objects: dict, style: str = "", quality: str = "medium",
                          handle=None) -> dict:
    """objects = {"glitter-bell": {"on-the-ribbon": "brief", "lying-in-grass": "brief"}, ...}
    Each state is drawn WITH the object's first state as reference, so the
    object is the same object in every state. Registered as key--state."""
    import httpx
    from ..cover.front_cover import _best_image_model
    from .plates import _draw_with_refs
    pp, prof = _profile(slug)
    udir = pp.parent
    pdir = udir / "props"; pdir.mkdir(exist_ok=True)
    reg = prof.setdefault("world", {}).setdefault("props_plates", {})
    words = prof.setdefault("creatives", {}).setdefault("props", {})
    made, failed = {}, []
    async with httpx.AsyncClient(timeout=260) as client:
        model = await _best_image_model(client)
        for key, states in objects.items():
            base_ref = None
            existing = reg.get(key)
            if isinstance(existing, dict) and (udir / existing["file"]).exists():
                base_ref = udir / existing["file"]
            for state, brief in states.items():
                k2 = f"{key}--{state}"
                dest = pdir / f"{k2}.png"
                if dest.exists() and isinstance(reg.get(k2), dict) and reg[k2].get("md5") == _md5(dest):
                    made[k2] = reg[k2]["file"]; base_ref = base_ref or dest; continue
                prompt = (f"{brief} {style} The object exists exactly once in the picture. No characters, "
                          "no text. Painted in the same style and palette as the reference picture; if a "
                          "reference shows the object, it is THE SAME object — same shape, size, colour and detail.")
                got = await _draw_with_refs(client, model, prompt, [base_ref] if base_ref else [],
                                            dest, size="1536x1024", quality=quality)
                if not got or not dest.exists():
                    failed.append(k2); continue
                reg[k2] = {"file": f"props/{k2}.png", "md5": _md5(dest), "state_of": key, "brief": brief}
                words.setdefault(k2, {"words": [key.replace("-", " "), state.replace("-", " ")], "brief": brief})
                made[k2] = reg[k2]["file"]
                base_ref = base_ref or dest
                if handle:
                    handle.progress(0.6, "objects", k2)
    _save_profile(pp, prof)
    if failed:
        raise RuntimeError("these object states could not be drawn: " + ", ".join(failed))
    return {"objects": made}


# ── the gallery for approval ────────────────────────────────────────────────
def _thumb(p: Path, w: int = 480) -> str:
    from PIL import Image
    im = Image.open(p).convert("RGB")
    im.thumbnail((w, w))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=72)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build_gallery(slug: str, out: Path | None = None, title: str = "Foundation") -> Path:
    """FOUNDATION.html: pose sheets, atlas and object sets, each picture with its hash."""
    pp, prof = _profile(slug)
    udir = pp.parent
    out = out or udir / "FOUNDATION.html"
    w = prof.get("world") or {}; c = prof.get("creatives") or {}
    parts = [f"<title>{title}</title><style>body{{font:14px system-ui;background:#fbf8f2;color:#222;margin:0;padding:24px}}"
             "h1{font-size:22px}h2{font-size:17px;margin:28px 0 8px}h3{font-size:14px;margin:18px 0 6px;color:#555}"
             ".g{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}"
             ".g figure{margin:0;background:#fff;border:1px solid #e6e0d4;border-radius:8px;overflow:hidden}"
             ".g img{width:100%;display:block}.g figcaption{padding:6px 8px;font-size:12px;color:#444}"
             "code{font-size:10px;color:#999}</style>",
             f"<h1>{title} — {slug}</h1>"]
    parts.append("<h2>Characters — canonical plates and pose sheets</h2>")
    for name, rec in (w.get("plates") or {}).items():
        canon = udir / (rec["file"] if isinstance(rec, dict) else rec)
        parts.append(f"<h3>{name.capitalize()}</h3><div class='g'>")
        if canon.exists():
            parts.append(f"<figure><img src='{_thumb(canon)}'><figcaption><b>canonical</b> <code>{_md5(canon)[:10]}</code></figcaption></figure>")
        for pslug, prec in ((w.get("poses") or {}).get(name) or {}).items():
            f = udir / prec["file"]
            if f.exists():
                parts.append(f"<figure><img src='{_thumb(f)}'><figcaption>{prec.get('kind','')}: {prec.get('text', pslug)} <code>{prec.get('md5','')[:10]}</code></figcaption></figure>")
        parts.append("</div>")
    parts.append("<h2>The atlas — places</h2><div class='g'>")
    for key, rel in (c.get("locations") or {}).items():
        f = udir / rel
        if f.exists():
            parts.append(f"<figure><img src='{_thumb(f)}'><figcaption><b>{key}</b><br>{str((c.get('place_briefs') or {}).get(key) or '')[:140]} <code>{_md5(f)[:10]}</code></figcaption></figure>")
    parts.append("</div><h2>Objects — one picture per state</h2><div class='g'>")
    for key, rec in (w.get("props_plates") or {}).items():
        f = udir / (rec["file"] if isinstance(rec, dict) else rec)
        if f.exists():
            parts.append(f"<figure><img src='{_thumb(f)}'><figcaption><b>{key}</b> <code>{_md5(f)[:10]}</code></figcaption></figure>")
    parts.append("</div>")
    out.write_text("\n".join(parts))
    return out
