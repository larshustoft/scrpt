"use client";

import { useEffect, useState } from "react";
import { scrpt } from "@/lib/scrpt";

interface Settings {
  publisher_name?: string;
  copyright_holder?: string;
  website?: string;
  kdp_email?: string;
  writing_model?: string;
  elevenlabs_api_key?: string;
  elevenlabs_voice_id?: string;
  elevenlabs_voice_name?: string;
  [key: string]: unknown;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>({});
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);
  const [savedField, setSavedField] = useState("");

  useEffect(() => {
    (async () => {
      const online = await scrpt.health();
      setEngineOnline(online);
      if (online) {
        try {
          const res = await fetch(`${scrpt.engineUrl}/api/settings`);
          if (res.ok) setSettings(await res.json());
        } catch { /* ignore */ }
      }
    })();
  }, []);

  const save = async (key: string, value: string) => {
    setSettings((s) => ({ ...s, [key]: value }));
    try {
      await fetch(`${scrpt.engineUrl}/api/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: value }),
      });
      setSavedField(key);
      setTimeout(() => setSavedField(""), 1600);
    } catch { /* engine offline */ }
  };

  return (
    <div className="max-w-[700px] mx-auto px-8 py-12 fade-up">
      <h1 className="serif-display text-[32px] font-semibold">Settings</h1>
      <p className="text-[13px] text-text-secondary mt-1">
        Stored locally in the SCRPT engine on this machine. Each field saves on
        blur.
      </p>

      {engineOnline === false && (
        <div className="card mt-6" style={{ borderLeft: "3px solid var(--status-amber)" }}>
          <div className="text-[13px] text-text-secondary">
            The local engine is offline — settings can&apos;t be loaded or saved.
          </div>
        </div>
      )}

      <Section title="Publisher identity"
               sub="Used on title pages, copyright pages, and cover spines.">
        <Field label="Publisher / imprint name" k="publisher_name"
               placeholder="Midnight Quill Press"
               settings={settings} save={save} savedField={savedField} />
        <Field label="Copyright holder" k="copyright_holder"
               placeholder="Your company or personal name"
               settings={settings} save={save} savedField={savedField} />
        <Field label="Website" k="website" placeholder="https://…"
               settings={settings} save={save} savedField={savedField} />
      </Section>

      <AccountSection />

      <Section title="Amazon KDP"
               sub="For reference only. SCRPT never automates KDP logins and never stores your KDP password — uploads are manual (3/day cap), royalties come from report file imports.">
        <Field label="KDP account email" k="kdp_email" placeholder="you@example.com"
               settings={settings} save={save} savedField={savedField} />
      </Section>

      <Section title="Writing engine"
               sub="The Claude model that drafts manuscripts. The Anthropic API key lives in the engine's .env file.">
        <Field label="Model" k="writing_model" placeholder="claude-sonnet-5"
               settings={settings} save={save} savedField={savedField} />
        <CraftPlaybooks />
      </Section>

      <Section title="Audiobook narration"
               sub="ElevenLabs credentials for the narration pipeline. Pick a voice in your ElevenLabs voice library and paste its ID here.">
        <Field label="ElevenLabs API key" k="elevenlabs_api_key" secret
               placeholder="sk_…" settings={settings} save={save} savedField={savedField} />
        <Field label="Voice ID" k="elevenlabs_voice_id"
               placeholder="21m00Tcm4TlvDq8ikWAM"
               settings={settings} save={save} savedField={savedField} />
        <Field label="Voice name (for closing credits)" k="elevenlabs_voice_name"
               placeholder="e.g. Marcus Hale"
               settings={settings} save={save} savedField={savedField} />
      </Section>
    </div>
  );
}

function AccountSection() {
  const isLocal = process.env.NEXT_PUBLIC_AUTH_MODE === "local";
  const [current, setCurrent] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");

  useEffect(() => {
    if (isLocal) return;
    import("@/lib/supabase-browser").then(({ getSupabaseBrowser }) => {
      getSupabaseBrowser()?.auth.getUser()
        .then(({ data }) => setEmail(data.user?.email || ""));
    });
  }, [isLocal]);

  const change = async () => {
    setErr(""); setMsg("");
    if (pw.length < 8) { setErr("At least 8 characters."); return; }
    if (pw !== pw2) { setErr("Passwords don't match."); return; }
    setBusy(true);
    try {
      if (isLocal) {
        const { localChange } = await import("@/lib/local-auth");
        const { error } = await localChange(current, pw);
        if (error) { setErr(error); return; }
      } else {
        const { getSupabaseBrowser } = await import("@/lib/supabase-browser");
        const supabase = getSupabaseBrowser();
        if (!supabase) { setErr("Auth not configured."); return; }
        const { error } = await supabase.auth.updateUser({ password: pw });
        if (error) { setErr(error.message); return; }
      }
      setMsg("Password updated.");
      setCurrent(""); setPw(""); setPw2("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section title="Account"
             sub={isLocal
               ? "This installation is locked with a house password stored (hashed) on this Mac. Changing it signs out every other window."
               : `Signed in${email ? ` as ${email}` : ""}. Set a new password here any time — handy if you came in through an email link.`}>
      <div className="grid md:grid-cols-3 gap-4">
        {isLocal && (
          <div>
            <div className="label-scrpt">Current password</div>
            <input className="input-scrpt" type="password" value={current}
                   autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} />
          </div>
        )}
        <div>
          <div className="label-scrpt">New password</div>
          <input className="input-scrpt" type="password" value={pw}
                 autoComplete="new-password" onChange={(e) => setPw(e.target.value)} />
        </div>
        <div>
          <div className="label-scrpt">Repeat it</div>
          <input className="input-scrpt" type="password" value={pw2}
                 autoComplete="new-password" onChange={(e) => setPw2(e.target.value)} />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button className="btn-ghost text-[12px]" disabled={busy || !pw || (isLocal && !current)}
                onClick={change}>
          {busy ? "Updating…" : "Update password"}
        </button>
        {msg && <span className="text-[12px]" style={{ color: "var(--status-green)" }}>{msg}</span>}
        {err && <span className="text-[12px]" style={{ color: "var(--status-red)" }}>{err}</span>}
      </div>
    </Section>
  );
}

function CraftPlaybooks() {
  interface Playbook { family: string; exists: boolean; chars: number; regenerated: string }
  const [books, setBooks] = useState<Playbook[]>([]);
  const [busy, setBusy] = useState<Record<string, string>>({});

  const reload = () =>
    fetch(`${scrpt.engineUrl}/api/scrpt/craft`)
      .then((r) => r.json()).then((d) => setBooks(d.playbooks || []))
      .catch(() => {});
  useEffect(() => { reload(); }, []);

  const regenerate = async (family: string) => {
    setBusy((b) => ({ ...b, [family]: "Re-researching…" }));
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/craft/regenerate/${family}`,
        { method: "POST" });
      const { job_id } = await res.json();
      const { pollJob } = await import("@/lib/scrpt");
      const job = await pollJob(job_id, (j) =>
        setBusy((b) => ({ ...b, [family]: j.detail || "Working…" })));
      if (job.status !== "done") {
        setBusy((b) => ({ ...b, [family]: "Failed — old playbook kept" }));
        setTimeout(() => setBusy((b) => { const c = { ...b }; delete c[family]; return c; }), 4000);
        return;
      }
      reload();
      setBusy((b) => { const c = { ...b }; delete c[family]; return c; });
    } catch {
      setBusy((b) => { const c = { ...b }; delete c[family]; return c; });
    }
  };

  return (
    <div>
      <div className="label-scrpt">Craft playbooks</div>
      <p className="text-[12px] text-text-tertiary leading-relaxed">
        The house&apos;s genre craft standards, injected into every outline,
        chapter and revision prompt. After a model upgrade, regenerate them —
        the new model re-researches the craft and every future book is written
        to the better standard. The previous version is kept as a backup.
      </p>
      <div className="mt-3 space-y-2">
        {books.map((p) => (
          <div key={p.family} className="flex items-center gap-3 text-[13px]">
            <span className="capitalize w-[110px] font-medium">{p.family}</span>
            <span className="text-[11px] text-text-faint flex-1">
              {p.regenerated ? `regenerated ${p.regenerated}` : "original research edition"}
            </span>
            {busy[p.family] ? (
              <span className="text-[11px] text-text-tertiary pulse-soft">{busy[p.family]}</span>
            ) : (
              <button className="btn-ghost text-[11px]" onClick={() => regenerate(p.family)}>
                Regenerate with current model
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Section({ title, sub, children }: {
  title: string; sub: string; children: React.ReactNode;
}) {
  return (
    <div className="card mt-6">
      <div className="serif-display text-[17px] font-semibold">{title}</div>
      <p className="text-[12px] text-text-tertiary mt-1 leading-relaxed">{sub}</p>
      <div className="mt-4 space-y-4">{children}</div>
    </div>
  );
}

function Field({ label, k, settings, save, savedField, placeholder, secret = false }: {
  label: string; k: string;
  settings: Record<string, unknown>;
  save: (key: string, value: string) => void;
  savedField: string;
  placeholder?: string;
  secret?: boolean;
}) {
  const [value, setValue] = useState("");
  const [touched, setTouched] = useState(false);
  const stored = (settings[k] as string) || "";

  useEffect(() => {
    if (!touched) setValue(stored);
  }, [stored, touched]);

  return (
    <div>
      <div className="label-scrpt flex items-center gap-2">
        {label}
        {savedField === k && <span className="text-status-green normal-case tracking-normal">saved</span>}
      </div>
      <input
        className="input-scrpt"
        type={secret ? "password" : "text"}
        placeholder={placeholder}
        value={value}
        onChange={(e) => { setTouched(true); setValue(e.target.value); }}
        onBlur={() => { if (touched && value !== stored) save(k, value); }}
      />
    </div>
  );
}
