"use client";

import { useRef, useState } from "react";

/**
 * The brand film on the sales page.
 *
 * A bare <video controls> shows a browser's default chrome and, on some
 * browsers, a black rectangle until it decides to fetch a frame. A visitor
 * deciding whether to spend eighty seconds should see a still from the film
 * and one obvious way in — so this holds a poster and a play button, and
 * hands over to the native controls only once playing.
 */
export function FilmPlayer({ src, poster, caption, fullBleed = false }: {
  src: string; poster: string; caption?: string; fullBleed?: boolean;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  // Driven by the ELEMENT, not by a flag we set ourselves. Tracking it
  // separately meant one stray play event left the overlay hidden for good
  // and the film sat there with no visible way in.
  const [playing, setPlaying] = useState(false);

  const start = () => {
    const v = ref.current;
    if (!v) return;
    v.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  };

  return (
    <figure className="m-0">
      <div
        className={`relative overflow-hidden group ${fullBleed ? "" : "rounded-[10px]"}`}
        style={fullBleed
          ? { background: "#0b0907" }
          : { boxShadow: "var(--shadow-page)",
              border: "1px solid var(--border-subtle)",
              background: "#0b0907" }}
      >
        <video
          ref={ref}
          src={src}
          poster={poster}
          controls={playing}
          playsInline
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(!(ref.current?.paused ?? true))}
          onEnded={() => setPlaying(false)}
          className="w-full block"
          style={{ aspectRatio: "16 / 9" }}
        />

        {!playing && (
          <button
            onClick={start}
            aria-label="Play the film"
            className="absolute inset-0 flex items-center justify-center cursor-pointer"
            style={{ background:
              "linear-gradient(180deg, rgba(10,8,6,0.10) 0%, rgba(10,8,6,0.42) 100%)" }}
          >
            <span
              className="flex items-center justify-center rounded-full transition-transform
                         duration-300 group-hover:scale-[1.06]"
              style={{
                width: fullBleed ? 104 : 82, height: fullBleed ? 104 : 82,
                background: "rgba(14,12,9,0.55)",
                border: "1px solid rgba(236,229,218,0.55)",
                backdropFilter: "blur(6px)",
                boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
              }}
            >
              {/* a triangle, optically centred — a centred glyph looks left-heavy */}
              <svg width={fullBleed ? 32 : 26} height={fullBleed ? 37 : 30} viewBox="0 0 26 30" aria-hidden
                   style={{ marginLeft: 5 }}>
                <path d="M0 0 L26 15 L0 30 Z" fill="#f2ece1" />
              </svg>
            </span>
          </button>
        )}
      </div>
      {caption && (
        <figcaption className="text-[12.5px] text-text-faint text-center mt-4">
          {caption}
        </figcaption>
      )}
    </figure>
  );
}
