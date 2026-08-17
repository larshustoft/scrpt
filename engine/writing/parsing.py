"""
Chapter text <-> Block parsing.

Claude drafts chapters in a constrained markdown dialect; this module converts
that text into structured Blocks (and back, for revision prompts).

Dialect:
  - paragraphs separated by blank lines
  - "***" alone on a line          -> scene break
  - "## Heading" / "### Heading"   -> heading level 2/3 (non-fiction)
  - "> quoted text"                -> blockquote
  - "- item" lines                 -> bullet list
  - "1. item" lines                -> numbered list
  - ":::callout Title" ... ":::"   -> callout box
  - ":::exercise Title" ... ":::"  -> exercise box
  - *italic* preserved inline
"""

import re
import uuid

from ..prose.models import Block, BlockType


def _bid() -> str:
    return uuid.uuid4().hex[:10]


def parse_chapter_text(text: str) -> list[Block]:
    blocks: list[Block] = []
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    para: list[str] = []
    list_items: list[str] = []
    list_kind: str | None = None

    def flush_para():
        nonlocal para
        joined = " ".join(s.strip() for s in para).strip()
        if joined:
            blocks.append(Block(id=_bid(), type=BlockType.PARAGRAPH, text=joined))
        para = []

    def flush_list():
        nonlocal list_items, list_kind
        if list_items:
            btype = BlockType.BULLET_LIST if list_kind == "bullet" else BlockType.NUMBERED_LIST
            blocks.append(Block(id=_bid(), type=btype, items=list_items))
        list_items, list_kind = [], None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # box blocks
        m = re.match(r"^:::(callout|exercise)\s*(.*)$", stripped)
        if m:
            flush_para(); flush_list()
            kind, title = m.group(1), m.group(2).strip()
            body: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                body.append(lines[i])
                i += 1
            btype = BlockType.CALLOUT if kind == "callout" else BlockType.EXERCISE
            blocks.append(Block(id=_bid(), type=btype, title=title,
                                text="\n".join(body).strip()))
            i += 1
            continue

        if stripped in ("***", "* * *", "◆ ◆ ◆"):
            flush_para(); flush_list()
            blocks.append(Block(id=_bid(), type=BlockType.SCENE_BREAK))
        elif stripped.startswith("### "):
            flush_para(); flush_list()
            blocks.append(Block(id=_bid(), type=BlockType.HEADING, level=3, text=stripped[4:].strip()))
        elif stripped.startswith("## "):
            flush_para(); flush_list()
            blocks.append(Block(id=_bid(), type=BlockType.HEADING, level=2, text=stripped[3:].strip()))
        elif stripped.startswith("> "):
            flush_para(); flush_list()
            quote = [stripped[2:]]
            while i + 1 < len(lines) and lines[i + 1].strip().startswith("> "):
                i += 1
                quote.append(lines[i].strip()[2:])
            blocks.append(Block(id=_bid(), type=BlockType.BLOCKQUOTE, text=" ".join(quote).strip()))
        elif re.match(r"^[-•] ", stripped):
            flush_para()
            if list_kind not in (None, "bullet"):
                flush_list()
            list_kind = "bullet"
            list_items.append(stripped[2:].strip())
        elif re.match(r"^\d+[.)] ", stripped):
            flush_para()
            if list_kind not in (None, "numbered"):
                flush_list()
            list_kind = "numbered"
            list_items.append(re.sub(r"^\d+[.)] ", "", stripped))
        elif stripped == "":
            flush_para(); flush_list()
        else:
            if list_kind:
                flush_list()
            para.append(line)
        i += 1

    flush_para(); flush_list()
    return blocks


def blocks_to_text(blocks: list[Block]) -> str:
    """Serialize blocks back to the drafting dialect (for revision prompts)."""
    out: list[str] = []
    for b in blocks:
        if b.type == BlockType.PARAGRAPH:
            out.append(b.text)
        elif b.type == BlockType.SCENE_BREAK:
            out.append("***")
        elif b.type == BlockType.HEADING:
            out.append(("### " if b.level == 3 else "## ") + b.text)
        elif b.type == BlockType.BLOCKQUOTE:
            out.append("> " + b.text)
        elif b.type == BlockType.BULLET_LIST:
            out.append("\n".join(f"- {item}" for item in b.items))
        elif b.type == BlockType.NUMBERED_LIST:
            out.append("\n".join(f"{n+1}. {item}" for n, item in enumerate(b.items)))
        elif b.type in (BlockType.CALLOUT, BlockType.EXERCISE):
            tag = "callout" if b.type == BlockType.CALLOUT else "exercise"
            out.append(f":::{tag} {b.title}\n{b.text}\n:::")
    return "\n\n".join(out)


def count_words(blocks: list[Block]) -> int:
    total = 0
    for b in blocks:
        total += len(b.text.split())
        for item in b.items:
            total += len(item.split())
    return total
