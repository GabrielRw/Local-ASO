import { useEffect, useRef } from "react";
import { RefreshCw, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { useInvalidate, useSyncStatus } from "@/lib/queries";
import { formatDateTime, relativeDays } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Background rank sync (startup and every 24 hours). Reloads the dashboard
 * once a running sync finishes so the new ranks appear without a refresh.
 */
export function SyncIndicator() {
  const { data: sync } = useSyncStatus();
  const invalidate = useInvalidate();
  const wasRunning = useRef(false);

  useEffect(() => {
    if (!sync) return;
    if (wasRunning.current && sync.state !== "running") {
      void invalidate.bootstrap();
      if (sync.targets > 0) {
        toast.success(
          `Background sync checked ${sync.targets} keyword${sync.targets === 1 ? "" : "s"}` +
            (sync.failures ? ` (${sync.failures} failed)` : ""),
        );
      }
    }
    wasRunning.current = sync.state === "running";
  }, [sync, invalidate]);

  if (!sync || sync.state === "disabled" || sync.state === "idle") return null;
  const running = sync.state === "running";
  const failed = sync.state === "error";
  const label = running
    ? "Checking stale keywords…"
    : failed
      ? "Last sync failed"
      : `Ranks synced ${relativeDays(sync.finishedAt)}`;
  const title = failed
    ? (sync.error ?? "The background sync failed.")
    : sync.finishedAt
      ? `Last finished ${formatDateTime(sync.finishedAt)}. Next ${formatDateTime(sync.nextRunAt)}.`
      : undefined;

  return (
    <div
      role="status"
      title={title}
      className={cn(
        "text-muted-foreground flex items-center gap-2 rounded-md px-2 py-1.5 text-xs group-data-[collapsible=icon]:hidden",
        failed && "text-destructive",
      )}
    >
      {failed ? (
        <TriangleAlert className="size-3.5 shrink-0" />
      ) : (
        <RefreshCw className={cn("size-3.5 shrink-0", running && "animate-spin motion-reduce:animate-none")} />
      )}
      <span className="truncate">{label}</span>
    </div>
  );
}
