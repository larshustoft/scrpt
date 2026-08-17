"""
Idea development — the acquisitions desk.

Takes a publisher's rough idea ("a series of romance fiction books, historic
England, aimed at female readers") and returns a researched concept package:
market positioning, the extended idea, series engine, and title suggestions —
grounded in the house's genre playbooks and market norms.
"""

from ..craft import craft
from ..prose.models import GENRE_PRESETS
from .client import complete, extract_json


async def develop_idea(kind: str, genre_preset: str, idea: str,
                       series_books: int = 0) -> dict:
    preset = GENRE_PRESETS.get(genre_preset, {})
    is_series = series_books and series_books > 1
    playbook = craft(genre_preset, "OUTLINE")

    series_fields = (
        '"series_titles": ["3 candidate SERIES titles — short, ownable, brandable"], '
        '"series_engine": "what generates a new book every time. Thriller '
        'default: SAME-HERO franchise — one recurring protagonist (the brand), '
        'a new self-contained mission per book, supporting cast that accrues. '
        'Romance default: interconnected standalones — new couple per book in '
        'a shared world/family/town, prior couples cameo. State the recurring '
        'main characters and what changes per book", '
        f'"book_ideas": [{{"title": "...", "logline": "..."}} for the first '
        f'{min(series_books or 3, 6)} books], '
        if is_series else
        '"title_suggestions": [{"title": "...", "logline": "..."} x3], '
    )

    prompt = (
        f"A publisher brings you this rough idea for a {preset.get('label', 'book')}"
        f"{' SERIES of ' + str(series_books) + ' books' if is_series else ''}:\n"
        f'"""\n{idea}\n"""\n\n'
        f"House market norms for this genre: target {preset.get('target_words', 0):,} "
        f"words, {preset.get('pov', '')}, structure: {preset.get('structure', '')}.\n"
        f"{playbook}\n\n"
        "As head of acquisitions, develop this into a commissioning package. "
        "Draw on real, current market knowledge of the genre — actual reader "
        "appetites, actual comparable authors and titles, tropes with proven "
        "demand. Be concrete and commercially honest, never generic.\n"
        "Return JSON only:\n"
        "{"
        '"market_analysis": "150-220 words: who the reader is, what they buy '
        'now, 3-5 REAL comparable authors/titles, which tropes/subgenres in '
        'this space have demand, where the gap is", '
        '"positioning": "one sentence: how this catalog entry wins its shelf", '
        '"extended_idea": "the rough idea developed into a rich 120-180 word '
        'commissioning brief: setting made specific, protagonist archetypes, '
        'the emotional promise, the hook that differentiates it", '
        f"{series_fields}"
        '"pen_name": "ONE genre-credible pen name for this catalog entry — '
        'reads native to the genre shelf (thriller: punchy Anglo surname; '
        'romance: warm, feminine, memorable; nonfiction: credible full name). '
        'Never a real published author\'s name", '
        '"cover_direction": "60-90 words of visual direction for the covers of '
        'this concept: palette, motifs, typography feel, what bestselling '
        'covers in the genre do — written so it can seed artwork prompts", '
        '"recommendations": {"heat_or_tone": "...", "target_words": 0, '
        '"notes": "anything the publisher should decide before commissioning"}'
        "}"
    )
    raw = await complete(
        "You are the head of acquisitions at a commercial publishing house — "
        "equal parts market analyst and story editor. Your market knowledge is "
        "real and current; you name actual authors, titles and tropes, and you "
        "flag honestly when demand is thin.",
        prompt, max_tokens=6000)
    return extract_json(raw)
