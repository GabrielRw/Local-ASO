// Shapes for the Optimize view's endpoints (src/local_aso_tracker/web/server.py:
// save_listing_coverage and localization_studio). Only fields the UI reads.

import type { AgentProvider, Health, ListingMetadata } from "@/lib/types";

export type CoverageGoal = ListingMetadata["channelGoal"];

export interface CoverageMatch {
  keyword: string;
  rank: number | null;
  found: boolean;
  result_limit: number;
  sources: string[];
}

export interface CoverageUntracked {
  keyword: string;
  sources: string[];
}

export interface CoverageAnalysis {
  target_terms: number;
  keyword_field_terms: number;
  tracked_matches: number;
  ranked_keywords: number;
  unranked_keywords: number;
  matched: CoverageMatch[];
  untracked_terms: number;
  untracked_matches: CoverageUntracked[];
}

export interface StrategyPrinciple {
  key: string;
  label: string;
  passed: boolean | null;
  detail: string;
}

export interface StrategyAnalysis {
  goal: CoverageGoal;
  goal_label: string;
  brand_term: string;
  no_repetition: StrategyPrinciple;
  title_order: StrategyPrinciple;
}

export interface ListingCoverageResult {
  metadata: ListingMetadata;
  country: string;
  device: string;
  analysis: CoverageAnalysis;
  strategy: StrategyAnalysis;
  health: Health | null;
}

// --- Localization studio ----------------------------------------------------

import type { AppStoreConnectStatus } from "@/lib/types";

export type { AppStoreConnectStatus };

export interface LocalizationCountry {
  code: string;
  name: string;
  locale: string;
  language: string;
  isMain: boolean;
}

export type LocalizationFieldKey = "name" | "subtitle" | "keywords" | "description" | "promotionalText" | "whatsNew";

export interface LocalizationIssue {
  field?: string;
  severity: "error" | "warning" | string;
  message: string;
}

export interface LocalizationDraft {
  id: number;
  sourceCountry: string;
  sourceLocale: string;
  targetLocale: string;
  targetCountries: string[];
  language: string;
  status: "needs_review" | "approved" | "pushed" | "failed" | string;
  iterationCount: number;
  provider: string;
  fields: Partial<Record<LocalizationFieldKey, string>>;
  validation: { hasErrors?: boolean; score?: number | null; issues?: LocalizationIssue[] };
  remote: { versionId: string | null; versionState: string | null };
  error: string | null;
  updatedAt: string | null;
  approvedAt: string | null;
  pushedAt: string | null;
}

export interface LocalizationStudio {
  appId: number;
  bundleId: string | null;
  mainCountry: string;
  sourceLocale: string;
  sourceLanguage: string;
  sourceFields: Partial<Record<LocalizationFieldKey, string>>;
  connection: AppStoreConnectStatus;
  countries: LocalizationCountry[];
  drafts: LocalizationDraft[];
  providers: AgentProvider[];
  defaultProvider: string;
}
