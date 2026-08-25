"""
Story Grid craft rules — the scene-level engine.

Shawn Coyne's method, adopted 2026-08-24 because it attacks precisely the
faults the acceptance desk keeps catching. Across 54 revision orders in this
catalogue the top complaints were exposition, "dramatize this", rumination,
telling-not-showing and flat recitation — all of which are one fault in Story
Grid terms: A SCENE WITH NO VALUE SHIFT AND NO CRISIS.

Two pillars:

1. THE FIVE COMMANDMENTS. Every unit of story — scene, chapter, act, novel —
   runs inciting incident -> progressive complications -> turning point ->
   crisis -> climax -> resolution. Every unit also has a STORY EVENT: one
   sentence saying what happens and WHICH VALUE CHANGES. If no value shifts,
   it is not a scene; it is exposition with dialogue tags.

2. GLOBAL GENRE. Each genre owes the reader specific OBLIGATORY SCENES. They
   must be ON THE PAGE, not referred to afterwards. A thriller with no
   hero-at-the-mercy-of-the-villain scene has broken its promise.

The point of holding these as data is that they are TESTABLE. "Name the value
that shifted and the dilemma the character faced" is a pass/fail question; a
score out of ten is not.
"""

# ── the obligatory scenes readers actually pay for ───────────────
# Keyed loosely so a preset name only has to contain the key.

OBLIGATORY = {
    "romance": [
        "The lovers meet — and the meeting matters",
        "They are forced together by circumstance despite resistance",
        "A first kiss or first intimacy that changes the relationship",
        "The confession of love (spoken or unmistakably acted)",
        "The lovers break apart — the relationship looks over",
        "A proof of love: one sacrifices something real for the other",
        "The lovers reunite, changed, and the ending settles their future",
    ],
    "thriller": [
        "The hero's first encounter with the antagonist (or the antagonist's work)",
        "The antagonist forces the hero to act — the hero cannot walk away",
        "A false victory or false defeat that turns out to be the opposite",
        "The hero is at the mercy of the villain — genuinely, on the page",
        "The all-is-lost moment where the hero's plan fails completely",
        "The hero and antagonist meet face to face at the climax",
        "The stakes are settled: what was threatened is saved or lost",
    ],
    "mystery": [
        "The crime or disturbance that opens the case",
        "The detective takes the case and states what they are after",
        "A false lead pursued far enough to cost something",
        "The clue that reframes everything already seen",
        "The detective is threatened or personally implicated",
        "The revelation: who, how and why, staged on the page",
        "The consequence — justice, or its absence, lands on someone",
    ],
    "fantasy": [
        "The ordinary world and what the hero lacks in it",
        "The call into the other world or power, and its refusal",
        "A mentor, guide or rule-giver establishes the cost of the magic",
        "A first test that proves the rules are real and dangerous",
        "The all-is-lost moment where the power fails or betrays",
        "The final confrontation on the antagonist's terms",
        "The hero returns changed, and the world's balance is settled",
    ],
    "default": [
        "The inciting incident that knocks the protagonist's life out of balance",
        "The protagonist commits to a course of action with a cost",
        "Escalating complications that close off easier options",
        "A midpoint turn that changes what the story is about",
        "The all-is-lost moment",
        "The climax: the protagonist acts and reveals who they are",
        "The resolution: what the change cost and what it bought",
    ],
}


def obligatory_scenes(genre_preset: str) -> list:
    g = (genre_preset or "").lower()
    if "romance" in g or "romantasy" in g:
        return OBLIGATORY["romance"]
    if "mystery" in g or "cozy" in g or "detective" in g:
        return OBLIGATORY["mystery"]
    if "thriller" in g or "crime" in g or "techno" in g:
        return OBLIGATORY["thriller"]
    if "fantasy" in g:
        return OBLIGATORY["fantasy"]
    return OBLIGATORY["default"]


# ── what every chapter must be able to answer ────────────────────

STORY_EVENT_RULE = (
    "STORY EVENT (Story Grid — non-negotiable). Every chapter must be a SCENE, "
    "not a report. A scene has:\n"
    "  · an inciting incident that upsets the chapter's balance;\n"
    "  · progressive complications that each cost more than the last;\n"
    "  · a turning point that forces a decision;\n"
    "  · a CRISIS — a genuine dilemma, either a best bad choice (two bad "
    "options) or irreconcilable goods (two good ones);\n"
    "  · a climax: the character ACTS on that choice;\n"
    "  · a resolution that leaves the world changed.\n"
    "And above all a VALUE SHIFT: something the reader cares about must move "
    "from one pole to its opposite in this chapter — safety to danger, trust to "
    "betrayal, hope to despair, loneliness to connection. If nothing shifts, the "
    "chapter is exposition and must be rewritten."
)

# Derived from the faults this catalogue's acceptance desk keeps catching.
FORBIDDEN = (
    "NEVER DO THESE — the editor rejects them every time:\n"
    "  · characters taking turns reciting findings or explaining plot to each other;\n"
    "  · a scene that only conveys information and changes nothing;\n"
    "  · rumination — a character thinking at length instead of acting;\n"
    "  · recapping what the reader has already read;\n"
    "  · telling the reader a feeling instead of staging behaviour that shows it;\n"
    "  · dialogue where everyone speaks in the same register."
)


def craft_block(genre_preset: str, story_event: str = "") -> str:
    """The craft rules injected into a drafting prompt."""
    bits = [STORY_EVENT_RULE, FORBIDDEN]
    if story_event:
        bits.insert(0, f"THIS CHAPTER'S STORY EVENT (write to it):\n{story_event}")
    return "\n\n".join(bits)


def obligatory_block(genre_preset: str) -> str:
    lines = "\n".join(f"  {i}. {s}" for i, s in enumerate(obligatory_scenes(genre_preset), 1))
    return (
        "OBLIGATORY SCENES (Story Grid). Readers of this genre have paid for "
        "these moments and will feel cheated without them. Every one must be "
        "STAGED ON THE PAGE in its own chapter — never summarised, never "
        "referred to as having happened off-page:\n" + lines
    )
