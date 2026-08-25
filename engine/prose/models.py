"""
SCRPT Manuscript Models
========================
Pydantic contracts for prose books (fiction + non-fiction).

The whole manuscript lives inside the book's `data` JSON under `data["manuscript"]`,
alongside `data["format"]` (typesetting config), `data["cover"]`, `data["audio"]`,
and `data["series"]`. This keeps the existing books table schema unchanged.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ── Kinds & genres ───────────────────────────────────────────────

class BookKind(str, Enum):
    FICTION = "fiction"
    NONFICTION = "nonfiction"
    CHILDRENS = "childrens"


# Children's books are measured in SPREADS and reading age, not chapters.
# A picture book is 32 pages by printing convention (a multiple of 8), of
# which ~14 are story spreads. Word counts are the ones the market expects —
# going long is the commonest mistake in the category.
CHILDRENS_PRESETS = {
    "picture_book": {
        "kind": "childrens", "label": "Picture book",
        "age": "3-5", "reading": "read aloud by an adult",
        "spreads": 14, "words_per_spread": 40, "target_words": 560,
        # Print reality: a picture book is folded from sheets, so the page
        # count MUST be divisible by 8 — 24, 32 or 40. 32 is the industry
        # standard: 4 pages of front matter + 14 story spreads (28 pages).
        "pages": 32, "trim": "8.5x8.5", "bleed": 0.125, "safe_margin": 0.25,
        "gutter": 0.375, "paper": "premium_color", "font": "quicksand",
        "voice": "warm, playful, musical — written to be read aloud",
                "describe": "A big square full-colour book an adult reads aloud at bedtime. "
                    "Few words, one picture per page turn.",
        "physical": "32 pages · 8.5 × 8.5 in square · full colour throughout · full-bleed art",
        "example_text": "Pip loved light. Pip did not love dark. Not one single bit.",
        "example_note": "~40 words a spread — the picture carries half the story.",
        "rules": ("Short sentences. Strong rhythm and repetition a child can join in with. "
                  "Concrete nouns and active verbs. One idea per spread. No abstraction, no "
                  "irony, no adult jokes over the child's head. Every spread must give the "
                  "illustrator something new to draw."),
    },
    "early_reader": {
        "kind": "childrens", "label": "Early reader",
        "age": "5-7", "reading": "read by the child, with help",
        "spreads": 16, "words_per_spread": 110, "target_words": 1760,
        "pages": 40, "trim": "6x9", "bleed": 0.125, "safe_margin": 0.25,
        "gutter": 0.375, "paper": "premium_color", "font": "quicksand",
        "voice": "simple, confident, encouraging — the child is the reader now",
                "describe": "The child reads it themselves, with a little help. Short sentences, "
                    "big type, a picture on every page to keep them going.",
        "physical": "40 pages · 6 × 9 in · full colour · larger type, shorter lines",
        "example_text": "Ben opened the door. The wind was loud. \"Come on,\" he said. \"We can do this.\"",
        "example_note": "~110 words a spread — sentences a new reader can decode alone.",
        "rules": ("Simple sentences, mostly common words, sparing use of anything longer than "
                  "two syllables. Dialogue is welcome and helps. Repetition supports decoding. "
                  "Every page turn should reward the effort of getting there."),
    },
    "chapter_book": {
        "kind": "childrens", "label": "Chapter book",
        "age": "7-10", "reading": "read independently",
        "spreads": 10, "words_per_spread": 900, "target_words": 9000,
        "pages": 96, "trim": "5.5x8.5", "bleed": 0.0, "safe_margin": 0.25,
        "gutter": 0.375, "paper": "cream_bw", "font": "crimson",
        "voice": "funny, fast, full of character — never talks down",
                "describe": "Their first proper novel. Short chapters, black-and-white line art, "
                    "read alone under the covers.",
        "physical": "96 pages · 5.5 × 8.5 in · black and white · ~10 short chapters",
        "example_text": "There are three rules about the attic, and Mabel had already broken two of them.",
        "example_note": "~900 words a chapter — every chapter ends on a reason to keep going.",
        "rules": ("Short chapters that each end on a reason to keep going. Real jeopardy at "
                  "a child's scale. Humour and heart. Vocabulary can stretch a little, but "
                  "never at the cost of pace."),
    },
}

# Genre presets drive prompts, typography defaults, and pricing defaults.
# Lengths calibrated against market norms — see docs/BOOK_LENGTH_NORMS.md.
# min_words = genre credibility floor (Publishing checklist warns below it);
# wpp = words-per-printed-page divisor for page estimates at the preset trim.
GENRE_PRESETS = {
    # fiction
    "action_thriller": {
        "kind": "fiction", "label": "Action Thriller",
        "comps": "propulsive international action-thriller in the tradition of the great espionage franchises",
        "trim": "5.5x8.5", "paper": "cream_bw",
        "target_words": 95000, "min_words": 70000, "chapter_words": 2300, "wpp": 265,
        "pov": "third limited, alternating hero/antagonist",
        "structure": "short scene-chapters (3-5 pages), every chapter ends on a hook",
        "font": "garamond",
    },
    "legal_thriller": {
        "kind": "fiction", "label": "Legal Thriller",
        "comps": "courtroom-driven legal thriller with procedural authenticity and moral stakes",
        "trim": "5.5x8.5", "paper": "cream_bw",
        "target_words": 100000, "min_words": 80000, "chapter_words": 3800, "wpp": 265,
        "pov": "third limited",
        "structure": "longer procedural chapters, escalating stakes, minimal POV-hopping",
        "font": "garamond",
    },
    "conspiracy_thriller": {
        "kind": "fiction", "label": "Conspiracy Thriller",
        "comps": "puzzle-driven conspiracy thriller weaving history, symbols and chase sequences",
        "trim": "5.5x8.5", "paper": "cream_bw",
        "target_words": 105000, "min_words": 90000, "chapter_words": 1300, "wpp": 265,
        "pov": "third limited, 3+ rotating POV threads",
        "structure": "very short 2-5 page chapters, ~90-110 of them, each ending on a "
                     "micro-reveal or cliffhanger; 24-48 hour story clock",
        "font": "garamond",
    },
    "romance": {
        "kind": "fiction", "label": "Romance",
        "comps": "emotionally rich contemporary romance with a guaranteed happily-ever-after",
        "trim": "5.25x8", "paper": "cream_bw",
        "target_words": 62000, "min_words": 45000, "chapter_words": 3000, "wpp": 245,
        "pov": "first person, dual POV alternating",
        "structure": "alternating hero/heroine chapters, HEA mandatory, epilogue expected",
        "font": "crimson",
    },
    "historical_romance": {
        "kind": "fiction", "label": "Historical Romance",
        "comps": "sweeping historical romance with period-authentic texture and slow-burn tension",
        "trim": "5.25x8", "paper": "cream_bw",
        "target_words": 90000, "min_words": 75000, "chapter_words": 3000, "wpp": 245,
        "pov": "third limited, dual POV",
        "structure": "alternating POV, period world-building woven through, HEA mandatory",
        "font": "crimson",
    },
    "psychological_thriller": {
        "kind": "fiction", "label": "Psychological Thriller",
        "comps": "twisty psychological thriller with an unreliable narrator and domestic secrets",
        "trim": "5.5x8.5", "paper": "cream_bw",
        "target_words": 85000, "min_words": 65000, "chapter_words": 2800, "wpp": 265,
        "pov": "first person, often unreliable; single or dual timeline",
        "structure": "slow-burn dread, midpoint perspective flip, twist at 85-90% that "
                     "recontextualizes everything, final-page sting",
        "font": "garamond",
    },
    "crime_thriller": {
        "kind": "fiction", "label": "Crime / Detective",
        "comps": "propulsive detective thriller with procedural authenticity and a haunted investigator",
        "trim": "5.5x8.5", "paper": "cream_bw",
        "target_words": 90000, "min_words": 70000, "chapter_words": 3200, "wpp": 265,
        "pov": "third limited on the detective, occasional victim/killer interludes",
        "structure": "body early, investigation ladder with false leads, personal cost "
                     "subplot, killer confrontation climax",
        "font": "garamond",
    },
    "cozy_mystery": {
        "kind": "fiction", "label": "Cozy Mystery",
        "comps": "charming small-town cozy mystery with an amateur sleuth and zero gore",
        "trim": "5x8", "paper": "cream_bw",
        "target_words": 60000, "min_words": 45000, "chapter_words": 2800, "wpp": 240,
        "pov": "first person amateur sleuth",
        "structure": "on-page community warmth, murder off-page, suspect carousel, "
                     "sleuth-in-peril beat, tidy reveal; no explicit violence or sex",
        "font": "crimson",
    },
    "romantasy": {
        "kind": "fiction", "label": "Romantasy",
        "comps": "high-heat fantasy romance with an immersive world and fated tension",
        "trim": "5.5x8.5", "paper": "cream_bw",
        "target_words": 105000, "min_words": 80000, "chapter_words": 3200, "wpp": 265,
        "pov": "first person heroine, sometimes dual POV",
        "structure": "romance beat sheet inside a fantasy quest spine; world-building "
                     "woven through desire, power-imbalance tension, HEA/HFN",
        "font": "crimson",
    },
    "dark_romance": {
        "kind": "fiction", "label": "Dark Romance",
        "comps": "intense dark romance with morally gray leads and high emotional stakes",
        "trim": "5.25x8", "paper": "cream_bw",
        "target_words": 70000, "min_words": 50000, "chapter_words": 2800, "wpp": 245,
        "pov": "first person, dual POV alternating",
        "structure": "antihero love interest, captor/enemy dynamics with clear consent "
                     "codes, trauma arcs, HEA required, content warnings expected",
        "font": "crimson",
    },
    "techno_thriller": {
        "kind": "fiction", "label": "Techno-Thriller",
        "comps": "high-stakes techno-thriller where cutting-edge technology drives the danger",
        "trim": "5.5x8.5", "paper": "cream_bw",
        "target_words": 95000, "min_words": 75000, "chapter_words": 2600, "wpp": 265,
        "pov": "third limited, alternating specialist/antagonist",
        "structure": "tech premise grounded in real plausibility, countdown clock, "
                     "expert protagonist, global-stakes escalation",
        "font": "garamond",
    },
    # non-fiction
    "self_help": {
        "kind": "nonfiction", "label": "Self-Help / Personal Development",
        "comps": "practical, framework-driven personal development in the tradition of modern habit and mindset bestsellers",
        "trim": "6x9", "paper": "white_bw",
        "target_words": 52000, "min_words": 35000, "chapter_words": 3500, "wpp": 285,
        "pov": "second person, direct address",
        "structure": "numbered framework in parts, one tactic per chapter, "
                     "chapter-end summary box",
        "font": "literata",
    },
    "business": {
        "kind": "nonfiction", "label": "Business / Productivity",
        "comps": "actionable business book built around one ownable framework, written for operators",
        "trim": "6x9", "paper": "white_bw",
        "target_words": 60000, "min_words": 45000, "chapter_words": 4000, "wpp": 285,
        "pov": "second person, direct address",
        "structure": "case study + principle + action step rhythm per chapter",
        "font": "sourceserif",
    },
    "personal_finance": {
        "kind": "nonfiction", "label": "Personal Finance",
        "comps": "clear-eyed personal finance book that turns money anxiety into a simple system",
        "trim": "6x9", "paper": "white_bw",
        "target_words": 50000, "min_words": 35000, "chapter_words": 3500, "wpp": 285,
        "pov": "second person, direct address",
        "structure": "money psychology first, then a numbered system, worked examples "
                     "with real arithmetic, action steps per chapter",
        "font": "sourceserif",
    },
    "health_wellness": {
        "kind": "nonfiction", "label": "Health & Wellness",
        "comps": "practical evidence-aware health book with sustainable habits over hacks",
        "trim": "6x9", "paper": "white_bw",
        "target_words": 55000, "min_words": 40000, "chapter_words": 3500, "wpp": 285,
        "pov": "second person, direct address",
        "structure": "myth-busting openers, mechanism explained simply, protocol per "
                     "chapter, never invented studies — established knowledge only",
        "font": "literata",
    },
    "mindfulness": {
        "kind": "nonfiction", "label": "Mindfulness / Spirituality",
        "comps": "calm, present-tense spiritual guide that turns one deep idea over patiently",
        "trim": "5.5x8.5", "paper": "cream_bw",
        "target_words": 45000, "min_words": 30000, "chapter_words": 3800, "wpp": 260,
        "pov": "second person, gentle direct address",
        "structure": "one deep idea per chapter, practice section closing each",
        "font": "ebgaramond_lg",
    },
}


# ── Manuscript blocks ────────────────────────────────────────────

class BlockType(str, Enum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"          # non-fiction subheads (level 2/3)
    SCENE_BREAK = "scene_break"  # fiction ornament break
    BLOCKQUOTE = "blockquote"
    BULLET_LIST = "bullet_list"
    NUMBERED_LIST = "numbered_list"
    CALLOUT = "callout"          # boxed key idea (non-fiction)
    EXERCISE = "exercise"        # action step block (non-fiction)


class Block(BaseModel):
    id: str
    type: BlockType = BlockType.PARAGRAPH
    text: str = ""                       # markdown-lite: *italic* only
    level: int = 2                       # for headings
    items: list[str] = Field(default_factory=list)  # for lists
    title: str = ""                      # for callout/exercise boxes


class ChapterStatus(str, Enum):
    OUTLINED = "outlined"
    DRAFTING = "drafting"
    DRAFTED = "drafted"
    REVISED = "revised"
    FINAL = "final"


class Chapter(BaseModel):
    id: str
    index: int                            # 1-based
    title: str = ""
    subtitle: str = ""
    epigraph: str = ""
    epigraph_source: str = ""
    blocks: list[Block] = Field(default_factory=list)
    status: ChapterStatus = ChapterStatus.OUTLINED
    outline_summary: str = ""             # what this chapter should do (from outline)
    story_event: str = ""                 # Story Grid: what happens + which value shifts
    crisis: str = ""                      # Story Grid: the dilemma this chapter turns on
    value_shift: str = ""                 # what the editor found actually shifted
    audited_crisis: str = ""              # the dilemma the editor found on the page
    beats: list[str] = Field(default_factory=list)
    rolling_summary: str = ""             # what actually happened (for continuity)
    word_count: int = 0
    quality_score: Optional[float] = None # 1-10 from the quality gate
    quality_notes: str = ""
    hook_type: str = ""                   # classified chapter-ending hook
    revised: bool = False                 # rewritten by the quality gate


# ── Bibles ───────────────────────────────────────────────────────

class Character(BaseModel):
    name: str
    role: str = ""                        # protagonist / antagonist / supporting
    description: str = ""
    arc: str = ""
    voice: str = ""                       # speech pattern notes


class StoryBible(BaseModel):
    """Fiction continuity bible."""
    logline: str = ""
    premise: str = ""
    genre: str = ""
    tone: str = ""
    pov: str = ""
    tense: str = "past"
    setting: str = ""
    time_period: str = ""
    characters: list[Character] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    style_notes: str = ""
    ending: str = ""                      # where it must land
    facts: list[str] = Field(default_factory=list)  # canon facts accumulated while drafting


class ConceptBible(BaseModel):
    """Non-fiction framework bible."""
    thesis: str = ""
    promise: str = ""                     # reader transformation
    audience: str = ""
    framework_name: str = ""
    framework_steps: list[str] = Field(default_factory=list)
    terminology: dict[str, str] = Field(default_factory=dict)   # term -> definition
    tone: str = ""
    style_notes: str = ""
    evidence_policy: str = (
        "Never invent studies, statistics, named researchers, or quotations. "
        "Use only broadly established knowledge, first-principles reasoning, and "
        "clearly illustrative composite examples introduced as such."
    )


class SeriesInfo(BaseModel):
    series_id: str = ""
    series_title: str = ""
    book_number: int = 1
    total_planned: int = 1
    series_bible: str = ""                # cross-book canon: arcs, recurring cast, world rules


# ── Front / back matter ──────────────────────────────────────────

class FrontMatterConfig(BaseModel):
    half_title: bool = True
    also_by: list[str] = Field(default_factory=list)   # titles for the "Also by" page
    title_page: bool = True
    copyright_page: bool = True
    copyright_text: str = ""              # empty -> auto-generated from settings
    dedication: str = ""
    epigraph: str = ""
    epigraph_source: str = ""
    toc: Optional[bool] = None            # None -> auto (nonfiction yes, fiction no)
    introduction_title: str = ""          # nonfiction optional intro chapter lives in chapters[0]


class BackMatterConfig(BaseModel):
    acknowledgments: str = ""
    about_the_author: str = ""
    next_in_series_cta: str = ""          # fiction: hook + link text for book N+1
    also_by: list[str] = Field(default_factory=list)


# ── The manuscript root ──────────────────────────────────────────

class ManuscriptStatus(str, Enum):
    IDEA = "idea"
    PLOTTING = "plotting"                 # plot/framework options generated, awaiting pick
    BIBLE = "bible"
    OUTLINED = "outlined"
    DRAFTING = "drafting"
    DRAFTED = "drafted"
    EDITING = "editing"
    LOCKED = "locked"                     # pagination frozen; cover spec valid


class Manuscript(BaseModel):
    kind: BookKind = BookKind.FICTION
    genre_preset: str = "action_thriller"
    idea: str = ""                        # the user's original prompt
    plot_options: list[dict] = Field(default_factory=list)  # generated options [{title, logline, synopsis}]
    chosen_plot: Optional[int] = None
    story_bible: Optional[StoryBible] = None
    concept_bible: Optional[ConceptBible] = None
    target_words: int = 85000
    status: ManuscriptStatus = ManuscriptStatus.IDEA
    chapters: list[Chapter] = Field(default_factory=list)
    front_matter: FrontMatterConfig = Field(default_factory=FrontMatterConfig)
    back_matter: BackMatterConfig = Field(default_factory=BackMatterConfig)
    blurb: str = ""                       # back-cover / listing description
    tagline: str = ""
    ai_disclosure: bool = True            # KDP AI-generated content disclosure flag
    word_count: int = 0
    quality_report: dict = Field(default_factory=dict)  # book-level audit
    arc_map: dict = Field(default_factory=dict)         # story architecture (acts, pinned beats, threads)


# ── Typesetting config (shared contract with frontend) ───────────

FONT_PRESETS = {
    "garamond":     {"label": "EB Garamond",     "family": "EB Garamond",    "size_pt": 11.5, "leading": 1.35},
    "ebgaramond_lg":{"label": "EB Garamond Large","family": "EB Garamond",   "size_pt": 12.5, "leading": 1.42},
    "crimson":      {"label": "Crimson Pro",     "family": "Crimson Pro",    "size_pt": 11.5, "leading": 1.38},
    "literata":     {"label": "Literata",        "family": "Literata",       "size_pt": 10.5, "leading": 1.45},
    "sourceserif":  {"label": "Source Serif 4",  "family": "Source Serif 4", "size_pt": 10.5, "leading": 1.45},
}


class FormatConfig(BaseModel):
    trim_size: str = "5.5x8.5"
    paper_type: str = "cream_bw"
    bleed: bool = False                   # prose interiors don't bleed
    font_preset: str = "garamond"
    font_size_pt: Optional[float] = None  # None -> preset default
    leading: Optional[float] = None
    justify: bool = True
    paragraph_style: str = "indent"       # indent | spaced (nonfiction may use spaced)
    chapter_sink: float = 0.30            # fraction of text block height
    drop_caps: bool = False
    running_header_verso: str = "author"  # author | title | none
    running_header_recto: str = "title"   # title | chapter | none
    scene_break_glyph: str = "* * *"
    # margins: outside/top/bottom chosen by design; gutter computed from page count
    margin_top: float = 0.85
    margin_bottom: float = 0.75
    margin_outside: float = 0.70
    gutter_extra: float = 0.15            # added on top of KDP minimum gutter


class InteriorState(BaseModel):
    page_count: int = 0                   # last pagination result
    locked: bool = False
    pdf_path: str = ""
    exported_at: str = ""
    validation: dict = Field(default_factory=dict)


class CoverMode(str, Enum):
    AI = "ai"
    UPLOAD = "upload"


class CoverState(BaseModel):
    mode: CoverMode = CoverMode.AI
    status: str = "none"                  # none | draft | final | stale
    spec: dict = Field(default_factory=dict)          # computed wrap dimensions
    spec_page_count: int = 0              # page count the spec was computed for
    artwork_path: str = ""
    cover_pdf: str = ""
    cover_front_png: str = ""
    ebook_cover_path: str = ""
    uploaded_path: str = ""
    validation: dict = Field(default_factory=dict)


class AudioChapter(BaseModel):
    index: int
    title: str = ""
    audio_path: str = ""
    duration_s: float = 0.0
    chars: int = 0


class AudioState(BaseModel):
    status: str = "none"                  # none | scripting | rendering | mastered | error
    voice_id: str = ""
    voice_name: str = ""
    model_id: str = "eleven_multilingual_v2"
    pronunciation: dict[str, str] = Field(default_factory=dict)  # word -> phonetic hint
    chapters: list[AudioChapter] = Field(default_factory=list)
    sample_path: str = ""
    total_duration_s: float = 0.0
    mastered_dir: str = ""


# ── Requests ─────────────────────────────────────────────────────

class WorkOrderBook(BaseModel):
    """One book within a work order (a series creates several)."""
    title: str = ""                       # empty -> AI proposes
    idea: str = ""


class WorkOrderRequest(BaseModel):
    kind: BookKind
    genre_preset: str
    idea: str                             # the concept for the book or the whole series
    title: str = ""                       # optional working title
    pen_name: str = ""
    series_title: str = ""                # empty -> standalone
    series_books: int = 1
    book_titles: List[str] = []           # researched titles, one per series book
    target_words: Optional[int] = None
    trim_size: Optional[str] = None
    paper_type: Optional[str] = None
    font_preset: Optional[str] = None
    cover_direction: str = ""             # visual direction from the acquisitions research
    generate_plot_options: bool = True    # produce 3 plot options for approval first
    auto_draft: bool = False              # skip approval, draft immediately with option 1


class PlotChoiceRequest(BaseModel):
    catalog_number: str
    chosen_plot: int                      # index into plot_options
    edits: str = ""                       # user notes to fold into the bible


class DraftRequest(BaseModel):
    catalog_number: str
    chapters: Optional[list[int]] = None  # None -> all remaining


class ChapterEditRequest(BaseModel):
    catalog_number: str
    chapter_id: str
    blocks: list[Block]                   # full replacement of the chapter's blocks


class BlurbRequest(BaseModel):
    catalog_number: str
