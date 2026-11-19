import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { AgentProvider } from "@/lib/types";

// Shapes from src/local_aso_tracker/repositories/niches.py (niche_board_payload)
// and server.niche*(). Every metric is a local ratings-based estimate.

export interface NicheMetric {
  /** Local 0–100 audience estimate; null when no rated matches. */
  volume: number | null;
  /** Local 0–100 competition estimate; null when no rated matches. */
  difficulty: number | null;
  sampleSize: number | null;
  status: "pending" | "success" | "error" | string;
  checkedAt: string | null;
  error: string | null;
}

export interface NicheKeyword {
  id: number;
  keyword: string;
  /** One metric per board country, in board.countries order. */
  metrics: NicheMetric[];
}

export interface NicheCountry {
  code: string;
  name: string;
}

export interface NicheBoard {
  id: number;
  name: string;
  brief: string;
  provider: string;
  updatedAt: string | null;
  countries: NicheCountry[];
  keywords: NicheKeyword[];
}

export interface NicheCheck {
  searches: number;
  failures: number;
}

export interface NichePayload {
  boards: { id: number; name: string; brief: string; updatedAt: string | null }[];
  availableCountries: NicheCountry[];
  selectedBoardId: number | null;
  board: NicheBoard | null;
  providers: AgentProvider[];
  defaultProvider: string;
  generation?: { provider: string; keywords: string[]; check: NicheCheck };
  agent?: { provider: string; keywords: string[]; check: NicheCheck | null };
  check?: NicheCheck;
  countryChange?: { country: string; added?: boolean; removed?: boolean; check?: NicheCheck | null };
}

export const nicheKeys = {
  workspace: (boardId: number | null) => ["niche", boardId] as const,
};

export function useNiche(boardId: number | null) {
  return useQuery({
    queryKey: nicheKeys.workspace(boardId),
    queryFn: ({ signal }) => apiGet<NichePayload>("/api/niche", { boardId }, signal),
    placeholderData: keepPreviousData,
  });
}

export function useNicheCache() {
  const client = useQueryClient();
  return (payload: NichePayload) => client.setQueryData(nicheKeys.workspace(payload.selectedBoardId), payload);
}
