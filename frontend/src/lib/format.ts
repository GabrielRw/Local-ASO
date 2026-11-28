// Display rules shared by every view. These encode product guarantees from
// AGENTS.md: a missing rank is shown as ">limit" (never an invented number),
// local estimates carry "~", and Apple's popularity floor reads "Low".

import type { Device, PopularityStatus } from "./types";

/** Apple Ads' lowest popularity value: too few searches for Apple to rank. */
export const APPLE_POPULARITY_FLOOR = 5;
/** Popularity at or above this is clear demand for an exact App Store query. */
export const HIGH_POPULARITY = 20;

export type Tone = "good" | "mid" | "low" | "bad" | "neutral";

export interface RankLike {
  rank: number | null;
  found: boolean | null;
  resultLimit?: number | null;
  status?: string;
}

/** "#12", ">200" when Apple's result window did not contain the app, "!" on error. */
export function rankLabel(item: RankLike | null | undefined): string {
  if (!item) return "—";
  if (item.status === "error") return "!";
  if (item.found && item.rank) return `#${item.rank}`;
  if (item.found === false) return `>${item.resultLimit || 200}`;
  return "—";
}

export interface Demand {
  /** Short column/metric label. */
  label: string;
  /** Text to display: Apple value, "Low", "~48", or "—". */
  value: string;
  /** Numeric score for sorting and bars; null when unknown. */
  score: number | null;
  /** True when the value is Apple's own measurement, not a local estimate. */
  measured: boolean;
  tone: Tone;
  title: string;
}

interface DemandSource {
  popularity?: number | null;
  popularityStatus?: PopularityStatus;
  volume?: number | null;
  volumeEstimate?: number | null;
}

/**
 * Apple Ads popularity for this exact query. With Apple Ads connected, a query Apple has
 * not scored reads "—": the ratings-based estimate measures how big the ranking apps are,
 * not how often the query is searched, so it never stands in for Apple's value. Only
 * without Apple Ads is that estimate shown, always marked with "~".
 */
export function demand(source: DemandSource | null | undefined, market?: string): Demand {
  const where = market ? ` in ${market.toUpperCase()}` : "";
  if (source?.popularityStatus === "unavailable" || source?.popularityStatus === "pending") {
    return {
      label: "Popularity",
      value: "—",
      score: null,
      measured: false,
      tone: "neutral",
      title:
        source.popularityStatus === "unavailable"
          ? `Apple Ads has no popularity for this exact query${where}.`
          : `Not measured yet${where}: Apple Ads popularity is fetched when the dashboard starts, then every 7 days.`,
    };
  }
  if (source?.popularityStatus === "measured" && source.popularity != null) {
    const value = source.popularity;
    if (value <= APPLE_POPULARITY_FLOOR) {
      return {
        label: "Popularity",
        value: "Low",
        score: value,
        measured: true,
        tone: "low",
        title: `Apple Ads popularity${where} is at its floor of ${APPLE_POPULARITY_FLOOR}: too few searches for Apple to rank.`,
      };
    }
    return {
      label: "Popularity",
      value: String(value),
      score: value,
      measured: true,
      tone: value >= HIGH_POPULARITY ? "good" : "mid",
      title: `Apple Ads search popularity${where} for this exact query, on Apple's 5–100 scale.`,
    };
  }
  const estimate = source?.volume ?? source?.volumeEstimate ?? null;
  const reason = "Connect Apple Ads in Paid search to show Apple's popularity. ";
  return {
    label: "Est. volume",
    value: estimate == null ? "—" : `~${estimate}`,
    score: estimate,
    measured: false,
    tone: estimate == null ? "neutral" : estimate >= 35 ? "good" : estimate >= 15 ? "mid" : "low",
    title: `${reason}Local estimate of audience from matching-app ratings; not Apple search volume.`,
  };
}

/** Sort key that keeps Apple-measured values ahead of local estimates (different scales). */
export function demandSortValue(source: DemandSource): number | null {
  const value = demand(source);
  if (value.score == null) return null;
  return value.measured ? 1000 + value.score : value.score;
}

export function difficultyTone(value: number | null | undefined): Tone {
  if (value == null) return "neutral";
  if (value >= 67) return "bad";
  if (value >= 34) return "mid";
  return "good";
}

export function countryFlag(code: string): string {
  return [...code.toUpperCase()]
    .map((char) => String.fromCodePoint(127397 + char.charCodeAt(0)))
    .join("");
}

export function deviceName(device: Device | string): string {
  return device === "ipad" ? "iPad" : "iPhone";
}

export function initials(value: string | null | undefined): string {
  return (value || "AS")
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] ?? "")
    .join("")
    .toUpperCase();
}

export function formatDate(value: string | null | undefined): string {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value)) : "—";
}

export function formatDateTime(value: string | null | undefined): string {
  return value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
    : "—";
}

export function relativeDays(value: string | null | undefined, now: number = Date.now()): string {
  if (!value) return "—";
  const days = Math.max(0, Math.floor((now - +new Date(value)) / 86_400_000));
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  return `${days} days ago`;
}

export function formatCompact(value: number | null | undefined): string {
  return new Intl.NumberFormat(undefined, {
    notation: Number(value) >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value || 0);
}

export function formatBytes(value: number | null | undefined): string {
  return value ? `${Math.round(value / 1024 / 1024)} MB` : "—";
}

export function formatMoney(value: string | number | null | undefined, currency?: string | null): string {
  if (value == null) return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  if (currency) {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount);
    } catch {
      return `${amount.toFixed(2)} ${currency}`;
    }
  }
  return amount.toFixed(2);
}

/** Text tone classes shared by metric values. */
export const toneText: Record<Tone, string> = {
  good: "text-emerald-600 dark:text-emerald-400",
  mid: "text-amber-600 dark:text-amber-400",
  low: "text-muted-foreground",
  bad: "text-rose-600 dark:text-rose-400",
  neutral: "text-muted-foreground",
};

/** Bar fill classes for the same tones. */
export const toneFill: Record<Tone, string> = {
  good: "bg-emerald-500",
  mid: "bg-amber-500",
  low: "bg-muted-foreground/40",
  bad: "bg-rose-500",
  neutral: "bg-muted-foreground/30",
};
