import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { apiGet, apiPost } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

interface BackgroundSyncStatus {
  supported: boolean;
  enabled: boolean;
  plistPath: string;
  program: string[] | null;
  programMissing: boolean;
  lastRunAt: string | null;
  logPath: string;
}

const KEY = ["background-sync"] as const;

/** Opt-in daily rank checks while the app is closed (a macOS LaunchAgent). */
export function BackgroundSyncDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const client = useQueryClient();
  const status = useQuery({
    queryKey: KEY,
    queryFn: ({ signal }) => apiGet<BackgroundSyncStatus>("/api/background-sync", undefined, signal),
    enabled: open,
  });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => apiPost<BackgroundSyncStatus>("/api/background-sync", { enabled }),
    onSuccess: (result) => {
      client.setQueryData(KEY, result);
      toast.success(result.enabled ? "Daily background checks are on" : "Daily background checks are off");
    },
    onError: (error) => toast.error(error.message),
  });
  const data = status.data;

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Background checks</DialogTitle>
          <DialogDescription>
            Check every tracked keyword once a day, even when Local ASO is closed. Keywords checked in the last 24
            hours are skipped, and Apple Ads popularity is refreshed too.
          </DialogDescription>
        </DialogHeader>
        {data && !data.supported ? (
          <Alert>
            <AlertDescription>
              Background checks are available on macOS. Elsewhere, schedule <code>aso sync</code> with cron or Task
              Scheduler.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="grid gap-4">
            <div className="flex items-start justify-between gap-4 rounded-lg border p-4">
              <Label htmlFor="background-sync" className="grid gap-1 font-normal">
                <span className="font-medium">Check ranks daily</span>
                <span className="text-muted-foreground text-sm">
                  Runs at login and every 24 hours while your Mac is awake; a missed run happens on wake.
                </span>
              </Label>
              <Switch
                id="background-sync"
                checked={data?.enabled ?? false}
                disabled={!data || toggle.isPending}
                onCheckedChange={(checked) => toggle.mutate(checked)}
              />
            </div>
            {data?.programMissing ? (
              <Alert variant="destructive">
                <AlertDescription>
                  The scheduled check points to an app that has moved. Turn it off and on again to fix it.
                </AlertDescription>
              </Alert>
            ) : null}
            {data?.enabled ? (
              <p className="text-muted-foreground text-xs">
                Last run: {data.lastRunAt ? formatDateTime(data.lastRunAt) : "not yet"} · Log: {data.logPath}
              </p>
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
