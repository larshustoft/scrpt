"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthContext } from "@/components/AuthProvider";
import { LOCAL_AUTH, localLogin, localSetup, localStatus } from "@/lib/local-auth";

type Mode = "signin" | "magic";

function Shell({ children, footer }: { children: React.ReactNode; footer?: React.ReactNode }) {
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
        <div className="card">{children}</div>
        {footer}
      </div>
    </div>
  );
}

function LocalLogin() {
  const router = useRouter();
  const [passwordSet, setPasswordSet] = useState<boolean | null>(null);
  const [engineDown, setEngineDown] = useState(false);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    localStatus().then((s) => {
      if (!s) setEngineDown(true);
      else setPasswordSet(s.passwordSet);
    });
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!passwordSet && pw !== pw2) { setError("The passwords don't match."); return; }
    setBusy(true);
    try {
      const { error } = passwordSet ? await localLogin(pw) : await localSetup(pw);
      if (error) setError(error);
      else router.replace("/front");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell footer={
      <div className="text-center mt-5 text-[12px] text-text-faint">
        This installation is locked with its house password.
      </div>
    }>
      {engineDown ? (
        <div className="text-[13px] text-text-secondary leading-relaxed">
          <div className="font-semibold text-text-primary mb-2">Engine offline</div>
          Start SCRPT&apos;s companion engine, then reload this page.
        </div>
      ) : passwordSet === null ? (
        <div className="text-[13px] text-text-tertiary pulse-soft">One moment…</div>
      ) : (
        <form onSubmit={submit}>
          {!passwordSet && (
            <p className="text-[12.5px] text-text-secondary leading-relaxed mb-4">
              First run — set the house password. It locks this installation;
              there are no accounts and nothing leaves this machine.
            </p>
          )}
          <div className="label-scrpt">{passwordSet ? "Password" : "Choose a password"}</div>
          <input className="input-scrpt" type="password" value={pw} required minLength={8}
                 autoComplete={passwordSet ? "current-password" : "new-password"}
                 autoFocus onChange={(e) => setPw(e.target.value)} />
          {!passwordSet && (
            <>
              <div className="label-scrpt mt-4">Repeat it</div>
              <input className="input-scrpt" type="password" value={pw2} required minLength={8}
                     autoComplete="new-password" onChange={(e) => setPw2(e.target.value)} />
            </>
          )}
          {error && <div className="text-[12px] mt-3" style={{ color: "var(--status-red)" }}>{error}</div>}
          <button type="submit" className="btn-brass w-full justify-center mt-5" disabled={busy}>
            {busy ? "One moment…" : passwordSet ? "Unlock SCRPT" : "Set password & enter"}
          </button>
        </form>
      )}
    </Shell>
  );
}

export default function LoginPage() {
  if (LOCAL_AUTH) return <LocalLogin />;
  return <SupabaseLogin />;
}

function SupabaseLogin() {
  const { signInWithEmail, signInWithMagicLink, configured } = useAuthContext();
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
                         autoComplete="current-password"
                         minLength={8}
                         onChange={(e) => setPassword(e.target.value)} />
                </>
              )}

              {error && <div className="text-[12px] mt-3" style={{ color: "var(--status-red)" }}>{error}</div>}
              {notice && <div className="text-[12px] mt-3" style={{ color: "var(--status-green)" }}>{notice}</div>}

              <button type="submit" className="btn-brass w-full justify-center mt-5" disabled={busy}>
                {busy ? "One moment…"
                  : mode === "signin" ? "Sign in"
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
            {mode !== "magic" && (
              <button onClick={() => setMode("magic")} className="hover:text-text-primary transition-colors">
                Email me a link
              </button>
            )}
            <span className="text-text-faint">Invite-only — accounts open at launch</span>
          </div>
        )}
      </div>
    </div>
  );
}
