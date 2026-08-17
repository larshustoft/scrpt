"use client";

import Link from "next/link";
import { useAuthContext } from "@/components/AuthProvider";

/**
 * scrpt.ai — the sales page.
 * Public, full-bleed, no app chrome.
 */
export default function SalesPage() {
  const { user } = useAuthContext();

  return (
    <div className="min-h-screen">
      {/* top bar */}
      <header className="absolute top-0 inset-x-0 z-20 h-[72px] px-8 flex items-center justify-between">
        <span className="serif-display text-[24px] font-semibold tracking-[0.22em] text-accent">
          SCRPT
        </span>
        <nav className="flex items-center gap-6">
          <a href="#how" className="text-[13px] text-text-secondary hover:text-text-primary transition-colors hidden sm:inline">
            How it works
          </a>
          <a href="#pricing" className="text-[13px] text-text-secondary hover:text-text-primary transition-colors hidden sm:inline">
            Pricing
          </a>
          {user ? (
            <Link href="/hq" className="btn-brass">Open the studio</Link>
          ) : (
            <Link href="/login" className="btn-brass">Sign in</Link>
          )}
        </nav>
      </header>

      {/* hero */}
      <section className="relative overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url(/hq-background.png)" }}
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(180deg, rgba(14,12,9,0.55) 0%, rgba(14,12,9,0.35) 45%, var(--bg) 100%)",
          }}
        />
        <div className="relative max-w-[1100px] mx-auto px-8 pt-44 pb-28 text-center">
          <h1
            className="serif-display text-[52px] leading-[1.1] font-semibold text-text-primary max-w-[750px] mx-auto"
            style={{ textShadow: "0 2px 30px rgba(0,0,0,0.85)" }}
          >
            Your publishing house.
            <br />
            <span className="text-accent">Population: you.</span>
          </h1>
          <p
            className="text-[16px] text-text-secondary mt-6 max-w-[560px] mx-auto leading-relaxed"
            style={{ textShadow: "0 1px 16px rgba(0,0,0,0.9)" }}
          >
            SCRPT plots, writes, and typesets professional books — thrillers,
            romance, non-fiction — formats them precisely for Amazon KDP,
            narrates the audiobook, and tracks every royalty. You are the
            publisher. SCRPT is the house.
          </p>
          <div className="flex items-center justify-center gap-4 mt-10">
            <Link href="/login" className="btn-brass text-[14px] px-7 py-3">
              Start your catalog
            </Link>
            <a href="#how" className="btn-ghost"
               style={{ background: "rgba(14,12,9,0.5)", backdropFilter: "blur(8px)" }}>
              See how it works
            </a>
          </div>
        </div>
      </section>

      {/* how it works */}
      <section id="how" className="max-w-[1100px] mx-auto px-8 py-24">
        <h2 className="serif-display text-[32px] font-semibold text-center">
          From idea to bookstore
        </h2>
        <p className="text-[14px] text-text-secondary text-center mt-2 max-w-[520px] mx-auto">
          One work order sets the whole house in motion.
        </p>
        <div className="grid md:grid-cols-4 gap-5 mt-14">
          <Step
            n="I"
            title="Commission"
            body="Describe the book — or the series. Pick the genre. SCRPT develops three plot directions and builds a full story bible before a word is written."
          />
          <Step
            n="II"
            title="Write"
            body="Chapter by chapter, with a living continuity bible, genre structure, and your edits folded back in. You direct; the house writes."
          />
          <Step
            n="III"
            title="Format"
            body="A true-to-print page studio: real trim sizes, mirrored margins, running heads, front matter — exported as a vector PDF that passes KDP's checks."
          />
          <Step
            n="IV"
            title="Publish"
            body="Print, ebook, and AI-narrated audiobook masters, listing copy included. Then royalty reports flow back into one quiet dashboard."
          />
        </div>
      </section>

      {/* the details */}
      <section className="border-t border-border-subtle">
        <div className="max-w-[1100px] mx-auto px-8 py-24 grid md:grid-cols-3 gap-10">
          <Detail
            title="KDP-exact, to the thousandth of an inch"
            body="Gutter margins from Amazon's own page-count tables, spine width from paper stock, bleed geometry, embedded fonts. The preview is the print file."
          />
          <Detail
            title="Series that remember themselves"
            body="A series bible carries your characters, world, and arcs across every book, so book four never contradicts book one."
          />
          <Detail
            title="Honest AI, disclosed"
            body="SCRPT follows Amazon's AI-content policy — disclosure on, quality first. The tool accelerates a publisher; it doesn't spam a marketplace."
          />
        </div>
      </section>

      {/* pricing */}
      <section id="pricing" className="border-t border-border-subtle">
        <div className="max-w-[720px] mx-auto px-8 py-24 text-center">
          <h2 className="serif-display text-[32px] font-semibold">Pricing</h2>
          <div className="card mt-10 py-12">
            <div className="serif-display text-[22px] font-semibold text-accent">
              Early access
            </div>
            <p className="text-[14px] text-text-secondary mt-3 max-w-[420px] mx-auto">
              SCRPT is in private early access while the first catalogs are
              built. Create an account to join the list — founding publishers
              set their own terms.
            </p>
            <Link href="/login" className="btn-brass mt-8">
              Request access
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-border-subtle">
        <div className="max-w-[1100px] mx-auto px-8 py-10 flex items-center justify-between">
          <span className="serif-display text-[15px] tracking-[0.22em] text-text-tertiary">
            SCRPT
          </span>
          <span className="text-[12px] text-text-faint">
            Write. Publish. Sell.
          </span>
        </div>
      </footer>
    </div>
  );
}

function Step({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <div className="card">
      <div className="serif-display text-[26px] text-accent">{n}</div>
      <div className="serif-display text-[18px] font-semibold mt-3">{title}</div>
      <p className="text-[13px] text-text-secondary mt-2 leading-relaxed">{body}</p>
    </div>
  );
}

function Detail({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <h3 className="serif-display text-[19px] font-semibold leading-snug">{title}</h3>
      <p className="text-[13px] text-text-secondary mt-3 leading-relaxed">{body}</p>
    </div>
  );
}
