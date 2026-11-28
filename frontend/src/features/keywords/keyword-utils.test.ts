import { describe, expect, it } from "vitest";
import type { HistoryPoint, Ranking, TopApp } from "@/lib/types";
import {
  checkedWithinDay,
  dailyKeywordSnapshots,
  localDateKey,
  losingTo,
  reducedStorefronts,
  sortRankings,
  storefrontSummaries,
  summarizeRanks,
  trendChip,
} from "./keyword-utils";

function row(patch: Partial<Ranking>): Ranking {
  return {
    targetId: 1,
    keyword: "kw",
    competitorBrand: false,
    country: "us",
    device: "iphone",
    rank: null,
    found: false,
    resultLimit: 200,
    volumeEstimate: null,
    popularity: null,
    popularityStatus: null,
    popularityFetchedAt: null,
    difficultyEstimate: null,
    estimateSampleSize: null,
    topApps: [],
    previousRank: null,
    previousFound: null,
    change: "—",
    checkedAt: "2026-11-10T10:00:00Z",
    opportunity: null,
    signal: null,
    status: "success",
    error: null,
    ...patch,
  };
}

function app(position: number, appId: number, patch: Partial<TopApp> = {}): TopApp {
  return { position, appId, name: `App ${appId}`, artworkUrl: null, averageRating: null, ratingCount: null, ...patch };
}

describe("sortRankings", () => {
  const rows = [
    row({ targetId: 1, keyword: "charlie", rank: 30, found: true }),
    row({ targetId: 2, keyword: "alpha", rank: null, found: false }),
    row({ targetId: 3, keyword: "bravo", rank: 3, found: true }),
    row({ targetId: 4, keyword: "delta", rank: 3, found: true }),
  ];

  it("sorts ranks ascending with missing ranks last and ties by keyword", () => {
    expect(sortRankings(rows, "rank", "asc").map((item) => item.keyword)).toEqual(["bravo", "delta", "charlie", "alpha"]);
  });

  it("keeps missing ranks last when descending", () => {
    expect(sortRankings(rows, "rank", "desc").map((item) => item.keyword)).toEqual(["charlie", "bravo", "delta", "alpha"]);
  });

  it("sorts Apple-measured popularity ahead of local estimates", () => {
    const demandRows = [
      row({ keyword: "estimate", volumeEstimate: 90 }),
      row({ keyword: "measured", popularity: 20, popularityStatus: "measured" }),
      row({ keyword: "unknown" }),
    ];
    expect(sortRankings(demandRows, "popularity", "desc").map((item) => item.keyword)).toEqual([
      "measured",
      "estimate",
      "unknown",
    ]);
  });
});

describe("dailyKeywordSnapshots", () => {
  const point = (patch: Partial<HistoryPoint>): HistoryPoint => ({
    targetId: 1,
    keyword: "kw",
    country: "us",
    device: "iphone",
    rank: null,
    found: false,
    resultLimit: 200,
    checkedAt: "2026-11-10T12:00:00",
    ...patch,
  });

  it("uses each keyword's latest check per day and never averages missing ranks", () => {
    const snapshots = dailyKeywordSnapshots(
      [
        point({ targetId: 1, rank: 40, found: true, checkedAt: "2026-11-10T08:00:00" }),
        point({ targetId: 1, rank: 8, found: true, checkedAt: "2026-11-10T18:00:00" }),
        point({ targetId: 2, rank: null, found: false, checkedAt: "2026-11-10T09:00:00" }),
        point({ targetId: 3, rank: 20, found: true, checkedAt: "2026-11-10T09:00:00" }),
        point({ targetId: 1, rank: 2, found: true, checkedAt: "2026-11-11T09:00:00", country: "gb" }),
        point({ targetId: 1, rank: 5, found: true, checkedAt: "2026-11-09T09:00:00" }),
      ],
      "us",
      "iphone",
    );
    expect(snapshots.map((item) => item.dateKey)).toEqual(["2026-11-09", "2026-11-10"]);
    expect(snapshots[1]).toMatchObject({ tracked: 3, found: 2, top10: 1, top50: 2, averageRank: 14 });
  });

  it("formats local date keys", () => {
    expect(localDateKey(new Date(2026, 0, 5, 23, 0))).toBe("2026-01-05");
  });
});

describe("losingTo", () => {
  it("counts top-5 apps ahead of the tracked app, excluding the app itself", () => {
    const result = losingTo(
      [
        row({ keyword: "b", rank: 3, found: true, topApps: [app(1, 10), app(2, 20), app(3, 99), app(4, 30)] }),
        row({
          keyword: "a",
          rank: null,
          found: false,
          checkedAt: "2026-11-12T10:00:00Z",
          topApps: [app(1, 20, { averageRating: 4.5, ratingCount: 1200 }), app(5, 30)],
        }),
      ],
      99,
    );
    expect(result.map((item) => [item.appId, item.count])).toEqual([
      [20, 2],
      [10, 1],
      [30, 1],
    ]);
    expect(result[0]).toMatchObject({ keywords: ["a", "b"], averageRating: 4.5, ratingCount: 1200 });
    expect(result[1].averageRating).toBeNull();
  });
});

describe("checkedWithinDay", () => {
  const now = +new Date("2026-11-10T12:00:00Z");
  it("skips successful checks from the last 24 hours only", () => {
    expect(checkedWithinDay(row({ checkedAt: "2026-11-10T01:00:00Z" }), now)).toBe(true);
    expect(checkedWithinDay(row({ checkedAt: "2026-11-09T01:00:00Z" }), now)).toBe(false);
    expect(checkedWithinDay(row({ checkedAt: "2026-11-10T01:00:00Z", status: "error" }), now)).toBe(false);
  });
});

describe("trendChip", () => {
  it("formats percent changes and hides empty 30-day baselines", () => {
    expect(trendChip({ current: 6, baseline: 4, percent: 50, better: true }, 7)).toMatchObject({
      text: "+50.0%",
      tone: "better",
    });
    expect(trendChip({ current: 6, baseline: 0, percent: null, better: null }, 7)?.text).toBe("NEW");
    expect(trendChip({ current: 6, baseline: 0, percent: null, better: null }, 30)).toBeNull();
    expect(trendChip(undefined, 7)).toBeNull();
  });
});

describe("summarizeRanks", () => {
  it("averages found ranks only", () => {
    expect(
      summarizeRanks([row({ rank: 4, found: true }), row({ rank: 60, found: true }), row({ rank: null, found: false })]),
    ).toEqual({ top10: 1, top50: 1, averageRank: 32 });
  });
});

describe("sortRankings by opportunity", () => {
  it("puts the biggest opportunity first and keywords without one last", () => {
    const rows = [
      row({ targetId: 1, keyword: "small", opportunity: 3 }),
      row({ targetId: 2, keyword: "none", opportunity: null }),
      row({ targetId: 3, keyword: "big", opportunity: 30 }),
      row({ targetId: 4, keyword: "won", opportunity: 0 }),
    ];
    expect(sortRankings(rows, "opportunity", "desc").map((item) => item.keyword)).toEqual(["big", "small", "won", "none"]);
  });
});

describe("storefrontSummaries", () => {
  it("counts rank bands per storefront on one device, best storefronts first", () => {
    const rankings = [
      row({ targetId: 1, country: "fr", rank: 4, found: true }),
      row({ targetId: 2, country: "fr", rank: 30, found: true }),
      row({ targetId: 3, country: "fr", rank: 120, found: true }),
      row({ targetId: 4, country: "fr" }),
      row({ targetId: 5, country: "de", rank: 2, found: true }),
      row({ targetId: 6, country: "de", rank: 9, found: true }),
      row({ targetId: 7, country: "de", device: "ipad", rank: 1, found: true }),
    ];
    const countries = [
      { code: "de", name: "Germany", active: true },
      { code: "fr", name: "France", active: true },
      { code: "it", name: "Italy", active: true },
    ];
    const counts = { "fr:iphone": 5, "de:iphone": 2, "de:ipad": 1, "it:iphone": 0 };
    const summaries = storefrontSummaries(rankings, countries, counts, "iphone");
    expect(summaries.map((item) => [item.code, item.top10, item.top50, item.ranked, item.tracked])).toEqual([
      ["de", 2, 2, 2, 2],
      ["fr", 1, 2, 3, 5],
    ]);
    expect(summaries[0].best?.rank).toBe(2);
  });
});

describe("reducedStorefronts", () => {
  const summary = (code: string, tracked: number) => ({
    code,
    name: code.toUpperCase(),
    active: true,
    tracked,
    top10: 0,
    top50: 0,
    ranked: 0,
    best: null,
  });
  // Overview order (best results first), not tracked-count order.
  const summaries = [summary("no", 34), summary("ch", 138), summary("fr", 93), summary("ca", 86), summary("us", 77)];
  const codes = (items: ReturnType<typeof reducedStorefronts>) => items.map((item) => item.code);

  it("keeps the selected storefront and the pinned ones, in the overview's order", () => {
    expect(codes(reducedStorefronts(summaries, "no", ["us", "fr"]))).toEqual(["no", "fr", "us"]);
    expect(codes(reducedStorefronts(summaries, "fr", ["us", "fr"]))).toEqual(["fr", "us"]);
  });

  it("falls back to the two storefronts that track the most keywords", () => {
    expect(codes(reducedStorefronts(summaries, "us", []))).toEqual(["ch", "fr", "us"]);
    expect(codes(reducedStorefronts(summaries, "ch", []))).toEqual(["ch", "fr", "ca"]);
  });
});

describe("sortRankings by signal", () => {
  it("sorts the rank-based label alphabetically, empty last", () => {
    const rows = [
      row({ targetId: 1, keyword: "b", signal: "Growth range (#11-50)" }),
      row({ targetId: 2, keyword: "a", signal: "Defend visibility (#1-10)" }),
      row({ targetId: 3, keyword: "c", signal: null }),
    ];
    expect(sortRankings(rows, "signal", "asc").map((item) => item.keyword)).toEqual(["a", "b", "c"]);
  });
});
