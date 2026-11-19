import { useCallback } from "react";
import { useSearchParams } from "react-router";
import type { Device } from "./types";

// The selected app, storefront, and device live in the URL (hash route query),
// so views are linkable and the browser back button behaves.

export interface Selection {
  appId: number | null;
  country: string;
  device: Device;
}

export function useSelection(defaults?: { appId?: number | null; country?: string }) {
  const [params, setParams] = useSearchParams();
  const rawApp = params.get("app");
  const selection: Selection = {
    appId: rawApp ? Number(rawApp) : (defaults?.appId ?? null),
    country: params.get("country") || defaults?.country || "us",
    device: params.get("device") === "ipad" ? "ipad" : "iphone",
  };

  const update = useCallback(
    (patch: Partial<Selection>) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (patch.appId !== undefined) {
            if (patch.appId === null) next.delete("app");
            else next.set("app", String(patch.appId));
          }
          if (patch.country !== undefined) next.set("country", patch.country);
          if (patch.device !== undefined) next.set("device", patch.device);
          return next;
        },
        { replace: false },
      );
    },
    [setParams],
  );

  return [selection, update] as const;
}
