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

      <Section title="Amazon KDP"
               sub="For reference only. SCRPT never automates KDP logins and never stores your KDP password — uploads are manual (3/day cap), royalties come from report file imports.">
        <Field label="KDP account email" k="kdp_email" placeholder="you@example.com"
               settings={settings} save={save} savedField={savedField} />
      </Section>

      <Section title="Writing engine"
               sub="The Claude model that drafts manuscripts. The Anthropic API key lives in the engine's .env file.">
        <Field label="Model" k="writing_model" placeholder="claude-sonnet-5"
               settings={settings} save={save} savedField={savedField} />
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
