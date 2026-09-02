"""The Show Bible: one document, generated from the universe's canonical assets.

Characters, objects, places and the world's standing rules — each picture
shown beside its words and its content hash. It is generated from the same
files every episode is verified against, so what is signed off and what is
drawn from are the same bytes by construction (Lars, 2026-09-02: "the show
bible should be referenced in all processes of drawing storyboards and
generating video").

    python3 -m engine.trailer.show_bible SC-039 princess-the-unicorn

`manifest(profile)` returns the hashes of everything the bible contains; an
episode writes it into its run record, so any film can be traced to the
exact bible it was drawn from.
"""
from __future__ import annotations

import base64, hashlib, html, io, json, sys, time
from pathlib import Path

CHAR_KEYS = ["age", "build", "body shape)", "face", "eyes", "hair", "length",
             "skin_or_fur", "notable features)", "with colours and hex)",
             "clothing", "palette", "hold things)", "never"]


def _img(f: Path, w=820):
    from PIL import Image
    if not f.exists():
        return "", "missing"
    im = Image.open(f).convert("RGB"); im.thumbnail((w, w))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=84)
    return ("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
            hashlib.md5(f.read_bytes()).hexdigest()[:12])


def manifest(profile: dict) -> dict:
    """Every canonical picture the bible holds, by hash."""
    udir = Path(profile.get("profile_path") or ".").parent
    w = profile.get("world") or {}; c = profile.get("creatives") or {}
    out = {"characters": {}, "objects": {}, "places": {}}
    for k, v in (w.get("plates") or {}).items():
        out["characters"][k] = v.get("md5")
    for k, v in (w.get("props_plates") or {}).items():
        out["objects"][k] = v.get("md5")
    for k, rel in (c.get("locations") or {}).items():
        f = udir / rel
        out["places"][k] = hashlib.md5(f.read_bytes()).hexdigest() if f.exists() else None
    out["world_rules"] = hashlib.md5(json.dumps(c.get("world_rules") or [], sort_keys=True).encode()).hexdigest()[:12]
    # THE BOOKENDS AND THE LULLABY ARE FIXED (Lars, 2026-09-02: "the lullaby
    # should not be changed"). Their hashes travel with every run's record,
    # so a change to them is always visible and never accidental.
    out["fixed"] = {}
    for key in ("show_intro", "show_outro"):
        rel = c.get(key)
        f = (udir.parents[1] / rel) if rel and rel.startswith("universe/") else (udir / rel) if rel else None
        out["fixed"][key] = hashlib.md5(f.read_bytes()).hexdigest() if f and f.exists() else None
    lul = ((profile.get("lullaby") or {}).get("frontrunner") or "").split(" ")[0].strip()
    lf = udir / lul if lul else None
    out["fixed"]["lullaby"] = hashlib.md5(lf.read_bytes()).hexdigest() if lf and lf.exists() else None
    return out


def build(catalog: str, slug: str, out: Path = None) -> Path:
    from ..database import get_book_by_catalog
    root = Path(__file__).resolve().parents[2]; udir = root / "universe" / slug
    prof = json.loads((udir / "profile.json").read_text()); prof["profile_path"] = str(udir / "profile.json")
    w = prof.get("world") or {}; c = prof.get("creatives") or {}
    book = get_book_by_catalog(catalog)
    chars = ((book["data"].get("childrens") or {}).get("bible") or {}).get("characters") or []
    title = (prof.get("name") or slug).strip()

    def section(h, body): return f'<section><h2>{html.escape(h)}</h2>{body}</section>'
    def card(pic, cap, code, rows):
        img = f'<img src="{pic}" alt="{html.escape(cap)}">' if pic else '<p class="miss">no plate</p>'
        return f'<article class="c"><figure>{img}<figcaption>{html.escape(cap)} <code>{code}</code></figcaption></figure><dl>{rows}</dl></article>'

    # characters
    cc = []
    for ch in chars:
        name = str(ch.get("name") or ""); pl = (w.get("plates") or {}).get(name.lower()) or {}
        pic, code = _img(udir / pl.get("file", "")) if pl else ("", "no canonical plate")
        rows = "".join(f"<dt>{html.escape(k.rstrip(')'))}</dt><dd>{html.escape(str(ch[k]))}</dd>" for k in CHAR_KEYS if ch.get(k))
        cc.append(card(pic, name, code, rows))
    # objects
    oc = []
    for k, spec in (c.get("props") or {}).items():
        pl = (w.get("props_plates") or {}).get(k) or {}
        pic, code = _img(udir / pl.get("file", "")) if pl else ("", "not yet in the universe")
        look = spec.get("look") if isinstance(spec, dict) else str(spec)
        worn = spec.get("worn_by") if isinstance(spec, dict) else None
        rows = f"<dt>look</dt><dd>{html.escape(str(look))}</dd>"
        if worn: rows += f"<dt>worn by</dt><dd>{html.escape(', '.join(worn if isinstance(worn, list) else [worn]))}</dd>"
        oc.append(card(pic, (spec.get("name") if isinstance(spec, dict) else None) or k, code, rows))
    # places
    pc = []
    for k, rel in (c.get("locations") or {}).items():
        pic, code = _img(udir / rel)
        brief = (c.get("place_briefs") or {}).get(k, "")
        ex = (c.get("place_exemptions") or {}).get(k)
        rows = f"<dt>brief</dt><dd>{html.escape(str(brief))}</dd>" + (f"<dt>may show</dt><dd>{html.escape(', '.join(ex))}</dd>" if ex else "")
        pc.append(card(pic, k, code, rows))
    # world
    rules = "".join(f"<li>{html.escape(r)}</li>" for r in (c.get("world_rules") or []))
    scale_pic, _ = _img(udir / (c.get("scale_plate") or "__none__"))
    world = (f'<ul class="rules">{rules}</ul><p><b>Size chart.</b> {html.escape(str(c.get("scale_chart") or ""))} '
             f'{html.escape(str(c.get("scale_chart_stone") or ""))}</p>' + (f'<img src="{scale_pic}" alt="scale">' if scale_pic else ""))
    m = manifest(prof)
    page = f"""<!doctype html><meta charset="utf-8"><title>{html.escape(title)} — Show Bible</title>
<style>body{{font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:1100px;margin:32px auto;padding:0 24px;color:#1B1A2E;background:#F6F3EE}}
h1{{font-weight:600;margin-bottom:4px}} h2{{margin:44px 0 8px;padding-top:18px;border-top:2px solid #1B1A2E}} .note{{color:#6E6B80;font-size:14px}}
.c{{display:grid;grid-template-columns:340px 1fr;gap:22px;margin:22px 0;padding-top:18px;border-top:1px solid #DDD8E6}} .c img{{width:100%;border-radius:6px}}
figcaption{{margin-top:8px;font-weight:600}} code{{font-weight:400;color:#6E6B80;font-size:12px;margin-left:8px}} dl{{margin:0}}
dt{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#6E6B80;margin-top:10px}} dd{{margin:2px 0 0}} .miss{{color:#C98A1E}}
.rules li{{margin:6px 0}} section>img{{max-width:100%;border-radius:6px;margin-top:10px}}</style>
<h1>{html.escape(title)} — Show Bible</h1>
<p class="note">Generated {time.strftime('%Y-%m-%d %H:%M')} from the universe's canonical plates. Every picture here is, byte for byte, what every episode is verified against before it draws; the code beside each name is its content hash. Manifest: {len(m['characters'])} characters, {len(m['objects'])} objects, {len(m['places'])} places, rules {m['world_rules']}.</p>
{section('The world', world)}{section('Characters', ''.join(cc))}{section('Objects', ''.join(oc))}{section('Places', ''.join(pc))}"""
    out = out or (udir / "SHOW-BIBLE.html"); out.write_text(page); return out


if __name__ == "__main__":
    cat = sys.argv[1] if len(sys.argv) > 1 else "SC-039"; slug = sys.argv[2] if len(sys.argv) > 2 else "princess-the-unicorn"
    print("show bible:", build(cat, slug))
