"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The film IS the hero.
 *
 * A 16:9 film at full width is 966px tall on a 1728x985 screen — it nearly
 * fills the window on its own. So a hero above it and the film's full height
 * cannot both fit; something always got cut. Making the film the hero
 * removes the competition entirely: it fills the window, the headline sits
 * on it, and pressing play swaps the silent background loop for the real
 * film, with sound and subtitles.
 */
export function FilmHero({
  ambient, film, poster, children,
}: {
  ambient: string; film: string; poster: string; children: React.ReactNode;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const [watching, setWatching] = useState(false);

  // The autoPlay attribute alone is unreliable once React has hydrated —
  // the element can settle after the browser's autoplay moment has passed.
  // Ask once on mount; muted playback is always permitted.
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    v.muted = true;
    const go = () => v.play().catch(() => {});
    if (v.readyState >= 2) go();
    else v.addEventListener("loadeddata", go, { once: true });
  }, []);

  const play = () => {
    const v = ref.current;
    if (!v) return;
    v.src = film;              // the subtitled cut, with sound
    v.loop = false;
    v.muted = false;
    v.currentTime = 0;
    v.play().then(() => setWatching(true)).catch(() => setWatching(false));
  };

  return (
    <section
      className="relative w-full overflow-hidden"
      style={{ height: "min(92vh, calc(100vw * 9 / 16))" }}
    >
      <video
        ref={ref}
        src={ambient}
        poster={poster}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        controls={watching}
        onEnded={() => setWatching(false)}
        className="absolute inset-0 w-full h-full"
        style={{ objectFit: "cover" }}
      />

      {!watching && (
        <>
          {/* enough shade for white type, not so much that the room disappears */}
          <div className="absolute inset-0 pointer-events-none"
               style={{ background:
                 "linear-gradient(180deg, rgba(14,12,9,0.74) 0%, rgba(14,12,9,0.40) 44%,"
                 + " rgba(14,12,9,0.72) 100%)" }} />
          <div className="relative h-full flex flex-col items-center justify-center
                          text-center px-8">
            {children}
            <button
              onClick={play}
              className="mt-9 flex items-center gap-3 group"
              aria-label="Watch the film with sound"
            >
              <span
                className="flex items-center justify-center rounded-full
                           transition-transform duration-300 group-hover:scale-[1.07]"
                style={{
                  width: "clamp(52px, 4vw, 72px)", height: "clamp(52px, 4vw, 72px)",
                  background: "rgba(14,12,9,0.5)",
                  border: "1px solid rgba(236,229,218,0.5)",
                  backdropFilter: "blur(6px)",
                }}
              >
                <svg viewBox="0 0 26 30" aria-hidden
                     style={{ width: "clamp(16px, 1.3vw, 22px)", marginLeft: "0.18em" }}>
                  <path d="M0 0 L26 15 L0 30 Z" fill="#f2ece1" />
                </svg>
              </span>
              <span className="text-[12px] tracking-[0.2em] uppercase"
                    style={{ color: "rgba(236,229,218,0.8)",
                             textShadow: "0 1px 12px rgba(0,0,0,0.9)" }}>
                Watch the film
              </span>
            </button>
          </div>
        </>
      )}
    </section>
  );
}
