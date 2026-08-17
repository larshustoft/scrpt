"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  scrpt, type BookKind, type GenrePreset, type WorkOrderPayload,
} from "@/lib/scrpt";

// Amazon KDP paperback trim sizes (docs/KDP_INTERIOR_SPEC.md)
const KDP_TRIMS: { key: string; hint?: string }[] = [
  { key: "5x8", hint: "compact fiction" },
  { key: "5.06x7.81" },
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
        generate_plot_options: flow === "options",
        auto_draft: flow === "auto",
      };
      const result = await scrpt.createWorkOrder(payload);
      router.push(`/shelf/${result.books[0].catalog_number}`);
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
        <div className="grid grid-cols-2 gap-3 mt-2">
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
        </div>

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
        {preset && (
          <div className="text-[12px] text-text-faint mt-3">
            Market norm: {preset.target_words.toLocaleString()} words ≈{" "}
            {Math.round(((targetWords || preset.target_words) as number) /
              ((preset as { wpp?: number }).wpp || 275) + 12)}{" "}
            printed pages at {preset.trim.replace("x", '" × ')}&quot; ·{" "}
            {preset.paper === "cream_bw" ? "cream paper" : "white paper"} · {preset.pov}
          </div>
        )}
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
        <div className="grid md:grid-cols-2 gap-4 mt-4">
          <div>
            <div className="label-scrpt">Working title (optional)</div>
            <input className="input-scrpt" placeholder="SCRPT proposes titles if left empty"
                   value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <div className="label-scrpt">Pen name</div>
            <input className="input-scrpt" placeholder="Author name on the cover"
                   value={penName} onChange={(e) => setPenName(e.target.value)} />
          </div>
        </div>
      </section>

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
        <div className="label-scrpt">Format (optional — the genre default is right for most books)</div>
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
                  {t.key.replace("x", '\u2033 × ')}\u2033{t.hint ? ` — ${t.hint}` : ""}
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
            title="Draft immediately"
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
            ? "Drafting a full book takes roughly 30–60 minutes."
            : "Plot directions arrive in about a minute."}
        </span>
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
