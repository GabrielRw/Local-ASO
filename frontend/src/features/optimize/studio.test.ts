import { describe, expect, it } from "vitest";
import { connectionReady, selectableTargets } from "./studio";
import type { AppStoreConnectStatus } from "./types";

const base: AppStoreConnectStatus = {
  configured: true,
  ready: false,
  issuerId: "issuer",
  keyId: "KEY",
  keyPath: "~/AuthKey.p8",
  keyExists: true,
  keyModeSafe: true,
};

describe("connectionReady", () => {
  it("needs saved credentials and a private key file readable only by the user", () => {
    expect(connectionReady(undefined)).toBe(false);
    expect(connectionReady(base)).toBe(true);
    expect(connectionReady({ ...base, keyModeSafe: false })).toBe(false);
    expect(connectionReady({ ...base, configured: false, keyExists: false })).toBe(false);
    expect(connectionReady({ ...base, configured: false, ready: true })).toBe(true);
  });
});

describe("selectableTargets", () => {
  it("excludes the main storefront and storefronts sharing its locale", () => {
    const targets = selectableTargets({
      sourceLocale: "en-US",
      countries: [
        { code: "us", name: "United States", locale: "en-US", language: "English", isMain: true },
        { code: "ca", name: "Canada", locale: "en-US", language: "English", isMain: false },
        { code: "fr", name: "France", locale: "fr-FR", language: "French", isMain: false },
      ],
    });
    expect([...targets]).toEqual(["fr"]);
  });
});
