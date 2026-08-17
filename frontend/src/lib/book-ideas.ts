// SCRPT Book Ideas — Shared Data Module
// ========================================
// Curated book concepts extracted from the research page.
// Used by both /research and /design/[ideaId] pages.

import type { BookType, PaperType } from "./types";

// ── Types ───────────────────────────────────────────────────────

export type IdeaCategory = "bestsellers" | "emerging" | "seasonal" | "quick_wins";

export interface MarketData {
  bsr: number;
  search_results: string;
  reviews: number;
  demand: "very_strong" | "strong" | "moderate" | "weak";
  verified_date: string;
}

export interface BookIdea {
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
  market_data?: MarketData | null;
}

// ── Constants ───────────────────────────────────────────────────

export const CATEGORY_META: Record<
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

export const ALL_CATEGORIES: IdeaCategory[] = [
  "bestsellers",
  "emerging",
  "seasonal",
  "quick_wins",
];

// ── 28 Curated Book Ideas ───────────────────────────────────────

export const BOOK_IDEAS: BookIdea[] = [
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
      "The highest-selling KDP activity book niche. Top KDP book ranks BSR #7,898 with 7,655 reviews. Large print format targets the 65+ demographic with themed puzzles.",
    target_audience: "Seniors 65+",
    est_monthly_revenue: "$200 - $500",
    category: "bestsellers",
    generator_config: {
      subtitle: "Relaxing Themed Puzzles",
      num_puzzles: 55,
      grid_size: 15,
      words_per_puzzle: 15,
      difficulty: "medium",
      large_print: true,
    },
    market_data: {
      bsr: 7898,
      search_results: "60,000+",
      reviews: 7655,
      demand: "very_strong",
      verified_date: "2026-03-13",
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
      "Beginner-friendly sudoku in large print. Top KDP book ranks BSR #18,576 with only 198 reviews — less entrenched than word search, easier to compete.",
    target_audience: "New puzzlers / Seniors",
    est_monthly_revenue: "$100 - $250",
    category: "bestsellers",
    generator_config: {
      subtitle: "Gentle Brain Training",
      num_puzzles: 55,
      difficulty: "easy",
      large_print: true,
    },
    market_data: {
      bsr: 18576,
      search_results: "10,000+",
      reviews: 198,
      demand: "strong",
      verified_date: "2026-03-13",
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
      "Parents buy math workbooks year-round. Top KDP book BSR #31,979, 430 reviews, #18 in Arithmetic. Solid perennial demand with strong back-to-school spikes.",
    target_audience: "Parents / Kids 8-10",
    est_monthly_revenue: "$80 - $200",
    category: "bestsellers",
    generator_config: {
      subtitle: "Multiplication & Division Practice",
      num_pages: 50,
      problems_per_page: 20,
      operation: "mixed",
      difficulty: "medium",
      large_print: true,
    },
    market_data: {
      bsr: 31979,
      search_results: "1,000+",
      reviews: 430,
      demand: "strong",
      verified_date: "2026-03-13",
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
      "Caution: niche dominated by physical spiral-bound products, not KDP paperbacks. Top KDP book BSR #359,250 despite 2,017 reviews. Lower revenue potential than puzzle books.",
    target_audience: "Seniors / Non-tech users",
    est_monthly_revenue: "$15 - $50",
    category: "bestsellers",
    generator_config: {
      subtitle: "Keep Your Passwords Safe & Organized",
      log_type: "password_organizer",
    },
    market_data: {
      bsr: 359250,
      search_results: "40,000+",
      reviews: 2017,
      demand: "weak",
      verified_date: "2026-03-13",
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
      "Proven evergreen wellness niche. Top KDP journal BSR #27,754 with 1,451 reviews, #121 in Journal Writing. Cream paper gives a premium feel with structured prompts.",
    target_audience: "Wellness / Self-help",
    est_monthly_revenue: "$100 - $250",
    category: "bestsellers",
    generator_config: {
      subtitle: "Start Each Day with Gratitude",
      log_type: "gratitude_journal",
    },
    market_data: {
      bsr: 27754,
      search_results: "60,000+",
      reviews: 1451,
      demand: "strong",
      verified_date: "2026-03-13",
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
      "Smaller niche (4K results) but less competition. Top KDP book BSR #64,794, 64 reviews, #227 in Logic & Brain Teasers. Room to become a top seller with quality content.",
    target_audience: "Adult puzzle fans",
    est_monthly_revenue: "$50 - $120",
    category: "bestsellers",
    generator_config: {
      subtitle: "Decode Famous Quotes",
      num_puzzles: 55,
      large_print: true,
    },
    market_data: {
      bsr: 64794,
      search_results: "4,000+",
      reviews: 64,
      demand: "moderate",
      verified_date: "2026-03-13",
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
      "A design variant of the password organizer niche. Note: KDP paperback password books face stiff competition from spiral-bound physical products. Low revenue potential.",
    target_audience: "Women 40+ / Gift buyers",
    est_monthly_revenue: "$10 - $40",
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

export function getIdeaById(id: string): BookIdea | undefined {
  return BOOK_IDEAS.find((idea) => idea.id === id);
}

export function formatTrim(trim: string): string {
  const parts = trim.split("x");
  if (parts.length === 2) return `${parts[0]}" x ${parts[1]}"`;
  return trim;
}
