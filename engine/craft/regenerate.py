"""
Playbook regeneration — the house improves its own craft.

The playbooks are the factory's craft knowledge as data. This module lets the
current writing model re-research and rewrite a playbook: it receives the
existing playbook as the baseline and must strictly improve it — deepen the
research, sharpen the numbers, keep everything that is working. Run it after
a model upgrade and every future book is written to the better standard.

The old playbook is kept as <family>.md.bak-<date> beside the file, and the
files are versioned in git, so a regeneration can always be rolled back.
"""

from datetime import date
from pathlib import Path

from ..writing.client import complete, writing_model
from . import PLAYBOOK_DIR, reload_playbooks

FAMILIES = ("thriller", "romance", "nonfiction")

REQUIRED_SECTIONS = ("## OUTLINE", "## CHAPTER", "## REVISION")


async def regenerate_playbook(family: str) -> dict:
    if family not in FAMILIES:
        raise ValueError(f"Unknown playbook family: {family}")
    path = Path(PLAYBOOK_DIR) / f"{family}.md"
    current = path.read_text() if path.exists() else ""

    prompt = (
        f"This is the house craft playbook for the {family} family at a "
        "commercial publishing operation. It is injected into the outline, "
        "chapter and revision prompts of the writing pipeline, so its quality "
        "directly sets the quality of every book the house produces.\n\n"
        f"CURRENT PLAYBOOK:\n\"\"\"\n{current}\n\"\"\"\n\n"
        "Rewrite it as a strict improvement, drawing on your full, current "
        "knowledge of the genre's bestselling craft: structure and beat "
        "percentages, retention mechanics, language norms, reader "
        "expectations, and what makes readers quit. Rules:\n"
        "- Keep the exact section structure: ## OUTLINE, ## CHAPTER, "
        "## REVISION (these are parsed by machine — do not rename them).\n"
        "- Keep every principle that is correct; sharpen numbers where you "
        "know better figures; add what is missing; cut only what is wrong "
        "or redundant.\n"
        "- Everything must be actionable instruction to a writing model, "
        "not commentary about writing.\n"
        "- Stay in the same terse, imperative house style. Similar overall "
        "length (within ~30%).\n"
        "- Never name living authors as content to imitate in output text; "
        "citing craft norms is fine.\n"
        "Return ONLY the playbook markdown, starting with the first line of "
        "the file."
    )
    text = await complete(
        "You are the head of editorial craft at a commercial publishing "
        "house — a story doctor with deep, current market knowledge. You are "
        "revising the house's own standards document.",
        prompt, max_tokens=16000)

    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    missing = [s for s in REQUIRED_SECTIONS if s not in text]
    if missing:
        raise ValueError(f"Regenerated playbook missing sections: {missing} — kept the old one")

    if current:
        backup = path.with_suffix(f".md.bak-{date.today().isoformat()}")
        backup.write_text(current)
    stamp = (f"<!-- regenerated {date.today().isoformat()} "
             f"by {writing_model()} -->\n")
    path.write_text(stamp + text + "\n")
    reload_playbooks()
    return {"family": family, "model": writing_model(),
            "chars": len(text), "path": str(path)}
