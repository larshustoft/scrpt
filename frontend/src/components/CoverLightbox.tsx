"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

/** A lightbox can be a single image, or a run you can page through — a book
 *  opened fullscreen should turn its pages, not force you back out to move on. */
type LightboxState =
  | { src: string; alt: string; nav?: undefined }
  | { src?: undefined; alt: string; nav: LightboxNav }
  | null;

/** A frame is what you look at in one step — one page, or two facing pages
 *  shown together because that is how the book is bound. */
export type LightboxFrame = { label: string; srcs: string[] };

export type LightboxNav = {
  index: number;                       // which frame we are on
  frames: LightboxFrame[];
};

const Ctx = createContext<(v: LightboxState) => void>(() => {});

/** Wrap any cover image element to make it open fullscreen on click. */
export function useCoverLightbox() {
  const open = useContext(Ctx);
  return useCallback(
    (src: string, alt = "Cover") => open({ src, alt }),
    [open],
  );
}

/** Open fullscreen with forward/back through a sequence of images. */
export function useLightboxRun() {
  const open = useContext(Ctx);
  return useCallback(
    (nav: LightboxNav, alt = "Page") => open({ nav, alt }),
    [open],
  );
}

export function CoverLightboxProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<LightboxState>(null);
  const [i, setI] = useState(0);

  useEffect(() => {
    if (state?.nav) setI(state.nav.index);
  }, [state]);

  const nav = state?.nav;
  const min = 0;
  const max = nav ? nav.frames.length - 1 : 0;
  const step = useCallback((d: number) => {
    if (!nav) return;
    setI((v) => Math.max(0, Math.min(nav.frames.length - 1, v + d)));
  }, [nav]);

  useEffect(() => {
    if (!state) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setState(null); return; }
      if (!nav) return;
      if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
      if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    };
    window.addEventListener("keydown", onKey);
    // lock scroll while open
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [state, nav, step]);

  const frame = nav ? nav.frames[Math.max(0, Math.min(i, max))] : null;
  const srcs = frame ? frame.srcs : state?.src ? [state.src] : [];
  const label = frame ? frame.label : state?.alt;

  // neighbouring frames are fetched while you look at this one, so a page
  // turn is instant instead of a blank flash
  const ahead = nav && i < max ? nav.frames[i + 1].srcs : [];
  const behind = nav && i > min ? nav.frames[i - 1].srcs : [];

  return (
    <Ctx.Provider value={setState}>
      {children}
      {state && (
        <div
          onClick={() => setState(null)}
          className="fixed inset-0 z-[200] flex items-center justify-center p-6 md:p-12"
          style={{ background: "rgba(8,7,5,0.92)", backdropFilter: "blur(6px)",
                   animation: "lb-fade 160ms ease-out" }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="relative flex items-center justify-center max-h-full max-w-full"
            style={{
              // One shadow around the PAIR. Shadowing each half separately
              // put two dark edges together at the fold and it read as a
              // black seam through the middle of the picture.
              boxShadow: "0 30px 90px rgba(0,0,0,0.75)",
              borderRadius: 6,
              overflow: "hidden",
              animation: "lb-pop 180ms cubic-bezier(0.2,0.8,0.2,1)",
            }}
          >
            {srcs.map((u, k) => (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                key={u + k}
                src={u}
                alt={`${label}${srcs.length > 1 ? ` (${k === 0 ? "left" : "right"})` : ""}`}
                className="object-contain block"
                style={{ maxHeight: "88vh",
                         maxWidth: srcs.length > 1 ? "46vw" : "92vw" }}
              />
            ))}
            {srcs.length > 1 && (
              /* the gutter: a whisper of shading where the paper folds, the
                 way an open book actually looks — not a drawn line */
              <div className="pointer-events-none absolute inset-y-0"
                   style={{ left: "50%", width: 34, transform: "translateX(-50%)",
                            background:
                              "linear-gradient(to right, rgba(0,0,0,0) 0%, rgba(0,0,0,0.16) 42%,"
                              + " rgba(0,0,0,0.22) 50%, rgba(0,0,0,0.16) 58%, rgba(0,0,0,0) 100%)" }} />
            )}
          </div>
          {/* preloaded neighbours, never shown */}
          {[...ahead, ...behind].map((u) => (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img key={`pre-${u}`} src={u} alt="" className="hidden" />
          ))}

          {nav && (
            <>
              <button
                onClick={(e) => { e.stopPropagation(); step(-1); }}
                disabled={i <= min}
                aria-label="Previous page"
                className="absolute left-3 md:left-8 top-1/2 -translate-y-1/2 h-12 w-12
                           rounded-full flex items-center justify-center text-[24px]
                           transition-all disabled:opacity-25 disabled:cursor-default
                           text-[#c9beac] hover:text-white"
                style={{ background: "rgba(20,17,13,0.7)",
                         border: "1px solid rgba(236,229,218,0.14)" }}
              >
                ‹
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); step(1); }}
                disabled={i >= max}
                aria-label="Next page"
                className="absolute right-3 md:right-8 top-1/2 -translate-y-1/2 h-12 w-12
                           rounded-full flex items-center justify-center text-[24px]
                           transition-all disabled:opacity-25 disabled:cursor-default
                           text-[#c9beac] hover:text-white"
                style={{ background: "rgba(20,17,13,0.7)",
                         border: "1px solid rgba(236,229,218,0.14)" }}
              >
                ›
              </button>
            </>
          )}

          <button
            onClick={() => setState(null)}
            aria-label="Close"
            className="absolute top-5 right-6 text-[26px] leading-none text-[#c9beac] hover:text-white transition-colors"
          >
            ×
          </button>
          <div className="absolute bottom-5 left-0 right-0 text-center text-[11px]
                          tracking-[0.15em] uppercase text-[#8c826f]">
            {label}
            {nav ? " · arrow keys turn the page · Esc to close"
                 : " · click anywhere or press Esc to close"}
          </div>
          <style>{`
            @keyframes lb-fade { from { opacity: 0 } to { opacity: 1 } }
            @keyframes lb-pop { from { transform: scale(0.96); opacity: 0 }
                                to { transform: scale(1); opacity: 1 } }
          `}</style>
        </div>
      )}
    </Ctx.Provider>
  );
}
