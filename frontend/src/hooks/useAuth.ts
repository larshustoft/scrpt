"use client"

import { useState, useEffect, useCallback } from "react"
import { getSupabaseBrowser, resetSupabaseBrowser } from "@/lib/supabase-browser"
import type { User, Session } from "@supabase/supabase-js"

interface AuthState {
  user: User | null
  session: Session | null
  loading: boolean
  configured: boolean
}

/**
 * Recovery from stale Vercel deploys that corrupt the Supabase auth client.
 * Phase 1: reload to release stuck Web Locks API lock.
 * Phase 2: clear auth tokens and reload (forces re-login).
 */
function recoverFromStaleDeploy() {
  if (typeof window === "undefined") return

  const GUARD_KEY = "scrpt-auth-recovery"
  const stored = sessionStorage.getItem(GUARD_KEY)
  const now = Date.now()

  let attempts = 0
  let lastTime = 0
  if (stored) {
    const parts = stored.split(",")
    attempts = parseInt(parts[0]) || 0
    lastTime = parseInt(parts[1]) || 0
  }

  if (now - lastTime > 60_000) attempts = 0
  if (attempts >= 2) return

  if (attempts >= 1) {
    const keysToRemove: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && key.includes("sb-") && key.includes("auth-token")) {
        keysToRemove.push(key)
      }
    }
    keysToRemove.forEach((k) => localStorage.removeItem(k))
  }

  sessionStorage.setItem(GUARD_KEY, `${attempts + 1},${now}`)
  window.location.reload()
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    session: null,
    loading: true,
    configured: false,
  })

  useEffect(() => {
    const supabase = getSupabaseBrowser()

    if (!supabase) {
      setState({ user: null, session: null, loading: false, configured: false })
      return
    }

    setState((prev) => ({ ...prev, configured: true }))

    supabase.auth
      .getSession()
      .then(({ data: { session }, error }) => {
        if (error) {
          if (
            error.message?.includes("Failed to fetch") ||
            error.message?.includes("timed out")
          ) {
            recoverFromStaleDeploy()
            return
          }
        }
        setState({
          user: session?.user || null,
          session,
          loading: false,
          configured: true,
        })
      })
      .catch(() => {
        recoverFromStaleDeploy()
      })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setState({
        user: session?.user || null,
        session,
        loading: false,
        configured: true,
      })
    })

    return () => subscription.unsubscribe()
  }, [])

  const signInWithEmail = useCallback(async (email: string, password: string) => {
    let supabase = getSupabaseBrowser()
    if (!supabase) return { error: "Supabase not configured" }

    try {
      const timeout = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("Sign-in timed out")), 12_000)
      )
      const result = await Promise.race([
        supabase.auth.signInWithPassword({ email, password }),
        timeout,
      ])
      return { error: result.error?.message || null }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sign-in failed"
      if (msg.includes("Failed to fetch") || msg.includes("timed out")) {
        resetSupabaseBrowser()
        supabase = getSupabaseBrowser()
        if (!supabase) return { error: "Supabase not configured" }
        try {
          const retry = await supabase.auth.signInWithPassword({ email, password })
          return { error: retry.error?.message || null }
        } catch {
          return { error: "Sign-in failed — please reload and try again" }
        }
      }
      return { error: msg }
    }
  }, [])

  const signUpWithEmail = useCallback(async (email: string, password: string) => {
    const supabase = getSupabaseBrowser()
    if (!supabase) return { error: "Supabase not configured" }

    try {
      const { error } = await supabase.auth.signUp({ email, password })
      return { error: error?.message || null }
    } catch (err: unknown) {
      return { error: err instanceof Error ? err.message : "Sign-up failed" }
    }
  }, [])

  const signInWithMagicLink = useCallback(async (email: string) => {
    const supabase = getSupabaseBrowser()
    if (!supabase) return { error: "Supabase not configured" }

    try {
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: { emailRedirectTo: window.location.origin },
      })
      return { error: error?.message || null }
    } catch (err: unknown) {
      return { error: err instanceof Error ? err.message : "Magic link failed" }
    }
  }, [])

  const signOut = useCallback(async () => {
    const supabase = getSupabaseBrowser()
    if (!supabase) return
    await supabase.auth.signOut()
  }, [])

  return {
    ...state,
    signInWithEmail,
    signUpWithEmail,
    signInWithMagicLink,
    signOut,
  }
}
