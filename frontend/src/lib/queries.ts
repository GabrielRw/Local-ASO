import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { apiGet } from "./api";
import type { AuditPayload, Bootstrap, Device, SyncStatus } from "./types";

export const queryKeys = {
  bootstrap: (appId: number | null, country: string) => ["bootstrap", appId, country] as const,
  sync: ["sync-status"] as const,
  audit: (appId: number, country: string, device: Device, runId?: number | null) =>
    ["audit", appId, country, device, runId ?? null] as const,
};

/** The dashboard's main payload: apps, rankings for both devices, history, listing. */
export function useBootstrap(appId: number | null, country: string) {
  return useQuery({
    queryKey: queryKeys.bootstrap(appId, country),
    queryFn: ({ signal }) => apiGet<Bootstrap>("/api/bootstrap", { appId, country }, signal),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

/**
 * The bootstrap for the app and storefront in the URL. When the URL has no
 * app yet, the server picks one and the views use its `selectedAppId`.
 */
export function useCurrentBootstrap() {
  const [params] = useSearchParams();
  const app = params.get("app");
  const country = params.get("country") || "us";
  return useBootstrap(app ? Number(app) : null, country);
}

/** Background rank sync status; polls quickly only while a sync is running. */
export function useSyncStatus() {
  return useQuery({
    queryKey: queryKeys.sync,
    queryFn: ({ signal }) => apiGet<{ sync: SyncStatus }>("/api/sync-status", undefined, signal),
    select: (data) => data.sync,
    refetchInterval: (query) => (query.state.data?.sync.state === "running" ? 5_000 : 60_000),
  });
}

/** Latest audit for an app/storefront/device; polls while a run is queued or running. */
export function useAudit(appId: number | null, country: string, device: Device, runId?: number | null) {
  return useQuery({
    enabled: appId != null,
    queryKey: queryKeys.audit(appId ?? 0, country, device, runId),
    queryFn: ({ signal }) =>
      apiGet<AuditPayload>(runId ? `/api/audits/${runId}` : "/api/audits", { appId, country, device }, signal),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => {
      const status = query.state.data?.run?.status;
      return status === "queued" || status === "running" ? 1_500 : false;
    },
  });
}

export function useInvalidate() {
  const client = useQueryClient();
  return {
    bootstrap: () => client.invalidateQueries({ queryKey: ["bootstrap"] }),
    audit: () => client.invalidateQueries({ queryKey: ["audit"] }),
    all: () => client.invalidateQueries(),
  };
}
