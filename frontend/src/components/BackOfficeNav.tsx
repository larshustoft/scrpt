"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/office", label: "Overview", match: (p: string) => p === "/office" },
  { href: "/shelf", label: "Bookshelf", match: (p: string) => p.startsWith("/shelf") },
  { href: "/analytics", label: "Analytics & Royalties", match: (p: string) => p.startsWith("/analytics") },
  { href: "/settings", label: "Settings", match: (p: string) => p.startsWith("/settings") },
];

/** Slim tool menu shown across all Back Office pages. */
export function BackOfficeNav() {
  const pathname = usePathname();
  return (
    <div className="h-[46px] px-16 flex items-center gap-1 border-b border-border-subtle"
         style={{ background: "var(--surface)" }}>
      {ITEMS.map((item) => {
        const active = item.match(pathname);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`px-3 py-[5px] rounded-md text-[12.5px] font-medium transition-colors ${
              active
                ? "text-accent bg-accent-subtle"
                : "text-text-tertiary hover:text-text-primary"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </div>
  );
}
