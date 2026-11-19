import { describe, expect, it } from "vitest";
import type { PaidKeyword, PaidKeywordCountry } from "./api";
import { asoRankView, nextSort, paidRowsSummary, sortPaidKeywords, visiblePaidGroups } from "./keywords";

function row(text: string, patch: Partial<PaidKeyword> = {}): PaidKeyword {
  return {
    country: "US",
    countryName: "United States",
    text,
    matchTypes: ["EXACT"],
    status: "ENABLED",
    campaignStatus: "ENABLED",
    campaignCount: 1,
    campaigns: ["Brand"],
    bidMin: "1.00",
    bidMax: "1.00",
    currency: "USD",
    metrics: { spend: "0", currency: "USD", impressions: 0, taps: 0, tapInstalls: 0, totalInstalls: 0, cpt: null },
    asoRank: null,
    asoFound: false,
    asoChecked: false,
    asoLimit: null,
    asoError: false,
    ...patch,
  };
}

const names = (rows: PaidKeyword[]) => rows.map((item) => item.text);

describe("sortPaidKeywords", () => {
  it("sorts ASO rank ascending with >limit after exact ranks and unchecked last", () => {
    const rows = [
      row("unchecked"),
      row("outside", { asoChecked: true, asoLimit: 200 }),
      row("ten", { asoFound: true, asoRank: 10, asoChecked: true, asoLimit: 200 }),
      row("two", { asoFound: true, asoRank: 2, asoChecked: true, asoLimit: 200 }),
    ];
    expect(names(sortPaidKeywords(rows, { field: "asoRank", direction: "asc" }))).toEqual([
      "two",
      "ten",
      "outside",
      "unchecked",
    ]);
  });

  it("sorts decimal spend numerically and breaks ties by keyword", () => {
    const spend = (value: string) => ({ ...row("x").metrics, spend: value });
    const rows = [row("b", { metrics: spend("9.5") }), row("a", { metrics: spend("10") }), row("c", { metrics: spend("10") })];
    expect(names(sortPaidKeywords(rows, { field: "spend", direction: "desc" }))).toEqual(["a", "c", "b"]);
  });
});

describe("nextSort", () => {
  it("toggles the active column and starts metrics descending", () => {
    expect(nextSort({ field: "spend", direction: "desc" }, "spend").direction).toBe("asc");
    expect(nextSort({ field: "keyword", direction: "asc" }, "taps")).toEqual({ field: "taps", direction: "desc" });
    expect(nextSort({ field: "taps", direction: "desc" }, "asoRank")).toEqual({ field: "asoRank", direction: "asc" });
  });
});

describe("visiblePaidGroups", () => {
  const groups: PaidKeywordCountry[] = [
    { code: "US", name: "United States", summary: row("x").metrics, keywords: [row("live"), row("paused", { status: "PAUSED" })] },
    { code: "GB", name: "United Kingdom", summary: row("x").metrics, keywords: [row("old", { status: "PAUSED" })] },
  ];

  it("hides paused rows and drops groups left empty", () => {
    const visible = visiblePaidGroups(groups, { country: "all", showPaused: false }, { field: "keyword", direction: "asc" });
    expect(visible.map((group) => group.code)).toEqual(["US"]);
    expect(names(visible[0].keywords)).toEqual(["live"]);
  });

  it("filters to one country and can include paused rows", () => {
    const visible = visiblePaidGroups(groups, { country: "GB", showPaused: true }, { field: "keyword", direction: "asc" });
    expect(visible.map((group) => group.code)).toEqual(["GB"]);
  });
});

describe("paidRowsSummary", () => {
  it("sums metrics and drops a mixed currency", () => {
    const metrics = (spend: string, currency: string, taps: number) => ({ ...row("x").metrics, spend, currency, taps });
    const summary = paidRowsSummary([row("a", { metrics: metrics("1.5", "USD", 3) }), row("b", { metrics: metrics("2", "EUR", 4) })]);
    expect(summary).toMatchObject({ spend: 3.5, taps: 7, currency: null });
  });
});

describe("asoRankView", () => {
  it("never invents a rank beyond Apple's window", () => {
    expect(asoRankView(row("a", { asoChecked: true, asoLimit: 200 })).label).toBe(">200");
    expect(asoRankView(row("a", { asoFound: true, asoRank: 4, asoChecked: true })).label).toBe("#4");
    expect(asoRankView(row("a", { asoError: true })).state).toBe("error");
    expect(asoRankView(row("a")).state).toBe("unchecked");
  });
});
