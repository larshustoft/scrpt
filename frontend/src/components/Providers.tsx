"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import { AuthProvider, useAuthContext } from "@/components/AuthProvider"
import { Sidebar } from "@/components/sidebar"

/** Routes that don't require authentication */
const PUBLIC_PATHS = ["/login"]

/**
 * Auth gate — redirects unauthenticated users to /login.
 * Public paths are exempt.
 */
function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading, configured } = useAuthContext()
  const pathname = usePathname()
  const router = useRouter()
  const isPublicPage = PUBLIC_PATHS.includes(pathname)
  const isLoginPage = pathname === "/login"

  useEffect(() => {
    if (loading) return

    // Not authenticated — redirect to login (only from protected pages)
    if (configured && !user && !isPublicPage) {
      router.replace("/login")
    }

    // Not configured — redirect to login (shows setup guide)
    if (!configured && !isPublicPage) {
      router.replace("/login")
    }

    // Logged in but on login page — redirect to dashboard
    if (configured && user && isLoginPage) {
      router.replace("/")
    }
  }, [user, loading, configured, isPublicPage, isLoginPage, router])

  // While auth is resolving on protected pages, show loading
  if (loading && !isPublicPage) {
    return (
      <div className="min-h-screen bg-[#0F1219] flex items-center justify-center">
        <div className="text-slate-500 text-sm animate-pulse">Loading...</div>
      </div>
    )
  }

  // Not authenticated and on a protected page — wait for redirect
  if (!isPublicPage && !user && !loading) {
    return (
      <div className="min-h-screen bg-[#0F1219] flex items-center justify-center">
        <div className="text-slate-500 text-sm animate-pulse">Loading...</div>
      </div>
    )
  }

  return <>{children}</>
}

/**
 * Layout wrapper — login page renders full-page, all other pages get sidebar.
 */
function LayoutShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isPublicPage = PUBLIC_PATHS.includes(pathname)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    setVisible(false)
    const frame = requestAnimationFrame(() => setVisible(true))
    return () => cancelAnimationFrame(frame)
  }, [pathname])

  if (isPublicPage) {
    return <>{children}</>
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main
        className="flex-1 overflow-auto transition-all duration-200"
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? "translateY(0)" : "translateY(6px)",
        }}
      >
        {children}
      </main>
    </div>
  )
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthGate>
        <LayoutShell>
          {children}
        </LayoutShell>
      </AuthGate>
    </AuthProvider>
  )
}
