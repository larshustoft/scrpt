/**
 * Local house password — auth client for the installed edition.
 * Active when NEXT_PUBLIC_AUTH_MODE=local; the hosted product uses Supabase.
 */

const ENGINE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const TOKEN_KEY = "scrpt-local-token";

export const LOCAL_AUTH = process.env.NEXT_PUBLIC_AUTH_MODE === "local";

export function localToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(TOKEN_KEY) || "";
}

export async function localStatus(): Promise<{ passwordSet: boolean } | null> {
  try {
    const res = await fetch(`${ENGINE}/api/auth/local/status`);
    const d = await res.json();
    return { passwordSet: !!d.password_set };
  } catch {
    return null; // engine offline
  }
}

export async function localVerify(): Promise<boolean> {
  const token = localToken();
  if (!token) return false;
  try {
    const res = await fetch(`${ENGINE}/api/auth/local/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    const d = await res.json();
    return !!d.valid;
  } catch {
    return false;
  }
}

async function tokenCall(path: string, body: object): Promise<{ error: string | null }> {
  try {
    const res = await fetch(`${ENGINE}/api/auth/local/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = await res.json();
    if (!res.ok) return { error: d.detail || "Failed" };
    localStorage.setItem(TOKEN_KEY, d.token);
    return { error: null };
  } catch {
    return { error: "The engine is offline — start SCRPT's companion first." };
  }
}

export function localSetup(password: string) {
  return tokenCall("setup", { password });
}

export function localLogin(password: string) {
  return tokenCall("login", { password });
}

export function localChange(currentPassword: string, newPassword: string) {
  return tokenCall("change", { current_password: currentPassword, new_password: newPassword });
}

export function localSignOut() {
  if (typeof window !== "undefined") localStorage.removeItem(TOKEN_KEY);
}
