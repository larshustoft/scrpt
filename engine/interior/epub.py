"""
EPUB 3 export — the ebook edition, hand-rolled (no dependencies).

Reflowable EPUB from the manuscript blocks: title page, copyright, chapters,
back matter. No embedded cover page (KDP adds the marketing cover itself and
their guidance is to leave it out of the interior). Kindle overrides fonts,
so we ship clean semantic XHTML + restrained CSS.
"""

import html
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..config import OUTPUT_DIR
from ..database import get_book_by_catalog, get_setting, update_book
from ..prose.models import BlockType, Manuscript

CSS = """
body { margin: 0.5em 1em; font-family: serif; line-height: 1.5; }
h1.chapter { text-align: center; margin: 3em 0 2em 0; font-size: 1.5em; font-weight: 600; }
h1 .chlabel { display: block; font-size: 0.6em; letter-spacing: 0.2em;
  text-transform: uppercase; opacity: 0.6; margin-bottom: 0.8em; font-weight: 400; }
p { margin: 0; text-indent: 1.3em; text-align: justify; }
p.noindent { text-indent: 0; }
h2 { font-size: 1.15em; margin: 1.4em 0 0.5em 0; }
h3 { font-size: 1em; font-style: italic; margin: 1.1em 0 0.4em 0; }
.scenebreak { text-align: center; margin: 1.2em 0; letter-spacing: 0.4em; text-indent: 0; }
blockquote { margin: 0.8em 1.5em; font-style: italic; }
.box { border: 1px solid #666; padding: 0.7em 0.9em; margin: 1em 0; }
.boxtitle { font-weight: 600; font-size: 0.85em; letter-spacing: 0.1em;
  text-transform: uppercase; margin-bottom: 0.4em; }
.titlepage { text-align: center; margin-top: 20%; }
.titlepage .title { font-size: 2em; }
.titlepage .author { font-size: 1.1em; margin-top: 3em; }
.titlepage .tagline { font-style: italic; opacity: 0.75; margin-top: 1.5em; }
.copyright { font-size: 0.8em; margin-top: 30%; }
.copyright p { text-indent: 0; margin-bottom: 0.7em; text-align: left; }
"""


def _smarten(s: str) -> str:
    s = re.sub(r"(\w)'(\w)", "\u2019".join([r"\1", r"\2"]), s)
    s = re.sub(r'(^|[\s([{\u2014\u2013-])"', "\\1\u201c", s)
    s = re.sub(r"(^|[\s([{\u2014\u2013-])'", "\\1\u2018", s)
    s = s.replace('"', "\u201d").replace("'", "\u2019").replace("--", "\u2014")
    return s


def _inline(s: str) -> str:
    out = html.escape(_smarten(s), quote=False)
    return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", out)


def _blocks_to_xhtml(blocks, first_noindent=True) -> str:
    parts = []
    noindent_next = first_noindent
    for b in blocks:
        t = b.type
        if t == BlockType.PARAGRAPH:
            cls = ' class="noindent"' if noindent_next else ""
            parts.append(f"<p{cls}>{_inline(b.text)}</p>")
            noindent_next = False
        elif t == BlockType.SCENE_BREAK:
            parts.append('<p class="scenebreak">* * *</p>')
            noindent_next = True
        elif t == BlockType.HEADING:
            tag = "h3" if b.level == 3 else "h2"
            parts.append(f"<{tag}>{_inline(b.text)}</{tag}>")
            noindent_next = True
        elif t == BlockType.BLOCKQUOTE:
            parts.append(f"<blockquote>{_inline(b.text)}</blockquote>")
        elif t == BlockType.BULLET_LIST:
            items = "".join(f"<li>{_inline(i)}</li>" for i in b.items)
            parts.append(f"<ul>{items}</ul>")
        elif t == BlockType.NUMBERED_LIST:
            items = "".join(f"<li>{_inline(i)}</li>" for i in b.items)
            parts.append(f"<ol>{items}</ol>")
        elif t in (BlockType.CALLOUT, BlockType.EXERCISE):
            title = f'<div class="boxtitle">{_inline(b.title)}</div>' if b.title else ""
            body = "".join(f'<p class="noindent">{_inline(p)}</p>'
                           for p in (b.text or "").split("\n\n") if p.strip())
            parts.append(f'<div class="box">{title}{body}</div>')
    return "\n".join(parts)


def _xhtml(title: str, body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">\n'
        f"<head><title>{html.escape(title)}</title>"
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
        f"<body>{body}</body></html>"
    )


def build_epub(catalog: str) -> dict:
    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError(f"Book {catalog} not found")
    ms = Manuscript.model_validate(book["data"].get("manuscript", {}))
    chapters = [c for c in ms.chapters if c.blocks]
    if not chapters:
        raise ValueError("No drafted chapters to export")

    title = book["title"]
    author = (book["data"].get("author_name") or "").strip() or "Unknown"
    lang = "en"
    uid = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, f'scrpt:{catalog}')}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    publisher = get_setting("publisher_name", "")

    files: list[tuple[str, str]] = []  # (name, xhtml)

    # title page
    series = book["data"].get("series") or {}
    series_line = (f'<p class="noindent" style="margin-top:2em;opacity:0.7">'
                   f'{html.escape(series.get("series_title", ""))} · Book '
                   f'{series.get("book_number", "")}</p>'
                   if series.get("series_title") else "")
    tagline = (f'<div class="tagline">{_inline(ms.tagline)}</div>'
               if ms.tagline else "")
    files.append(("title.xhtml", _xhtml(title,
        f'<div class="titlepage"><div class="title">{_inline(title)}</div>'
        f"{tagline}{series_line}"
        f'<div class="author">{_inline(author)}</div></div>')))

    # copyright
    year = datetime.now().year
    cp = [f"<p>Copyright \u00a9 {year} {html.escape(author)}</p>",
          "<p>All rights reserved.</p>"]
    if ms.kind.value == "fiction":
        cp.append("<p>This is a work of fiction. Names, characters, businesses, "
                  "places, events, and incidents are either the products of the "
                  "author\u2019s imagination or used in a fictitious manner.</p>")
    if publisher:
        cp.append(f"<p>Published by {html.escape(publisher)}</p>")
    files.append(("copyright.xhtml", _xhtml("Copyright",
        f'<div class="copyright">{"".join(cp)}</div>')))

    # chapters
    for ch in chapters:
        label = (f'<span class="chlabel">Chapter {ch.index}</span>'
                 if ms.kind.value == "fiction" else "")
        head = f'<h1 class="chapter">{label}{_inline(ch.title)}</h1>'
        files.append((f"ch{ch.index:03d}.xhtml",
                      _xhtml(ch.title, head + _blocks_to_xhtml(ch.blocks))))

    # back matter
    bm = ms.back_matter
    for key, heading, text in [
        ("next", "The story continues", bm.next_in_series_cta),
        ("ack", "Acknowledgments", bm.acknowledgments),
        ("author", "About the Author", bm.about_the_author),
    ]:
        if text:
            body = "".join(f'<p class="noindent">{_inline(p)}</p>'
                           for p in text.split("\n\n") if p.strip())
            files.append((f"back-{key}.xhtml",
                          _xhtml(heading, f'<h1 class="chapter">{heading}</h1>{body}')))

    # nav
    nav_items = "".join(
        f'<li><a href="{name}">{html.escape(t)}</a></li>'
        for name, t in
        [("title.xhtml", title), ("copyright.xhtml", "Copyright")]
        + [(f"ch{c.index:03d}.xhtml",
            (f"Chapter {c.index}: {c.title}" if ms.kind.value == "fiction" else c.title))
           for c in chapters]
        + [(n, h) for (n, h, t) in [("back-next.xhtml", "The story continues", bm.next_in_series_cta),
                                     ("back-ack.xhtml", "Acknowledgments", bm.acknowledgments),
                                     ("back-author.xhtml", "About the Author", bm.about_the_author)]
           if t])
    nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>'
        '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>'
        f"{nav_items}</ol></nav></body></html>"
    )

    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="css" href="style.css" media-type="text/css"/>']
    spine = []
    for i, (name, _) in enumerate(files):
        fid = f"f{i}"
        manifest.append(f'<item id="{fid}" href="{name}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{fid}"/>')

    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">\n'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f"<dc:identifier id=\"uid\">{uid}</dc:identifier>\n"
        f"<dc:title>{html.escape(title)}</dc:title>\n"
        f"<dc:creator>{html.escape(author)}</dc:creator>\n"
        f"<dc:language>{lang}</dc:language>\n"
        + (f"<dc:publisher>{html.escape(publisher)}</dc:publisher>\n" if publisher else "")
        + f'<meta property="dcterms:modified">{now}</meta>\n'
        "</metadata>\n"
        f"<manifest>{''.join(manifest)}</manifest>\n"
        f"<spine>{''.join(spine)}</spine>\n"
        "</package>"
    )

    out_dir = Path(OUTPUT_DIR) / catalog
    out_dir.mkdir(parents=True, exist_ok=True)
    epub_path = out_dir / "ebook.epub"
    with zipfile.ZipFile(epub_path, "w") as z:
        z.writestr("mimetype", "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0" encoding="utf-8"?>\n'
                   '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>',
                   compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", CSS, compress_type=zipfile.ZIP_DEFLATED)
        for name, content in files:
            z.writestr(f"OEBPS/{name}", content, compress_type=zipfile.ZIP_DEFLATED)

    data = dict(book["data"])
    data.setdefault("ebook", {})
    data["ebook"] = {"epub_path": str(epub_path),
                     "exported_at": now, "chapters": len(chapters)}
    update_book(book["id"], data)
    return {"epub_path": str(epub_path), "chapters": len(chapters)}
