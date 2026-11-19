import { describe, expect, it } from "vitest";
import { APPLE_POPULARITY_FLOOR, countryFlag, demand, demandSortValue, rankLabel } from "./format";

describe("rankLabel", () => {
  it("shows the exact rank Apple returned", () => {
    expect(rankLabel({ rank: 12, found: true, resultLimit: 200 })).toBe("#12");
  });

  it("never invents a rank beyond Apple's result window", () => {
    expect(rankLabel({ rank: null, found: false, resultLimit: 200 })).toBe(">200");
    expect(rankLabel({ rank: null, found: false, resultLimit: 50 })).toBe(">50");
  });

  it("flags failed checks", () => {
    expect(rankLabel({ rank: null, found: false, status: "error" })).toBe("!");
  });
});

describe("demand", () => {
  it("shows Apple's floor as Low, not a number", () => {
    const value = demand({ popularity: APPLE_POPULARITY_FLOOR, popularityStatus: "measured" });
    expect(value.value).toBe("Low");
    expect(value.measured).toBe(true);
  });

  it("shows measured Apple popularity as-is", () => {
    expect(demand({ popularity: 41, popularityStatus: "measured" }).value).toBe("41");
  });

  it("marks local estimates with ~ and never as Apple data", () => {
    const value = demand({ popularityStatus: null, volumeEstimate: 48 });
    expect(value.value).toBe("~48");
    expect(value.measured).toBe(false);
    expect(value.title).toContain("not Apple search volume");
  });

  it("explains when Apple had no value", () => {
    expect(demand({ popularityStatus: "unavailable", volumeEstimate: 30 }).title).toContain(
      "Apple Ads returned no popularity",
    );
  });

  it("does not invent a value when nothing is known", () => {
    expect(demand({ popularityStatus: null, volumeEstimate: null }).value).toBe("—");
  });
});

describe("demandSortValue", () => {
  it("sorts measured popularity ahead of estimates on a different scale", () => {
    const measuredLow = demandSortValue({ popularity: 5, popularityStatus: "measured" })!;
    const estimatedHigh = demandSortValue({ volumeEstimate: 90, popularityStatus: null })!;
    expect(measuredLow).toBeGreaterThan(estimatedHigh);
  });
});

describe("countryFlag", () => {
  it("builds a regional-indicator flag", () => {
    expect(countryFlag("fr")).toBe("🇫🇷");
  });
});
