// Word highlighting for the live listing editor. Mirrors the server's analysis
// tokens (services/coverage.py): accents folded, case ignored, short words and
// common stop words skipped, so a word counts as "repeated" exactly when the
// strategy audit would flag it.

import type { ListingMetadata } from "@/lib/types";

export type TokenTone = "unique" | "brand" | "repeated";

export const toneMark: Record<TokenTone, string> = {
  unique: "bg-emerald-500/15 text-emerald-900 dark:text-emerald-100",
  brand: "bg-sky-500/20 text-sky-900 dark:text-sky-100",
  repeated: "bg-amber-500/30 text-amber-950 dark:text-amber-50",
};

export const toneLabel: Record<TokenTone, string> = {
  unique: "Unique keyword",
  brand: "Brand term",
  repeated: "Repeated",
};

export interface Segment {
  text: string;
  /** null for separators, punctuation, and words that are not analysed. */
  tone: TokenTone | null;
}

export interface HighlightContext {
  counts: Map<string, number>;
  brandWords: Set<string>;
}

const STOP_WORDS = new Set([
  "a", "an", "and", "app", "de", "des", "du", "el", "en", "et", "for", "la", "le", "les", "of", "para", "por", "the",
  "to", "un", "une", "your",
]);

export function analysisTokens(value: string | null | undefined): string[] {
  const matches = String(value ?? "")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .match(/[a-z0-9]+/g);
  return (matches ?? []).filter((token) => token.length > 1 && !STOP_WORDS.has(token));
}

export function highlightContext(fields: string[], brandTerm: string): HighlightContext {
  const counts = new Map<string, number>();
  for (const value of fields) {
    for (const token of analysisTokens(value)) counts.set(token, (counts.get(token) ?? 0) + 1);
  }
  return { counts, brandWords: new Set(analysisTokens(brandTerm)) };
}

/** Repeated wins over brand: a brand word used twice still wastes characters. */
export function classifyTokens(tokens: string[], context: HighlightContext): TokenTone | null {
  if (!tokens.length) return null;
  if (tokens.some((token) => (context.counts.get(token) ?? 0) > 1)) return "repeated";
  if (tokens.some((token) => context.brandWords.has(token))) return "brand";
  return "unique";
}

/** Name and subtitle: every word is highlighted on its own. */
export function textSegments(value: string, context: HighlightContext): Segment[] {
  const segments: Segment[] = [];
  let cursor = 0;
  for (const match of value.matchAll(/[^\W_]+(?:['’][^\W_]+)?/gu)) {
    const index = match.index ?? cursor;
    if (index > cursor) segments.push({ text: value.slice(cursor, index), tone: null });
    segments.push({ text: match[0], tone: classifyTokens(analysisTokens(match[0]), context) });
    cursor = index + match[0].length;
  }
  if (cursor < value.length) segments.push({ text: value.slice(cursor), tone: null });
  return segments;
}

/** Keyword field: each comma-separated entry is highlighted as one phrase. */
export function keywordFieldSegments(value: string, context: HighlightContext): Segment[] {
  const segments: Segment[] = [];
  for (const part of value.split(/([,\n]+)/)) {
    if (!part) continue;
    const tone = /^[,\n]+$/.test(part) ? null : classifyTokens(analysisTokens(part), context);
    if (!tone) {
      segments.push({ text: part, tone: null });
      continue;
    }
    const leading = part.match(/^\s*/)?.[0] ?? "";
    const trailing = part.match(/\s*$/)?.[0] ?? "";
    if (leading) segments.push({ text: leading, tone: null });
    segments.push({ text: part.slice(leading.length, part.length - trailing.length), tone });
    if (trailing) segments.push({ text: trailing, tone: null });
  }
  return segments;
}

/** "Name: Brand" → "Brand"; used only as a starting suggestion for the brand term. */
export function inferBrand(name: string): string {
  const parts = name.split(/\s*[:|–—-]\s*/).filter(Boolean);
  return parts.length > 1 ? (parts.at(-1) ?? "") : "";
}

/** The health score stays locked until the listing strategy audit has been saved. */
export function coverageConfigured(metadata: ListingMetadata | null | undefined): boolean {
  return Boolean(metadata?.name?.trim() && metadata?.brandTerm?.trim() && metadata?.channelGoal);
}
