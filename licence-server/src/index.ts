// Stripe Checkout success page that hands out Local ASO licence keys.
//
// The Stripe Payment Link redirects buyers to /key?session_id={CHECKOUT_SESSION_ID}.
// This Worker asks Stripe whether that session is paid for the right price, then signs
// a licence key with Ed25519. Signatures are deterministic, so reopening the link shows
// the same key. There is no database; the app verifies keys offline.
//
// Key format (must match src/local_aso_tracker/licensing.py):
//   LASO1-<base32(payload)>.<base32(signature)>, base32 without padding,
//   payload = JSON with sorted keys and no spaces:
//   {"email":…,"id":<session id>,"issued":"YYYY-MM-DD","product":"desktop-lifetime","v":1}

export interface Env {
  STRIPE_SECRET_KEY: string;
  STRIPE_PRICE_ID: string;
  LICENCE_PRIVATE_KEY: string; // PKCS#8 PEM
  LICENCE_PUBLIC_KEY?: string; // raw, base64 (self-check)
}

const PRODUCT = "desktop-lifetime";
const SESSION_ID = /^cs_(test|live)_[A-Za-z0-9]{8,200}$/;
const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

export function base32(bytes: Uint8Array): string {
  let bits = 0;
  let value = 0;
  let out = "";
  for (const byte of bytes) {
    value = (value << 8) | byte;
    bits += 8;
    while (bits >= 5) {
      out += BASE32[(value >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  if (bits > 0) out += BASE32[(value << (5 - bits)) & 31];
  return out;
}

export function payloadBytes(id: string, email: string, issued: string): Uint8Array {
  // Keys in sorted order; JSON.stringify escapes like Python's json.dumps for these
  // ASCII-safe fields (Stripe emails and session ids).
  const json = JSON.stringify({ email, id, issued, product: PRODUCT, v: 1 });
  return new TextEncoder().encode(json);
}

function pemToDer(pem: string): ArrayBuffer {
  const body = pem.replace(/-----[^-]+-----/g, "").replace(/\s+/g, "");
  const raw = atob(body);
  const bytes = new Uint8Array(raw.length);
  for (let index = 0; index < raw.length; index++) bytes[index] = raw.charCodeAt(index);
  return bytes.buffer;
}

function fromBase64(text: string): Uint8Array {
  const raw = atob(text);
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

export async function mintKey(env: Env, id: string, email: string, issued: string): Promise<string> {
  const privateKey = await crypto.subtle.importKey("pkcs8", pemToDer(env.LICENCE_PRIVATE_KEY), { name: "Ed25519" }, false, ["sign"]);
  const payload = payloadBytes(id, email.trim().toLowerCase(), issued);
  const signature = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, privateKey, payload));
  if (env.LICENCE_PUBLIC_KEY) {
    const publicKey = await crypto.subtle.importKey("raw", fromBase64(env.LICENCE_PUBLIC_KEY), { name: "Ed25519" }, false, ["verify"]);
    if (!(await crypto.subtle.verify({ name: "Ed25519" }, publicKey, signature, payload))) {
      throw new Error("LICENCE_PRIVATE_KEY does not match LICENCE_PUBLIC_KEY");
    }
  }
  return `LASO1-${base32(payload)}.${base32(signature)}`;
}

interface StripeSession {
  id: string;
  status?: string;
  payment_status?: string;
  created?: number;
  customer_details?: { email?: string | null } | null;
  line_items?: { data?: { price?: { id?: string } | null }[] };
}

async function fetchSession(env: Env, id: string): Promise<StripeSession | null> {
  const url = `https://api.stripe.com/v1/checkout/sessions/${encodeURIComponent(id)}?expand[]=line_items`;
  const response = await fetch(url, { headers: { Authorization: `Bearer ${env.STRIPE_SECRET_KEY}` } });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Stripe returned HTTP ${response.status}`);
  return (await response.json()) as StripeSession;
}

const escapeHtml = (text: string) =>
  text.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] ?? char);

function page(status: number, title: string, body: string): Response {
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(title)} · Local ASO</title><meta name="robots" content="noindex">
<style>
:root{color-scheme:light dark;--bg:#fafafa;--fg:#0f172a;--muted:#64748b;--card:#fff;--line:#e2e8f0}
@media (prefers-color-scheme:dark){:root{--bg:#0b1120;--fg:#e2e8f0;--muted:#94a3b8;--card:#111827;--line:#1f2937}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,BlinkMacSystemFont,system-ui,sans-serif}
main{max-width:40rem;margin:0 auto;padding:3rem 1rem}h1{font-size:1.5rem;margin:0 0 .5rem}p{color:var(--muted)}
textarea{width:100%;box-sizing:border-box;min-height:7rem;padding:.75rem;border:1px solid var(--line);border-radius:.5rem;background:var(--card);color:var(--fg);font:13px/1.4 ui-monospace,Menlo,monospace;word-break:break-all}
ol{padding-left:1.25rem}li{margin:.25rem 0}
</style></head><body><main>${body}</main></body></html>`;
  return new Response(html, {
    status,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method !== "GET" || url.pathname !== "/key") {
      return page(404, "Not found", "<h1>Not found</h1>");
    }
    const id = url.searchParams.get("session_id") ?? "";
    if (!SESSION_ID.test(id)) {
      return page(400, "Missing order", "<h1>We couldn't find your order</h1><p>Open the link from your Stripe receipt or checkout page.</p>");
    }
    let session: StripeSession | null;
    try {
      session = await fetchSession(env, id);
    } catch {
      return page(502, "Try again", "<h1>Stripe didn't answer</h1><p>Reload this page in a minute. Your payment is safe.</p>");
    }
    const paid = session && session.status === "complete" && session.payment_status === "paid";
    const rightProduct = session?.line_items?.data?.some((item) => item.price?.id === env.STRIPE_PRICE_ID);
    const email = session?.customer_details?.email ?? "";
    if (!session || !paid || !rightProduct || !email) {
      return page(402, "Not paid", "<h1>This order isn't a completed Local ASO purchase</h1><p>If you just paid, reload in a moment.</p>");
    }
    const issued = new Date((session.created ?? 0) * 1000).toISOString().slice(0, 10);
    const key = await mintKey(env, session.id, email, issued);
    return page(
      200,
      "Your licence",
      `<h1>Thanks! Here is your Local ASO licence</h1>
<p>Licensed to ${escapeHtml(email.toLowerCase())}. Keep this page or the key below; the link keeps working.</p>
<textarea readonly aria-label="Licence key">${escapeHtml(key)}</textarea>
<ol><li>Open Local ASO on your Mac.</li><li>Choose <b>Settings → Licence…</b>.</li><li>Paste the key and choose <b>Activate</b>.</li></ol>`,
    );
  },
};
