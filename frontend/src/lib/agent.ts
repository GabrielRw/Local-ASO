import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import type { AgentCheck } from "@/lib/types";

/** Ask one AI tool for a tiny answer: installed, signed in, working? */
export function useAgentCheck(onDone?: (result: AgentCheck) => void) {
  return useMutation({
    mutationFn: (provider: string) => apiPost<AgentCheck>("/api/agent/check", { provider }),
    onSuccess: (result) => {
      if (result.ok) toast.success(result.message);
      else toast.error(result.message);
      onDone?.(result);
    },
    onError: (error) => toast.error(error.message),
  });
}

/** Open Terminal with the tool's sign-in command; the user finishes there, then checks again. */
export function useAgentSignIn() {
  return useMutation({
    mutationFn: (provider: string) => apiPost<{ command: string }>("/api/agent/sign-in", { provider }),
    onSuccess: () => toast.success("Terminal opened. Finish signing in there, then choose Check."),
    onError: (error) => toast.error(error.message),
  });
}
