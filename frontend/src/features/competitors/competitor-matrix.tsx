import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { RefreshCw, Trophy, Users, X } from "lucide-react";
import { toast } from "sonner";
import { AppIcon } from "@/components/app-icon";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { apiPost } from "@/lib/api";
import { countryFlag, deviceName, formatDateTime, toneText } from "@/lib/format";
import type { Device } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useCompetitorCache, type CompetitorMatrix, type MatrixApp, type MatrixKeyword } from "./api";
import { bestRankAppIds, cellsByApp, matrixCellView } from "./matrix";

export function CompetitorMatrixCard({
  matrix,
  appId,
  country,
  device,
}: {
  matrix: CompetitorMatrix;
  appId: number;
  country: string;
  device: Device;
}) {
  const cache = useCompetitorCache();
  const [removing, setRemoving] = useState<MatrixApp | null>(null);

  const refresh = useMutation({
    mutationFn: () => apiPost<CompetitorMatrix>("/api/competitors/refresh", { appId, country, device }),
    onSuccess: (result) => {
      cache.setMatrix(appId, country, device, result);
      const searches = result.refresh?.searches ?? 0;
      const failures = result.refresh?.failures ?? 0;
      const message = `Competitor rankings refreshed: ${searches} search${searches === 1 ? "" : "es"}${failures ? `, ${failures} failed` : ""}`;
      if (failures) toast.warning(message);
      else toast.success(message);
    },
    onError: (error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (app: MatrixApp) => apiPost("/api/competitors/remove", { competitorAppId: app.appleAppId }),
    onSuccess: async (_result, app) => {
      toast.success(`${app.name} removed from competitors`);
      setRemoving(null);
      await cache.invalidateMatrix();
    },
    onError: (error) => toast.error(error.message),
  });

  const apps = matrix.apps;
  const keywords = matrix.keywords;

  return (
    <Card>
      <CardHeader>
        <CardDescription>
          {countryFlag(country)} {country.toUpperCase()} · {deviceName(device)} · {keywords.length} tracked keyword
          {keywords.length === 1 ? "" : "s"}
        </CardDescription>
        <CardTitle className="text-base">{matrix.app.name} vs competitors</CardTitle>
        <CardAction className="flex items-center gap-2">
          <Badge variant="outline" className="hidden font-normal sm:inline-flex">
            {matrix.lastCheckedAt ? `Checked ${formatDateTime(matrix.lastCheckedAt)}` : "Not checked yet"}
          </Badge>
          <Button
            size="sm"
            onClick={() => refresh.mutate()}
            disabled={!matrix.competitorCount || !keywords.length || refresh.isPending}
          >
            {refresh.isPending ? <Spinner /> : <RefreshCw />}
            {refresh.isPending ? "Refreshing…" : "Refresh rankings"}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-4 px-0">
        {!matrix.competitorCount ? (
          <div className="px-6">
            <Empty className="border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Users />
                </EmptyMedia>
                <EmptyTitle>No competitors yet</EmptyTitle>
                <EmptyDescription>
                  Open Keywords and select an app icon in a keyword&rsquo;s Top 5 to add it here. Its rank is then
                  checked against every keyword you track in this storefront.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          </div>
        ) : (
          <p className="text-muted-foreground px-6 text-sm">
            Add more competitors from the Top 5 icons in Keywords. Ranks come from one Apple search per keyword; apps
            outside the returned window show as &gt;limit.
          </p>
        )}
        <Table aria-busy={refresh.isPending}>
          <TableHeader>
            <TableRow>
              <TableHead className="bg-card sticky left-0 z-10 min-w-44 pl-6 align-bottom">Keyword</TableHead>
              {apps.map((app) => (
                <AppHeader key={app.appleAppId} app={app} onRemove={() => setRemoving(app)} />
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {keywords.length ? (
              keywords.map((row) => (
                <KeywordRow key={row.targetId} row={row} apps={apps} pending={refresh.isPending} />
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={apps.length + 1} className="text-muted-foreground py-8 pl-6 text-sm">
                  No tracked keywords for this storefront and device.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>

      <AlertDialog open={removing != null} onOpenChange={(open) => !open && setRemoving(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove {removing?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              It leaves the competitor matrix for every app and storefront. You can add it again from a keyword&rsquo;s
              Top 5 in Keywords.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={remove.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (removing) remove.mutate(removing);
              }}
            >
              {remove.isPending ? <Spinner /> : null} Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function AppHeader({ app, onRemove }: { app: MatrixApp; onRemove: () => void }) {
  return (
    <TableHead className={cn("h-auto min-w-28 py-3 text-center align-bottom", app.isPrimary && "bg-muted/40")}>
      <div className="flex flex-col items-center gap-1.5">
        <div className="relative">
          <AppIcon name={app.name} artworkUrl={app.artworkUrl} className="size-9" />
          {app.isPrimary ? null : (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="icon-xs"
                  className="bg-background absolute -top-1.5 -right-2 size-5 rounded-full"
                  aria-label={`Remove ${app.name} from competitors`}
                  onClick={onRemove}
                >
                  <X className="size-3" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Remove from competitors</TooltipContent>
            </Tooltip>
          )}
        </div>
        <span className="max-w-28 truncate text-xs font-medium" title={app.name}>
          {app.name}
        </span>
        {app.isPrimary ? <span className="text-muted-foreground text-[11px] font-normal">Your app</span> : null}
      </div>
    </TableHead>
  );
}

function KeywordRow({ row, apps, pending }: { row: MatrixKeyword; apps: MatrixApp[]; pending: boolean }) {
  const byApp = useMemo(() => cellsByApp(row.cells), [row.cells]);
  const best = useMemo(() => bestRankAppIds(row.cells), [row.cells]);
  return (
    <TableRow>
      <TableHead scope="row" className="bg-card sticky left-0 z-10 max-w-56 truncate pl-6 font-medium">
        {row.keyword}
      </TableHead>
      {apps.map((app) => {
        const view = matrixCellView(byApp.get(app.appleAppId), app.name);
        const isBest = best.has(app.appleAppId);
        return (
          <TableCell
            key={app.appleAppId}
            title={isBest ? `${view.title} · best in this row` : view.title}
            className={cn(
              "text-center tabular-nums",
              app.isPrimary && "bg-muted/40",
              pending && "animate-pulse motion-reduce:animate-none",
            )}
          >
            <span
              className={cn(
                "inline-flex min-w-12 items-center justify-center gap-1 rounded-md px-1.5 py-0.5 text-sm",
                toneText[view.tone],
                isBest && "bg-emerald-500/10 font-semibold ring-1 ring-emerald-500/30",
              )}
            >
              {isBest ? <Trophy className="size-3" aria-hidden /> : null}
              {view.label}
              {isBest ? <span className="sr-only"> (best in row)</span> : null}
            </span>
          </TableCell>
        );
      })}
    </TableRow>
  );
}
