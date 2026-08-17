"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { scrpt } from "@/lib/scrpt";
import { useAuthContext } from "@/components/AuthProvider";
import { ScrptLogo } from "@/components/Logo";

const NAV_ITEMS = [
  { href: "/hq", label: "HQ" },
  { href: "/office", label: "Back Office" },
];

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
      <Link href="/hq" className="text-accent hover:opacity-80 transition-opacity">
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
