import { NextResponse } from "next/server";

/**
 * Pre-launch interest list.
 *
 * Vercel's filesystem is ephemeral, so an address written to disk here is
 * gone at the next deploy. The address is therefore forwarded to whatever
 * list you actually run, named by INTEREST_WEBHOOK.
 *
 * With no webhook configured the route still ACCEPTS the address and logs
 * it — a visitor should never see a form fail because of our configuration
 * — but the entry lives only in the deployment log, so set the variable
 * before the site goes anywhere near an audience.
 */
export async function POST(req: Request) {
  let email = "";
  try {
    ({ email } = await req.json());
  } catch {
    return NextResponse.json({ error: "Bad request" }, { status: 400 });
  }

  email = String(email || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || email.length > 254) {
    return NextResponse.json({ error: "That doesn't look like an email address." },
                             { status: 400 });
  }

  const hook = process.env.INTEREST_WEBHOOK;
  if (hook) {
    try {
      const r = await fetch(hook, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(process.env.INTEREST_WEBHOOK_TOKEN
            ? { Authorization: `Bearer ${process.env.INTEREST_WEBHOOK_TOKEN}` }
            : {}),
        },
        body: JSON.stringify({ email, source: "scrpt.ai", at: new Date().toISOString() }),
      });
      if (!r.ok) {
        console.error("interest webhook rejected", r.status, await r.text().catch(() => ""));
      }
    } catch (e) {
      console.error("interest webhook unreachable", e);
    }
  } else {
    console.warn("INTEREST_WEBHOOK is not set — signup only recorded here:", email);
  }

  return NextResponse.json({ ok: true });
}
