"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"

type Mode = "signin" | "signup" | "magic"

export default function LoginPage() {
  const router = useRouter()
  const { signInWithEmail, signUpWithEmail, signInWithMagicLink, configured } = useAuth()

  const [mode, setMode] = useState<Mode>("signin")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [magicLinkSent, setMagicLinkSent] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      if (mode === "magic") {
        const result = await signInWithMagicLink(email)
        if (result.error) {
          setError(result.error)
        } else {
          setMagicLinkSent(true)
        }
        return
      }

      const fn = mode === "signin" ? signInWithEmail : signUpWithEmail
      const result = await fn(email, password)

      if (result.error) {
        setError(result.error)
      } else {
        router.push("/")
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong")
    } finally {
      setLoading(false)
    }
  }

  // Supabase not configured — show setup instructions
  if (!configured) {
    return (
      <div className="min-h-screen bg-[#0F1219] flex items-center justify-center px-6">
        <div className="max-w-[480px] mx-auto">
          <div className="flex justify-center mb-8">
            <span className="text-[28px] font-semibold tracking-[0.12em] text-white">
              SCRPT
            </span>
          </div>

          <h1 className="text-xl font-semibold text-white text-center mb-2">
            Welcome to SCRPT
          </h1>
          <p className="text-sm text-slate-400 text-center mb-8">
            Set up a free cloud account to get started.
          </p>

          <div className="space-y-4 text-sm text-slate-400">
            {[
              {
                n: 1,
                title: "Create a Supabase project",
                desc: (
                  <>
                    Go to{" "}
                    <a href="https://supabase.com" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">
                      supabase.com
                    </a>{" "}
                    and create a free project.
                  </>
                ),
              },
              {
                n: 2,
                title: "Run the database schema",
                desc: (
                  <>
                    In your Supabase project, go to <strong className="text-slate-300">SQL Editor</strong> and run{" "}
                    <code className="font-mono bg-white/5 px-1.5 py-0.5 rounded text-[12px]">supabase/schema.sql</code>
                  </>
                ),
              },
              {
                n: 3,
                title: "Add your API keys",
                desc: (
                  <>
                    Copy{" "}
                    <code className="font-mono bg-white/5 px-1.5 py-0.5 rounded text-[12px]">.env.local.example</code>{" "}
                    to{" "}
                    <code className="font-mono bg-white/5 px-1.5 py-0.5 rounded text-[12px]">.env.local</code>{" "}
                    and paste your Project URL and anon key.
                  </>
                ),
              },
              {
                n: 4,
                title: "Restart the app",
                desc: (
                  <>
                    Stop and restart{" "}
                    <code className="font-mono bg-white/5 px-1.5 py-0.5 rounded text-[12px]">npm run dev</code>
                  </>
                ),
              },
            ].map((step) => (
              <div key={step.n} className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-500/10 text-blue-400 flex items-center justify-center text-[11px] font-medium">
                  {step.n}
                </span>
                <div>
                  <p className="text-white font-medium">{step.title}</p>
                  <p className="mt-1">{step.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  // Supabase configured — show sign-in / sign-up form
  return (
    <div className="min-h-screen bg-[#0F1219] flex items-center justify-center px-6">
      <div className="w-full max-w-[380px] mx-auto">
        <div className="flex justify-center mb-8">
          <span className="text-[28px] font-semibold tracking-[0.12em] text-white">
            SCRPT
          </span>
        </div>

        <h1 className="text-xl font-semibold text-white text-center mb-6">
          {mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Magic link"}
        </h1>

        {magicLinkSent ? (
          <div className="text-center space-y-4">
            <p className="text-sm text-slate-400">
              Check your inbox for a login link.
            </p>
            <button
              onClick={() => { setMagicLinkSent(false); setMode("signin") }}
              className="text-sm text-slate-500 hover:text-white transition-colors"
            >
              Back to sign in
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[13px] font-medium text-slate-300 mb-1.5">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                className="w-full rounded-lg border border-slate-700 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {mode !== "magic" && (
              <div>
                <label className="block text-[13px] font-medium text-slate-300 mb-1.5">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="w-full rounded-lg border border-slate-700 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
            )}

            {error && (
              <p className="text-sm text-red-400">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading
                ? "Loading..."
                : mode === "signin"
                ? "Sign in"
                : mode === "signup"
                ? "Create account"
                : "Send magic link"}
            </button>

            <div className="flex items-center gap-3 text-sm text-slate-600">
              <div className="flex-1 h-px bg-slate-800" />
              <span>or</span>
              <div className="flex-1 h-px bg-slate-800" />
            </div>

            <div className="flex justify-center gap-4 text-sm">
              {mode !== "signin" && (
                <button type="button" onClick={() => setMode("signin")} className="text-slate-500 hover:text-white transition-colors">
                  Sign in
                </button>
              )}
              {mode !== "signup" && (
                <button type="button" onClick={() => setMode("signup")} className="text-slate-500 hover:text-white transition-colors">
                  Create account
                </button>
              )}
              {mode !== "magic" && (
                <button type="button" onClick={() => setMode("magic")} className="text-slate-500 hover:text-white transition-colors">
                  Magic link
                </button>
              )}
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
