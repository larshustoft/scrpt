"use client";

import { useState } from "react";
import { useAuthContext } from "@/components/AuthProvider";

type Mode = "signin" | "signup" | "magic";

export default function LoginPage() {
  const { signInWithEmail, signUpWithEmail, signInWithMagicLink, configured } = useAuthContext();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "magic") {
        const { error } = await signInWithMagicLink(email);
        if (error) setError(error);
        else setNotice("Check your inbox — the sign-in link is on its way.");
      } else if (mode === "signup") {
        const { error } = await signUpWithEmail(email, password);
        if (error) setError(error);
        else setNotice("Account created. Check your inbox to confirm your email, then sign in.");
      } else {
        const { error } = await signInWithEmail(email, password);
        if (error) setError(error);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen relative flex items-center justify-center px-6">
      <div className="absolute inset-0 bg-cover"
           style={{ backgroundImage: "url(/hq-background.png)", backgroundPosition: "center 30%" }} />
      <div className="absolute inset-0" style={{ background: "rgba(14,12,9,0.72)" }} />

      <div className="relative w-full max-w-[400px]">
        <div className="flex justify-center">
          {/* the PNG carries internal padding — negative margins rebalance it */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo-transparent.png" alt="SCRPT" className="w-[260px] -mt-14 -mb-10"
               style={{ filter: "drop-shadow(0 2px 18px rgba(0,0,0,0.6))" }} />
        </div>

        <div className="card">
          {!configured ? (
            <div className="text-[13px] text-text-secondary leading-relaxed">
              <div className="font-semibold text-text-primary mb-2">Setup needed</div>
              Supabase credentials are missing. Copy{" "}
              <code className="text-accent">.env.local.example</code> to{" "}
              <code className="text-accent">.env.local</code> in the frontend
              folder and add your project&apos;s URL and anon key.
            </div>
          ) : (
            <form onSubmit={submit}>
              <div className="label-scrpt">Email</div>
              <input className="input-scrpt" type="email" value={email} required
                     autoComplete="email"
                     onChange={(e) => setEmail(e.target.value)} />
              {mode !== "magic" && (
                <>
                  <div className="label-scrpt mt-4">Password</div>
                  <input className="input-scrpt" type="password" value={password} required
                         autoComplete={mode === "signup" ? "new-password" : "current-password"}
                         minLength={8}
                         onChange={(e) => setPassword(e.target.value)} />
                </>
              )}

              {error && <div className="text-[12px] mt-3" style={{ color: "var(--status-red)" }}>{error}</div>}
              {notice && <div className="text-[12px] mt-3" style={{ color: "var(--status-green)" }}>{notice}</div>}

              <button type="submit" className="btn-brass w-full justify-center mt-5" disabled={busy}>
                {busy ? "One moment…"
                  : mode === "signin" ? "Sign in"
                  : mode === "signup" ? "Create account"
                  : "Send sign-in link"}
              </button>
            </form>
          )}
        </div>

        {configured && (
          <div className="flex justify-center gap-5 mt-5 text-[12px] text-text-tertiary">
            {mode !== "signin" && (
              <button onClick={() => setMode("signin")} className="hover:text-text-primary transition-colors">
                Sign in
              </button>
            )}
            {mode !== "signup" && (
              <button onClick={() => setMode("signup")} className="hover:text-text-primary transition-colors">
                Create account
              </button>
            )}
            {mode !== "magic" && (
              <button onClick={() => setMode("magic")} className="hover:text-text-primary transition-colors">
                Email me a link
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
