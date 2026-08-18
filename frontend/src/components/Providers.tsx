"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import { AuthProvider, useAuthContext } from "@/components/AuthProvider"
import { Navbar } from "@/components/Navbar"
import { BackOfficeNav } from "@/components/BackOfficeNav"

/** Route prefixes that live in the Back Office and share its tool menu. */
const BACK_OFFICE_PREFIXES = ["/office", "/shelf", "/queue", "/analytics", "/settings"]

/** Routes that don't require authentication */
const PUBLIC_PATHS = ["/", "/login"]
/** Route prefixes rendered bare: no auth, no navbar (headless print engine) */
const BARE_PREFIXES = ["/print"]

function isPublic(pathname: string) {
  return (
    PUBLIC_PATHS.includes(pathname) ||
    BARE_PREFIXES.some((p) => pathname.startsWith(p))
  )
}

/**
 * Auth gate — redirects unauthenticated users to /login.
 * Public paths are exempt.
 */
/** Local-dev auth bypass — set NEXT_PUBLIC_DEV_NO_AUTH=1 in .env.local only. */
const DEV_NO_AUTH = process.env.NEXT_PUBLIC_DEV_NO_AUTH === "1"

/**
 * Local house-password gate (installed edition, NEXT_PUBLIC_AUTH_MODE=local).
 * The engine holds the password hash; we hold an opaque session token.
 */
function LocalAuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const isPublicPage = isPublic(pathname) || DEV_NO_AUTH
  const isLoginPage = pathname === "/login"
  const [state, setState] = useState<"checking" | "in" | "out">("checking")

  useEffect(() => {
    let alive = true
    import("@/lib/local-auth").then(({ localVerify }) =>
      localVerify().then((ok) => { if (alive) setState(ok ? "in" : "out") }))
    return () => { alive = false }
  }, [pathname])

  useEffect(() => {
    if (state === "out" && !isPublicPage) router.replace("/login")
    if (state === "in" && isLoginPage) router.replace("/front")
  }, [state, isPublicPage, isLoginPage, router])

  if (!isPublicPage && state !== "in") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <span className="serif-display text-accent text-lg tracking-[0.3em] pulse-soft">
          SCRPT
        </span>
      </div>
    )
  }
  return <>{children}</>
}

function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading, configured } = useAuthContext()
  const pathname = usePathname()
  const router = useRouter()
  const isPublicPage = isPublic(pathname) || DEV_NO_AUTH
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

    // Logged in but on login page — into the study
    if (configured && user && isLoginPage) {
      router.replace("/front")
    }
  }, [user, loading, configured, isPublicPage, isLoginPage, router])

  if (loading && !isPublicPage) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <span className="serif-display text-accent text-lg tracking-[0.3em] pulse-soft">
          SCRPT
        </span>
      </div>
    )
  }

  if (!isPublicPage && !user && !loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <span className="serif-display text-accent text-lg tracking-[0.3em] pulse-soft">
          SCRPT
        </span>
      </div>
    )
  }

  return <>{children}</>
}

/**
 * Layout wrapper — public + print pages render full-bleed,
 * app pages get the SCRPT navbar.
 */
function LayoutShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const bare = isPublic(pathname)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    setVisible(false)
    const frame = requestAnimationFrame(() => setVisible(true))
    return () => cancelAnimationFrame(frame)
  }, [pathname])

  if (bare) {
    return <>{children}</>
  }

  const inBackOffice = BACK_OFFICE_PREFIXES.some((p) => pathname.startsWith(p))

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      {inBackOffice && <BackOfficeNav />}
      <main
        className="flex-1 transition-all duration-200"
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

const LOCAL_AUTH = process.env.NEXT_PUBLIC_AUTH_MODE === "local"

export function Providers({ children }: { children: React.ReactNode }) {
  if (LOCAL_AUTH) {
    return (
      <LocalAuthGate>
        <LayoutShell>
          {children}
        </LayoutShell>
      </LocalAuthGate>
    )
  }
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
