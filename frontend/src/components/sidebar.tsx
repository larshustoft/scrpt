"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IconDashboard,
  IconLibrary,
  IconPlus,
  IconSearch,
  IconSettings,
} from "@/components/icons";
import { checkHealth } from "@/lib/companion";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", Icon: IconDashboard },
  { href: "/catalog", label: "Catalog", Icon: IconLibrary },
  { href: "/create", label: "Create Book", Icon: IconPlus },
  { href: "/research", label: "Research", Icon: IconSearch },
  { href: "/settings", label: "Settings", Icon: IconSettings },
];

export function Sidebar() {
  const pathname = usePathname();
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);

  useEffect(() => {
    // Check immediately, then poll every 30 seconds
    checkHealth().then(setEngineOnline);
    const interval = setInterval(() => {
      checkHealth().then(setEngineOnline);
    }, 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <aside className="flex w-[220px] flex-col bg-[#0B0F1A] text-slate-300 shrink-0">
      {/* Brand */}
      <div className="flex h-14 items-center px-5 border-b border-white/[0.06]">
        <span className="text-[15px] font-semibold tracking-[0.12em] text-white">
          SCRPT
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-3 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] font-medium transition-colors ${
                isActive
                  ? "bg-white/[0.08] text-white"
                  : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
              }`}
            >
              <item.Icon className="w-[16px] h-[16px] shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Engine Status */}
      {engineOnline !== null && (
        <div className="px-5 py-2.5 border-t border-white/[0.06]">
          <div className="flex items-center gap-2">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                engineOnline ? "bg-emerald-400" : "bg-red-400"
              }`}
            />
            <span className="text-[11px] text-slate-500">
              {engineOnline ? "Engine running" : "Engine offline"}
            </span>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="px-5 py-3 border-t border-white/[0.06]">
        <p className="text-[10px] text-slate-600 tracking-wide">
          v1.0 &middot; KDP Publishing Engine
        </p>
      </div>
    </aside>
  );
}
