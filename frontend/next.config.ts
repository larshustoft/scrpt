import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // hide the framework's dev-tools badge (the "N" bubble) — SCRPT.app runs
  // against the dev server locally and the badge doesn't belong in the studio
  devIndicators: false,
};

export default nextConfig;
