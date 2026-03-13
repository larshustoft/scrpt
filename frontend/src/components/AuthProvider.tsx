"use client"

import { createContext, useContext } from "react"
import { useAuth } from "@/hooks/useAuth"
import type { User, Session } from "@supabase/supabase-js"

interface AuthContextValue {
  user: User | null
  session: Session | null
  loading: boolean
  configured: boolean
  signInWithEmail: (email: string, password: string) => Promise<{ error: string | null }>
  signUpWithEmail: (email: string, password: string) => Promise<{ error: string | null }>
  signInWithMagicLink: (email: string) => Promise<{ error: string | null }>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  session: null,
  loading: true,
  configured: false,
  signInWithEmail: async () => ({ error: "Not configured" }),
  signUpWithEmail: async () => ({ error: "Not configured" }),
  signInWithMagicLink: async () => ({ error: "Not configured" }),
  signOut: async () => {},
})

export function useAuthContext() {
  return useContext(AuthContext)
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const auth = useAuth()

  return (
    <AuthContext.Provider value={auth}>
      {children}
    </AuthContext.Provider>
  )
}
