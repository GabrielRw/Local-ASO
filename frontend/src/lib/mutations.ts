import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiPost } from "./api";
import { useInvalidate } from "./queries";
import type { Device } from "./types";

export interface AddKeywordsResult {
  keywords: string[];
  keywordsRequested: number;
  keywordsCreated: number;
  targetsCreated: number;
  targetsReactivated: number;
  targetsUnchanged: number;
  automaticCheck: { checks: number; searches: number; failures: number } | null;
}

export function describeAddKeywords(result: AddKeywordsResult): string {
  const added = result.targetsCreated + result.targetsReactivated;
  const parts = [
    added
      ? `${added} keyword target${added === 1 ? "" : "s"} now tracked`
      : "Already tracked",
  ];
  if (result.automaticCheck?.checks) {
    parts.push(
      `first check done${result.automaticCheck.failures ? ` (${result.automaticCheck.failures} failed)` : ""}`,
    );
  }
  return parts.join(" · ");
}

/** Track keywords in storefronts; the server runs the first Apple check right away. */
export function useTrackKeywords() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (input: { appId: number; keywords: string[]; countries: string[]; devices: Device[] }) =>
      apiPost<AddKeywordsResult>("/api/keywords", input),
    onSuccess: async (result) => {
      toast.success(describeAddKeywords(result));
      await invalidate.bootstrap();
    },
    onError: (error) => toast.error(error.message),
  });
}
