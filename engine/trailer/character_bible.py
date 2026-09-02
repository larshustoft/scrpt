"""The Character Bible is generated FROM the canonical plates — one source.

On 2026-09-01 the bible Lars approved was a document made separately from
the plate files the pipeline drew from, and an hour later the plates were
replaced by pictures nobody had approved. Two definitions of a character,
nothing connecting them.

Now the document is built from `universe/<slug>/plates/*.png` — the same
bytes every episode is verified against by hash — plus the bible's words.
What Lars signs off and what the pipeline draws from are the same file by
construction. Regenerate it whenever a plate or the bible changes:

    python3 -m engine.trailer.character_bible SC-039 princess-the-unicorn
"""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import sys
import time
from pathlib import Path

SPEC_KEYS = ["age", "build", "body shape)", "face", "eyes", "hair", "length",
             "skin_or_fur", "notable features)", "with colours and hex)",
             "clothing", "palette", "hold things)"]


def build(catalog: str, slug: str, out: Path = None) -> Path:
    from ..database import get_book_by_catalog
    from PIL import Image
    root = Path(__file__).resolve().parents[2]
    udir = root / "universe" / slug
    prof = json.loads((udir / "profile.json").read_text())
    plates = (prof.get("world") or {}).get("plates") or {}
    book = get_book_by_catalog(catalog)
    chars = ((book["data"].get("childrens") or {}).get("bible") or {}).get("characters") or []
    title = (prof.get("name") or slug).strip()

    def img(rel):
        f = udir / rel
        if not f.exists():
            return "", "missing"
        im = Image.open(f).convert("RGB"); im.thumbnail((900, 900))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=86)
        return ("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
                hashlib.md5(f.read_bytes()).hexdigest()[:12])

    cards = []
    for c in chars:
        name = str(c.get("name") or "")
        pl = plates.get(name.lower()) or {}
        src, h = img(pl.get("file") or "") if pl else ("", "no canonical plate")
        rows = "".join(f"<dt>{html.escape(k.rstrip(')'))}</dt><dd>{html.escape(str(c[k]))}</dd>"
                       for k in SPEC_KEYS if c.get(k))
        pic = f'<img src="{src}" alt="{html.escape(name)}">' if src else '<p class="miss">no plate</p>'
        cards.append(f'<section class="c"><figure>{pic}'
                     f'<figcaption>{html.escape(name)} <code>{h}</code></figcaption></figure><dl>{rows}</dl></section>')
    scale = ""
    sp = (prof.get("creatives") or {}).get("scale_plate")
    if sp and (udir / sp).exists():
        s_src, _ = img(sp); scale = f'<section class="c wide"><h2>How big they are, side by side</h2><img src="{s_src}" alt="scale"></section>'

    page = f"""<!doctype html><meta charset="utf-8"><title>{html.escape(title)} — Character Bible</title>
<style>body{{font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:1100px;margin:32px auto;padding:0 24px;color:#1B1A2E;background:#F6F3EE}}
h1{{font-weight:600}} .note{{color:#6E6B80;font-size:14px}} .c{{display:grid;grid-template-columns:360px 1fr;gap:24px;margin:36px 0;padding-top:24px;border-top:1px solid #DDD8E6}}
.c.wide{{display:block}} .c img{{width:100%;border-radius:6px}} figcaption{{margin-top:8px;font-weight:600}} code{{font-weight:400;color:#6E6B80;font-size:12px;margin-left:8px}}
dl{{margin:0}} dt{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#6E6B80;margin-top:10px}} dd{{margin:2px 0 0}} .miss{{color:#C98A1E}}</style>
<h1>{html.escape(title)} — Character Bible</h1>
<p class="note">Generated {time.strftime('%Y-%m-%d %H:%M')} from the universe's canonical plates. These pictures are, byte for byte, what every episode draws from; the code beside each name is its content hash.</p>
{''.join(cards)}{scale}"""
    out = out or (udir / "CHARACTER-BIBLE.html")
    out.write_text(page)
    return out


if __name__ == "__main__":
    cat = sys.argv[1] if len(sys.argv) > 1 else "SC-039"
    slug = sys.argv[2] if len(sys.argv) > 2 else "princess-the-unicorn"
    p = build(cat, slug)
    print("character bible:", p)
