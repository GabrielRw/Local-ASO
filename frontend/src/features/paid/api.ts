import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { Device } from "@/lib/types";

// Shapes from src/local_aso_tracker/repositories/apple_ads.py (apple_ads_payload)
// and apple/ads.py (credential_status). Secret material is never sent to the UI.

export interface PaidSummary {
  /** Decimal string from the server. */
  spend: string | null;
  currency: string | null;
  impressions: number;
  taps: number;
  tapInstalls: number;
  totalInstalls: number;
  cpt: string | null;
}

export interface AdAccount {
  id: number;
  orgId: number;
  name: string;
  roles: string[];
  lastSyncedAt?: string | null;
}

export interface PaidCampaign {
  id: number;
  name: string;
  status: string;
  deleted: boolean;
  keywordCount: number;
  enabledKeywordCount: number;
  summary: PaidSummary;
}

export interface PaidKeyword {
  country: string;
  countryName: string;
  text: string;
  matchTypes: string[];
  status: "ENABLED" | "PAUSED" | string;
  campaignStatus: string;
  campaignCount: number;
  campaigns: string[];
  bidMin: string | null;
  bidMax: string | null;
  currency: string | null;
  metrics: PaidSummary;
  asoRank: number | null;
  asoFound: boolean;
  asoChecked: boolean;
  asoLimit: number | null;
  asoError: boolean;
}

export interface PaidKeywordCountry {
  code: string;
  name: string;
  summary: PaidSummary;
  keywords: PaidKeyword[];
}

export interface PaidSuggestion {
  text: string;
  /** Apple Ads popularity (5–100) when measured for this exact keyword. */
  popularity: number | null;
  inAppleAds: boolean;
  inAsoTracker: boolean;
  fetchedAt: string | null;
}

export interface PaidCredentials {
  available: boolean;
  path?: string;
  reason?: string;
  expiresAt?: string | null;
  private_permissions?: boolean;
}

export interface PaidSync {
  campaigns: number;
  keywords: number;
  metricRows: number;
  suggestions: number;
}

export interface AppleAdsPayload {
  credentials: PaidCredentials;
  accounts: AdAccount[];
  selectedAccountId: number | null;
  window: { days: number; start: string; end: string };
  campaigns: PaidCampaign[];
  keywords: PaidKeyword[];
  keywordCountries: PaidKeywordCountry[];
  suggestions: PaidSuggestion[];
  summary: PaidSummary;
  allMarketsSummary: PaidSummary;
  sync?: PaidSync;
}

export const paidKeys = {
  appleAds: (appId: number, country: string, device: Device) => ["apple-ads", appId, country, device] as const,
};

export function useAppleAds(appId: number | null, country: string, device: Device) {
  return useQuery({
    enabled: appId != null,
    queryKey: paidKeys.appleAds(appId ?? 0, country, device),
    queryFn: ({ signal }) => apiGet<AppleAdsPayload>("/api/apple-ads", { appId, country, device }, signal),
    placeholderData: keepPreviousData,
  });
}

export function usePaidCache() {
  const client = useQueryClient();
  return {
    set: (appId: number, country: string, device: Device, data: AppleAdsPayload) =>
      client.setQueryData(paidKeys.appleAds(appId, country, device), data),
    invalidate: () => client.invalidateQueries({ queryKey: ["apple-ads"] }),
  };
}
