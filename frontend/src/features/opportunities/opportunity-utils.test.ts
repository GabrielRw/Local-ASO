import { describe, expect, it } from "vitest";
import type { Ranking } from "@/lib/types";
import { actionPlan, filterGroups, groupByKeyword, sortGroups } from "./opportunity-utils";

let nextId = 1;

function row(keyword: string, country: string, patch: Partial<Ranking> = {}): Ranking {
  return {
    targetId: nextId++,
    keyword,
    competitorBrand: false,
    country,
    device: "iphone",
    rank: null,
    found: false,
    resultLimit: 200,
    volumeEstimate: null,
    popularity: null,
    popularityStatus: "pending",
    popularityFetchedAt: null,
    difficultyEstimate: null,
    estimateSampleSize: null,
    topApps: [],
    previousRank: null,
    previousFound: null,
    change: "—",
    checkedAt: "2026-11-28T10:00:00Z",
    opportunity: null,
    status: "success",
    error: null,
    ...patch,
  };
}

describe("groupByKeyword", () => {
  it("adds a keyword up over its storefronts", () => {
    const [group] = groupByKeyword([
      row("focus", "fr", { rank: 30, found: true, popularity: 40, difficultyEstimate: 60, opportunity: 12, change: "+3" }),
      row("focus", "de", { rank: 8, found: true, popularity: 51, difficultyEstimate: 70, opportunity: 2, change: "-1" }),
      row("focus", "us", { popularity: 45, difficultyEstimate: 80, opportunity: 9, change: "NEW" }),
    ]);
    expect(group.total).toBe(23);
    expect(group.popularity).toBe(51);
    expect(group.topMarket?.country).toBe("fr");
    expect(group.best?.country).toBe("de");
    expect([group.top10, group.top50]).toEqual([1, 2]);
    expect(group.difficulty).toBe(70);
    expect(group.difficultyRange).toEqual([60, 80]);
    expect([group.up, group.down]).toEqual([2, 1]);
  });

  it("never scores a keyword Apple has no popularity for", () => {
    const [group] = groupByKeyword([row("calm", "fr", { volumeEstimate: 60, difficultyEstimate: 30 })]);
    expect(group.total).toBeNull();
    expect(group.topMarket).toBeNull();
  });
});

describe("actionPlan", () => {
  const rows = [
    row("scroll", "fr", { rank: 21, found: true, opportunity: 6 }),
    row("scroll", "ch", { rank: 44, found: true, opportunity: 5 }),
    row("scroll", "de", { rank: 5, found: true, opportunity: 1 }),
    row("timer", "it", { rank: 12, found: true, opportunity: 9 }),
    row("pause", "fr", { opportunity: 30 }),
    row("pause", "de", { rank: 80, found: true, opportunity: 20 }),
    row("opal", "fr", { opportunity: 40, competitorBrand: true }),
    row("opal", "de", { opportunity: 15, competitorBrand: true }),
    row("calm", "fr", {}),
  ];
  const plan = actionPlan(rows);
  const entries = (groups: typeof plan.quickWins) =>
    groups.map((group) => [group.keyword, group.total, group.markets.map((market) => market.country)]);

  it("adds a quick win up over the storefronts where it ranks 11–50, so several storefronts come first", () => {
    expect(entries(plan.quickWins)).toEqual([
      ["scroll", 11, ["fr", "ch"]],
      ["timer", 9, ["it"]],
    ]);
  });

  it("sums big bets over the storefronts where they are not in the top 50 yet", () => {
    expect(entries(plan.bigBets)).toEqual([["pause", 50, ["fr", "de"]]]);
  });

  it("keeps competitor names out of the metadata lists", () => {
    expect(entries(plan.appleAds)).toEqual([["opal", 55, ["fr", "de"]]]);
    expect(plan.quickWins.concat(plan.bigBets).some((group) => group.competitorBrand)).toBe(false);
  });
});

describe("filterGroups and sortGroups", () => {
  const groups = groupByKeyword([
    row("alpha", "fr", { popularity: 20, difficultyEstimate: 40, opportunity: 10 }),
    row("bravo", "fr", { popularity: 60, difficultyEstimate: 80, opportunity: 11, rank: 4, found: true }),
    row("charlie", "fr", { opportunity: null }),
    row("delta", "fr", { popularity: 30, difficultyEstimate: 50, opportunity: 5, competitorBrand: true }),
  ]);

  it("applies scope, search and limits, and drops unknown values once a limit is set", () => {
    const names = (list: typeof groups) => list.map((group) => group.keyword);
    expect(names(filterGroups(groups, "metadata", "", {}))).toEqual(["alpha", "bravo", "charlie"]);
    expect(names(filterGroups(groups, "competitors", "", {}))).toEqual(["delta"]);
    expect(names(filterGroups(groups, "top10", "", {}))).toEqual(["bravo"]);
    expect(names(filterGroups(groups, "all", "AL", {}))).toEqual(["alpha"]);
    expect(names(filterGroups(groups, "all", "", { difficulty: 50 }))).toEqual(["alpha", "delta"]);
    expect(names(filterGroups(groups, "all", "", { opportunity: 6, popularity: 25 }))).toEqual(["bravo"]);
  });

  it("sorts with unknown values last in both directions", () => {
    const names = (list: typeof groups) => list.map((group) => group.keyword);
    expect(names(sortGroups(groups, "opportunity", "desc"))).toEqual(["bravo", "alpha", "delta", "charlie"]);
    expect(names(sortGroups(groups, "opportunity", "asc"))).toEqual(["delta", "alpha", "bravo", "charlie"]);
    expect(names(sortGroups(groups, "difficulty", "asc"))).toEqual(["alpha", "delta", "bravo", "charlie"]);
  });
});
