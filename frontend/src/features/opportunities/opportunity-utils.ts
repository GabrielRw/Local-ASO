// App-wide opportunities: every storefront of one device. Pure helpers, so the page only
// renders. A score is Apple popularity still to win (see services/keyword_popularity.py);
// keywords without one are listed but never scored from the local estimate.

import { changeTone } from "@/features/keywords/keyword-utils";
import type { Ranking } from "@/lib/types";

export const LIST_SIZE = 6;

/** One keyword over every storefront that tracks it on the device. */
export interface KeywordGroup {
  keyword: string;
  /** Its storefronts, the most opportunity left first. */
  markets: Ranking[];
  competitorBrand: boolean;
  /** Highest Apple popularity over its storefronts. */
  popularity: number | null;
  /** Opportunity summed over its storefronts; null when none has a score. */
  total: number | null;
  /** The storefront with the most opportunity left, when one has some. */
  topMarket: Ranking | null;
  /** Its best rank among the storefronts where Apple returned the app. */
  best: Ranking | null;
  top10: number;
  top50: number;
  /** Median difficulty over its storefronts, and the lowest and highest. */
  difficulty: number | null;
  difficultyRange: [number, number] | null;
  /** Storefronts where the rank went up (or entered) and down (or dropped out) at the last check. */
  up: number;
  down: number;
}

// No app-wide total: it would grow with the number of keywords tracked in each storefront.
// Each list is one entry per keyword, summed over the storefronts where it qualifies, so a
// keyword that pays off in several storefronts at once comes first.
export interface ActionPlan {
  /** Ranked 11–50 in these storefronts: metadata work there should pay off soon. */
  quickWins: KeywordGroup[];
  /** Not in the top 50 of these storefronts yet. */
  bigBets: KeywordGroup[];
  /** Competitor names: App Review keeps them out of metadata, so Apple Ads only. */
  appleAds: KeywordGroup[];
}

const isRanked = (row: Ranking): boolean => row.found && row.rank != null;
const rankOrder = (row: Ranking): number => (isRanked(row) ? (row.rank as number) : Number.POSITIVE_INFINITY);

function median(sorted: number[]): number | null {
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : Math.round((sorted[middle - 1] + sorted[middle]) / 2);
}

export function groupByKeyword(rows: Ranking[]): KeywordGroup[] {
  const groups = new Map<string, Ranking[]>();
  for (const row of rows) {
    const key = row.keyword.toLocaleLowerCase();
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  return [...groups.values()].map((items) => {
    const markets = [...items].sort(
      (a, b) => (b.opportunity ?? -1) - (a.opportunity ?? -1) || rankOrder(a) - rankOrder(b),
    );
    const ranked = markets.filter(isRanked).sort((a, b) => rankOrder(a) - rankOrder(b));
    const scores = markets.map((row) => row.opportunity).filter((value): value is number => value != null);
    const popularities = markets.map((row) => row.popularity).filter((value): value is number => value != null);
    const difficulties = markets
      .map((row) => row.difficultyEstimate)
      .filter((value): value is number => value != null)
      .sort((a, b) => a - b);
    const tones = markets.map((row) => changeTone(row.change));
    return {
      keyword: markets[0].keyword,
      markets,
      competitorBrand: markets.some((row) => row.competitorBrand),
      popularity: popularities.length ? Math.max(...popularities) : null,
      total: scores.length ? scores.reduce((sum, value) => sum + value, 0) : null,
      topMarket: (markets[0].opportunity ?? 0) > 0 ? markets[0] : null,
      best: ranked[0] ?? null,
      top10: ranked.filter((row) => (row.rank as number) <= 10).length,
      top50: ranked.filter((row) => (row.rank as number) <= 50).length,
      difficulty: median(difficulties),
      difficultyRange: difficulties.length ? [difficulties[0], difficulties[difficulties.length - 1]] : null,
      up: tones.filter((tone) => tone === "up" || tone === "new").length,
      down: tones.filter((tone) => tone === "down" || tone === "lost").length,
    };
  });
}

function byTotal(a: KeywordGroup, b: KeywordGroup): number {
  return (b.total ?? 0) - (a.total ?? 0) || (b.popularity ?? 0) - (a.popularity ?? 0) || a.keyword.localeCompare(b.keyword);
}

/** The scored groups with something left to win, the biggest first. */
function winnable(rows: Ranking[]): KeywordGroup[] {
  return groupByKeyword(rows)
    .filter((group) => (group.total ?? 0) > 0)
    .sort(byTotal);
}

export function actionPlan(rows: Ranking[], size = LIST_SIZE): ActionPlan {
  const scored = rows.filter((row) => row.opportunity != null);
  const own = scored.filter((row) => !row.competitorBrand);
  return {
    quickWins: winnable(own.filter((row) => isRanked(row) && (row.rank as number) > 10 && (row.rank as number) <= 50)).slice(
      0,
      size,
    ),
    bigBets: winnable(own.filter((row) => !isRanked(row) || (row.rank as number) > 50)).slice(0, size),
    appleAds: winnable(scored.filter((row) => row.competitorBrand)).slice(0, size),
  };
}

export type Scope = "all" | "metadata" | "top10" | "top50" | "unranked" | "competitors";

export const SCOPES: { value: Scope; label: string; test: (group: KeywordGroup) => boolean }[] = [
  { value: "all", label: "All keywords", test: () => true },
  { value: "metadata", label: "For metadata", test: (group) => !group.competitorBrand },
  { value: "top10", label: "In a top 10", test: (group) => group.top10 > 0 },
  { value: "top50", label: "In a top 50", test: (group) => group.top50 > 0 },
  { value: "unranked", label: "Not in any top 50", test: (group) => group.top50 === 0 },
  { value: "competitors", label: "Competitor names", test: (group) => group.competitorBrand },
];

/** Minimums (popularity, opportunity) and a maximum (difficulty); unset limits pass. */
export interface Limits {
  popularity?: number;
  difficulty?: number;
  opportunity?: number;
}

export function filterGroups(groups: KeywordGroup[], scope: Scope, search: string, limits: Limits): KeywordGroup[] {
  const test = SCOPES.find((item) => item.value === scope)?.test ?? (() => true);
  const needle = search.trim().toLocaleLowerCase();
  const atLeast = (value: number | null, limit?: number) => limit == null || (value != null && value >= limit);
  const atMost = (value: number | null, limit?: number) => limit == null || (value != null && value <= limit);
  return groups.filter(
    (group) =>
      test(group) &&
      (!needle || group.keyword.toLocaleLowerCase().includes(needle)) &&
      atLeast(group.popularity, limits.popularity) &&
      atMost(group.difficulty, limits.difficulty) &&
      atLeast(group.total, limits.opportunity),
  );
}

export type GroupSortField = "keyword" | "popularity" | "opportunity" | "market" | "rank" | "coverage" | "difficulty" | "change";

/** The direction a column sorts in on its first click: the best first. */
export const FIRST_DIRECTION: Record<GroupSortField, "asc" | "desc"> = {
  keyword: "asc",
  popularity: "desc",
  opportunity: "desc",
  market: "desc",
  rank: "asc",
  coverage: "desc",
  difficulty: "asc",
  change: "desc",
};

function groupSortValue(group: KeywordGroup, field: GroupSortField): number | string | null {
  switch (field) {
    case "keyword":
      return group.keyword.toLocaleLowerCase();
    case "popularity":
      return group.popularity;
    case "opportunity":
      return group.total;
    case "market":
      return group.topMarket?.opportunity ?? null;
    case "rank":
      return group.best?.rank ?? null;
    case "coverage":
      return group.top10 * 1000 + group.top50;
    case "difficulty":
      return group.difficulty;
    case "change":
      return group.up || group.down ? group.up - group.down : null;
  }
}

/** Sorts a copy: nulls last in either direction, then the biggest opportunity, then keyword. */
export function sortGroups(groups: KeywordGroup[], field: GroupSortField, direction: "asc" | "desc"): KeywordGroup[] {
  const sign = direction === "desc" ? -1 : 1;
  return [...groups].sort((left, right) => {
    const a = groupSortValue(left, field);
    const b = groupSortValue(right, field);
    if (a != null && b == null) return -1;
    if (a == null && b != null) return 1;
    if (a != null && b != null && a !== b) {
      const comparison = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
      return comparison * sign;
    }
    return byTotal(left, right);
  });
}
