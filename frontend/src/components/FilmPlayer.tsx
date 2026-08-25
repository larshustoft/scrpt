"use client";

import { useRef, useState } from "react";

/**
 * The brand film, edge to edge.
 *
 * Two earlier attempts got this wrong in opposite directions: a full-bleed
 * 16:9 film is taller than a laptop viewport, and capping its height left
 * bars down the sides that read as a bug. A modern product-film section does
 * neither — it runs the film at full width in its own shape and lets the
 * page scroll to it.
 *
 * It also plays. Muted and looping from the moment it loads, so the section
 * is alive rather than a frozen poster; one press brings the sound, starts
 * it from the top and hands over the native controls.
 */
export function FilmPlayer({ src, poster, caption }: {
  src: string; poster: string; caption?: string;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const [withSound, setWithSound] = useState(false);

  const play = () => {
    const v = ref.current;
    if (!v) return;
    v.muted = false;
    v.loop = false;
    v.currentTime = 0;
    v.play().then(() => setWithSound(true)).catch(() => setWithSound(false));
  };

  return (
    <figure className="m-0 relative w-full" style={{ background: "var(--bg)" }}>
      <video
        ref={ref}
        src={src}
        poster={poster}
        /* muted + playsInline + autoPlay is the only combination a browser
           will start unprompted; sound waits for a real press */
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        controls={withSound}
        onEnded={() => setWithSound(false)}
        className="w-full block"
        style={{ aspectRatio: "16 / 9" }}
      />

      {!withSound && (
        <button
          onClick={play}
          aria-label="Play the film with sound"
          className="absolute inset-0 flex items-center justify-center group cursor-pointer"
          style={{ background:
            "linear-gradient(180deg, rgba(10,8,6,0.06) 0%, rgba(10,8,6,0.34) 100%)" }}
        >
          <span
            className="flex items-center justify-center rounded-full transition-transform
                       duration-300 group-hover:scale-[1.07]"
            style={{
              width: "clamp(64px, 6vw, 104px)",
              height: "clamp(64px, 6vw, 104px)",
              background: "rgba(14,12,9,0.5)",
              border: "1px solid rgba(236,229,218,0.5)",
              backdropFilter: "blur(6px)",
              boxShadow: "0 8px 44px rgba(0,0,0,0.55)",
            }}
          >
            {/* optically centred — a mathematically centred triangle reads left-heavy */}
            <svg viewBox="0 0 26 30" aria-hidden
                 style={{ width: "clamp(20px, 1.9vw, 32px)", marginLeft: "0.18em" }}>
              <path d="M0 0 L26 15 L0 30 Z" fill="#f2ece1" />
            </svg>
          </span>
          <span className="absolute text-[11.5px] tracking-[0.2em] uppercase"
                style={{ bottom: "clamp(1.25rem, 4vh, 3rem)",
                         color: "rgba(236,229,218,0.72)" }}>
            Play with sound
          </span>
        </button>
      )}
      {caption && (
        <figcaption className="text-[12.5px] text-text-faint text-center mt-4">
          {caption}
        </figcaption>
      )}
    </figure>
  );
}
