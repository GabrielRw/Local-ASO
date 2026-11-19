import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { apiGet } from "@/lib/api";
import type { Bootstrap, Health, ListingMetadata } from "@/lib/types";
import type { LocalizationDraft, LocalizationStudio } from "./types";

export const localizationStudioKey = (appId: number, country: string) => ["localization-studio", appId, country] as const;

/** Main storefront, App Store Connect status, target markets, and saved drafts. */
export function useLocalizationStudio(appId: number | null, country: string) {
  return useQuery({
    enabled: appId != null,
    queryKey: localizationStudioKey(appId ?? 0, country),
    queryFn: ({ signal }) => apiGet<LocalizationStudio>("/api/localization-studio", { appId, country }, signal),
    staleTime: 30_000,
  });
}

/** Patch cached studio payloads in place (server answers with the changed piece only). */
export function usePatchStudio(appId: number | null) {
  const client = useQueryClient();
  return useCallback(
    (update: (studio: LocalizationStudio) => LocalizationStudio) =>
      client.setQueriesData<LocalizationStudio>({ queryKey: ["localization-studio", appId] }, (current) =>
        current ? update(current) : current,
      ),
    [client, appId],
  );
}

export function replaceDraft(studio: LocalizationStudio, draft: LocalizationDraft): LocalizationStudio {
  const exists = studio.drafts.some((item) => item.id === draft.id);
  return {
    ...studio,
    drafts: exists ? studio.drafts.map((item) => (item.id === draft.id ? draft : item)) : [...studio.drafts, draft],
  };
}

/**
 * Apply a saved listing audit to the cached bootstrap without a full refetch,
 * so autosave while typing does not re-download rankings and history.
 */
export function usePatchBootstrapListing() {
  const client = useQueryClient();
  return useCallback(
    (appId: number, country: string, metadata: ListingMetadata, health: Health | null) =>
      client.setQueriesData<Bootstrap>({ queryKey: ["bootstrap"] }, (current) => {
        if (!current || current.selectedAppId !== appId || current.selectedCountry !== country) return current;
        return { ...current, listingMetadata: metadata, health: health ?? current.health };
      }),
    [client],
  );
}
