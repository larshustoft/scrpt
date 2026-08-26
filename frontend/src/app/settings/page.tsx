"use client";

import { useEffect, useState } from "react";
import { scrpt } from "@/lib/scrpt";
import { OFFICES, rememberOffice, type OfficeKey } from "@/lib/background";

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

      <Section title="The office"
               sub="The room behind SCRPT — painted across the front desk and the sign-in screen. Same publisher, same mark on the wall; choose the window.">
        <div className="flex gap-3">
          {(Object.entries(OFFICES) as [OfficeKey, { label: string; src: string }][]).map(([k, o]) => {
            const active = ((settings.office_background as string) || "newyork") === k;
            return (
              <button key={k}
                      onClick={() => { save("office_background", k); rememberOffice(k); }}
                      className="text-left group" style={{ width: 220 }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={o.src} alt={o.label}
                     className="w-full rounded object-cover transition-opacity group-hover:opacity-90"
                     style={{ aspectRatio: "16/9",
                              border: active ? "2px solid var(--accent)" : "1px solid var(--line)" }} />
                <div className="text-[12px] mt-1.5"
                     style={{ color: active ? "var(--accent)" : "var(--text-secondary)" }}>
                  {o.label}{active ? " — chosen" : ""}
                </div>
              </button>
            );
          })}
        </div>
      </Section>

      <AccountSection />

      <Section title="Amazon KDP"
               sub="For reference only. SCRPT never automates KDP logins and never stores your KDP password — uploads are manual (3/day cap), royalties come from report file imports.">
        <Field label="KDP account email" k="kdp_email" placeholder="you@example.com"
               settings={settings} save={save} savedField={savedField} />
      </Section>

      <ModelSection settings={settings} save={save} />

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

      <IdentSection />
      <AssistantVoiceSection />
    </div>
  );
}

/** The writing engine's models, listed live from Anthropic so a model
 *  published tomorrow is selectable tomorrow. Three jobs, three choices:
 *  the one that writes the books, the one that does mechanical passes, and
 *  the one the assistant talks with (which wants speed over depth). */
function ModelSection({ settings, save }: {
  settings: Settings; save: (k: string, v: string) => Promise<void>;
}) {
  const [models, setModels] = useState<{ id: string; name: string }[]>([]);
  const [cur, setCur] = useState({ writing: "", mechanical: "", assistant: "" });
  const [note, setNote] = useState("Loading models…");

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${scrpt.engineUrl}/api/scrpt/models`);
        if (!r.ok) { setNote(`Could not list models (${r.status}).`); return; }
        const d = await r.json();
        setModels(d.models || []);
        setCur({ writing: d.current, mechanical: d.mechanical, assistant: d.assistant });
        setNote(d.error ? `Live list unavailable: ${d.error}` : "");
      } catch { setNote("The engine is offline — start the SCRPT companion."); }
    })();
  }, []);

  const pick = async (key: string, field: "writing" | "mechanical" | "assistant", v: string) => {
    setCur((c) => ({ ...c, [field]: v }));
    await save(key, v);
  };

  const Row = ({ label, hint, field, k }: {
    label: string; hint: string; field: "writing" | "mechanical" | "assistant"; k: string;
  }) => (
    <div className="flex items-baseline justify-between gap-4 py-2">
      <div className="min-w-0">
        <div className="text-[13px]">{label}</div>
        <div className="text-[11px] text-text-tertiary">{hint}</div>
      </div>
      <select value={cur[field]} disabled={!models.length}
              onChange={(e) => pick(k, field, e.target.value)}
              className="rounded-[6px] border border-border-subtle bg-transparent px-2 py-1.5 text-[12.5px] shrink-0"
              style={{ minWidth: 210 }}>
        {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
      </select>
    </div>
  );

  return (
    <Section title="Writing engine"
             sub="Which Claude model does which job. The list comes from Anthropic, so new models appear here as they are published. The API key lives in the engine's .env file.">
      {note && <div className="text-[11px] text-text-faint mb-1">{note}</div>}
      <Row label="Manuscripts" k="writing_model" field="writing"
           hint="Drafts the books — the one that decides how good they are." />
      <Row label="Mechanical passes" k="mechanical_model" field="mechanical"
           hint="Continuity, length repair, listing copy. Cheaper is fine here." />
      <Row label="Assistant" k="assistant_model" field="assistant"
           hint="The front-office conversation. Favour speed — it is spoken aloud." />
    </Section>
  );
}

/** The house ident — the audio logo every audiobook opens on, named after
 *  the Copyright holder. Built automatically; remade on demand. */
function IdentSection() {
  const [st, setSt] = useState<{
    house: string; line: string; voice_id: string; voice_name: string;
    exists: boolean; current: boolean; seconds: number | null; url: string | null;
    voices: { id: string; name: string; blurb: string }[];
  } | null>(null);
  const [line, setLine] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = async () => {
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/audiobook/ident`);
      if (!r.ok) return;
      const d = await r.json();
      setSt(d); setLine(d.line || "");
    } catch { /* engine offline */ }
  };
  useEffect(() => { load(); }, []);

  const rebuild = async (voice_id?: string) => {
    setBusy(true); setMsg("Recording the ident…");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/audiobook/ident`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ line, voice_id, force: true }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Could not build the ident");
      setMsg(`Ident ready — ${d.seconds}s${d.music ? "" : " (no music bed)"}`);
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally { setBusy(false); }
  };

  if (!st) return null;
  return (
    <Section title="Audiobook ident"
             sub="The short audio logo every audiobook opens on, as track 01 — and at the top of “Hear the opening”. Named after the Copyright holder above.">
      {!st.house && (
        <div className="text-[12px] text-text-faint">
          Set the Copyright holder above and the ident writes itself.
        </div>
      )}
      {st.house && (
        <>
          <div className="text-[11px] text-text-tertiary mb-1">The line</div>
          <input value={line} onChange={(e) => setLine(e.target.value)}
                 className="w-full rounded-[6px] border border-border-subtle bg-transparent px-3 py-1.5 text-[12.5px]" />
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            {st.url && (
              <audio controls src={`${scrpt.engineUrl}${st.url}`} style={{ height: 32 }} />
            )}
            <button className="btn-brass text-[12px]" disabled={busy}
                    onClick={() => rebuild()}>
              {busy ? "Recording…" : st.exists ? "Remake the ident" : "Make the ident"}
            </button>
            {!st.current && st.exists && (
              <span className="text-[11px]" style={{ color: "var(--status-amber)" }}>
                Out of date — the name, line or voice changed
              </span>
            )}
          </div>
          <div className="text-[11px] text-text-tertiary mt-3 mb-1">Voice</div>
          <div className="flex flex-col gap-1.5">
            {st.voices.map((v) => (
              <div key={v.id}
                   className="flex items-center gap-3 rounded-[6px] px-3 py-2"
                   style={{ border: `1px solid ${st.voice_id === v.id ? "var(--accent)" : "var(--border-subtle)"}` }}>
                <div className="flex-1">
                  <div className="text-[13px] font-semibold">
                    {v.name}
                    {st.voice_id === v.id && <span className="text-accent text-[11px] ml-2">SELECTED</span>}
                  </div>
                  <div className="text-[11px] text-text-tertiary">{v.blurb}</div>
                </div>
                <button className="btn-ghost text-[11px] shrink-0" disabled={busy}
                        onClick={() => rebuild(v.id)}>
                  {st.voice_id === v.id ? "Re-record" : "Use this voice"}
                </button>
              </div>
            ))}
          </div>
          {msg && <div className="text-[11px] text-text-faint mt-2">{msg}</div>}
        </>
      )}
    </Section>
  );
}

/** The assistant's own voice — a colleague in the room, not a narrator.
 *  Audition each one, then pick. Separate from the audiobook voice. */
function AssistantVoiceSection() {
  const [voices, setVoices] = useState<{ id: string; name: string; blurb: string }[]>([]);
  const [current, setCurrent] = useState("");
  const [playing, setPlaying] = useState("");
  const [msg, setMsg] = useState("");
  const [why, setWhy] = useState("Loading…");

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${scrpt.engineUrl}/api/scrpt/assistant/voice-options`);
        if (r.status === 404) {
          setWhy("The engine is running an older build — restart the SCRPT engine to load the voice picker.");
          return;
        }
        if (!r.ok) { setWhy(`The engine returned ${r.status}.`); return; }
        const d = await r.json();
        setVoices(d.voices || []);
        setCurrent(d.current || "");
        if (!(d.voices || []).length) setWhy("No voices configured.");
      } catch {
        setWhy("The engine is offline — start the SCRPT companion.");
      }
    })();
  }, []);

  const audition = async (id: string) => {
    setPlaying(id); setMsg("");
    try {
      const r = await fetch(`${scrpt.engineUrl}/api/scrpt/assistant/speak`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: "Morning. Two books cleared the desk overnight, and the trailer for Point Dume is ready when you are.",
          voice_id: id,
        }),
      });
      if (!r.ok) throw new Error("Could not play that voice");
      const url = URL.createObjectURL(await r.blob());
      const a = new Audio(url);
      a.onended = () => { URL.revokeObjectURL(url); setPlaying(""); };
      a.onerror = () => { URL.revokeObjectURL(url); setPlaying(""); };
      await a.play();
    } catch (e) {
      setPlaying("");
      setMsg(e instanceof Error ? e.message : "Could not play that voice");
    }
  };

  const choose = async (id: string) => {
    setCurrent(id);
    try {
      await fetch(`${scrpt.engineUrl}/api/scrpt/assistant/voice`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: id }),
      });
      setMsg("Voice saved");
      setTimeout(() => setMsg(""), 1600);
    } catch { setMsg("Could not save"); }
  };

  return (
    <Section title="Assistant voice"
             sub="How the assistant sounds when it speaks to you — younger and conversational, not a movie narrator. Hold F19 anywhere to talk to it; tap F19 to open it and keep listening.">
      {voices.length === 0 && (
        <div className="text-[12px] text-text-faint">{why}</div>
      )}
      <div className="flex flex-col gap-1.5">
        {voices.map((v) => (
          <div key={v.id}
               className="flex items-center gap-3 rounded-[6px] px-3 py-2"
               style={{ border: `1px solid ${current === v.id ? "var(--accent)" : "var(--border-subtle)"}` }}>
            <button onClick={() => choose(v.id)} className="flex-1 text-left">
              <div className="text-[13px] font-semibold">
                {v.name}
                {current === v.id && <span className="text-accent text-[11px] ml-2">SELECTED</span>}
              </div>
              <div className="text-[11px] text-text-tertiary">{v.blurb}</div>
            </button>
            <button className="btn-ghost text-[11px] shrink-0"
                    disabled={playing === v.id}
                    onClick={() => audition(v.id)}>
              {playing === v.id ? "Playing…" : "Hear it"}
            </button>
          </div>
        ))}
      </div>
      {msg && <div className="text-[11px] text-text-faint mt-2">{msg}</div>}
    </Section>
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
