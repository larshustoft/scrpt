"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useBooks } from "@/hooks/useBooks";
import { BOOK_TYPE_LABELS, BOOK_TYPE_SHORT } from "@/lib/types";
import type { BookType, PaperType } from "@/lib/types";
import { IconTarget, IconCheck, IconLoader } from "@/components/icons";

// ── Types ───────────────────────────────────────────────────────

type IdeaCategory = "bestsellers" | "emerging" | "seasonal" | "quick_wins";

interface BookIdea {
  id: string;
  title: string;
  book_type: BookType;
  subtitle: string;
  trim_size: string;
  paper_type: PaperType;
  page_count: number;
  list_price: number;
  niche_keyword: string;
  description: string;
  target_audience: string;
  est_monthly_revenue: string;
  category: IdeaCategory;
  generator_config: Record<string, unknown>;
}

// ── Constants ───────────────────────────────────────────────────

const CATEGORY_META: Record<
  IdeaCategory,
  { label: string; color: string; activeColor: string; description: string }
> = {
  bestsellers: {
    label: "Proven Bestsellers",
    color: "bg-emerald-50 text-emerald-700 border-emerald-200",
    activeColor: "bg-emerald-600 text-white border-emerald-600",
    description: "Established, high-volume demand niches",
  },
  emerging: {
    label: "Emerging Niches",
    color: "bg-violet-50 text-violet-700 border-violet-200",
    activeColor: "bg-violet-600 text-white border-violet-600",
    description: "Growing demand with lower competition",
  },
  seasonal: {
    label: "Seasonal & Trending",
    color: "bg-amber-50 text-amber-700 border-amber-200",
    activeColor: "bg-amber-500 text-white border-amber-500",
    description: "Tied to seasonal demand cycles",
  },
  quick_wins: {
    label: "Quick Wins",
    color: "bg-sky-50 text-sky-700 border-sky-200",
    activeColor: "bg-sky-600 text-white border-sky-600",
    description: "Simple formats, fast to produce and list",
  },
};

const BOOK_TYPE_COLORS: Record<string, string> = {
  word_search: "bg-blue-100 text-blue-700",
  sudoku: "bg-purple-100 text-purple-700",
  math_workbook: "bg-amber-100 text-amber-700",
  cryptogram: "bg-emerald-100 text-emerald-700",
  maze: "bg-rose-100 text-rose-700",
  password_log: "bg-slate-200 text-slate-700",
  journal: "bg-teal-100 text-teal-700",
};

const PAPER_LABELS: Record<string, string> = {
  white_bw: "White B&W",
  cream_bw: "Cream B&W",
  standard_color: "Standard Color",
  premium_color: "Premium Color",
};

// ── 28 Curated Book Ideas ───────────────────────────────────────

const BOOK_IDEAS: BookIdea[] = [
  // ── Proven Bestsellers (8) ──────────────────────────────────
  {
    id: "ws-seniors-large-print",
    title: "Ultimate Large Print Word Search for Seniors",
    book_type: "word_search",
    subtitle: "Relaxing Themed Puzzles",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 12.97,
    niche_keyword: "large print word search seniors",
    description:
      "The highest-selling KDP activity book niche. Large print format targets the 65+ demographic with themed puzzles across nature, travel, food, and everyday life.",
    target_audience: "Seniors 65+",
    est_monthly_revenue: "$150 - $300",
    category: "bestsellers",
    generator_config: {
      subtitle: "Relaxing Themed Puzzles",
      num_puzzles: 55,
      grid_size: 15,
      words_per_puzzle: 15,
      difficulty: "medium",
      large_print: true,
    },
  },
  {
    id: "su-beginners-easy",
    title: "Easy Sudoku for Beginners — Large Print",
    book_type: "sudoku",
    subtitle: "Gentle Brain Training",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 9.97,
    niche_keyword: "easy sudoku large print beginners",
    description:
      "Beginner-friendly sudoku with 35-40 clue puzzles in large print. Targets new puzzle solvers and seniors looking for relaxing brain exercise without frustration.",
    target_audience: "New puzzlers / Seniors",
    est_monthly_revenue: "$80 - $180",
    category: "bestsellers",
    generator_config: {
      subtitle: "Gentle Brain Training",
      num_puzzles: 55,
      difficulty: "easy",
      large_print: true,
    },
  },
  {
    id: "mw-multiplication-grade3",
    title: "Multiplication & Division Practice: Grades 3-4",
    book_type: "math_workbook",
    subtitle: "Multiplication & Division Practice",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 12.97,
    niche_keyword: "multiplication division practice grade 3 4",
    description:
      "Parents buy math workbooks year-round for supplemental practice. Multiplication and division focus for grades 3-4 is a perennial best-seller with strong back-to-school demand.",
    target_audience: "Parents / Kids 8-10",
    est_monthly_revenue: "$120 - $250",
    category: "bestsellers",
    generator_config: {
      subtitle: "Multiplication & Division Practice",
      num_pages: 50,
      problems_per_page: 20,
      operation: "mixed",
      difficulty: "medium",
      large_print: true,
    },
  },
  {
    id: "mw-addition-grade1",
    title: "Addition & Subtraction Practice: Grades 1-2",
    book_type: "math_workbook",
    subtitle: "Addition & Subtraction Practice",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 12.97,
    niche_keyword: "addition subtraction workbook grade 1 2",
    description:
      "The foundational math workbook for early elementary. Easy difficulty with single and double-digit problems. Strong year-round demand from parents and teachers.",
    target_audience: "Parents / Kids 6-7",
    est_monthly_revenue: "$120 - $250",
    category: "bestsellers",
    generator_config: {
      subtitle: "Addition & Subtraction Practice",
      num_pages: 50,
      problems_per_page: 20,
      operation: "mixed",
      difficulty: "easy",
      large_print: true,
    },
  },
  {
    id: "pl-password-organizer",
    title: "Internet Password Organizer",
    book_type: "password_log",
    subtitle: "Keep Your Passwords Safe & Organized",
    trim_size: "6x9",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 7.99,
    niche_keyword: "password organizer book alphabetical",
    description:
      "A top-10 KDP utility niche. Seniors and non-tech-savvy users buy physical password books for simple, secure offline storage. Alphabetical tabs for easy lookup.",
    target_audience: "Seniors / Non-tech users",
    est_monthly_revenue: "$60 - $150",
    category: "bestsellers",
    generator_config: {
      subtitle: "Keep Your Passwords Safe & Organized",
      log_type: "password_organizer",
    },
  },
  {
    id: "jn-gratitude-daily",
    title: "Daily Gratitude Journal",
    book_type: "journal",
    subtitle: "Start Each Day with Gratitude",
    trim_size: "6x9",
    paper_type: "cream_bw",
    page_count: 200,
    list_price: 9.99,
    niche_keyword: "gratitude journal daily",
    description:
      "Gratitude journals are a proven evergreen niche in wellness. Cream paper gives a premium feel. Each page includes structured prompts for morning reflection.",
    target_audience: "Wellness / Self-help",
    est_monthly_revenue: "$80 - $200",
    category: "bestsellers",
    generator_config: {
      subtitle: "Start Each Day with Gratitude",
      log_type: "gratitude_journal",
    },
  },
  {
    id: "cr-adults-large-print",
    title: "Large Print Cryptogram Puzzles for Adults",
    book_type: "cryptogram",
    subtitle: "Decode Famous Quotes",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 11.97,
    niche_keyword: "large print cryptogram puzzles adults",
    description:
      "Cryptograms are an underserved niche with strong demand from adult puzzle enthusiasts. Each puzzle decodes an inspirational quote, combining word play with motivation.",
    target_audience: "Adult puzzle fans",
    est_monthly_revenue: "$100 - $200",
    category: "bestsellers",
    generator_config: {
      subtitle: "Decode Famous Quotes",
      num_puzzles: 55,
      large_print: true,
    },
  },
  {
    id: "ws-kids-8-12",
    title: "Word Search Book for Kids Ages 8-12",
    book_type: "word_search",
    subtitle: "Fun Themed Puzzles for Smart Kids",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 9.97,
    niche_keyword: "word search kids ages 8 12",
    description:
      "Kids word search books have consistent demand from parents looking for screen-free activities. Medium difficulty with age-appropriate themes like animals, sports, and science.",
    target_audience: "Parents / Kids 8-12",
    est_monthly_revenue: "$80 - $160",
    category: "bestsellers",
    generator_config: {
      subtitle: "Fun Themed Puzzles for Smart Kids",
      num_puzzles: 50,
      grid_size: 13,
      words_per_puzzle: 12,
      difficulty: "easy",
      large_print: true,
    },
  },

  // ── Emerging Niches (7) ─────────────────────────────────────
  {
    id: "su-expert-challenge",
    title: "Expert Sudoku Challenge: 200+ Puzzles",
    book_type: "sudoku",
    subtitle: "200+ Expert Puzzles",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 9.97,
    niche_keyword: "hard sudoku expert puzzles",
    description:
      "The complement to beginner sudoku. Expert-level puzzles with 17-21 clues for serious solvers looking for a genuine challenge. Less competition than easy/medium books.",
    target_audience: "Experienced solvers",
    est_monthly_revenue: "$70 - $150",
    category: "emerging",
    generator_config: {
      subtitle: "200+ Expert Puzzles",
      num_puzzles: 55,
      difficulty: "expert",
      large_print: false,
    },
  },
  {
    id: "mz-adults-hard",
    title: "Challenging Mazes for Adults",
    book_type: "maze",
    subtitle: "Complex Brain Training Puzzles",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 9.97,
    niche_keyword: "hard maze book adults brain training",
    description:
      "Adult maze books with complex paths are an emerging niche. Targets the brain-training audience alongside crosswords and sudoku. Hard difficulty for a genuine challenge.",
    target_audience: "Adults / Brain training",
    est_monthly_revenue: "$60 - $140",
    category: "emerging",
    generator_config: {
      subtitle: "Complex Brain Training Puzzles",
      num_puzzles: 50,
      difficulty: "hard",
      large_print: false,
    },
  },
  {
    id: "ws-bible-large-print",
    title: "Bible Word Search: Large Print — Old & New Testament",
    book_type: "word_search",
    subtitle: "Inspiring Biblical Puzzles",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 12.97,
    niche_keyword: "bible word search large print",
    description:
      "Faith-based word search books have a dedicated, loyal audience. Themed puzzles covering stories, places, and people from both testaments. Strong gift-giving potential.",
    target_audience: "Christian adults / Seniors",
    est_monthly_revenue: "$100 - $220",
    category: "emerging",
    generator_config: {
      subtitle: "Inspiring Biblical Puzzles",
      num_puzzles: 55,
      grid_size: 15,
      words_per_puzzle: 15,
      difficulty: "medium",
      large_print: true,
    },
  },
  {
    id: "jn-anxiety-relief",
    title: "Anxiety Relief Journal: CBT-Inspired Prompts",
    book_type: "journal",
    subtitle: "Daily Calm Through Guided Reflection",
    trim_size: "6x9",
    paper_type: "cream_bw",
    page_count: 200,
    list_price: 11.99,
    niche_keyword: "anxiety relief journal CBT prompts",
    description:
      "Mental health journals are surging. CBT-inspired prompts help readers challenge negative thoughts and build coping strategies. Higher price point due to perceived therapeutic value.",
    target_audience: "Adults with anxiety / Therapists",
    est_monthly_revenue: "$100 - $200",
    category: "emerging",
    generator_config: {
      subtitle: "Daily Calm Through Guided Reflection",
      log_type: "gratitude_journal",
    },
  },
  {
    id: "ws-spanish-beginners",
    title: "Spanish Word Search for Beginners",
    book_type: "word_search",
    subtitle: "Learn Spanish with Fun Puzzles",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 11.97,
    niche_keyword: "spanish word search beginners",
    description:
      "Bilingual activity books are growing fast. Spanish word search targets language learners with themed vocabulary puzzles. Dual English/Spanish format adds unique value.",
    target_audience: "Spanish learners / Bilingual families",
    est_monthly_revenue: "$70 - $160",
    category: "emerging",
    generator_config: {
      subtitle: "Learn Spanish with Fun Puzzles",
      num_puzzles: 50,
      grid_size: 13,
      words_per_puzzle: 12,
      difficulty: "easy",
      large_print: true,
    },
  },
  {
    id: "mw-adults-sharpen",
    title: "Math Workbook for Adults: Sharpen Your Skills",
    book_type: "math_workbook",
    subtitle: "Sharpen Your Skills",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 12.97,
    niche_keyword: "math workbook adults practice",
    description:
      "Adult math practice is an underserved niche. Targets GED prep students, returning learners, and adults who want to stay sharp. Mixed operations at medium difficulty.",
    target_audience: "Adult learners / GED prep",
    est_monthly_revenue: "$80 - $170",
    category: "emerging",
    generator_config: {
      subtitle: "Sharpen Your Skills",
      num_pages: 50,
      problems_per_page: 20,
      operation: "mixed",
      difficulty: "medium",
      large_print: true,
    },
  },
  {
    id: "cr-movie-quotes",
    title: "Cryptogram Book: Movie Quotes Edition",
    book_type: "cryptogram",
    subtitle: "Decode Iconic Movie Lines",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 11.97,
    niche_keyword: "cryptogram movie quotes puzzles",
    description:
      "Themed cryptograms with movie quotes appeal to both puzzle fans and film lovers. A unique angle in the cryptogram space with very few competitors.",
    target_audience: "Movie fans / Puzzle enthusiasts",
    est_monthly_revenue: "$60 - $140",
    category: "emerging",
    generator_config: {
      subtitle: "Decode Iconic Movie Lines",
      num_puzzles: 55,
      large_print: true,
    },
  },

  // ── Seasonal & Trending (7) ─────────────────────────────────
  {
    id: "ws-summer-travel",
    title: "Summer Travel Word Search",
    book_type: "word_search",
    subtitle: "Vacation Puzzles On the Go",
    trim_size: "5.5x8.5",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 9.97,
    niche_keyword: "summer travel word search book",
    description:
      "Compact travel-sized word search for summer vacations. Smaller trim size fits in bags and backpacks. Peaks May-August with strong impulse purchase potential.",
    target_audience: "Travelers / Vacationers",
    est_monthly_revenue: "$60 - $150",
    category: "seasonal",
    generator_config: {
      subtitle: "Vacation Puzzles On the Go",
      num_puzzles: 50,
      grid_size: 13,
      words_per_puzzle: 12,
      difficulty: "easy",
      large_print: false,
    },
  },
  {
    id: "mw-back-to-school-grade2",
    title: "Back to School Math Practice: Grade 2",
    book_type: "math_workbook",
    subtitle: "Get Ready for 2nd Grade",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 12.97,
    niche_keyword: "back to school math practice grade 2",
    description:
      "Back-to-school season (July-September) drives massive demand for grade-specific workbooks. Grade 2 is the sweet spot where parents first seek supplemental materials.",
    target_audience: "Parents / Teachers",
    est_monthly_revenue: "$100 - $250",
    category: "seasonal",
    generator_config: {
      subtitle: "Get Ready for 2nd Grade",
      num_pages: 50,
      problems_per_page: 20,
      operation: "mixed",
      difficulty: "easy",
      large_print: true,
    },
  },
  {
    id: "ws-christmas-holiday",
    title: "Christmas Word Search: Large Print Holiday Puzzles",
    book_type: "word_search",
    subtitle: "Festive Holiday Puzzles",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 9.97,
    niche_keyword: "christmas word search large print",
    description:
      "Christmas-themed books spike October-December and make excellent stocking stuffers. Large print appeals to the senior gift market. List by September for maximum Q4 sales.",
    target_audience: "Gift buyers / Seniors",
    est_monthly_revenue: "$80 - $300",
    category: "seasonal",
    generator_config: {
      subtitle: "Festive Holiday Puzzles",
      num_puzzles: 50,
      grid_size: 15,
      words_per_puzzle: 15,
      difficulty: "easy",
      large_print: true,
    },
  },
  {
    id: "jn-new-year-goals",
    title: "New Year Goal Setting Journal",
    book_type: "journal",
    subtitle: "Plan Your Best Year Yet",
    trim_size: "6x9",
    paper_type: "cream_bw",
    page_count: 200,
    list_price: 9.99,
    niche_keyword: "new year goal setting journal planner",
    description:
      "Goal-setting journals peak November-January as people plan their new year resolutions. Structured prompts for monthly, weekly, and daily goal tracking.",
    target_audience: "Productivity / Self-improvement",
    est_monthly_revenue: "$70 - $200",
    category: "seasonal",
    generator_config: {
      subtitle: "Plan Your Best Year Yet",
      log_type: "gratitude_journal",
    },
  },
  {
    id: "pl-teacher-planner",
    title: "Teacher Planner & Organizer",
    book_type: "password_log",
    subtitle: "Lesson Plans, Grades & Notes",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 9.99,
    niche_keyword: "teacher planner organizer",
    description:
      "Teacher planners spike July-August as educators prepare for the school year. Larger format for lesson plans, grade tracking, and class notes. Strong repeat purchase potential.",
    target_audience: "Teachers / Educators",
    est_monthly_revenue: "$80 - $200",
    category: "seasonal",
    generator_config: {
      subtitle: "Lesson Plans, Grades & Notes",
      log_type: "password_organizer",
    },
  },
  {
    id: "su-stocking-stuffer",
    title: "Sudoku Stocking Stuffer: Pocket Size",
    book_type: "sudoku",
    subtitle: "Mini Puzzles for the Holidays",
    trim_size: "5x8",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 7.97,
    niche_keyword: "pocket sudoku stocking stuffer",
    description:
      "Pocket-sized sudoku books make ideal stocking stuffers at a low price point. The 5x8 trim keeps costs down and margins healthy. List by October for Q4 gift season.",
    target_audience: "Gift buyers",
    est_monthly_revenue: "$50 - $180",
    category: "seasonal",
    generator_config: {
      subtitle: "Mini Puzzles for the Holidays",
      num_puzzles: 55,
      difficulty: "medium",
      large_print: false,
    },
  },
  {
    id: "mz-road-trip-kids",
    title: "Road Trip Activity Mazes for Kids",
    book_type: "maze",
    subtitle: "Keep Kids Busy on the Road",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 80,
    list_price: 8.97,
    niche_keyword: "road trip maze activity book kids",
    description:
      "Travel activity books for kids peak during summer road trip season. Mazes are screen-free entertainment that parents actively seek. Easy difficulty for ages 5-9.",
    target_audience: "Parents / Kids 5-9",
    est_monthly_revenue: "$50 - $130",
    category: "seasonal",
    generator_config: {
      subtitle: "Keep Kids Busy on the Road",
      num_puzzles: 40,
      difficulty: "easy",
      large_print: true,
    },
  },

  // ── Quick Wins (6) ──────────────────────────────────────────
  {
    id: "pl-password-floral",
    title: "Password & Login Tracker: Floral Cover",
    book_type: "password_log",
    subtitle: "Beautiful & Practical Password Keeper",
    trim_size: "6x9",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 7.99,
    niche_keyword: "password tracker floral cover women",
    description:
      "A design variant of the proven password organizer niche. Floral covers appeal strongly to women 40+. Same interior, different cover — fast to produce with minimal effort.",
    target_audience: "Women 40+ / Gift buyers",
    est_monthly_revenue: "$40 - $120",
    category: "quick_wins",
    generator_config: {
      subtitle: "Beautiful & Practical Password Keeper",
      log_type: "password_organizer",
    },
  },
  {
    id: "su-relaxation",
    title: "Simple Sudoku: Relaxation Edition",
    book_type: "sudoku",
    subtitle: "Unwind with Easy Puzzles",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 120,
    list_price: 9.97,
    niche_keyword: "relaxation sudoku easy puzzles adults",
    description:
      "Positioning sudoku as relaxation rather than brain training taps into the wellness audience. Easy puzzles, large print, calming branding. Quick to produce with proven generators.",
    target_audience: "Wellness / Relaxation seekers",
    est_monthly_revenue: "$60 - $140",
    category: "quick_wins",
    generator_config: {
      subtitle: "Unwind with Easy Puzzles",
      num_puzzles: 55,
      difficulty: "easy",
      large_print: true,
    },
  },
  {
    id: "mz-kids-6-8",
    title: "Amazing Mazes for Kids Ages 6-8",
    book_type: "maze",
    subtitle: "Fun Puzzles for Young Explorers",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 9.97,
    niche_keyword: "maze book kids ages 6 8",
    description:
      "Kids maze books sell strongly in the educational activity category. Easy difficulty with large, clear paths designed for young solvers building spatial skills.",
    target_audience: "Kids 6-8 / Parents",
    est_monthly_revenue: "$80 - $160",
    category: "quick_wins",
    generator_config: {
      subtitle: "Fun Puzzles for Young Explorers",
      num_puzzles: 50,
      difficulty: "easy",
      large_print: true,
    },
  },
  {
    id: "jn-pregnancy",
    title: "Pregnancy Journal & Memory Book",
    book_type: "journal",
    subtitle: "Track Your Journey to Motherhood",
    trim_size: "6x9",
    paper_type: "cream_bw",
    page_count: 200,
    list_price: 12.99,
    niche_keyword: "pregnancy journal memory book",
    description:
      "Pregnancy journals have steady demand and command a higher price point. Prompts cover each trimester with space for milestones, appointments, and reflections.",
    target_audience: "Expecting mothers / Gift buyers",
    est_monthly_revenue: "$80 - $180",
    category: "quick_wins",
    generator_config: {
      subtitle: "Track Your Journey to Motherhood",
      log_type: "gratitude_journal",
    },
  },
  {
    id: "mw-division-grade4",
    title: "Division Practice: Grades 4-5",
    book_type: "math_workbook",
    subtitle: "Master Division Skills",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 12.97,
    niche_keyword: "division practice workbook grade 4 5",
    description:
      "Division-focused workbooks fill a gap between general math books. Grades 4-5 targets the age where division becomes critical. Simple generator config, fast to produce.",
    target_audience: "Parents / Kids 9-11",
    est_monthly_revenue: "$80 - $180",
    category: "quick_wins",
    generator_config: {
      subtitle: "Master Division Skills",
      num_pages: 50,
      problems_per_page: 20,
      operation: "division",
      difficulty: "medium",
      large_print: true,
    },
  },
  {
    id: "ws-teens-pop-culture",
    title: "Word Search for Teens: Pop Culture & Social Media",
    book_type: "word_search",
    subtitle: "Trending Topics for Gen Z",
    trim_size: "8.5x11",
    paper_type: "white_bw",
    page_count: 100,
    list_price: 9.97,
    niche_keyword: "word search teens pop culture",
    description:
      "Teen-focused activity books are underserved on KDP. Pop culture and social media themes resonate with 13-17 year olds. Medium difficulty with trendy vocabulary.",
    target_audience: "Teens 13-17 / Parents",
    est_monthly_revenue: "$50 - $130",
    category: "quick_wins",
    generator_config: {
      subtitle: "Trending Topics for Gen Z",
      num_puzzles: 50,
      grid_size: 14,
      words_per_puzzle: 14,
      difficulty: "medium",
      large_print: false,
    },
  },
];

// ── Helpers ─────────────────────────────────────────────────────

function formatTrim(trim: string): string {
  const parts = trim.split("x");
  if (parts.length === 2) return `${parts[0]}" x ${parts[1]}"`;
  return trim;
}

const ALL_CATEGORIES: IdeaCategory[] = [
  "bestsellers",
  "emerging",
  "seasonal",
  "quick_wins",
];

// ── Page Component ──────────────────────────────────────────────

export default function ResearchPage() {
  const router = useRouter();
  const { books, createBook } = useBooks();

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [createProgress, setCreateProgress] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<
    "all" | IdeaCategory
  >("all");
  const [typeFilter, setTypeFilter] = useState<"all" | BookType>("all");

  const filteredIdeas = BOOK_IDEAS.filter((idea) => {
    if (activeCategory !== "all" && idea.category !== activeCategory)
      return false;
    if (typeFilter !== "all" && idea.book_type !== typeFilter) return false;
    return true;
  });

  const selectedCount = selectedIds.size;

  const toggleSelect = (id: string) => {
    if (creating) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllVisible = () => {
    if (creating) return;
    const visibleIds = new Set(filteredIdeas.map((i) => i.id));
    const allSelected = filteredIdeas.every((i) => selectedIds.has(i.id));
    if (allSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        visibleIds.forEach((id) => next.delete(id));
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        visibleIds.forEach((id) => next.add(id));
        return next;
      });
    }
  };

  const isInCatalog = (idea: BookIdea) =>
    books.some((b) => b.title === idea.title);

  const handleCreate = async () => {
    setCreating(true);
    setError(null);

    const ideas = BOOK_IDEAS.filter((idea) => selectedIds.has(idea.id));

    try {
      for (let i = 0; i < ideas.length; i++) {
        const idea = ideas[i];
        setCreateProgress(`Creating ${i + 1} of ${ideas.length}...`);
        await createBook({
          title: idea.title,
          book_type: idea.book_type,
          subtitle: idea.subtitle,
          trim_size: idea.trim_size,
          paper_type: idea.paper_type,
          page_count: idea.page_count,
          list_price: idea.list_price,
          niche_keyword: idea.niche_keyword,
          generator_config: idea.generator_config,
        });
      }
      router.push("/catalog");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create books");
    } finally {
      setCreating(false);
      setCreateProgress("");
    }
  };

  // Count per category for badges
  const categoryCounts = ALL_CATEGORIES.reduce(
    (acc, cat) => {
      acc[cat] = BOOK_IDEAS.filter((i) => i.category === cat).length;
      return acc;
    },
    {} as Record<IdeaCategory, number>
  );

  // Unique book types present in ideas
  const availableTypes = Array.from(
    new Set(BOOK_IDEAS.map((i) => i.book_type))
  ).sort();

  return (
    <div className="p-8 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Book Ideas</h1>
          <p className="text-sm text-slate-500 mt-1">
            {BOOK_IDEAS.length} curated concepts ready for one-click creation
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={selectAllVisible}
            disabled={creating}
            className="text-sm text-slate-500 hover:text-slate-900 transition-colors disabled:opacity-50"
          >
            {filteredIdeas.every((i) => selectedIds.has(i.id)) &&
            filteredIdeas.length > 0
              ? "Deselect all"
              : "Select all"}
          </button>
          <button
            onClick={handleCreate}
            disabled={selectedCount === 0 || creating}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {creating ? (
              <>
                <IconLoader className="w-4 h-4" />
                {createProgress}
              </>
            ) : selectedCount > 0 ? (
              `Create ${selectedCount} ${selectedCount === 1 ? "Book" : "Books"}`
            ) : (
              "Select ideas to create"
            )}
          </button>
        </div>
      </div>

      {/* Info Banner */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 mb-6">
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100">
            <IconTarget className="w-4 h-4 text-blue-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-blue-800">
              One-Click Book Creation
            </h3>
            <p className="text-xs text-blue-600 mt-1">
              Each idea is pre-configured with optimal format, pricing, and
              generator settings for proven KDP niches. Select one or more and
              create production-ready book projects instantly.
            </p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        {/* Category pills */}
        <button
          onClick={() => setActiveCategory("all")}
          className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
            activeCategory === "all"
              ? "bg-slate-900 text-white border-slate-900"
              : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
          }`}
        >
          All ({BOOK_IDEAS.length})
        </button>
        {ALL_CATEGORIES.map((cat) => {
          const meta = CATEGORY_META[cat];
          const isActive = activeCategory === cat;
          return (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                isActive ? meta.activeColor : `${meta.color} hover:opacity-80`
              }`}
            >
              {meta.label} ({categoryCounts[cat]})
            </button>
          );
        })}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Book type filter */}
        <select
          value={typeFilter}
          onChange={(e) =>
            setTypeFilter(e.target.value as "all" | BookType)
          }
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="all">All types</option>
          {availableTypes.map((bt) => (
            <option key={bt} value={bt}>
              {BOOK_TYPE_LABELS[bt]}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 mb-6">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Empty state */}
      {filteredIdeas.length === 0 && (
        <div className="text-center py-16">
          <p className="text-sm text-slate-500">
            No ideas match the current filters.
          </p>
          <button
            onClick={() => {
              setActiveCategory("all");
              setTypeFilter("all");
            }}
            className="mt-2 text-sm text-blue-600 hover:text-blue-500"
          >
            Clear filters
          </button>
        </div>
      )}

      {/* Card Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredIdeas.map((idea) => {
          const selected = selectedIds.has(idea.id);
          const inCatalog = isInCatalog(idea);
          const typeColor =
            BOOK_TYPE_COLORS[idea.book_type] || "bg-gray-100 text-gray-700";
          const catMeta = CATEGORY_META[idea.category];

          return (
            <div
              key={idea.id}
              onClick={() => toggleSelect(idea.id)}
              className={`rounded-xl border p-5 cursor-pointer transition-all duration-150 ${
                selected
                  ? "border-blue-500 bg-blue-50/40 ring-1 ring-blue-500/20"
                  : "border-slate-200 bg-white hover:border-slate-300"
              } ${creating ? "opacity-60 cursor-not-allowed" : ""}`}
            >
              {/* Top Row: Checkbox + Badges + Title */}
              <div className="flex items-start gap-3">
                {/* Checkbox */}
                <div
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition-colors ${
                    selected
                      ? "border-blue-600 bg-blue-600"
                      : "border-slate-300 bg-white"
                  }`}
                >
                  {selected && <IconCheck className="w-3 h-3 text-white" />}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${typeColor}`}
                    >
                      {BOOK_TYPE_SHORT[idea.book_type]}
                    </span>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${catMeta.color}`}
                    >
                      {catMeta.label}
                    </span>
                    {inCatalog && (
                      <span className="inline-flex items-center gap-0.5 rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-medium text-green-700">
                        <IconCheck className="w-2.5 h-2.5" />
                        In catalog
                      </span>
                    )}
                  </div>
                  <h3 className="text-sm font-semibold text-slate-900 leading-tight mt-1.5">
                    {idea.title}
                  </h3>

                  {/* Description */}
                  <p className="text-xs text-slate-500 mt-2 line-clamp-2">
                    {idea.description}
                  </p>

                  {/* Specs Row */}
                  <div className="flex items-center gap-1.5 mt-3 flex-wrap">
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      {formatTrim(idea.trim_size)}
                    </span>
                    <span className="text-slate-300 text-[10px]">
                      &middot;
                    </span>
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      {idea.page_count} pages
                    </span>
                    <span className="text-slate-300 text-[10px]">
                      &middot;
                    </span>
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      ${idea.list_price.toFixed(2)}
                    </span>
                    <span className="text-slate-300 text-[10px]">
                      &middot;
                    </span>
                    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      {PAPER_LABELS[idea.paper_type] || idea.paper_type}
                    </span>
                  </div>

                  {/* Bottom Row */}
                  <div className="flex items-center justify-between mt-3">
                    <div className="flex items-center gap-3">
                      <span className="text-[11px] font-medium text-emerald-600">
                        Est. {idea.est_monthly_revenue}/mo
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {idea.target_audience}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Floating Action Bar */}
      {selectedCount > 0 && !creating && (
        <div className="fixed bottom-0 left-0 right-0 z-50">
          <div className="mx-auto max-w-4xl px-8 pb-6">
            <div className="rounded-xl border border-slate-200 bg-white shadow-lg px-6 py-4 flex items-center justify-between">
              <span className="text-sm text-slate-600">
                <span className="font-semibold text-slate-900">
                  {selectedCount}
                </span>{" "}
                {selectedCount === 1 ? "idea" : "ideas"} selected
              </span>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setSelectedIds(new Set())}
                  className="text-sm text-slate-500 hover:text-slate-900 transition-colors"
                >
                  Clear
                </button>
                <button
                  onClick={handleCreate}
                  className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
                >
                  Create {selectedCount}{" "}
                  {selectedCount === 1 ? "Book" : "Books"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
