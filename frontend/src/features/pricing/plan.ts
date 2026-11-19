import type { PriceRow } from "./types";

/** A row is worth changing when there is a real suggested point that differs from today's. */
export function changeable(row: PriceRow): boolean {
  return Boolean(row.suggestedPointId) && row.suggestedPointId !== row.currentPointId && row.changePercent !== 0;
}

/** Rows pre-selected for review: every changeable one. */
export function defaultSelection(rows: PriceRow[]): Set<string> {
  return new Set(rows.filter(changeable).map((row) => row.territory));
}

export function changeLabel(value: number | null): string {
  if (value == null) return "—";
  if (value === 0) return "0%";
  return `${value > 0 ? "+" : "−"}${Math.abs(value).toFixed(1)}%`;
}

export function percentInput(value: number): string {
  return String(Math.round(value * 100));
}

/** Parse a 1–100 percentage field to a ratio, or null when it isn't valid. */
export function parsePercent(text: string): number | null {
  const value = Number(text);
  if (!Number.isFinite(value) || value < 1 || value > 100) return null;
  return value / 100;
}
