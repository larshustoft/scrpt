"""
Idea development — the acquisitions desk.

Takes a publisher's rough idea ("a series of romance fiction books, historic
England, aimed at female readers") and returns a researched concept package:
market positioning, the extended idea, series engine, and title suggestions —
grounded in the house's genre playbooks and market norms.
"""

from ..prose.models import GENRE_PRESETS
from .client import complete, extract_json


async def develop_idea(kind: str, genre_preset: str, idea: str,
                       series_books: int = 0) -> dict:
    preset = GENRE_PRESETS.get(genre_preset, {})
    is_series = series_books and series_books > 1
    playbook = ""

    if is_series:
        series_decision = (
            f'"is_series": true (the publisher has committed to a series of '
            f'{series_books} books), '
            f'"recommended_books": {series_books}, ')
    else:
        series_decision = (
            '"is_series": true ONLY if the rough idea asks for or clearly '
            'implies a book SERIES (plural books, "series", a saga, linked '
            'installments) — otherwise false, '
            '"recommended_books": if a series, how many books this concept '
            'should launch with (usually 3-5, judge from the market); 0 if '
            'standalone, ')

    series_fields = series_decision + (
        'IF (and only if) a series: '
        '"series_titles": ["3 candidate SERIES titles — short, ownable, brandable"], '
        '"series_engine": "what generates a new book every time. Thriller '
        'default: SAME-HERO franchise — one recurring protagonist (the brand), '
        'a new self-contained mission per book, supporting cast that accrues. '
        'Romance default: interconnected standalones — new couple per book in '
        'a shared world/family/town, prior couples cameo. EVERY installment '
        'stands alone: complete story, real ending, readable without the '
        'other books. State the recurring '
        'main characters and what changes per book", '
        f'"book_ideas": [{{"title": "...", "logline": "..."}} for the first '
        f'{min(series_books, 6) if is_series else "3-5"} books]. '
        'IF a standalone instead: '
        '"title_suggestions": [{"title": "...", "logline": "..."} x3], '
    )

    prompt = (
        f"A publisher brings you this rough idea for a {preset.get('label', 'book')}"
        f"{' SERIES of ' + str(series_books) + ' books' if is_series else ''}:\n"
        f'"""\n{idea}\n"""\n\n'
        f"House market norms for this genre: target {preset.get('target_words', 0):,} "
        f"words, trim {preset.get('trim', '')}″, {preset.get('pov', '')}, "
        f"structure: {preset.get('structure', '')}.\n"
        f"{playbook}\n\n"
        "As head of acquisitions, develop this into a commissioning package. "
        "FIRST use web search to check the LIVE market: the current Amazon "
        "bestseller lists for this genre (Kindle and paperback), which titles "
        "and authors dominate right now, what their covers and titles signal, "
        "and any adjacent universe readers collect (e.g. Austen/Pride & "
        "Prejudice-adjacent shelves for Regency romance). Then combine that "
        "with your craft knowledge. Actual reader appetites, actual comparable "
        "authors and titles, tropes with proven demand. Be concrete and "
        "commercially honest, never generic.\n"
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
        '"recommendations": {"heat_or_tone": "...", '
        '"target_words": the market-right length for THIS concept (never 0), '
        '"trim_size": the KDP trim for this genre shelf as WxH like "5.25x8" '
        '— use the house norm above unless the market clearly demands another, '
        '"notes": "anything the publisher should decide before commissioning"}'
        "}"
    )
    raw = await complete(
        "You are the head of acquisitions at a commercial publishing house — "
        "equal parts market analyst and story editor. You verify the market "
        "with live web searches before you write; you name actual authors, "
        "titles and tropes, and you flag honestly when demand is thin.",
        prompt, max_tokens=8000, web_search=6)
    return extract_json(raw)
