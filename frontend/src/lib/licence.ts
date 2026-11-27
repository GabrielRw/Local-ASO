import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

/** /api/licence: the Mac app's licence and shell settings (src/local_aso_tracker/licensing.py). */
export interface LicenceStatus {
  desktop: boolean;
  /** False while Local ASO is free: no licence UI and nothing is locked. */
  paidEdition: boolean;
  licensed: boolean;
  required: boolean;
  email: string | null;
  issued: string | null;
  buyUrl: string | null;
  price: string;
  version: string;
  settings: { checkUpdates: boolean };
}

export const LICENCE_KEY = ["licence"] as const;

export function useLicence() {
  return useQuery({
    queryKey: LICENCE_KEY,
    queryFn: ({ signal }) => apiGet<LicenceStatus>("/api/licence", undefined, signal),
    staleTime: 5 * 60_000,
  });
}

/**
 * True when App Store Connect writes are locked (unlicensed Mac app). The server
 * enforces this too; the UI only avoids a confirmation that would end in a refusal.
 */
export function useWritesLocked(): boolean {
  return useLicence().data?.required ?? false;
}
