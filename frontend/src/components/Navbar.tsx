"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { scrpt } from "@/lib/scrpt";
import { useAuthContext } from "@/components/AuthProvider";
import { ScrptLogo } from "@/components/Logo";

const NAV_ITEMS = [
  { href: "/study", label: "The Study" },
  { href: "/office", label: "Back Office" },
];

declare global {
  interface Window {
    scrptDesktop?: {
      toggleFullscreen: () => Promise<boolean>;
      isFullscreen: () => Promise<boolean>;
    };
  }
}

function FullscreenToggle() {
  const [isFull, setIsFull] = useState(false);

  useEffect(() => {
    if (window.scrptDesktop) {
      window.scrptDesktop.isFullscreen().then(setIsFull);
    } else {
      const sync = () => setIsFull(Boolean(document.fullscreenElement));
      document.addEventListener("fullscreenchange", sync);
      return () => document.removeEventListener("fullscreenchange", sync);
    }
  }, []);

  const toggle = async () => {
    if (window.scrptDesktop) {
      setIsFull(await window.scrptDesktop.toggleFullscreen());
    } else if (document.fullscreenElement) {
      await document.exitFullscreen();
      setIsFull(false);
    } else {
      await document.documentElement.requestFullscreen();
      setIsFull(true);
    }
  };

  return (
    <button
      onClick={toggle}
      title={isFull ? "Exit full screen" : "Enter full screen"}
      className="text-text-tertiary hover:text-text-primary transition-colors p-1"
      aria-label="Toggle full screen"
    >
      {isFull ? (
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
          <path d="M6 2v4H2M10 2v4h4M6 14v-4H2M10 14v-4h4"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
                strokeLinejoin="round" />
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
          <path d="M2 6V2h4M14 6V2h-4M2 10v4h4M14 10v4h-4"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
                strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

export function Navbar() {
  const pathname = usePathname();
  const { signOut } = useAuthContext();
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);

  useEffect(() => {
    scrpt.health().then(setEngineOnline);
    const interval = setInterval(() => scrpt.health().then(setEngineOnline), 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header
      className="sticky top-0 z-50 h-[64px] px-8 flex items-center gap-6 border-b border-border-subtle"
      style={{ background: "var(--nav-bg)", backdropFilter: "blur(16px)" }}
    >
      <Link href="/study" className="text-accent hover:opacity-80 transition-opacity">
        <ScrptLogo size={15} />
      </Link>

      <div className="flex-1" />

      <nav className="flex items-center gap-1">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/office"
              ? ["/office", "/shelf", "/analytics", "/settings"].some((p) => pathname.startsWith(p))
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`px-3 py-[6px] rounded-md text-[13px] font-medium transition-colors ${
                isActive
                  ? "text-text-primary bg-accent-subtle"
                  : "text-text-tertiary hover:text-text-primary"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
        <Link href="/workorder" className="btn-brass ml-3 text-[12px] px-4 py-[7px]">
          New Work Order
        </Link>
      </nav>

      <div className="h-4 w-px bg-border-subtle" />

      <div className="flex items-center gap-4">
        <FullscreenToggle />
        <div className="flex items-center gap-2" title={engineOnline ? "Local engine running" : "Local engine offline — start the SCRPT companion"}>
          <span
            className={`h-[7px] w-[7px] rounded-full ${
              engineOnline === null
                ? "bg-text-faint"
                : engineOnline
                  ? "bg-status-green"
                  : "bg-status-red pulse-soft"
            }`}
          />
          <span className="text-[11px] text-text-tertiary hidden md:inline">
            {engineOnline === null ? "Engine…" : engineOnline ? "Engine" : "Offline"}
          </span>
        </div>
        <button
          onClick={() => signOut()}
          className="text-[12px] text-text-tertiary hover:text-text-primary transition-colors"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
