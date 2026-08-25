"use client";

import { useState } from "react";

/**
 * Pre-launch interest list.
 *
 * Deliberately one field. Every extra box on a pre-launch form costs
 * signups, and a name we would not use yet is not worth the loss.
 */
export function InterestForm() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = email.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) {
      setState("error"); setMsg("That doesn't look like an email address.");
      return;
    }
    setState("sending"); setMsg("");
    try {
      const r = await fetch("/api/interest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: value }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || "Failed");
      setState("done");
    } catch (err) {
      setState("error");
      setMsg(err instanceof Error ? err.message : "Something went wrong.");
    }
  };

  if (state === "done") {
    return (
      <div className="text-[15px] text-accent serif-display">
        Thank you — you&rsquo;re on the list.
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col items-center gap-3">
      <div className="flex flex-col sm:flex-row items-stretch gap-2 w-full max-w-[420px]">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => { setEmail(e.target.value); if (state === "error") setState("idle"); }}
          placeholder="you@example.com"
          aria-label="Email address"
          className="input-scrpt flex-1 text-[14px]"
          autoComplete="email"
        />
        <button type="submit" className="btn-brass px-6 text-[14px] whitespace-nowrap"
                disabled={state === "sending"}>
          {state === "sending" ? "Adding…" : "Notify me"}
        </button>
      </div>
      {state === "error" && (
        <div className="text-[12.5px]" style={{ color: "var(--status-red)" }}>{msg}</div>
      )}
    </form>
  );
}
