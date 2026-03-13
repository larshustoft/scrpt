import { createClient, SupabaseClient } from "@supabase/supabase-js"

let _supabase: SupabaseClient | null = null

/**
 * Client-side Supabase instance (for use in browser/React components).
 * Returns null if env vars are not configured.
 */
export function getSupabaseBrowser(): SupabaseClient | null {
  if (typeof window === "undefined") return null

  if (_supabase) return _supabase

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

  if (!url || !key) {
    return null
  }

  _supabase = createClient(url, key, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
    },
  })

  return _supabase
}

/**
 * Destroy the singleton so the next call creates a fresh client.
 * Use when the client's internal state is corrupted (e.g. after a Vercel deploy).
 */
export function resetSupabaseBrowser(): void {
  _supabase = null
}
