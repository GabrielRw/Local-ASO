// Pure helpers for the Keywords view. They never invent a rank: a keyword Apple
// did not return stays rank = null / found = false and is excluded from averages.

import { demandSortValue } from "@/lib/format";
import type { Country, Device, HistoryPoint, MetricTrend, Ranking } from "@/lib/types";

export type SortField = "keyword" | "rank" | "popularity" | "difficulty" | "top5" | "change" | "opportunity" | "updated";
export type SortDirection = "asc" | "desc";

export function rankingSortValue(row: Ranking, field: SortField): number | string | null {
  switch (field) {
    case "keyword":
      return row.keyword.toLocaleLowerCase();
    case "rank":
      // Only Apple-returned ranks sort numerically; ">limit" rows sort last.
      return row.found && row.rank != null ? row.rank : null;
    case "popularity":
      // Apple-measured popularity and the local estimate are different scales.
      return demandSortValue(row);
    case "difficulty":
      return row.difficultyEstimate ?? null;
    case "top5":
      return (row.topApps ?? []).map((app) => app.name).join(" ").toLocaleLowerCase() || null;
    case "change": {
      if (row.change === "NEW") return Number.POSITIVE_INFINITY;
      if (row.change === "LOST") return Number.NEGATIVE_INFINITY;
      const value = Number.parseFloat(row.change);
      return Number.isFinite(value) ? value : 0;
    }
    case "opportunity":
      return row.opportunity ?? null;
    case "updated": {
      const time = +new Date(row.checkedAt);
      return Number.isFinite(time) ? time : null;
    }
  }
}

/** Sorts a copy: nulls always last (either direction), ties broken by keyword. */
export function sortRankings(rows: Ranking[], field: SortField, direction: SortDirection): Ranking[] {
  const sign = direction === "desc" ? -1 : 1;
  return [...rows].sort((left, right) => {
    const a = rankingSortValue(left, field);
    const b = rankingSortValue(right, field);
    if (a == null && b == null) return left.keyword.localeCompare(right.keyword);
    if (a == null) return 1;
    if (b == null) return -1;
    let comparison: number;
    if (typeof a === "number" && typeof b === "number") {
      comparison = a === b ? 0 : a < b ? -1 : 1;
    } else {
      comparison = String(a).localeCompare(String(b), undefined, { numeric: true });
    }
    return comparison === 0 ? left.keyword.localeCompare(right.keyword) : comparison * sign;
  });
}

export function localDateKey(value: string | number | Date): string {
  const date = new Date(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export interface DailySnapshot {
  dateKey: string;
  timestamp: number;
  tracked: number;
  found: number;
  top10: number;
  top50: number;
  averageRank: number | null;
}

/**
 * One snapshot per local day: each keyword contributes its latest check that day.
 * Average rank uses found keywords only; missing apps are excluded, never imputed.
 */
export function dailyKeywordSnapshots(history: HistoryPoint[], country: string, device: Device): DailySnapshot[] {
  const byDate = new Map<string, Map<number, HistoryPoint>>();
  for (const check of history) {
    if (check.country !== country || check.device !== device) continue;
    const key = localDateKey(check.checkedAt);
    let day = byDate.get(key);
    if (!day) {
      day = new Map();
      byDate.set(key, day);
    }
    const latest = day.get(check.targetId);
    if (!latest || +new Date(check.checkedAt) > +new Date(latest.checkedAt)) day.set(check.targetId, check);
  }
  return [...byDate.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([dateKey, checks]) => {
      const latest = [...checks.values()];
      const ranks = latest.filter((check) => check.found && check.rank != null).map((check) => check.rank as number);
      return {
        dateKey,
        timestamp: new Date(`${dateKey}T12:00:00`).getTime(),
        tracked: latest.length,
        found: ranks.length,
        top10: ranks.filter((rank) => rank <= 10).length,
        top50: ranks.filter((rank) => rank <= 50).length,
        averageRank: ranks.length ? ranks.reduce((sum, rank) => sum + rank, 0) / ranks.length : null,
      };
    });
}

export interface LosingToApp {
  appId: number;
  name: string;
  artworkUrl: string | null;
  averageRating: number | null;
  ratingCount: number | null;
  count: number;
  keywords: string[];
}

/** Top-5 apps ranking above the tracked app, counted across the current keyword rows. */
export function losingTo(rows: Ranking[], ownAppleId: number | null): LosingToApp[] {
  const competitors = new Map<number, LosingToApp & { ratingCheckedAt: number }>();
  for (const row of rows) {
    const trackedRank = row.found && row.rank != null ? row.rank : Number.POSITIVE_INFINITY;
    for (const app of row.topApps ?? []) {
      if (app.appId === ownAppleId || app.position >= trackedRank) continue;
      const existing = competitors.get(app.appId) ?? {
        appId: app.appId,
        name: app.name,
        artworkUrl: app.artworkUrl,
        averageRating: null,
        ratingCount: null,
        ratingCheckedAt: Number.NEGATIVE_INFINITY,
        count: 0,
        keywords: [],
      };
      const checkedAt = +new Date(row.checkedAt);
      if (
        (app.averageRating != null || app.ratingCount != null) &&
        Number.isFinite(checkedAt) &&
        checkedAt >= existing.ratingCheckedAt
      ) {
        existing.averageRating = app.averageRating;
        existing.ratingCount = app.ratingCount;
        existing.ratingCheckedAt = checkedAt;
      }
      existing.count += 1;
      existing.keywords.push(row.keyword);
      competitors.set(app.appId, existing);
    }
  }
  return [...competitors.values()]
    .map(({ ratingCheckedAt: _ignored, ...app }) => ({
      ...app,
      keywords: [...app.keywords].sort((left, right) => left.localeCompare(right)),
    }))
    .sort((left, right) => right.count - left.count || left.name.localeCompare(right.name));
}

/** A successful check in the last 24 hours; the server would skip it anyway. */
export function checkedWithinDay(row: Ranking, now: number = Date.now()): boolean {
  if (row.status !== "success" || !row.checkedAt) return false;
  const checkedAt = +new Date(row.checkedAt);
  return Number.isFinite(checkedAt) && now - checkedAt < 86_400_000;
}

export interface TrendChip {
  text: string;
  period: string;
  tone: "better" | "worse" | "flat";
  title: string;
}

/** 7-day and 30-day comparison chips for the metric cards. */
export function trendChip(trend: MetricTrend | undefined, periodDays: 7 | 30): TrendChip | null {
  if (!trend) return null;
  if (periodDays === 30 && trend.baseline === 0) return null;
  const tone = trend.better === true ? "better" : trend.better === false ? "worse" : "flat";
  const title = `${periodDays}-day comparison: ${trend.current ?? "—"} now vs ${trend.baseline ?? "—"} for the latest stored check on or before ${periodDays} days ago.`;
  if (trend.percent == null) {
    return periodDays === 7 ? { text: "NEW", period: "7d", tone, title } : null;
  }
  const sign = trend.percent > 0 ? "+" : trend.percent < 0 ? "−" : "";
  return { text: `${sign}${Math.abs(trend.percent).toFixed(1)}%`, period: `${periodDays}d`, tone, title };
}

export interface RankSummary {
  top10: number;
  top50: number;
  averageRank: number | null;
}

export function summarizeRanks(rows: Ranking[]): RankSummary {
  const ranks = rows.filter((row) => row.found && row.rank != null).map((row) => row.rank as number);
  return {
    top10: ranks.filter((rank) => rank <= 10).length,
    top50: ranks.filter((rank) => rank <= 50).length,
    averageRank: ranks.length ? ranks.reduce((sum, rank) => sum + rank, 0) / ranks.length : null,
  };
}

export function changeTone(change: string): "new" | "lost" | "up" | "down" | "flat" {
  if (change === "NEW") return "new";
  if (change === "LOST") return "lost";
  if (change.startsWith("+")) return "up";
  if (change.startsWith("-")) return "down";
  return "flat";
}

/** One storefront's ranks on a device: how many tracked keywords sit in each rank band. */
export interface StorefrontSummary {
  code: string;
  name: string;
  active: boolean;
  tracked: number;
  top10: number;
  top50: number;
  /** Keywords Apple returned the app for, at any rank. */
  ranked: number;
  best: Ranking | null;
}

/**
 * Every storefront that tracks keywords on the device, best results first: top 10, then
 * top 50, then ranked at all. The order does not depend on the selected storefront.
 */
export function storefrontSummaries(
  rankings: Ranking[],
  countries: Country[],
  targetCounts: Record<string, number>,
  device: Device,
): StorefrontSummary[] {
  return countries
    .map((country) => {
      const ranked = rankings
        .filter((row) => row.country === country.code && row.device === device && row.found && row.rank != null)
        .sort((a, b) => (a.rank as number) - (b.rank as number));
      return {
        code: country.code,
        name: country.name,
        active: country.active,
        tracked: Number(targetCounts[`${country.code}:${device}`] ?? 0),
        top10: ranked.filter((row) => (row.rank as number) <= 10).length,
        top50: ranked.filter((row) => (row.rank as number) <= 50).length,
        ranked: ranked.length,
        best: ranked[0] ?? null,
      };
    })
    .filter((item) => item.tracked > 0)
    .sort(
      (a, b) =>
        b.top10 - a.top10 || b.top50 - a.top50 || b.ranked - a.ranked || b.tracked - a.tracked || a.name.localeCompare(b.name),
    );
}

/**
 * The storefronts a reduced overview keeps: the selected one, then the pinned ones in the
 * overview's order. With nothing pinned, the two that track the most keywords stand in.
 */
export function reducedStorefronts(
  summaries: StorefrontSummary[],
  selected: string,
  pinned: readonly string[],
): StorefrontSummary[] {
  const extra = pinned.length
    ? summaries.filter((item) => pinned.includes(item.code))
    : [...summaries].sort((a, b) => b.tracked - a.tracked || a.name.localeCompare(b.name)).filter((item) => item.code !== selected).slice(0, 2);
  const keep = new Set([selected, ...extra.map((item) => item.code)]);
  return summaries.filter((item) => keep.has(item.code));
}
