import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { Device, Health } from "@/lib/types";

// Shapes from src/local_aso_tracker/repositories/competitors.py and server.compare().

export interface MatrixApp {
  appleAppId: number;
  name: string;
  artworkUrl: string | null;
  isPrimary: boolean;
}

export interface MatrixCell {
  appleAppId: number;
  rank: number | null;
  found: boolean;
  /** Null while the pair has never been checked. */
  resultLimit: number | null;
  status: "pending" | "success" | "error" | string;
  checkedAt: string | null;
  error: string | null;
}

export interface MatrixKeyword {
  targetId: number;
  keyword: string;
  primaryRank: number | null;
  primaryFound: boolean;
  cells: MatrixCell[];
}

export interface CompetitorMatrix {
  app: { appleAppId: number; name: string };
  country: string;
  device: Device;
  apps: MatrixApp[];
  keywords: MatrixKeyword[];
  competitorCount: number;
  lastCheckedAt: string | null;
  refresh?: { searches: number; failures: number };
}

export interface CompareListing {
  appleAppId: number;
  name: string;
  bundleId: string | null;
  seller?: string | null;
  version: string | null;
  url: string | null;
  artworkUrl: string | null;
  genre: string | null;
  description?: string;
  averageRating?: number | null;
  ratingCount?: number | null;
  updatedAt?: string | null;
  languages?: string[];
  descriptionLength?: number;
}

export interface ComparePayload {
  primary: CompareListing;
  competitor: CompareListing;
  primaryHealth: Pick<Health, "score" | "label">;
  competitorHealth: Pick<Health, "score" | "label">;
}

export const competitorKeys = {
  matrix: (appId: number, country: string, device: Device) => ["competitors", appId, country, device] as const,
  compare: (appId: number, competitorId: number, country: string) =>
    ["compare", appId, competitorId, country] as const,
};

export function useCompetitorMatrix(appId: number | null, country: string, device: Device) {
  return useQuery({
    enabled: appId != null,
    queryKey: competitorKeys.matrix(appId ?? 0, country, device),
    queryFn: ({ signal }) => apiGet<CompetitorMatrix>("/api/competitors", { appId, country, device }, signal),
    placeholderData: keepPreviousData,
  });
}

/** Side-by-side public listing data; fetched on demand (two Apple lookups). */
export function useCompare(appId: number | null, competitorId: number | null, country: string) {
  return useQuery({
    enabled: appId != null && competitorId != null,
    queryKey: competitorKeys.compare(appId ?? 0, competitorId ?? 0, country),
    queryFn: ({ signal }) =>
      apiGet<ComparePayload>("/api/compare", { appId, competitorId, country }, signal),
    staleTime: 5 * 60_000,
  });
}

export function useCompetitorCache() {
  const client = useQueryClient();
  return {
    setMatrix: (appId: number, country: string, device: Device, data: CompetitorMatrix) =>
      client.setQueryData(competitorKeys.matrix(appId, country, device), data),
    invalidateMatrix: () => client.invalidateQueries({ queryKey: ["competitors"] }),
  };
}
