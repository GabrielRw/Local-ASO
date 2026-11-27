import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";
import worker, { base32, type Env } from "./index";

// Shared with tests/test_licensing.py: the Python verifier accepts exactly this key.
const vector = JSON.parse(readFileSync(new URL("../../tests/fixtures/licence_vector.json", import.meta.url), "utf8"));

async function testPem(): Promise<string> {
  // PKCS#8 for an Ed25519 seed: fixed 16-byte prefix + 32-byte seed.
  const prefix = Uint8Array.from([0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20]);
  const seed = Uint8Array.from(Buffer.from(vector.seedHex, "hex"));
  const der = new Uint8Array([...prefix, ...seed]);
  await webcrypto.subtle.importKey("pkcs8", der, { name: "Ed25519" }, false, ["sign"]);
  return `-----BEGIN PRIVATE KEY-----\n${Buffer.from(der).toString("base64")}\n-----END PRIVATE KEY-----`;
}

async function env(): Promise<Env> {
  return { STRIPE_SECRET_KEY: "sk_test_x", STRIPE_PRICE_ID: "price_lifetime", LICENCE_PRIVATE_KEY: await testPem(), LICENCE_PUBLIC_KEY: vector.publicKey };
}

function stripe(session: object | null, status = 200) {
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    expect(String(input)).toMatch(/^https:\/\/api\.stripe\.com\/v1\/checkout\/sessions\/cs_test_a1B2c3D4\?expand/);
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer sk_test_x");
    return new Response(session ? JSON.stringify(session) : "{}", { status: session ? status : 404 });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

const paid = {
  id: "cs_test_a1B2c3D4",
  status: "complete",
  payment_status: "paid",
  created: Date.parse("2026-11-19T15:00:00Z") / 1000,
  customer_details: { email: "Buyer@Example.com" },
  line_items: { data: [{ price: { id: "price_lifetime" } }] },
};

const get = async (query: string) => worker.fetch(new Request(`https://licence.example/key${query}`), await env());

afterEach(() => vi.unstubAllGlobals());

describe("licence key page", () => {
  it("signs the same key the Python app verifies for a paid session", async () => {
    stripe(paid);
    const response = await get("?session_id=cs_test_a1B2c3D4");
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    const html = await response.text();
    expect(html).toContain(vector.key);
    expect(html).toContain("buyer@example.com");
  });

  it("refuses unpaid sessions and other products", async () => {
    stripe({ ...paid, payment_status: "unpaid" });
    expect((await get("?session_id=cs_test_a1B2c3D4")).status).toBe(402);
    stripe({ ...paid, line_items: { data: [{ price: { id: "price_other" } }] } });
    expect((await get("?session_id=cs_test_a1B2c3D4")).status).toBe(402);
    stripe(null);
    expect((await get("?session_id=cs_test_a1B2c3D4")).status).toBe(402);
  });

  it("rejects missing or malformed session ids without calling Stripe", async () => {
    const mock = stripe(paid);
    expect((await get("")).status).toBe(400);
    expect((await get("?session_id=../../v1/customers")).status).toBe(400);
    expect(mock).not.toHaveBeenCalled();
  });

  it("refuses to sign with a key that doesn't match the public key", async () => {
    stripe(paid);
    const wrong = { ...(await env()), LICENCE_PUBLIC_KEY: Buffer.alloc(32, 7).toString("base64") };
    await expect(worker.fetch(new Request("https://licence.example/key?session_id=cs_test_a1B2c3D4"), wrong)).rejects.toThrow(/does not match/);
  });

  it("base32-encodes like Python without padding", () => {
    expect(base32(new TextEncoder().encode("foobar"))).toBe("MZXW6YTBOI");
  });
});
