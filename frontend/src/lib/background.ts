"use client";

import { useEffect, useState } from "react";
import { scrpt } from "@/lib/scrpt";

/** The office behind SCRPT: New York, or the Burbank lot.
 *
 *  One publisher, two addresses — the same room, the same mark on the wall,
 *  a different window. The choice is a real setting (it persists through the
 *  engine), with a localStorage echo so the right office paints instantly on
 *  load instead of flashing New York and then switching.
 */
export const OFFICES = {
  newyork: { label: "New York Office", src: "/hq-background.png" },
  burbank: { label: "The Burbank lot", src: "/hq-background-burbank.png" },
  maingate: { label: "The Main Gate", src: "/hq-background-maingate.png" },
} as const;

export type OfficeKey = keyof typeof OFFICES;

const CACHE = "scrpt-office-background";

export function officeSrc(key: string | undefined | null): string {
  return OFFICES[(key as OfficeKey) || "newyork"]?.src || OFFICES.newyork.src;
}

export function useOfficeBackground(): string {
  const [key, setKey] = useState<string>(() => {
    try {
      return localStorage.getItem(CACHE) || "newyork";
    } catch {
      return "newyork";
    }
  });

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch(`${scrpt.engineUrl}/api/settings`);
        if (!res.ok) return;
        const s = await res.json();
        const k = (s.office_background as string) || "newyork";
        if (alive && k !== key) setKey(k);
        try { localStorage.setItem(CACHE, k); } catch { /* private mode */ }
      } catch { /* engine offline: the cached office stands */ }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return officeSrc(key);
}

/** Called by Settings when the publisher picks an office. */
export function rememberOffice(key: string) {
  try { localStorage.setItem(CACHE, key); } catch { /* private mode */ }
}
