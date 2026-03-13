"use client";

import { useState, useRef } from "react";
import { useSettings } from "@/hooks/useSettings";
import type { AuthorPenName } from "@/hooks/useSettings";
import { BOOK_TYPE_LABELS, BOOK_TYPE_SHORT } from "@/lib/types";
import type { BookType } from "@/lib/types";
import { IconPlus, IconTrash, IconCheck } from "@/components/icons";
import { useAuthContext } from "@/components/AuthProvider";

// ── Trim / Paper options (mirror backend config) ────────────────
const TRIM_OPTIONS = [
  { value: "5x8", label: '5" x 8"' },
  { value: "5.25x8", label: '5.25" x 8"' },
  { value: "5.5x8.5", label: '5.5" x 8.5"' },
  { value: "6x9", label: '6" x 9"' },
  { value: "7x10", label: '7" x 10"' },
  { value: "8x10", label: '8" x 10"' },
  { value: "8.5x11", label: '8.5" x 11" (US Letter)' },
];

const PAPER_OPTIONS = [
  { value: "white_bw", label: "White (B&W)" },
  { value: "cream_bw", label: "Cream (B&W)" },
  { value: "standard_color", label: "Standard Color" },
  { value: "premium_color", label: "Premium Color" },
];

// ── Reusable input classes ──────────────────────────────────────
const INPUT_CLS =
  "w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500";
const LABEL_CLS = "block text-[13px] font-medium text-slate-900 mb-1.5";
const HINT_CLS = "text-xs text-slate-400 mt-1";

// ── Logo Upload Component ──────────────────────────────────────
const MAX_LOGO_SIZE = 512;
const MAX_FILE_BYTES = 500_000; // 500 KB

function LogoUpload({
  label,
  hint,
  currentLogo,
  onUpload,
  onRemove,
  variant,
}: {
  label: string;
  hint: string;
  currentLogo: string | null;
  onUpload: (dataUrl: string) => void;
  onRemove: () => void;
  variant: "light" | "dark";
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);

    // Validate type
    if (!file.type.startsWith("image/png")) {
      setError("Only PNG files are accepted");
      return;
    }

    // Validate size
    if (file.size > MAX_FILE_BYTES) {
      setError("File must be under 500 KB");
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        // Validate dimensions
        if (img.width > MAX_LOGO_SIZE || img.height > MAX_LOGO_SIZE) {
          setError(`Image must be ${MAX_LOGO_SIZE}x${MAX_LOGO_SIZE}px or smaller (got ${img.width}x${img.height})`);
          return;
        }
        onUpload(reader.result as string);
      };
      img.onerror = () => setError("Failed to load image");
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);

    // Reset input so same file can be re-selected
    if (fileRef.current) fileRef.current.value = "";
  };

  const previewBg = variant === "dark" ? "bg-slate-800 border-slate-700" : "bg-white border-slate-200";
  const emptyText = variant === "dark" ? "text-slate-500" : "text-slate-400";

  return (
    <div>
      <label className={LABEL_CLS}>{label}</label>
      <div className="flex items-start gap-4">
        {/* Preview */}
        <div
          className={`w-20 h-20 rounded-lg border flex items-center justify-center overflow-hidden cursor-pointer hover:border-blue-400 transition-colors ${previewBg}`}
          onClick={() => fileRef.current?.click()}
        >
          {currentLogo ? (
            <img
              src={currentLogo}
              alt={label}
              className="w-full h-full object-contain p-1"
            />
          ) : (
            <span className={`text-[10px] text-center leading-tight px-1 ${emptyText}`}>
              No logo
            </span>
          )}
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
            >
              {currentLogo ? "Change" : "Upload"}
            </button>
            {currentLogo && (
              <button
                type="button"
                onClick={onRemove}
                className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-500 hover:bg-red-50 transition-colors"
              >
                Remove
              </button>
            )}
          </div>
          <p className={HINT_CLS}>
            {hint}
          </p>
          {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
        </div>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="image/png"
        onChange={handleFile}
        className="hidden"
      />
    </div>
  );
}

export default function SettingsPage() {
  const { allSettings, defaults, settings: userSettings, loading, saving, updateDefaults, updateSettings: updateUserSettings } = useSettings();
  const { user, signOut } = useAuthContext();
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Flat settings for backward-compatible accessors
  const settings = allSettings as Record<string, unknown>;

  // ── Helpers ──────────────────────────────────────────────────
  const set = (key: string, value: unknown) => {
    // Determine if key belongs to defaults or settings
    const defaultKeys = ["publisher_name", "publisher_logo", "publisher_logo_light", "copyright_holder", "website", "kdp_email", "default_trim_size", "default_paper_type", "default_description_template", "default_keywords", "default_categories"];
    if (defaultKeys.includes(key)) {
      updateDefaults({ [key]: value } as Record<string, unknown>);
    } else {
      updateUserSettings({ [key]: value } as Record<string, unknown>);
    }
  };

  const str = (key: string) => (settings?.[key] as string) || "";
  const arr = (key: string) => (settings?.[key] as string[]) || [];
  const penNames = () => (userSettings?.author_pen_names as AuthorPenName[]) || [];

  // ── Save (now auto-saves via debounce, but keep button for UX feedback)
  const handleSave = async () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  // ── Pen‑name management ──────────────────────────────────────
  const addPenName = () => {
    const current = penNames();
    updateUserSettings({ author_pen_names: [...current, { name: "", genres: [] }] });
  };

  const updatePenName = (index: number, field: "name" | "genres", value: unknown) => {
    const current = [...penNames()];
    current[index] = { ...current[index], [field]: value };
    updateUserSettings({ author_pen_names: current });
  };

  const removePenName = (index: number) => {
    updateUserSettings({ author_pen_names: penNames().filter((_, i) => i !== index) });
  };

  const toggleGenre = (penIndex: number, genre: string) => {
    const current = [...penNames()];
    const genres = current[penIndex].genres || [];
    if (genres.includes(genre)) {
      current[penIndex] = { ...current[penIndex], genres: genres.filter((g) => g !== genre) };
    } else {
      current[penIndex] = { ...current[penIndex], genres: [...genres, genre] };
    }
    updateUserSettings({ author_pen_names: current });
  };

  // ── Keywords as comma-separated input ────────────────────────
  const keywordsStr = arr("default_keywords").join(", ");
  const setKeywords = (raw: string) => {
    const kws = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    set("default_keywords", kws);
  };

  // ── Loading / Error states ───────────────────────────────────
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  if (error && !settings) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 text-[13px]">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-2xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="text-[13px] text-slate-500 mt-1">
          Configure your SCRPT publishing engine
        </p>
      </div>

      <div className="space-y-10">
        {/* ─── Publisher Identity ──────────────────────────────── */}
        <section>
          <h2 className="text-sm font-semibold text-slate-900 mb-1">
            Publisher Identity
          </h2>
          <p className={HINT_CLS + " mb-4"}>
            Standard information printed on every book
          </p>
          <div className="space-y-4">
            <div>
              <label className={LABEL_CLS}>Publisher Name</label>
              <input
                type="text"
                value={str("publisher_name")}
                onChange={(e) => set("publisher_name", e.target.value)}
                placeholder="e.g., Olive Tree Publishing"
                className={INPUT_CLS}
              />
              <p className={HINT_CLS}>Appears on title page and copyright page</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <LogoUpload
                label="Logo (for light backgrounds)"
                hint="Dark logo for interior pages and light covers. PNG, max 512×512px."
                variant="light"
                currentLogo={defaults?.publisher_logo || null}
                onUpload={(dataUrl) => updateDefaults({ publisher_logo: dataUrl })}
                onRemove={() => updateDefaults({ publisher_logo: null })}
              />
              <LogoUpload
                label="Logo (for dark backgrounds)"
                hint="Light/white logo for colored covers and dark surfaces. PNG, max 512×512px."
                variant="dark"
                currentLogo={defaults?.publisher_logo_light || null}
                onUpload={(dataUrl) => updateDefaults({ publisher_logo_light: dataUrl })}
                onRemove={() => updateDefaults({ publisher_logo_light: null })}
              />
            </div>
            <div>
              <label className={LABEL_CLS}>Copyright Holder</label>
              <input
                type="text"
                value={str("copyright_holder")}
                onChange={(e) => set("copyright_holder", e.target.value)}
                placeholder="e.g., Olive Tree Publishing LLC"
                className={INPUT_CLS}
              />
              <p className={HINT_CLS}>
                Legal entity for the copyright notice on each book
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={LABEL_CLS}>Website</label>
                <input
                  type="url"
                  value={str("website")}
                  onChange={(e) => set("website", e.target.value)}
                  placeholder="https://olivetreepublishing.com"
                  className={INPUT_CLS}
                />
              </div>
              <div>
                <label className={LABEL_CLS}>KDP Email</label>
                <input
                  type="email"
                  value={str("kdp_email")}
                  onChange={(e) => set("kdp_email", e.target.value)}
                  placeholder="you@example.com"
                  className={INPUT_CLS}
                />
              </div>
            </div>
          </div>
        </section>

        {/* ─── Author Pen Names ───────────────────────────────── */}
        <section>
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-sm font-semibold text-slate-900">
              Author Pen Names
            </h2>
            <button
              onClick={addPenName}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
            >
              <IconPlus className="w-3.5 h-3.5" />
              Add Name
            </button>
          </div>
          <p className={HINT_CLS + " mb-4"}>
            Different pen names for different book genres. Assign each name to the
            book types it should be used for.
          </p>

          {penNames().length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 py-8 text-center">
              <p className="text-sm text-slate-400">No pen names configured</p>
              <p className="text-xs text-slate-400 mt-1">
                Add author names and assign them to book genres
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {penNames().map((pen, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-slate-200 bg-white p-4"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex-1">
                      <input
                        type="text"
                        value={pen.name}
                        onChange={(e) => updatePenName(idx, "name", e.target.value)}
                        placeholder="Author name"
                        className={INPUT_CLS}
                      />
                    </div>
                    <button
                      onClick={() => removePenName(idx)}
                      className="mt-1.5 rounded p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                      title="Remove pen name"
                    >
                      <IconTrash className="w-4 h-4" />
                    </button>
                  </div>
                  <p className="text-xs text-slate-400 mt-3 mb-2">
                    Assigned genres
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {(Object.keys(BOOK_TYPE_LABELS) as BookType[]).map((bt) => {
                      const active = (pen.genres || []).includes(bt);
                      return (
                        <button
                          key={bt}
                          onClick={() => toggleGenre(idx, bt)}
                          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors ${
                            active
                              ? "bg-slate-900 text-white"
                              : "bg-slate-100 text-slate-500 hover:bg-slate-200"
                          }`}
                        >
                          <span className="font-mono text-[10px]">
                            {BOOK_TYPE_SHORT[bt]}
                          </span>
                          {BOOK_TYPE_LABELS[bt]}
                          {active && <IconCheck className="w-3 h-3 ml-0.5" />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ─── Book Defaults ──────────────────────────────────── */}
        <section>
          <h2 className="text-sm font-semibold text-slate-900 mb-1">
            Book Defaults
          </h2>
          <p className={HINT_CLS + " mb-4"}>
            Standard values pre-filled when creating a new book
          </p>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={LABEL_CLS}>Default Trim Size</label>
                <select
                  value={str("default_trim_size") || "8.5x11"}
                  onChange={(e) => set("default_trim_size", e.target.value)}
                  className={INPUT_CLS}
                >
                  {TRIM_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className={LABEL_CLS}>Default Paper Type</label>
                <select
                  value={str("default_paper_type") || "white_bw"}
                  onChange={(e) => set("default_paper_type", e.target.value)}
                  className={INPUT_CLS}
                >
                  {PAPER_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className={LABEL_CLS}>Default Description Template</label>
              <textarea
                value={str("default_description_template")}
                onChange={(e) =>
                  set("default_description_template", e.target.value)
                }
                placeholder="A standard description template used as a starting point for new books..."
                rows={4}
                className={INPUT_CLS + " resize-y"}
              />
              <p className={HINT_CLS}>
                Used as the base description when creating new books. Variables
                like {"{{title}}"}, {"{{author}}"}, {"{{page_count}}"} will be
                substituted.
              </p>
            </div>
            <div>
              <label className={LABEL_CLS}>Default Keywords</label>
              <input
                type="text"
                value={keywordsStr}
                onChange={(e) => setKeywords(e.target.value)}
                placeholder="puzzle books, large print, seniors, activity books"
                className={INPUT_CLS}
              />
              <p className={HINT_CLS}>
                Comma-separated. These are pre-filled for every new book (you can
                edit per book).
              </p>
            </div>
          </div>
        </section>

        {/* ─── Upload Settings ────────────────────────────────── */}
        <section>
          <h2 className="text-sm font-semibold text-slate-900 mb-4">
            Upload Settings
          </h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-[13px] font-medium text-slate-900">
                  Auto Upload
                </label>
                <p className="text-xs text-slate-400">
                  Automatically upload books that pass quality checks
                </p>
              </div>
              <button
                onClick={() => set("auto_upload", !settings?.auto_upload)}
                className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                  settings?.auto_upload ? "bg-blue-600" : "bg-slate-200"
                }`}
              >
                <span
                  className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform shadow-sm ${
                    settings?.auto_upload ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
            <div>
              <label className={LABEL_CLS}>Daily Upload Limit</label>
              <input
                type="number"
                value={(settings?.daily_upload_limit as number) || 3}
                onChange={(e) =>
                  set("daily_upload_limit", parseInt(e.target.value) || 3)
                }
                min={1}
                max={10}
                className="w-32 rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none"
              />
              <p className={HINT_CLS}>
                Amazon recommends max 3/day to avoid throttling
              </p>
            </div>
          </div>
        </section>

        {/* ─── AI Art Settings ────────────────────────────────── */}
        <section>
          <h2 className="text-sm font-semibold text-slate-900 mb-4">
            AI Art (ComfyUI)
          </h2>
          <div>
            <label className={LABEL_CLS}>ComfyUI Server URL</label>
            <input
              type="url"
              value={str("comfyui_url") || "http://127.0.0.1:8188"}
              onChange={(e) => set("comfyui_url", e.target.value)}
              className={INPUT_CLS}
            />
            <p className={HINT_CLS}>
              Local Stable Diffusion server for cover artwork generation
            </p>
          </div>
        </section>

        {/* ─── Save Bar ───────────────────────────────────────── */}
        <div className="flex items-center gap-3 pt-4 border-t border-slate-200">
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {saving ? "Saving..." : "Save Settings"}
          </button>
          {saved && (
            <span className="text-[13px] text-green-600 font-medium flex items-center gap-1">
              <IconCheck className="w-4 h-4" />
              Settings saved
            </span>
          )}
          {saving && (
            <span className="text-[11px] text-slate-400">Auto-saving...</span>
          )}
          {error && (
            <span className="text-[13px] text-red-500">{error}</span>
          )}
        </div>

        {/* ─── Account ───────────────────────────────────────── */}
        <section className="pt-6 border-t border-slate-200">
          <h2 className="text-sm font-semibold text-slate-900 mb-4">Account</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-700">{user?.email || "Not signed in"}</p>
              <p className="text-xs text-slate-400 mt-0.5">Signed in via Supabase Auth</p>
            </div>
            <button
              onClick={() => signOut()}
              className="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
            >
              Sign Out
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
