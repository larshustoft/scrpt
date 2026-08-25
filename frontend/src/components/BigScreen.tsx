"use client";

/**
 * The big screen.
 *
 * Plug a monitor into the iMac and it becomes SCRPT's cinema: every clip the
 * app plays — a trailer today, a film when the movie engine ships — opens
 * fullscreen on that monitor, while the page you are on stays the remote.
 * Unplug it and everything falls back to playing inline. Nothing to set up.
 *
 * It works on ANY <video> in the app without those components knowing about
 * it: this listens for play/pause/seek in the capture phase, so a new video
 * anywhere is picked up automatically.
 */

import { useEffect, useState } from "react";

interface Desktop {
  cinemaAvailable: () => Promise<boolean>;
  cinemaPlay: (src: string, time: number) => Promise<boolean>;
  cinemaPause: () => Promise<boolean>;
  cinemaSeek: (time: number) => Promise<boolean>;
  cinemaVolume: (volume: number, muted: boolean) => Promise<boolean>;
  cinemaStop: () => Promise<boolean>;
  onCinemaAvailability: (cb: (available: boolean) => void) => () => void;
}

function desktop(): Desktop | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { scrptDesktop?: Partial<Desktop> };
  const d = w.scrptDesktop;
  // older desktop builds expose only the fullscreen helpers
  return d && typeof d.cinemaAvailable === "function" ? (d as Desktop) : null;
}

export function BigScreen() {
  const [available, setAvailable] = useState(false);
  const [showing, setShowing] = useState(false);

  // is a second screen attached?
  useEffect(() => {
    const d = desktop();
    if (!d) return;
    let alive = true;
    d.cinemaAvailable().then((a) => { if (alive) setAvailable(a); }).catch(() => {});
    const off = d.onCinemaAvailability((a) => {
      setAvailable(a);
      if (!a) setShowing(false);
    });
    return () => { alive = false; off?.(); };
  }, []);

  // mirror any video in the app onto the big screen
  useEffect(() => {
    const d = desktop();
    if (!d || !available) return;

    const isVideo = (t: EventTarget | null): t is HTMLVideoElement =>
      t instanceof HTMLVideoElement;

    const onPlay = (e: Event) => {
      const v = e.target;
      if (!isVideo(v) || !v.currentSrc) return;
      // the big screen does the playing; the inline player is only the remote
      v.pause();
      v.muted = true;
      setShowing(true);
      void d.cinemaPlay(v.currentSrc, v.currentTime);
    };
    const onPause = (e: Event) => {
      if (!isVideo(e.target)) return;
      void d.cinemaPause();
    };
    const onSeek = (e: Event) => {
      const v = e.target;
      if (!isVideo(v)) return;
      void d.cinemaSeek(v.currentTime);
    };
    const onVolume = (e: Event) => {
      const v = e.target;
      if (!isVideo(v)) return;
      // the inline player stays silent — it is the remote, not the speaker
      void d.cinemaVolume(v.volume, false);
    };

    document.addEventListener("play", onPlay, true);
    document.addEventListener("pause", onPause, true);
    document.addEventListener("seeked", onSeek, true);
    document.addEventListener("volumechange", onVolume, true);
    return () => {
      document.removeEventListener("play", onPlay, true);
      document.removeEventListener("pause", onPause, true);
      document.removeEventListener("seeked", onSeek, true);
      document.removeEventListener("volumechange", onVolume, true);
    };
  }, [available]);

  if (!available || !showing) return null;

  return (
    <div className="fixed bottom-8 left-8 z-40 flex items-center gap-3 rounded-full px-4 py-2"
         style={{ background: "var(--surface)", boxShadow: "var(--shadow-card)",
                  border: "1px solid var(--border-subtle)" }}>
      <span className="text-[11px] uppercase tracking-[0.18em] text-text-secondary">
        Playing on the big screen
      </span>
      <button className="text-[11px] uppercase tracking-[0.14em] text-text-faint hover:text-text-primary"
              onClick={() => {
                document.querySelectorAll("video").forEach((v) => v.pause());
                void desktop()?.cinemaStop();
                setShowing(false);
              }}>
        Stop
      </button>
    </div>
  );
}
