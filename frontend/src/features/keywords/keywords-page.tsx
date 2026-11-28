import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";
import { Page } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { apiPost } from "@/lib/api";
import { countryFlag, deviceName } from "@/lib/format";
import { useCurrentBootstrap, useInvalidate } from "@/lib/queries";
import { useSelection } from "@/lib/selection";
import type { Ranking, TopApp } from "@/lib/types";
import { AddKeywordsDialog } from "./add-keywords-dialog";
import { KeywordHistoryCard, LosingToCard, OverallRankCard } from "./history-cards";
import {
  checkedWithinDay,
  dailyKeywordSnapshots,
  losingTo,
  sortRankings,
  storefrontSummaries,
  summarizeRanks,
  type SortField,
} from "./keyword-utils";
import { MetricCards } from "./metric-cards";
import { RankingsTable, type SortState } from "./rankings-table";
import { StorefrontOverview } from "./storefront-overview";

interface CheckResult {
  checks: number;
  searches: number;
  failures: number;
  skipped: number;
  rankings: Ranking[];
}

interface RunProgress {
  checkingId: number | null;
  queued: Set<number>;
  done: number;
  total: number;
}

const NO_QUEUE: ReadonlySet<number> = new Set();

export function KeywordsPage() {
  const bootstrap = useCurrentBootstrap();
  const data = bootstrap.data;
  const [selection, select] = useSelection({ appId: data?.selectedAppId, country: data?.selectedCountry });
  const { appId, country, device } = selection;
  const invalidate = useInvalidate();
  const queryClient = useQueryClient();

  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<SortState>({ field: "rank", direction: "asc" });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [pendingStop, setPendingStop] = useState<Ranking | null>(null);
  const [progress, setProgress] = useState<RunProgress | null>(null);
  // Rows refreshed during a run, shown in place until the bootstrap reloads.
  const [patches, setPatches] = useState<Map<number, Ranking>>(() => new Map());
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const rankings = useMemo(
    () => (data?.rankings ?? []).map((row) => patches.get(row.targetId) ?? row),
    [data?.rankings, patches],
  );
  const marketRows = useMemo(
    () => rankings.filter((row) => row.country === country && row.device === device),
    [rankings, country, device],
  );
  const visibleRows = useMemo(() => {
    const needle = filter.trim().toLocaleLowerCase();
    const filtered = needle ? marketRows.filter((row) => row.keyword.toLocaleLowerCase().includes(needle)) : marketRows;
    return sortRankings(filtered, sort.field, sort.direction);
  }, [marketRows, filter, sort]);
  const snapshots = useMemo(
    () => dailyKeywordSnapshots(data?.history ?? [], country, device),
    [data?.history, country, device],
  );
  const competitorsAhead = useMemo(() => losingTo(marketRows, appId), [marketRows, appId]);
  const summary = useMemo(() => summarizeRanks(marketRows), [marketRows]);
  const storefronts = useMemo(
    () => storefrontSummaries(rankings, data?.countries ?? [], data?.targetCounts ?? {}, device),
    [rankings, data?.countries, data?.targetCounts, device],
  );
  const marketKey = `${country}:${device}`;
  const trackedCount = Number(data?.targetCounts?.[marketKey] ?? 0);
  const selected = marketRows.find((row) => row.targetId === selectedId) ?? null;
  const market = `${countryFlag(country)} ${country.toUpperCase()} · ${deviceName(device)}`;

  const onSort = (field: SortField) =>
    setSort((current) =>
      current.field === field
        ? { field, direction: current.direction === "asc" ? "desc" : "asc" }
        : { field, direction: "asc" },
    );

  const runCheck = useMutation({
    mutationFn: async () => {
      if (!appId) throw new Error("Choose an app first.");
      const due = marketRows.filter((row) => !checkedWithinDay(row));
      let skipped = marketRows.length - due.length;
      if (!due.length) return { checked: 0, failures: 0, skipped, total: marketRows.length };
      let checked = 0;
      let failures = 0;
      const queued = new Set(due.map((row) => row.targetId));
      for (const [index, row] of due.entries()) {
        if (!mounted.current) break;
        queued.delete(row.targetId);
        setProgress({ checkingId: row.targetId, queued: new Set(queued), done: index, total: due.length });
        let patched: Ranking;
        try {
          const result = await apiPost<CheckResult>("/api/check", {
            appId,
            country: row.country,
            device: row.device,
            keyword: row.keyword,
          });
          failures += Number(result.failures || 0);
          skipped += Number(result.skipped || 0);
          checked += Number(result.checks || 0);
          patched = result.rankings?.find((item) => item.targetId === row.targetId) ?? result.rankings?.[0] ?? row;
        } catch (error) {
          failures += 1;
          patched = { ...row, status: "error", error: error instanceof Error ? error.message : "Apple check failed" };
        }
        setPatches((current) => new Map(current).set(patched.targetId, patched));
      }
      return { checked, failures, skipped, total: marketRows.length };
    },
    onSuccess: ({ checked, failures, skipped, total }) => {
      if (!checked && !failures) {
        if (total) toast.info(`All ${total} keyword rows were checked within the last 24 hours.`);
        else toast.error("No checked keyword rows are available to refresh.");
        return;
      }
      const skippedText = skipped
        ? ` ${skipped} row${skipped === 1 ? " was" : "s were"} skipped because data already exists from the last 24 hours.`
        : "";
      const message = `Checked ${checked} keyword row${checked === 1 ? "" : "s"}${failures ? `; ${failures} failed` : ""}.${skippedText}`;
      if (failures) toast.warning(message);
      else toast.success(message);
    },
    onError: (error) => toast.error(error.message),
    onSettled: async () => {
      setProgress(null);
      await invalidate.bootstrap();
      if (mounted.current) setPatches(new Map());
    },
  });

  const stopTracking = useMutation({
    mutationFn: (row: Ranking) => apiPost("/api/targets/deactivate", { targetId: row.targetId }),
    onSuccess: async (_result, row) => {
      toast.success(`Stopped tracking “${row.keyword}” in ${row.country.toUpperCase()} · ${deviceName(row.device)}`);
      if (row.targetId === selectedId) setSelectedId(null);
      await invalidate.bootstrap();
    },
    onError: (error) => toast.error(error.message),
    onSettled: () => setPendingStop(null),
  });

  const addCompetitor = useMutation({
    mutationFn: (app: TopApp) =>
      apiPost("/api/competitors/add", {
        appId,
        competitorAppId: app.appId,
        name: app.name,
        artworkUrl: app.artworkUrl || null,
      }),
    onSuccess: async (_result, app) => {
      toast.success(`${app.name} added to competitors. Refresh rankings in Competitors to load its positions.`);
      await queryClient.invalidateQueries({ queryKey: ["competitors"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const running = runCheck.isPending;
  const percent = progress ? Math.round((progress.done / Math.max(progress.total, 1)) * 100) : 0;

  const actions = (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => runCheck.mutate()}
        disabled={!appId || running || !marketRows.length}
      >
        <RefreshCw className={running ? "animate-spin motion-reduce:animate-none" : undefined} />
        <span className="hidden sm:inline">
          {progress ? `Checking ${progress.done + 1}/${progress.total}` : "Run check"}
        </span>
      </Button>
      <Button size="sm" onClick={() => setAddOpen(true)} disabled={!appId}>
        <Plus /> <span className="hidden sm:inline">Add keywords</span>
      </Button>
    </>
  );

  return (
    <Page title="Keywords" actions={actions}>
      {bootstrap.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load keywords</AlertTitle>
          <AlertDescription>{bootstrap.error.message}</AlertDescription>
        </Alert>
      ) : null}

      {!data && bootstrap.isLoading ? (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
          </div>
          <Skeleton className="h-96" />
        </>
      ) : null}

      {data && !appId ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyTitle>No app selected</EmptyTitle>
            <EmptyDescription>Add an App Store app from the sidebar to start tracking keywords.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {data && appId && storefronts.length > 1 ? (
        <StorefrontOverview
          summaries={storefronts}
          selected={country}
          device={device}
          onSelect={(code) => {
            setSelectedId(null);
            select({ country: code });
          }}
        />
      ) : null}

      {data && appId && !marketRows.length ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <KeyRound />
            </EmptyMedia>
            <EmptyTitle>
              {trackedCount > 0 ? "No checks yet" : "No keywords tracked"} for {market}
            </EmptyTitle>
            <EmptyDescription>
              {trackedCount > 0
                ? "Run a check to retrieve the first rankings for this storefront."
                : "Add the exact searches you want to rank for. Each one is checked against Apple right away, and stays on this Mac."}
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button onClick={() => setAddOpen(true)}>
              <Plus /> Add keywords
            </Button>
          </EmptyContent>
        </Empty>
      ) : null}

      {data && appId && marketRows.length ? (
        <>
          <MetricCards
            summary={summary}
            trends={data.metricTrends?.[marketKey] ?? {}}
            trends30d={data.metricTrends30d?.[marketKey] ?? {}}
            snapshots={snapshots}
            country={country}
            device={device}
          />

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Rankings</CardTitle>
              <CardDescription>
                {market} · {marketRows.length} keyword{marketRows.length === 1 ? "" : "s"}. Popularity is Apple Ads&rsquo;
                score for the exact query; values with ~ are local estimates.
              </CardDescription>
              <CardAction>
                <div className="relative">
                  <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" aria-hidden />
                  <Input
                    type="search"
                    value={filter}
                    onChange={(event) => setFilter(event.target.value)}
                    placeholder="Filter keywords"
                    aria-label="Filter keywords"
                    className="h-8 w-36 pl-8 sm:w-52"
                  />
                </div>
              </CardAction>
            </CardHeader>
            {progress ? (
              <div className="grid gap-1.5 px-6">
                <div className="text-muted-foreground flex justify-between text-xs">
                  <span>Checking Apple one keyword at a time</span>
                  <span className="tabular-nums">
                    {progress.done}/{progress.total}
                  </span>
                </div>
                <Progress value={Math.max(4, percent)} aria-label="Rank check progress" />
              </div>
            ) : null}
            <CardContent className="px-0">
              {visibleRows.length ? (
                <RankingsTable
                  rows={visibleRows}
                  sort={sort}
                  onSort={onSort}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  checkingId={progress?.checkingId ?? null}
                  queued={progress?.queued ?? NO_QUEUE}
                  ownAppleId={appId}
                  onAddCompetitor={(app) => addCompetitor.mutate(app)}
                  addingCompetitor={addCompetitor.isPending}
                  onStopTracking={setPendingStop}
                  busy={running || stopTracking.isPending}
                />
              ) : (
                <p className="text-muted-foreground px-6 py-8 text-center text-sm">
                  No matching keywords. Try a different filter.
                </p>
              )}
            </CardContent>
          </Card>

          <div className="grid items-start gap-6 lg:grid-cols-2">
            <KeywordHistoryCard ranking={selected} history={data.history ?? []} />
            <OverallRankCard snapshots={snapshots} country={country} device={device} />
          </div>

          <LosingToCard apps={competitorsAhead} country={country} device={device} />
        </>
      ) : null}

      {appId ? (
        <AddKeywordsDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          appId={appId}
          countries={(data?.countries ?? []).filter((item) => item.active)}
          defaultCountry={country}
          defaultDevice={device}
        />
      ) : null}

      <AlertDialog open={pendingStop != null} onOpenChange={(open) => !open && !stopTracking.isPending && setPendingStop(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Stop tracking “{pendingStop?.keyword}”?</AlertDialogTitle>
            <AlertDialogDescription>
              Checks stop for {pendingStop ? `${pendingStop.country.toUpperCase()} · ${deviceName(pendingStop.device)}` : "this storefront"}.
              Rank history stays stored, and adding the keyword again resumes tracking.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={stopTracking.isPending}>Keep tracking</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={stopTracking.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (pendingStop) stopTracking.mutate(pendingStop);
              }}
            >
              Stop tracking
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Page>
  );
}
