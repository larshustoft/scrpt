"use client";

/**
 * The Assistant — the front office's voice. Bronze orb bottom-right;
 * click to open the conversation. Voice in via the engine's local
 * speech-to-text, voice out via ElevenLabs (browser speech fallback).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { scrpt } from "@/lib/scrpt";

type OrbState = "idle" | "listening" | "thinking" | "speaking";
interface Msg { role: "user" | "assistant"; content: string }

const OPENERS = [
  "At your desk. What do you need?",
  "The office is listening.",
  "Ready when you are.",
];

export function AssistantDock() {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<OrbState>("idle");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [voiceOn, setVoiceOn] = useState(true);
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, state]);

  const speakReply = useCallback(async (text: string) => {
    if (!voiceOn) { setState("idle"); return; }
    setState("speaking");
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/assistant/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error("no elevenlabs");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      await new Promise<void>((resolve) => {
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = () => { URL.revokeObjectURL(url); resolve(); };
        audio.onerror = () => { URL.revokeObjectURL(url); resolve(); };
        audio.play().catch(() => resolve());
      });
    } catch {
      // fallback: browser speech synthesis
      await new Promise<void>((resolve) => {
        try {
          const u = new SpeechSynthesisUtterance(text);
          u.rate = 1.02;
          u.onend = () => resolve();
          u.onerror = () => resolve();
          speechSynthesis.speak(u);
        } catch { resolve(); }
      });
    } finally {
      audioRef.current = null;
      setState("idle");
    }
  }, [voiceOn]);

  const send = useCallback(async (text: string) => {
    const clean = text.trim();
    if (!clean || state === "thinking") return;
    setInput("");
    const nextMessages: Msg[] = [...messages, { role: "user" as const, content: clean }];
    setMessages(nextMessages);
    setState("thinking");
    try {
      const res = await fetch(`${scrpt.engineUrl}/api/scrpt/assistant/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nextMessages }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "The assistant is unavailable");
      }
      const { reply } = await res.json();
      setMessages((m) => [...m, { role: "assistant", content: reply }]);
      await speakReply(reply);
    } catch (e) {
      setMessages((m) => [...m, {
        role: "assistant",
        content: e instanceof Error && e.message.includes("engine")
          ? "The engine is offline — start the SCRPT companion and I'm back."
          : `Something went wrong: ${e instanceof Error ? e.message : e}`,
      }]);
      setState("idle");
    }
  }, [messages, speakReply, state]);

  // ── microphone (push-to-talk toggle) ──
  const stopRecording = useCallback(() => {
    recorderRef.current?.stop();
    setRecording(false);
  }, []);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data); };
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setState("thinking");
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        try {
          const form = new FormData();
          form.append("file", blob, "speech.webm");
          const res = await fetch(`${scrpt.engineUrl}/api/scrpt/assistant/listen`, {
            method: "POST", body: form,
          });
          const { text } = await res.json();
          if (text) {
            await send(text);
          } else {
            setState("idle");
          }
        } catch {
          setState("idle");
          setMessages((m) => [...m, { role: "assistant",
            content: "I couldn't hear that — the transcriber isn't available." }]);
        }
      };
      rec.start();
      recorderRef.current = rec;
      setRecording(true);
      setState("listening");
    } catch {
      setMessages((m) => [...m, { role: "assistant",
        content: "I need microphone access to listen — check System Settings → Privacy." }]);
    }
  }, [send]);

  const orbGlow = {
    idle: "0 0 40px rgba(201,164,92,0.35)",
    listening: "0 0 55px rgba(93,161,115,0.55)",
    thinking: "0 0 55px rgba(212,162,68,0.6)",
    speaking: "0 0 65px rgba(218,184,111,0.75)",
  }[state];

  return (
    <div className="absolute bottom-16 right-16 flex flex-col items-end gap-4 z-40">
      {/* conversation panel */}
      {open && (
        <div className="card fade-up flex flex-col"
             style={{ width: 360, maxHeight: 460, padding: 0 }}>
          <div className="flex items-center justify-between px-4 py-3"
               style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <div>
              <div className="text-[13px] font-semibold">Assistant</div>
              <div className="text-[10px] tracking-[0.14em] uppercase text-text-faint">
                {state === "idle" ? "at your service"
                 : state === "listening" ? "listening…"
                 : state === "thinking" ? "thinking…" : "speaking…"}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button title={voiceOn ? "Voice on" : "Voice off"}
                      onClick={() => { setVoiceOn(!voiceOn); audioRef.current?.pause(); }}
                      className={`text-[11px] transition-colors ${voiceOn ? "text-accent" : "text-text-faint"}`}>
                {voiceOn ? "VOICE ON" : "VOICE OFF"}
              </button>
              <button onClick={() => setOpen(false)}
                      className="text-text-tertiary hover:text-text-primary text-[16px] leading-none">
                ×
              </button>
            </div>
          </div>

          <div ref={threadRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3"
               style={{ minHeight: 160 }}>
            {messages.length === 0 && (
              <div className="text-[13px] text-text-tertiary italic">
                {OPENERS[Math.floor(Date.now() / 3600000) % OPENERS.length]} Ask about
                the catalog, production, royalties — or what to do next.
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`text-[13px] leading-relaxed ${
                m.role === "user" ? "text-right" : ""}`}>
                <span className={`inline-block px-3 py-2 rounded-[10px] max-w-[92%] text-left ${
                  m.role === "user" ? "" : ""}`}
                      style={{
                        background: m.role === "user" ? "var(--accent-subtle)" : "var(--surface-elevated)",
                        border: "1px solid var(--border-subtle)",
                      }}>
                  {m.content}
                </span>
              </div>
            ))}
            {state === "thinking" && (
              <div className="text-[12px] text-text-faint pulse-soft">…</div>
            )}
          </div>

          <div className="flex items-center gap-2 px-3 py-3"
               style={{ borderTop: "1px solid var(--border-subtle)" }}>
            <button
              onClick={recording ? stopRecording : startRecording}
              title={recording ? "Stop and send" : "Speak"}
              className="shrink-0 h-9 w-9 rounded-full flex items-center justify-center transition-all"
              style={{
                background: recording ? "var(--status-red)" : "var(--surface-elevated)",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <MicIcon active={recording} />
            </button>
            <input
              className="input-scrpt flex-1"
              placeholder={recording ? "Listening — click the mic to send" : "Ask the office…"}
              value={input}
              disabled={recording}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") send(input); }}
            />
            <button className="btn-brass px-3 py-2 text-[12px]" onClick={() => send(input)}
                    disabled={!input.trim() || state === "thinking"}>
              Send
            </button>
          </div>
        </div>
      )}

      {/* the orb */}
      <div className="flex flex-col items-center gap-2">
        <button
          aria-label="Assistant"
          onClick={() => setOpen(!open)}
          className="relative h-[64px] w-[64px] rounded-full transition-transform hover:scale-105"
          style={{
            background:
              "radial-gradient(circle at 35% 30%, rgba(218,184,111,0.95), rgba(138,109,53,0.9) 55%, rgba(23,18,5,0.95))",
            boxShadow: `${orbGlow}, 0 8px 24px rgba(0,0,0,0.6), inset 0 1px 2px rgba(255,255,255,0.35)`,
          }}
        >
          <span
            className={`absolute inset-[-10px] rounded-full ${state !== "idle" ? "" : "pulse-soft"}`}
            style={{
              boxShadow: orbGlow,
              animation: state === "speaking" ? "pulseSoft 0.6s ease-in-out infinite"
                : state === "thinking" ? "pulseSoft 1s ease-in-out infinite"
                : undefined,
            }}
          />
        </button>
        <span className="text-[10px] tracking-[0.26em] uppercase text-text-secondary select-none"
              style={{ textShadow: "0 1px 8px rgba(0,0,0,0.9)" }}>
          Assistant
        </span>
      </div>
    </div>
  );
}

function MicIcon({ active }: { active: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect x="6" y="1.5" width="4" height="8" rx="2"
            stroke={active ? "#fff" : "currentColor"} strokeWidth="1.4" />
      <path d="M3.5 8a4.5 4.5 0 0 0 9 0M8 12.5V15"
            stroke={active ? "#fff" : "currentColor"} strokeWidth="1.4"
            strokeLinecap="round" />
    </svg>
  );
}
