"""
SCRPT Manuscript Models
========================
Pydantic contracts for prose books (fiction + non-fiction).

The whole manuscript lives inside the book's `data` JSON under `data["manuscript"]`,
alongside `data["format"]` (typesetting config), `data["cover"]`, `data["audio"]`,
and `data["series"]`. This keeps the existing books table schema unchanged.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Kinds & genres ───────────────────────────────────────────────

class BookKind(str, Enum):
    FICTION = "fiction"
    NONFICTION = "nonfiction"


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
    target_words: Optional[int] = None
    trim_size: Optional[str] = None
    paper_type: Optional[str] = None
    font_preset: Optional[str] = None
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
