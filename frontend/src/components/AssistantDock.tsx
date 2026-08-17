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

      {/* the orb — a living presence, motion per state */}
      <div className="flex flex-col items-center gap-2">
        <button
          aria-label="Assistant"
          onClick={() => setOpen(!open)}
          className="relative h-[64px] w-[64px] rounded-full transition-transform hover:scale-105 overflow-hidden"
          style={{ boxShadow: `${orbGlow}, 0 8px 24px rgba(0,0,0,0.6)` }}
        >
          <OrbCanvas state={state} />
        </button>
        <span className="text-[10px] tracking-[0.26em] uppercase text-text-secondary select-none"
              style={{ textShadow: "0 1px 8px rgba(0,0,0,0.9)" }}>
          Assistant
        </span>
      </div>
    </div>
  );
}

/** The presence inside the orb — canvas animation keyed to the state. */
function OrbCanvas({ state }: { state: OrbState }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<OrbState>(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const size = 64;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    const ctx = canvas.getContext("2d")!;
    ctx.scale(dpr, dpr);
    const cx = size / 2, cy = size / 2;
    let raf = 0;

    const draw = (tMs: number) => {
      const t = tMs / 1000;
      const s = stateRef.current;
      ctx.clearRect(0, 0, size, size);

      // sphere base
      const base = ctx.createRadialGradient(cx * 0.7, cy * 0.6, 4, cx, cy, size * 0.55);
      base.addColorStop(0, "rgba(218,184,111,0.95)");
      base.addColorStop(0.55, "rgba(138,109,53,0.9)");
      base.addColorStop(1, "rgba(23,18,5,0.98)");
      ctx.fillStyle = base;
      ctx.beginPath();
      ctx.arc(cx, cy, size / 2, 0, Math.PI * 2);
      ctx.fill();

      // breathing core (always, stronger when engaged)
      const breathe = 0.5 + 0.5 * Math.sin(t * (s === "idle" ? 1.4 : 3));
      const coreR = s === "speaking"
        ? 9 + 7 * (0.4 + 0.6 * Math.abs(Math.sin(t * 7.3) * Math.sin(t * 4.1)))
        : 8 + 5 * breathe;
      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR * 1.9);
      core.addColorStop(0, "rgba(255,244,220,0.95)");
      core.addColorStop(0.45, "rgba(230,196,130,0.55)");
      core.addColorStop(1, "rgba(230,196,130,0)");
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(cx, cy, coreR * 1.9, 0, Math.PI * 2);
      ctx.fill();

      if (s === "listening") {
        // sonar rings drifting outward
        for (let i = 0; i < 3; i++) {
          const phase = (t * 0.9 + i / 3) % 1;
          ctx.strokeStyle = `rgba(240,220,180,${0.5 * (1 - phase)})`;
          ctx.lineWidth = 1.4;
          ctx.beginPath();
          ctx.arc(cx, cy, 6 + phase * 24, 0, Math.PI * 2);
          ctx.stroke();
        }
      } else if (s === "thinking") {
        // a spark orbiting the core
        for (let i = 0; i < 2; i++) {
          const a = t * 2.6 + i * Math.PI;
          const r = 18;
          const x = cx + r * Math.cos(a), y = cy + r * 0.55 * Math.sin(a);
          const g = ctx.createRadialGradient(x, y, 0, x, y, 5);
          g.addColorStop(0, "rgba(255,244,220,0.9)");
          g.addColorStop(1, "rgba(255,244,220,0)");
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(x, y, 5, 0, Math.PI * 2);
          ctx.fill();
        }
      } else if (s === "speaking") {
        // voice rings shimmering with pseudo-amplitude
        for (let i = 0; i < 2; i++) {
          const amp = Math.abs(Math.sin(t * (6 + i * 2.4) + i));
          ctx.strokeStyle = `rgba(245,228,190,${0.28 + 0.32 * amp})`;
          ctx.lineWidth = 1.6;
          ctx.beginPath();
          ctx.arc(cx, cy, 13 + i * 7 + amp * 3.5, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      // glass highlight
      const gloss = ctx.createRadialGradient(cx * 0.68, cy * 0.5, 1, cx * 0.68, cy * 0.5, 16);
      gloss.addColorStop(0, "rgba(255,255,255,0.34)");
      gloss.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = gloss;
      ctx.beginPath();
      ctx.arc(cx * 0.68, cy * 0.5, 16, 0, Math.PI * 2);
      ctx.fill();

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <canvas ref={canvasRef}
            style={{ width: 64, height: 64, display: "block", borderRadius: "50%" }} />
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
