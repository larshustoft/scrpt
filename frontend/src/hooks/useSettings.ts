"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { getSupabaseBrowser } from "@/lib/supabase-browser"
import { useAuthContext } from "@/components/AuthProvider"

export interface AuthorPenName {
  name: string
  genres: string[]
}

export interface UserDefaults {
  publisher_name: string
  publisher_logo: string | null  // base64 data URL (PNG, max 512x512) — dark logo for light backgrounds
  publisher_logo_light: string | null  // base64 data URL (PNG, max 512x512) — light logo for dark backgrounds
  copyright_holder: string
  website: string
  kdp_email: string
  default_trim_size: string
  default_paper_type: string
  default_description_template: string
  default_keywords: string[]
  default_categories: string[]
}

export interface UserSettings {
  author_pen_names: AuthorPenName[]
  comfyui_url: string
  auto_upload: boolean
  daily_upload_limit: number
}

const CACHE_KEY = "scrpt-settings"

const DEFAULT_DEFAULTS: UserDefaults = {
  publisher_name: "",
  publisher_logo: null,
  publisher_logo_light: null,
  copyright_holder: "",
  website: "",
  kdp_email: "",
  default_trim_size: "8.5x11",
  default_paper_type: "white_bw",
  default_description_template: "",
  default_keywords: [],
  default_categories: [],
}

const DEFAULT_SETTINGS: UserSettings = {
  author_pen_names: [],
  comfyui_url: "",
  auto_upload: false,
  daily_upload_limit: 5,
}

function loadCache(): { defaults: UserDefaults; settings: UserSettings } | null {
  if (typeof window === "undefined") return null
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveCache(defaults: UserDefaults, settings: UserSettings) {
  if (typeof window === "undefined") return
  try {
    // Strip logos from cache to save space
    const stripped = {
      ...defaults,
      publisher_logo: defaults.publisher_logo ? "_hasLogo" : null,
      publisher_logo_light: defaults.publisher_logo_light ? "_hasLogo" : null,
    }
    localStorage.setItem(CACHE_KEY, JSON.stringify({ defaults: stripped, settings }))
  } catch {
    // silently ignore
  }
}

export function useSettings() {
  const { user } = useAuthContext()
  const cached = loadCache()
  const [defaults, setDefaults] = useState<UserDefaults>(cached?.defaults || DEFAULT_DEFAULTS)
  const [settings, setSettings] = useState<UserSettings>(cached?.settings || DEFAULT_SETTINGS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const fetchedRef = useRef(false)
  const saveTimerRef = useRef<NodeJS.Timeout | null>(null)

  // Fetch from Supabase
  const fetchSettings = useCallback(async () => {
    const supabase = getSupabaseBrowser()
    if (!supabase || !user) return

    try {
      const { data, error } = await supabase
        .from("user_settings")
        .select("*")
        .eq("user_id", user.id)
        .single()

      if (error) {
        // No row yet — create default
        if (error.code === "PGRST116") {
          await supabase.from("user_settings").insert({
            user_id: user.id,
            defaults: DEFAULT_DEFAULTS,
            settings: DEFAULT_SETTINGS,
          })
          return
        }
        throw new Error(error.message)
      }

      const d = { ...DEFAULT_DEFAULTS, ...(data.defaults as Record<string, unknown>) } as UserDefaults
      const s = { ...DEFAULT_SETTINGS, ...(data.settings as Record<string, unknown>) } as UserSettings
      setDefaults(d)
      setSettings(s)
      saveCache(d, s)
    } catch {
      // Use defaults
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    if (!user || fetchedRef.current) return
    fetchedRef.current = true
    fetchSettings()
  }, [user, fetchSettings])

  // Save to Supabase (debounced)
  const persist = useCallback(
    (newDefaults: UserDefaults, newSettings: UserSettings) => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
      saveTimerRef.current = setTimeout(async () => {
        const supabase = getSupabaseBrowser()
        if (!supabase || !user) return

        setSaving(true)
        try {
          await supabase
            .from("user_settings")
            .update({
              defaults: newDefaults,
              settings: newSettings,
            })
            .eq("user_id", user.id)
        } catch {
          // silently ignore
        } finally {
          setSaving(false)
        }
      }, 1000)
    },
    [user]
  )

  // Update defaults
  const updateDefaults = useCallback(
    (patch: Partial<UserDefaults>) => {
      setDefaults((prev) => {
        const next = { ...prev, ...patch }
        saveCache(next, settings)
        persist(next, settings)
        return next
      })
    },
    [settings, persist]
  )

  // Update settings
  const updateSettings = useCallback(
    (patch: Partial<UserSettings>) => {
      setSettings((prev) => {
        const next = { ...prev, ...patch }
        saveCache(defaults, next)
        persist(defaults, next)
        return next
      })
    },
    [defaults, persist]
  )

  // Get all settings as a flat record (for backward compatibility)
  const allSettings: Record<string, unknown> = {
    ...defaults,
    ...settings,
  }

  return {
    defaults,
    settings,
    allSettings,
    loading,
    saving,
    updateDefaults,
    updateSettings,
    fetchSettings,
  }
}
