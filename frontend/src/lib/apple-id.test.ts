import { describe, expect, it } from "vitest";
import { parseAppleId } from "./apple-id";

describe("parseAppleId", () => {
  it("accepts a numeric ID or an App Store link", () => {
    expect(parseAppleId("6756268723")).toBe(6756268723);
    expect(parseAppleId("https://apps.apple.com/fr/app/spiritual-couple-i-feel-you/id6756268723")).toBe(6756268723);
    expect(parseAppleId("https://apps.apple.com/us/app/x/id123456789?l=fr")).toBe(123456789);
  });

  it("rejects other hosts and bundle IDs", () => {
    expect(parseAppleId("https://example.com/app/id123456789")).toBeNull();
    expect(parseAppleId("com.example.app")).toBeNull();
    expect(parseAppleId("")).toBeNull();
  });
});
