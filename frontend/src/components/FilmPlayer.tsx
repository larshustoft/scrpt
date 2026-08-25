"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The brand film: full width, its own shape, and no words on it.
 *
 * It plays muted on a loop as soon as it loads so the section is alive
 * rather than a frozen poster; one press brings the sound, restarts it from
 * the top and hands over the native controls.
 */
export function FilmPlayer({ ambient, film, poster }: {
  ambient: string; film: string; poster: string;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const [watching, setWatching] = useState(false);

  // autoPlay alone is unreliable after hydration — the element can settle
  // after the browser's autoplay moment has passed. Ask once on mount.
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
    v.src = film;                 // the subtitled cut, with sound
    v.loop = false;
    v.muted = false;
    v.currentTime = 0;
    v.play().then(() => setWatching(true)).catch(() => setWatching(false));
  };

  return (
    <div className="relative w-full" style={{ background: "var(--bg)" }}>
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
        className="w-full block"
        style={{ aspectRatio: "16 / 9" }}
      />
      {!watching && (
        <button
          onClick={play}
          aria-label="Play the film with sound"
          className="absolute inset-0 flex items-center justify-center group cursor-pointer"
          style={{ background:
            "linear-gradient(180deg, rgba(10,8,6,0.04) 0%, rgba(10,8,6,0.26) 100%)" }}
        >
          <span
            className="flex items-center justify-center rounded-full transition-transform
                       duration-300 group-hover:scale-[1.07]"
            style={{
              width: "clamp(64px, 5.5vw, 100px)",
              height: "clamp(64px, 5.5vw, 100px)",
              background: "rgba(14,12,9,0.5)",
              border: "1px solid rgba(236,229,218,0.5)",
              backdropFilter: "blur(6px)",
              boxShadow: "0 8px 44px rgba(0,0,0,0.55)",
            }}
          >
            {/* optically centred — a mathematically centred triangle reads left-heavy */}
            <svg viewBox="0 0 26 30" aria-hidden
                 style={{ width: "clamp(20px, 1.8vw, 30px)", marginLeft: "0.18em" }}>
              <path d="M0 0 L26 15 L0 30 Z" fill="#f2ece1" />
            </svg>
          </span>
        </button>
      )}
    </div>
  );
}
