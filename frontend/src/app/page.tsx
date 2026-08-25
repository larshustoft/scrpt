"use client";

import Link from "next/link";
import { useAuthContext } from "@/components/AuthProvider";
import { ScrptLogo } from "@/components/Logo";
import { FilmPlayer } from "@/components/FilmPlayer";
import { InterestForm } from "@/components/InterestForm";

/**
 * scrpt.ai — the sales page.
 * Public, full-bleed, real product screenshots. No app chrome.
 */
export default function SalesPage() {
  const { user } = useAuthContext();
  const appHref = user ? "/front" : "/login";

  return (
    <div className="min-h-screen">
      {/* top bar */}
      <header className="absolute top-0 inset-x-0 z-20 h-[72px] px-8 md:px-14 flex items-center justify-between">
        <span className="text-text-primary"><ScrptLogo size={24} /></span>
        <nav className="flex items-center gap-6">
          <a href="#studio" className="text-[13px] text-text-secondary hover:text-text-primary transition-colors hidden sm:inline">
            The Studio
          </a>
          <a href="#how" className="text-[13px] text-text-secondary hover:text-text-primary transition-colors hidden sm:inline">
            How it works
          </a>
          <a href="#access" className="text-[13px] text-text-secondary hover:text-text-primary transition-colors hidden sm:inline">
            Early access
          </a>
          <Link href={appHref} className="btn-brass">
            {user ? "Open SCRPT" : "Sign in"}
          </Link>
        </nav>
      </header>

      {/* hero — the room, the headline, the copy */}
      <section className="relative overflow-hidden">
        <div
          className="absolute inset-0"
          style={{ backgroundImage: "url(/hq-background.png)",
                   backgroundSize: "cover",
                   backgroundPosition: "center 30%",
                   backgroundRepeat: "no-repeat" }}
        />
        <div
          className="absolute inset-0"
          style={{ background:
            "linear-gradient(180deg, rgba(14,12,9,0.72) 0%, rgba(14,12,9,0.55) 42%, var(--bg) 97%)" }}
        />
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background:
            "radial-gradient(ellipse 62% 70% at 50% 42%, rgba(14,12,9,0) 0%,"
            + " rgba(14,12,9,0.30) 58%, rgba(14,12,9,0.68) 100%)" }}
        />
        {/* the room fills the window, whatever the window is: 100dvh so a
            phone's collapsing address bar cannot leave a strip of page
            showing underneath, and the content centres in whatever height
            that turns out to be */}
        <div className="relative max-w-[1150px] mx-auto px-8 text-center
                        flex flex-col justify-center"
             style={{ minHeight: "100dvh",
                      paddingTop: "clamp(4rem, 8vh, 7rem)",
                      paddingBottom: "clamp(2rem, 5vh, 4rem)" }}>
          <h1 className="serif-display font-semibold text-text-primary max-w-[820px] mx-auto"
              style={{ fontSize: "clamp(2.2rem, 4vw, 3.5rem)", lineHeight: 1.06,
                       textShadow: "0 2px 30px rgba(0,0,0,0.85)" }}>
            From writer
            <br />
            to <span className="text-accent">publishing house.</span>
          </h1>
          <p className="text-text-secondary mt-6 max-w-[640px] mx-auto leading-relaxed"
             style={{ fontSize: "clamp(0.95rem, 1.05vw, 1.03rem)",
                      textShadow: "0 1px 16px rgba(0,0,0,0.9)" }}>
            SCRPT writes and typesets the book, designs the cover, produces the
            audiobook, cuts the trailer — and when the story earns it, the film.
            It keeps your catalogue, tracks what every title earns, runs the
            marketing, and reports to you each morning through your own
            publishing assistant.
          </p>
          <div className="flex items-center justify-center gap-4 mt-8">
            <Link href="/login" className="btn-brass text-[14px] px-7 py-3">
              Start your catalog
            </Link>
            <a href="#access" className="btn-ghost"
               style={{ background: "rgba(14,12,9,0.5)", backdropFilter: "blur(8px)" }}>
              Get early access
            </a>
          </div>
        </div>
      </section>

      {/* the film — the whole section, edge to edge, and nothing written on it */}
      <section className="relative w-full">
        <FilmPlayer
          ambient="/film/scrpt-ambient.mp4"
          film="/film/scrpt.mp4"
          poster="/film/poster.jpg"
        />
      </section>

      {/* the proof — a real typeset spread */}
      <section className="border-t border-border-subtle">
        <div className="max-w-[1150px] mx-auto px-8 py-20 text-center">
          <div id="studio" className="rounded-[14px] overflow-hidden"
               style={{ boxShadow: "0 0 0 1px rgba(236,229,218,0.1), 0 30px 90px rgba(0,0,0,0.7)" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/marketing/formatting-studio.jpg"
                 alt="The SCRPT Formatting Studio — a real book spread, typeset to print"
                 className="w-full block" />
          </div>
          <p className="text-[12px] text-text-faint mt-4">
            The Formatting Studio — a real manuscript, typeset live at print
            size. What you see is the file Amazon receives.
          </p>
        </div>
      </section>

      {/* how it works */}
      <section id="how" className="max-w-[1150px] mx-auto px-8 py-24">
        <h2 className="serif-display text-[34px] font-semibold text-center">
          From idea to bookstore
        </h2>
        <p className="text-[14px] text-text-secondary text-center mt-2 max-w-[520px] mx-auto">
          One work order sets the whole house in motion.
        </p>
        <div className="grid md:grid-cols-4 gap-5 mt-14">
          <Step n="I" title="Commission"
                body="Describe the book — or the series. Pick the genre. SCRPT develops three plot directions and builds a full story bible before a word is written." />
          <Step n="II" title="Write"
                body="Chapter by chapter with a living continuity bible and market-calibrated genre structure. You direct; the house writes. Edit any paragraph and the book reflows." />
          <Step n="III" title="Format"
                body="True-to-print pages: real trim sizes, mirrored margins, running heads, front matter — exported as a vector PDF that passes Amazon's checks." />
          <Step n="IV" title="Publish"
                body="Print, ebook, and narrated audiobook masters with listing copy included. Royalty reports flow back into one quiet dashboard." />
        </div>
      </section>

      {/* the front office */}
      <section className="border-t border-border-subtle">
        <div className="max-w-[1150px] mx-auto px-8 py-24 grid md:grid-cols-2 gap-12 items-center">
          <div>
            <h2 className="serif-display text-[30px] font-semibold leading-snug">
              A front office with an assistant who knows the whole catalog
            </h2>
            <p className="text-[14px] text-text-secondary mt-4 leading-relaxed">
              Walk in, see the book being written right now, and talk to the
              house. The assistant answers with live production facts — word
              counts, page counts, royalty math per copy — and speaks its
              answers aloud. Ask what to do next and it tells you, precisely.
            </p>
            <ul className="mt-5 space-y-2 text-[13px] text-text-secondary">
              <ListItem>Live status on the current title, down to the chapter</ListItem>
              <ListItem>Voice in, voice out — speech recognition runs locally</ListItem>
              <ListItem>KDP economics answered with real numbers, print and ebook</ListItem>
            </ul>
          </div>
          <div className="rounded-[14px] overflow-hidden"
               style={{ boxShadow: "0 0 0 1px rgba(236,229,218,0.1), 0 20px 60px rgba(0,0,0,0.6)" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/marketing/front-office.jpg" alt="The SCRPT Front Office" className="w-full block" />
          </div>
        </div>
      </section>

      {/* three pillars */}
      <section className="border-t border-border-subtle">
        <div className="max-w-[1150px] mx-auto px-8 py-24 grid md:grid-cols-3 gap-10">
          <Detail
            title="KDP-exact, to the thousandth of an inch"
            body="Gutter margins from Amazon's own page-count tables, spine width computed from paper stock, embedded fonts, validated PDFs. The preview is the print file — no surprises at review."
          />
          <Detail
            title="Series that remember themselves"
            body="A series bible carries your characters, world, and arcs across every book, so book four never contradicts book one. Genre length norms are built in — a thriller ships at thriller length."
          />
          <Detail
            title="Every format from one manuscript"
            body="Print interior, ebook, and an ElevenLabs-narrated audiobook mastered to retail spec — plus the cover designer package with exact wrap dimensions for your artist."
          />
        </div>
      </section>


      {/* pre-launch: no price, an invitation */}
      <section id="access" className="border-t border-border-subtle">
        <div className="max-w-[720px] mx-auto px-8 py-24 text-center">
          <h2 className="serif-display text-[34px] font-semibold">
            SCRPT opens soon.
          </h2>
          <p className="text-[14.5px] text-text-secondary mt-4 max-w-[520px] mx-auto leading-relaxed">
            The first catalogues are being built now. Leave your email and
            you&rsquo;ll hear the day it opens — nothing else, and never your
            address to anyone.
          </p>
          <div className="mt-9">
            <InterestForm />
          </div>
        </div>
      </section>

      {/* closing */}
      <section className="border-t border-border-subtle">
        <div className="max-w-[720px] mx-auto px-8 py-20 text-center">
          <h2 className="serif-display text-[28px] font-semibold leading-snug">
            The next book on your shelf hasn&apos;t been written yet.
          </h2>
          <a href="#access" className="btn-brass mt-8 text-[14px] px-7 py-3 inline-block">
            Get early access
          </a>
        </div>
      </section>

      <footer className="border-t border-border-subtle">
        <div className="max-w-[1150px] mx-auto px-8 py-10 flex items-center justify-between">
          <span className="text-text-tertiary"><ScrptLogo size={16} /></span>
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

function ListItem({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-3">
      <span className="text-accent mt-[1px]">—</span>
      <span>{children}</span>
    </li>
  );
}
