"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  scrpt, type BookKind, type GenrePreset, type WorkOrderPayload,
} from "@/lib/scrpt";

// Amazon KDP paperback trim sizes (docs/KDP_INTERIOR_SPEC.md)
const KDP_TRIMS: { key: string; hint?: string }[] = [
  { key: "5x8", hint: "compact fiction" },
  { key: "5.06x7.81", hint: "UK B-format (Bourne/Orion paperbacks)" },
  { key: "5.25x8", hint: "fiction / romance" },
  { key: "5.5x8.5", hint: "fiction workhorse" },
  { key: "6x9", hint: "trade standard / non-fiction" },
  { key: "6.14x9.21", hint: "large trade" },
  { key: "6.69x9.61" },
  { key: "7x10", hint: "workbooks" },
  { key: "7.44x9.69" },
  { key: "7.5x9.25" },
  { key: "8x10" },
  { key: "8.5x8.5", hint: "square" },
  { key: "8.5x11", hint: "large format" },
];

// the children's presets carry a fixed extent instead of novel page maths
interface ChildrensPreset {
  pages: number; spreads: number; words_per_spread: number; reading: string;
}

// house names are listed per shelf, so the label names the shelf
const KIND_AUTHOR_LABEL: Record<BookKind, string> = {
  fiction: "Fiction house authors",
  nonfiction: "Non-fiction house authors",
  childrens: "Children's house authors",
};

export default function WorkOrderPage() {
  const router = useRouter();
  const [genres, setGenres] = useState<Record<string, GenrePreset>>({});
  const [fonts, setFonts] = useState<Record<string, { label: string }>>({});
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);

  // form state
  const [kind, setKind] = useState<BookKind>("fiction");
  const [genre, setGenre] = useState("action_thriller");
  const [idea, setIdea] = useState("");
  const [title, setTitle] = useState("");
  const [penName, setPenName] = useState("");
  const [isSeries, setIsSeries] = useState(false);
  const [seriesTitle, setSeriesTitle] = useState("");
  const [seriesBooks, setSeriesBooks] = useState(3);
  const [targetWords, setTargetWords] = useState<number | "">("");
  const [trim, setTrim] = useState("");
  const [font, setFont] = useState("");
  const [flow, setFlow] = useState<"options" | "auto">("options");
  const [developing, setDeveloping] = useState(false);
  const [devMsg, setDevMsg] = useState("");
  interface DevPackage {
    market_analysis?: string; positioning?: string; extended_idea?: string;
    series_titles?: string[]; series_engine?: string;
    book_ideas?: { title: string; logline: string }[];
    title_suggestions?: { title: string; logline: string }[];
    pen_name?: string;
    is_series?: boolean;
    recommended_books?: number;
    cover_direction?: string;
    recommendations?: { heat_or_tone?: string; target_words?: number;
      trim_size?: string; notes?: string };
  }
  const [dev, setDev] = useState<DevPackage | null>(null);
  // the original rough idea, kept so "research again" re-develops from the
  // publisher's seed, not from the previous suggestion
  const [seedIdea, setSeedIdea] = useState("");
  // visual direction from the research — rides along into the cover generator
  const [coverDirection, setCoverDirection] = useState("");
  // researched titles for every series book — books 2+ are named from birth
  const [bookTitles, setBookTitles] = useState<string[]>([]);
  const [nameSuggestions, setNameSuggestions] = useState<{ name: string; rationale: string }[]>([]);
  const [suggestingNames, setSuggestingNames] = useState(false);
  interface HouseAuthor { name: string; kinds?: string[]; books: { catalog_number: string; title: string; series_title: string; status: string }[] }
  const [houseAuthors, setHouseAuthors] = useState<HouseAuthor[]>([]);
  // a pen name belongs to the shelf it writes for — a thriller author has no
  // business turning up on a picture book, and vice versa
  const kindAuthors = houseAuthors.filter((a) => !a.kinds?.length || a.kinds.includes(kind));
  const selectedAuthor = houseAuthors.find((a) => a.name === penName) || null;

  useEffect(() => {
    fetch(`${scrpt.engineUrl}/api/scrpt/pen-names`)
      .then((r) => r.json())
      .then((d) => setHouseAuthors(d.authors || []))
      .catch(() => {});
  }, []);

  // switching kind drops a house name that doesn't write for that shelf; a
  // name typed by hand is the publisher's own and is left alone
  useEffect(() => {
    if (!penName) return;
    const a = houseAuthors.find((x) => x.name === penName);
    if (a && a.kinds?.length && !a.kinds.includes(kind)) setPenName("");
  }, [kind, houseAuthors, penName]);

  const suggestPenNames = async () => {
    setSuggestingNames(true);
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/workorder/pen-names`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, genre_preset: genre, idea }),
      });
      const d = await res.json();
      setNameSuggestions(d.suggestions || []);
    } catch { /* offline */ } finally {
      setSuggestingNames(false);
    }
  };

  // fill the whole form from a commissioning package — the publisher only
  // re-presses the button if they want a different suggestion
  const applyPackage = (pkg: DevPackage) => {
    // the research decides series vs standalone from the idea itself
    const wantsSeries = pkg.is_series || Boolean(pkg.series_titles?.length);
    const nBooks = wantsSeries
      ? (pkg.recommended_books || pkg.book_ideas?.length || seriesBooks || 3)
      : 1;
    if (wantsSeries) {
      setIsSeries(true);
      setSeriesBooks(nBooks);
      if (pkg.series_titles?.length) setSeriesTitle(pkg.series_titles[0]);
    }

    // The idea field becomes the full commissioning brief: what the book is
    // (genre, standalone or series), then the storyline. This same text later
    // feeds the cover generator's premise when no story bible exists yet.
    const label = preset?.label || "book";
    const shape = wantsSeries
      ? `a series of ${nBooks} ${label} books`
      : `a standalone ${label}`;
    const brief = [
      `This is ${shape}${pkg.series_titles?.length ? ` — “${pkg.series_titles[0]}”` : ""}.`,
      pkg.positioning || "",
      "",
      pkg.extended_idea || "",
      pkg.series_engine ? `\nThe series engine: ${pkg.series_engine}` : "",
    ].join("\n").replace(/\n{3,}/g, "\n\n").trim();
    if (brief) setIdea(brief);

    const firstBook = pkg.book_ideas?.[0] || pkg.title_suggestions?.[0];
    // a title the publisher typed is the title — suggestions never overwrite it
    if (firstBook) setTitle((t) => (t.trim() ? t : firstBook.title));
    setBookTitles((pkg.book_ideas || []).map((b) => b.title));
    if (pkg.pen_name) setPenName((p) => (p.trim() ? p : pkg.pen_name!));
    // format comes from the research too — length and trim
    if (pkg.recommendations?.target_words) setTargetWords(pkg.recommendations.target_words);
    const recTrim = (pkg.recommendations?.trim_size || "").replace(/[″"\s]/g, "");
    if (KDP_TRIMS.some((t) => t.key === recTrim)) setTrim(recTrim);
    setCoverDirection(pkg.cover_direction || "");
  };

  const developIdea = async () => {
    const rough = (seedIdea || idea).trim();
    if (!rough) { setError("Write the rough idea first."); return; }
    if (!seedIdea) setSeedIdea(rough);
    setDeveloping(true);
    setError("");
    setDevMsg(dev ? "Dealing a fresh suggestion from your original idea…"
                  : "Researching the market and developing the concept…");
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/workorder/develop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ working_title: title.trim(), kind, genre_preset: genre, idea: rough,
                               series_books: isSeries ? seriesBooks : 0 }),
      });
      const { job_id } = await res.json();
      const { pollJob } = await import("@/lib/scrpt");
      const job = await pollJob(job_id, (j) => setDevMsg(j.detail || j.stage || "Working…"));
      if (job.status === "done") {
        const pkg = job.result as DevPackage;
        setDev(pkg);
        applyPackage(pkg);
        setDevMsg("");
      } else {
        setDevMsg(`Failed: ${(job.error || "").split("\n")[0]}`);
      }
    } catch (e) {
      setDevMsg(e instanceof Error ? e.message : "Development failed");
    } finally {
      setDeveloping(false);
    }
  };
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    scrpt.health().then(setEngineOnline);
    scrpt.presets().then((p) => {
      setGenres(p.genres);
      setFonts(p.fonts);
    }).catch(() => setEngineOnline(false));
  }, []);

  const genreEntries = Object.entries(genres).filter(([, g]) => g.kind === kind);
  const preset = genres[genre];

  // keep the genre valid when switching kind
  useEffect(() => {
    if (preset && preset.kind !== kind) {
      const first = Object.entries(genres).find(([, g]) => g.kind === kind);
      if (first) setGenre(first[0]);
    }
  }, [kind, genres]); // eslint-disable-line react-hooks/exhaustive-deps

  // research-backed defaults fill the format fields whenever the genre changes
  useEffect(() => {
    if (!preset) return;
    setTargetWords(preset.target_words);
    setTrim(preset.trim);
    setFont(preset.font);
  }, [genre, genres]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    if (!idea.trim()) {
      setError("Describe the book — the idea is the one thing SCRPT can't invent for you.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const payload: WorkOrderPayload = {
        kind,
        genre_preset: genre,
        idea: idea.trim(),
        title: title.trim(),
        pen_name: penName.trim(),
        series_title: isSeries ? seriesTitle.trim() : "",
        series_books: isSeries ? seriesBooks : 1,
        target_words: targetWords === "" ? null : targetWords,
        trim_size: trim || null,
        font_preset: font || null,
        cover_direction: coverDirection,
        book_titles: isSeries ? bookTitles : [],
        generate_plot_options: flow === "options",
        auto_draft: flow === "auto",
      };
      const result = await scrpt.createWorkOrder(payload);
      // covers start painting the moment the book is commissioned — land the
      // publisher on the Cover tab to pick from the four alternatives
      const coverStarted = (result as { cover_job_id?: string }).cover_job_id;
      router.push(`/shelf/${result.books[0].catalog_number}${coverStarted ? "?tab=cover" : ""}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-[860px] mx-auto px-8 py-12 fade-up">
      <h1 className="serif-display text-[32px] font-semibold">New Work Order</h1>
      <p className="text-[13px] text-text-secondary mt-1">
        Commission a book — or a whole series. SCRPT takes it from idea to
        print-ready.
      </p>

      {engineOnline === false && (
        <div className="card mt-6" style={{ borderLeft: "3px solid var(--status-red)" }}>
          <div className="text-[13px]">
            The local engine is offline — the work order can&apos;t be placed.
            Start the SCRPT companion first.
          </div>
        </div>
      )}

      {/* Kind */}
      <section className="card mt-8">
        <div className="label-scrpt">What kind of book</div>
        <div className="grid grid-cols-3 gap-3 mt-2">
          <KindCard
            active={kind === "fiction"}
            onClick={() => setKind("fiction")}
            title="Fiction"
            body="Thrillers, romance — story-driven series with a living story bible."
          />
          <KindCard
            active={kind === "nonfiction"}
            onClick={() => setKind("nonfiction")}
            title="Non-fiction"
            body="Self-help and business books built around one ownable framework."
          />
          <KindCard
            active={kind === "childrens"}
            onClick={() => setKind("childrens")}
            title="Children's book"
            body="Illustrated picture books, early readers and chapter books — written in spreads."
          />
        </div>

        {kind === "childrens" ? (
          <>
            <div className="label-scrpt mt-6">Format</div>
            <p className="text-[12px] text-text-tertiary mt-1 mb-2 max-w-[620px]">
              Three real formats, with the trim drawn to scale. The age band decides
              everything downstream: length, type size, how many pictures, and how the
              words are written.
            </p>
            <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(3, minmax(0,1fr))" }}>
              {genreEntries.map(([key, g]) => {
                const gg = g as unknown as {
                  label: string; age: string; physical?: string; describe?: string;
                  example_text?: string; example_note?: string; trim: string;
                };
                const [tw, th] = (gg.trim || "6x9").split("x").map(Number);
                // ONE scale across all three cards, so the covers show their real
                // relative size. Drawing each to the same height hid the point —
                // a picture book is a much bigger object than a chapter book.
                const tallest = Math.max(...genreEntries.map(([, e]) =>
                  Number(((e as unknown as { trim: string }).trim || "6x9").split("x")[1]) || 9));
                const PPI = 132 / tallest;
                const boxH = Math.round(th * PPI);
                const boxW = Math.round(tw * PPI);
                const on = genre === key;
                // a real cover in the real trim — the shape and the look of the
                // format in one glance, instead of an empty rectangle
                const cover = `/childrens/${key.replace(/_/g, "-")}.png`;
                return (
                  <button key={key} onClick={() => setGenre(key)}
                          className="text-left rounded-[10px] p-4 transition-all"
                          style={{
                            border: `1px solid ${on ? "var(--accent)" : "var(--border-subtle)"}`,
                            background: on ? "var(--surface-elevated)" : "transparent",
                          }}>
                    <div className="flex items-start gap-3">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={cover} alt={`${gg.label} cover`}
                           className="shrink-0 rounded-[3px] object-cover"
                           style={{ width: boxW, height: boxH,
                                    background: "var(--surface)",
                                    border: "1px solid var(--border-subtle)",
                                    boxShadow: "var(--shadow-card)" }} />
                      <div className="min-w-0">
                        <div className="text-[14px] font-semibold text-text-primary">{gg.label}</div>
                        <div className="text-[11.5px] text-accent mt-[2px]">Ages {gg.age}</div>
                        <div className="text-[11px] text-text-faint mt-2 leading-snug">{gg.physical}</div>
                      </div>
                    </div>
                    <div className="text-[12px] text-text-tertiary mt-3 leading-relaxed">{gg.describe}</div>
                    {gg.example_text && (
                      <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--border-subtle)" }}>
                        <div className="text-[10.5px] uppercase tracking-[0.12em] text-text-faint">How it reads</div>
                        <div className="serif-display text-[13.5px] text-text-primary mt-1 leading-relaxed">
                          &ldquo;{gg.example_text}&rdquo;
                        </div>
                        <div className="text-[11px] text-text-faint mt-1.5">{gg.example_note}</div>
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </>
        ) : (
        <>
        <div className="label-scrpt mt-6">Genre</div>
        <div className="flex flex-wrap gap-2 mt-1">
          {genreEntries.map(([key, g]) => (
            <button
              key={key}
              onClick={() => setGenre(key)}
              className={`px-3 py-[7px] rounded-md text-[13px] font-medium transition-all ${
                genre === key
                  ? "bg-accent-subtle text-accent"
                  : "text-text-tertiary hover:text-text-primary border border-border-subtle"
              }`}
              style={genre === key ? { border: "1px solid var(--accent-deep)" } : {}}
            >
              {g.label}
            </button>
          ))}
        </div>
        </>
        )}
        {preset && (kind === "childrens" ? (() => {
          // a children's book's extent is fixed by convention (a signature is
          // 8 pages), so the word count follows the format — never the reverse
          const cp = preset as unknown as ChildrensPreset;
          // a chapter book is counted in chapters; the two younger formats in
          // spreads — calling a chapter a "spread" would misdescribe the book
          const unit = genre === "chapter_book" ? ["chapters", "chapter"] : ["spreads", "spread"];
          return (
          <div className="text-[12px] text-text-faint mt-3">
            Market norm: {cp.pages} pages · {cp.spreads} {unit[0]} ·{" "}
            {preset.target_words.toLocaleString()} words
            {" "}(~{cp.words_per_spread} a {unit[1]}) ·{" "}
            {preset.trim.replace("x", '" × ')}&quot; · {cp.reading}
          </div>
          );
        })() : (
          <div className="text-[12px] text-text-faint mt-3">
            Market norm: {preset.target_words.toLocaleString()} words ≈{" "}
            {Math.round(((targetWords || preset.target_words) as number) /
              ((preset as { wpp?: number }).wpp || 275) + 12)}{" "}
            printed pages at {preset.trim.replace("x", '" × ')}&quot; ·{" "}
            {preset.paper === "cream_bw" ? "cream paper" : "white paper"} · {preset.pov}
          </div>
        ))}
      </section>

      {/* The idea */}
      <section className="card mt-5">
        <div className="label-scrpt">The idea</div>
        <textarea
          className="input-scrpt min-h-[130px] resize-y leading-relaxed"
          placeholder={
            kind === "fiction"
              ? "A disgraced interpreter overhears three words at a UN summit that get her marked for death — and the only person who believes her is the assassin sent to silence her…"
              : "A book that teaches overwhelmed founders to reclaim their calendar by treating attention like equity — invest it, don't spend it…"
          }
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
        />
        <div className="flex items-center gap-3 mt-3">
          <button className="btn-ghost text-[12px]" disabled={developing || !(seedIdea || idea).trim()}
                  onClick={developIdea}>
            {developing ? "Researching…"
              : dev ? "Not happy? Research again" : "Research & extend the idea"}
          </button>
          {!developing && devMsg && <span className="text-[11px] text-text-tertiary">{devMsg}</span>}
          {dev && !developing && !devMsg && (
            <span className="text-[11px] text-text-faint">
              The form below is filled from this suggestion — edit anything, or deal again.
            </span>
          )}
        </div>

        {developing && (
          <ResearchingPanel genreLabel={preset?.label || "the genre"}
                            series={isSeries} redeal={Boolean(dev)} />
        )}

        {dev && !developing && (
          <div className="mt-5 rounded-[10px] p-5 space-y-4"
               style={{ background: "var(--surface-elevated)", border: "1px solid var(--accent-deep)" }}>
            {dev.positioning && (
              <div className="serif-display text-[15px] italic text-accent">{dev.positioning}</div>
            )}
            {dev.market_analysis && (
              <div>
                <div className="label-scrpt">Market research</div>
                <p className="text-[13px] text-text-secondary leading-relaxed">{dev.market_analysis}</p>
              </div>
            )}
            {dev.extended_idea && (
              <div>
                <div className="label-scrpt">Extended idea — now in the form above</div>
                <p className="text-[13px] text-text-secondary leading-relaxed">{dev.extended_idea}</p>
              </div>
            )}
            {dev.series_engine && (
              <div>
                <div className="label-scrpt">Series engine</div>
                <p className="text-[13px] text-text-secondary leading-relaxed">{dev.series_engine}</p>
              </div>
            )}
            {(dev.series_titles?.length || 0) > 0 && (
              <div>
                <div className="label-scrpt">Series title — first one adopted, click to swap</div>
                <div className="flex flex-wrap gap-2 mt-1">
                  {dev.series_titles!.map((t, i) => (
                    <button key={i}
                            className={`px-3 py-[6px] rounded-md text-[13px] transition-all ${
                              seriesTitle === t ? "bg-accent-subtle text-accent" : "border border-border-subtle text-text-secondary hover:text-text-primary"}`}
                            onClick={() => { setIsSeries(true); setSeriesTitle(t); }}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {((dev.book_ideas || dev.title_suggestions)?.length || 0) > 0 && (
              <div>
                <div className="label-scrpt">
                  {dev.book_ideas ? "The books — book 1 titled above, click to swap" : "Titles — first one adopted, click to swap"}
                </div>
                <div className="space-y-2 mt-1">
                  {(dev.book_ideas || dev.title_suggestions)!.map((b, i) => (
                    <button key={i} className="block text-left w-full rounded-md px-3 py-2 transition-colors hover:bg-accent-subtle"
                            style={{ border: "1px solid var(--border-subtle)" }}
                            onClick={() => setTitle(b.title)}>
                      <span className="text-[13px] font-medium">{i + 1}. {b.title}</span>
                      <span className="text-[12px] text-text-tertiary ml-2 italic">{b.logline}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {dev.cover_direction && (
              <div>
                <div className="label-scrpt">Cover direction — rides along with the work order into the cover generator</div>
                <p className="text-[13px] text-text-secondary leading-relaxed">{dev.cover_direction}</p>
              </div>
            )}
            {dev.recommendations?.notes && (
              <div className="text-[12px] text-text-faint">
                {dev.recommendations.heat_or_tone && <span className="mr-3">Tone: {dev.recommendations.heat_or_tone}</span>}
                {Boolean(dev.recommendations.target_words) && (
                  <button className="underline mr-3"
                          onClick={() => setTargetWords(dev.recommendations!.target_words!)}>
                    Adopt {dev.recommendations.target_words!.toLocaleString()} words
                  </button>
                )}
                {dev.recommendations.notes}
              </div>
            )}
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-4 mt-4">
          <div>
            <div className="label-scrpt">Working title (optional)</div>
            <input className="input-scrpt" placeholder="SCRPT proposes titles if left empty"
                   value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <div className="label-scrpt flex items-center justify-between">
              <span>Pen name</span>
              <button className="text-accent normal-case tracking-normal hover:underline"
                      disabled={suggestingNames}
                      onClick={suggestPenNames}>
                {suggestingNames ? "thinking…" : "Suggest names"}
              </button>
            </div>
            <input className="input-scrpt" placeholder="Author name on the cover"
                   value={penName} onChange={(e) => setPenName(e.target.value)} />
            {nameSuggestions.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {nameSuggestions.map((n, i) => (
                  <button key={i} title={n.rationale}
                          className={`px-2.5 py-[5px] rounded-md text-[12px] transition-all ${
                            penName === n.name ? "bg-accent-subtle text-accent" : "border border-border-subtle text-text-secondary hover:text-text-primary"}`}
                          onClick={() => setPenName(n.name)}>
                    {n.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {kindAuthors.length > 0 && (
          <div className="mt-4">
            <div className="label-scrpt">{KIND_AUTHOR_LABEL[kind]} — click to reuse</div>
            <div className="flex flex-wrap gap-2 mt-1">
              {kindAuthors.map((a) => (
                <button key={a.name}
                        className={`px-2.5 py-[5px] rounded-md text-[12px] transition-all ${
                          penName === a.name ? "bg-accent-subtle text-accent" : "border border-border-subtle text-text-secondary hover:text-text-primary"}`}
                        onClick={() => setPenName(a.name)}>
                  {a.name} <span className="text-text-faint">({a.books.length})</span>
                </button>
              ))}
            </div>
            {selectedAuthor && (
              <div className="mt-3 rounded-md px-4 py-3"
                   style={{ background: "var(--surface-elevated)", border: "1px solid var(--border-subtle)" }}>
                <div className="text-[11px] tracking-[0.1em] uppercase text-text-faint mb-2">
                  {selectedAuthor.name} — catalog
                </div>
                {selectedAuthor.books.map((b) => (
                  <div key={b.catalog_number} className="flex items-baseline gap-3 text-[12px] py-0.5">
                    <span className="text-text-faint w-14 shrink-0">{b.catalog_number}</span>
                    <span className="text-text-secondary truncate">{b.title}</span>
                    {b.series_title && <span className="text-text-faint italic truncate">{b.series_title}</span>}
                    <span className="text-text-faint ml-auto shrink-0 capitalize">{b.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        <div className="hidden"></div>
      </section>

      {/* Series */}

      {/* Series */}
      <section className="card mt-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[14px] font-semibold">Book series</div>
            <div className="text-[12px] text-text-tertiary mt-0.5">
              Create several connected books under one series bible.
            </div>
          </div>
          <Toggle on={isSeries} onToggle={() => setIsSeries(!isSeries)} />
        </div>
        {isSeries && (
          <div className="grid md:grid-cols-2 gap-4 mt-5">
            <div>
              <div className="label-scrpt">Series title</div>
              <input className="input-scrpt" placeholder="The Meridian Files"
                     value={seriesTitle} onChange={(e) => setSeriesTitle(e.target.value)} />
            </div>
            <div>
              <div className="label-scrpt">Books in the series</div>
              <input type="number" min={2} max={12} className="input-scrpt"
                     value={seriesBooks}
                     onChange={(e) => setSeriesBooks(Math.max(2, Math.min(12, Number(e.target.value) || 2)))} />
            </div>
          </div>
        )}
      </section>

      {/* Format overrides */}
      <section className="card mt-5">
        <div className="label-scrpt">Format — researched market defaults for this genre, edit only with reason</div>
        <div className="grid md:grid-cols-3 gap-4 mt-2">
          <div>
            <div className="label-scrpt">Target length</div>
            <input type="number" className="input-scrpt"
                   placeholder={preset ? `${preset.target_words.toLocaleString()} words` : "words"}
                   value={targetWords}
                   onChange={(e) => setTargetWords(e.target.value === "" ? "" : Number(e.target.value))} />
          </div>
          <div>
            <div className="label-scrpt">Trim size</div>
            <select className="input-scrpt" value={trim} onChange={(e) => setTrim(e.target.value)}>
              <option value="">{preset ? `${preset.trim.replace("x", '\u2033 × ')}\u2033 (genre default)` : "Default"}</option>
              {KDP_TRIMS.map((t) => (
                <option key={t.key} value={t.key}>
                  {`${t.key.replace("x", "″ × ")}″${t.hint ? ` — ${t.hint}` : ""}`}
                </option>
              ))}
            </select>
          </div>
          <div>
            <div className="label-scrpt">Typeface</div>
            <select className="input-scrpt" value={font} onChange={(e) => setFont(e.target.value)}>
              <option value="">{preset && fonts[preset.font] ? `${fonts[preset.font].label} (default)` : "Default"}</option>
              {Object.entries(fonts).map(([key, f]) => (
                <option key={key} value={key}>{f.label}</option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {/* Flow */}
      <section className="card mt-5">
        <div className="label-scrpt">How to proceed</div>
        <div className="grid grid-cols-2 gap-3 mt-2">
          <KindCard
            active={flow === "options"}
            onClick={() => setFlow("options")}
            title="Show me plot directions first"
            body="SCRPT develops three distinct directions; you pick and refine before drafting begins. Recommended."
          />
          <KindCard
            active={flow === "auto"}
            onClick={() => setFlow("auto")}
            title="Write immediately"
            body="Skip approval — SCRPT chooses the strongest direction and writes the whole book."
          />
        </div>
      </section>

      {error && (
        <div className="text-[13px] mt-5" style={{ color: "var(--status-red)" }}>{error}</div>
      )}

      <div className="flex items-center gap-4 mt-8">
        <button className="btn-brass text-[14px] px-7 py-3" disabled={submitting || engineOnline === false}
                onClick={submit}>
          {submitting ? "Placing the order…" : isSeries ? `Commission ${seriesBooks} books` : "Commission this book"}
        </button>
        <span className="text-[12px] text-text-faint">
          {flow === "auto"
            ? "Writing a full book takes roughly 30–60 minutes."
            : "Plot directions arrive in about a minute."}
        </span>
      </div>
    </div>
  );
}

/** The acquisitions desk at work — visible motion while research runs. */
function ResearchingPanel({ genreLabel, series, redeal }: {
  genreLabel: string; series: boolean; redeal: boolean;
}) {
  const lines = [
    redeal ? "Setting the last suggestion aside — starting fresh from your idea…"
           : "Opening the acquisitions file…",
    `Reading the ${genreLabel} market — what readers are buying right now…`,
    "Weighing comparable authors and titles…",
    "Testing the hook against proven demand…",
    series ? "Shaping the series engine — what generates every next book…"
           : "Sharpening the premise into a commissioning brief…",
    series ? "Titling the series and the first books…" : "Writing title options…",
    "Choosing a pen name for the shelf…",
    "Sketching the cover direction…",
    "Weighing it all — the package is almost on your desk…",
  ];
  const [step, setStep] = useState(0);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const stepTimer = setInterval(() => setStep((v) => v + 1), 4000);
    const clock = setInterval(() => setSeconds((v) => v + 1), 1000);
    return () => { clearInterval(stepTimer); clearInterval(clock); };
  }, []);

  const line = lines[Math.min(step, lines.length - 1)];

  return (
    <div className="mt-5 rounded-[10px] p-5"
         style={{ background: "var(--surface-elevated)", border: "1px solid var(--accent-deep)" }}>
      <div className="flex items-center gap-3">
        <span className="work-beacon shrink-0" />
        <span className="serif-display text-[15px] font-semibold">
          The acquisitions desk is working
        </span>
        <span className="flex-1" />
        <span className="text-[11px] text-text-faint tabular-nums">
          {Math.floor(seconds / 60) > 0 ? `${Math.floor(seconds / 60)}m ` : ""}{seconds % 60}s
        </span>
      </div>
      <div key={step} className="status-rise text-[13px] text-text-secondary mt-3">
        {line}
      </div>
      <div className="mt-4 space-y-2.5">
        <div className="shimmer-line h-[11px] w-[88%]" />
        <div className="shimmer-line h-[11px] w-[72%]" style={{ animationDelay: "0.25s" }} />
        <div className="shimmer-line h-[11px] w-[80%]" style={{ animationDelay: "0.5s" }} />
      </div>
      <div className="text-[11px] text-text-faint mt-4">
        Deep market research takes about a minute — the package lands here, and
        the form fills itself.
      </div>
    </div>
  );
}

function KindCard({ active, onClick, title, body }: {
  active: boolean; onClick: () => void; title: string; body: string;
}) {
  return (
    <button
      onClick={onClick}
      className="text-left rounded-[10px] p-4 transition-all"
      style={{
        background: active ? "var(--accent-subtle)" : "var(--surface-elevated)",
        border: `1px solid ${active ? "var(--accent-deep)" : "var(--border-subtle)"}`,
      }}
    >
      <div className={`text-[14px] font-semibold ${active ? "text-accent" : "text-text-primary"}`}>
        {title}
      </div>
      <div className="text-[12px] text-text-tertiary mt-1 leading-relaxed">{body}</div>
    </button>
  );
}

function Toggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="w-[40px] h-[22px] rounded-full transition-colors relative shrink-0"
      style={{ background: on ? "var(--accent)" : "rgba(236,229,218,0.12)" }}
      aria-pressed={on}
    >
      <span
        className="absolute top-[2px] h-[18px] w-[18px] rounded-full bg-white transition-all"
        style={{ left: on ? 20 : 2, background: on ? "#171205" : "#c8beb0" }}
      />
    </button>
  );
}
