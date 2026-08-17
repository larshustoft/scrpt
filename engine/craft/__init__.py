"""
SCRPT Craft Playbooks
=====================
The house's craft knowledge as DATA, not code. Each genre family has a
playbook file (engine/craft/playbooks/<family>.md) holding researched,
market-calibrated craft guidance, split into stage sections that the writing
pipeline injects into its prompts:

  ## OUTLINE    -> structure, beats, pacing curve, chapter architecture
  ## CHAPTER    -> language, retention mechanics, chapter-level craft
  ## REVISION   -> quality checks for edit passes (future use)

Playbooks are versioned in git and meant to be RE-GENERATED as models and
research improve — update the file, every future book improves. No code
changes required.
"""

import re
from functools import lru_cache
from pathlib import Path

PLAYBOOK_DIR = Path(__file__).parent / "playbooks"

# genre preset -> playbook family
FAMILY = {
    "action_thriller": "thriller",
    "legal_thriller": "thriller",
    "conspiracy_thriller": "thriller",
    "romance": "romance",
    "historical_romance": "romance",
    "self_help": "nonfiction",
    "business": "nonfiction",
    "mindfulness": "nonfiction",
}

_SECTION_RE = re.compile(r"^## (OUTLINE|CHAPTER|REVISION)\s*$", re.MULTILINE)


@lru_cache(maxsize=16)
def _load_sections(family: str) -> dict:
    path = PLAYBOOK_DIR / f"{family}.md"
    if not path.exists():
        return {}
    text = path.read_text()
    sections = {}
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[m.group(1)] = text[m.start():end].split("\n", 1)[1].strip()
    return sections


def craft(genre_preset: str, stage: str) -> str:
    """Playbook text for a pipeline stage ('OUTLINE' | 'CHAPTER' | 'REVISION')."""
    family = FAMILY.get(genre_preset)
    if not family:
        return ""
    section = _load_sections(family).get(stage, "")
    if not section:
        return ""
    return f"\nCRAFT PLAYBOOK ({family}, {stage.lower()} stage — follow this; it is the house standard):\n{section}\n"


def reload_playbooks():
    """Clear the cache after a playbook file is updated."""
    _load_sections.cache_clear()
