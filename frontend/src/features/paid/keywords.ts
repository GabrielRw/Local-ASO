// Pure helpers for the Apple Ads keyword table: filtering by status and
// country, sorting within each country group, group totals, and the ASO rank
// cell. A keyword outside Apple's search window sorts after every exact rank
// but is never given an invented rank.

import { formatMoney } from "@/lib/format";
import type { PaidKeyword, PaidKeywordCountry, PaidSummary } from "./api";

export type PaidSortField =
  | "keyword"
  | "matchTypes"
  | "status"
  | "campaignCount"
  | "asoRank"
  | "bid"
  | "spend"
  | "impressions"
  | "taps"
  | "installs";

export type SortDirection = "asc" | "desc";

export interface PaidSort {
  field: PaidSortField;
  direction: SortDirection;
}

const ASCENDING_FIRST: PaidSortField[] = ["keyword", "matchTypes", "status", "asoRank"];

/** Clicking the active column flips direction; a new column starts at its natural direction. */
export function nextSort(current: PaidSort, field: PaidSortField): PaidSort {
  if (current.field === field) return { field, direction: current.direction === "asc" ? "desc" : "asc" };
  return { field, direction: ASCENDING_FIRST.includes(field) ? "asc" : "desc" };
}

export function paidSortValue(row: PaidKeyword, field: PaidSortField): string | number | null {
  const metrics = row.metrics;
  switch (field) {
    case "keyword":
      return row.text;
    case "matchTypes":
      return row.matchTypes.join(", ");
    case "status":
      return row.status;
    case "campaignCount":
      return row.campaignCount;
    case "asoRank":
      if (row.asoFound && row.asoRank != null) return row.asoRank;
      // Outside the window sorts just after the window; unchecked rows sort last.
      return row.asoChecked && row.asoLimit != null ? row.asoLimit + 1 : null;
    case "bid":
      return row.bidMin == null ? null : Number(row.bidMin);
    case "spend":
      return Number(metrics?.spend ?? 0);
    case "impressions":
      return metrics?.impressions ?? 0;
    case "taps":
      return metrics?.taps ?? 0;
    case "installs":
      return metrics?.tapInstalls ?? 0;
  }
}

export function sortPaidKeywords(rows: PaidKeyword[], sort: PaidSort): PaidKeyword[] {
  const direction = sort.direction === "asc" ? 1 : -1;
  const byText = (a: PaidKeyword, b: PaidKeyword) => a.text.localeCompare(b.text);
  return [...rows].sort((left, right) => {
    const a = paidSortValue(left, sort.field);
    const b = paidSortValue(right, sort.field);
    if (a == null && b == null) return byText(left, right);
    if (a == null) return 1;
    if (b == null) return -1;
    const comparison =
      typeof a === "number" && typeof b === "number"
        ? a - b
        : String(a).localeCompare(String(b), undefined, { numeric: true });
    return comparison ? comparison * direction : byText(left, right);
  });
}

export interface PaidGroupFilter {
  /** "all" or a country code as the server sends it (uppercase). */
  country: string;
  showPaused: boolean;
}

/** Status filter applied to every group (counts for the filter chips). */
export function filterByStatus(groups: PaidKeywordCountry[], showPaused: boolean): PaidKeywordCountry[] {
  return groups.map((group) => ({
    ...group,
    keywords: group.keywords.filter((row) => showPaused || row.status === "ENABLED"),
  }));
}

/** Groups visible in the table: status + country filter, empty groups dropped, rows sorted. */
export function visiblePaidGroups(
  groups: PaidKeywordCountry[],
  filter: PaidGroupFilter,
  sort: PaidSort,
): PaidKeywordCountry[] {
  return filterByStatus(groups, filter.showPaused)
    .filter((group) => filter.country === "all" || group.code === filter.country)
    .filter((group) => group.keywords.length)
    .map((group) => ({ ...group, keywords: sortPaidKeywords(group.keywords, sort) }));
}

/** Totals for a set of keyword rows; currency only when every row agrees. */
export function paidRowsSummary(rows: PaidKeyword[]): Pick<PaidSummary, "currency" | "impressions" | "taps" | "tapInstalls"> & {
  spend: number;
} {
  const currencies = new Set(rows.map((row) => row.metrics?.currency).filter(Boolean));
  return {
    spend: rows.reduce((total, row) => total + Number(row.metrics?.spend ?? 0), 0),
    currency: currencies.size === 1 ? ([...currencies][0] ?? null) : null,
    impressions: rows.reduce((total, row) => total + (row.metrics?.impressions ?? 0), 0),
    taps: rows.reduce((total, row) => total + (row.metrics?.taps ?? 0), 0),
    tapInstalls: rows.reduce((total, row) => total + (row.metrics?.tapInstalls ?? 0), 0),
  };
}

export function bidLabel(row: PaidKeyword): string {
  if (row.bidMin === row.bidMax) return formatMoney(row.bidMin, row.currency);
  return `${formatMoney(row.bidMin, row.currency)}–${formatMoney(row.bidMax, row.currency)}`;
}

export type AsoRankState = "found" | "outside" | "error" | "unchecked";

/** ASO rank cell: #N, >limit, ! on a failed check, or a prompt to search. */
export function asoRankView(row: PaidKeyword): { state: AsoRankState; label: string; title: string } {
  if (row.asoFound && row.asoRank) {
    return {
      state: "found",
      label: `#${row.asoRank}`,
      title: `Search again for the ${row.countryName} App Store rank of “${row.text}”`,
    };
  }
  if (row.asoChecked) {
    const limit = row.asoLimit ?? 200;
    return {
      state: "outside",
      label: `>${limit}`,
      title: `Not found in Apple’s top ${limit} for “${row.text}”; search again`,
    };
  }
  if (row.asoError) {
    return { state: "error", label: "!", title: `The last App Store check for “${row.text}” failed; retry` };
  }
  return {
    state: "unchecked",
    label: "Check",
    title: `Search the ${row.countryName} App Store ranking for “${row.text}”`,
  };
}
