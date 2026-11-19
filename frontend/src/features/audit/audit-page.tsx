import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Bot, Play, Square } from "lucide-react";
import { toast } from "sonner";
import { Page } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiPost } from "@/lib/api";
import { countryFlag, deviceName, formatDateTime, relativeDays } from "@/lib/format";
import { useAudit, useCurrentBootstrap, useInvalidate } from "@/lib/queries";
import { useSelection } from "@/lib/selection";
import type { AuditLatest, AuditRun } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AgentSheet } from "./agent-sheet";
import { CompetitorNameKeywords, DiscoverMore, FindingsCard, RecommendedKeywords, ScoreCard } from "./audit-results";
import { scoreLabel } from "@/components/score-gauge";

const STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  analyzing: "Analyzing",
  localizing: "Reviewing language",
  checking: "Checking Apple",
  synthesizing: "Editing findings",
  running: "Running",
  success: "Complete",
  partial: "Partial",
  error: "Needs retry",
  cancelled: "Cancelled",
};

function isActive(run: { status: string } | null | undefined): boolean {
  return run?.status === "queued" || run?.status === "running";
}

export function AuditPage() {
  const bootstrap = useCurrentBootstrap();
  const [selection, select] = useSelection({
    appId: bootstrap.data?.selectedAppId,
    country: bootstrap.data?.selectedCountry,
  });
  const appId = selection.appId;
  const audit = useAudit(appId, selection.country, selection.device);
  const invalidate = useInvalidate();
  const [agentOpen, setAgentOpen] = useState(false);
  const [provider, setProvider] = useState<string | null>(null);

  const payload = audit.data;
  const run = payload?.run ?? null;
  const providers = payload?.providers ?? [];
  const anyProvider = providers.some((item) => item.available);
  const chosenProvider = provider ?? payload?.defaultProvider ?? "auto";
  const active = isActive(run);

  const start = useMutation({
    mutationFn: () =>
      apiPost("/api/audits", {
        appId,
        scope: "country",
        country: selection.country,
        device: selection.device,
        provider: chosenProvider,
      }),
    onSuccess: () => invalidate.audit(),
    onError: (error) => toast.error(error.message),
  });
  const cancel = useMutation({
    mutationFn: () => apiPost("/api/audits/cancel", { appId, runId: run?.id }),
    onSuccess: () => invalidate.audit(),
    onError: (error) => toast.error(error.message),
  });
  const expand = useMutation({
    mutationFn: (instruction: string) =>
      apiPost<{ iteration?: { added: number } }>("/api/audits/expand", {
        appId,
        runId: run?.id,
        country: selection.country,
        instruction,
      }),
    onSuccess: async (result) => {
      const added = result.iteration?.added ?? 0;
      toast.success(`${added} new keyword${added === 1 ? "" : "s"} checked and added to this audit`);
      await invalidate.audit();
    },
    onError: (error) => toast.error(error.message),
  });

  const actions = (
    <>
      <Button variant="ghost" size="sm" onClick={() => setAgentOpen(true)}>
        <Bot /> <span className="hidden md:inline">AI agent</span>
      </Button>
      <Select value={chosenProvider} onValueChange={setProvider}>
        <SelectTrigger size="sm" className="hidden w-[7.5rem] md:flex" aria-label="Local agent">
          <SelectValue />
        </SelectTrigger>
        <SelectContent align="end">
          <SelectItem value="auto">Auto-detect</SelectItem>
          {providers.map((item) => (
            <SelectItem key={item.id} value={item.id} disabled={!item.available}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {active ? (
        <Button size="sm" variant="outline" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
          <Square /> Cancel
        </Button>
      ) : (
        <Button size="sm" onClick={() => start.mutate()} disabled={!appId || !anyProvider || start.isPending}>
          <Play /> {run ? "Rerun audit" : "Run audit"}
        </Button>
      )}
    </>
  );

  const country = run?.countries.find((item) => item.code === selection.country) ?? run?.countries[0];
  const tracked = bootstrap.data?.rankings ?? [];

  return (
    <Page title="Audit" actions={actions}>
      {payload && !anyProvider ? (
        <Alert>
          <Bot />
          <AlertTitle>Set up a local AI agent to run audits</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-3">
            Install the Claude or Codex CLI and sign in, or point Local ASO to its executable.
            <Button size="sm" variant="outline" onClick={() => setAgentOpen(true)}>
              Open agent settings
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {audit.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load the audit</AlertTitle>
          <AlertDescription>{audit.error.message}</AlertDescription>
        </Alert>
      ) : null}

      {!payload && audit.isLoading ? (
        <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
      ) : null}

      {run ? <RunStatus run={run} language={payload?.auditLanguage ?? "English"} /> : null}

      {payload && !run ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Play />
            </EmptyMedia>
            <EmptyTitle>
              No audit yet for {countryFlag(selection.country)} {selection.country.toUpperCase()} on{" "}
              {deviceName(selection.device)}
            </EmptyTitle>
            <EmptyDescription>
              The audit scores your listing from 0 to 100, finds the searches it misses, and checks every phrase
              against Apple. It takes about two minutes and stays on this Mac.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button onClick={() => start.mutate()} disabled={!appId || !anyProvider || start.isPending}>
              <Play /> Run audit
            </Button>
          </EmptyContent>
        </Empty>
      ) : null}

      {run && country && country.status !== "error" && !active ? (
        <>
          <div className="grid items-start gap-6 lg:grid-cols-[20rem_1fr]">
            <ScoreCard country={country} />
            <FindingsCard country={country} device={selection.device} tracked={tracked} />
          </div>
          {appId ? (
            <>
              <RecommendedKeywords appId={appId} country={country} device={selection.device} tracked={tracked} />
              <CompetitorNameKeywords appId={appId} country={country} device={selection.device} />
            </>
          ) : null}
          <DiscoverMore
            disabled={!anyProvider}
            pending={expand.isPending}
            onDiscover={(instruction) => expand.mutate(instruction)}
          />
        </>
      ) : null}

      {run && country?.status === "error" && !active ? (
        <Alert variant="destructive">
          <AlertTitle>This audit needs a retry</AlertTitle>
          <AlertDescription>{country.error ?? run.error ?? "The audit did not finish."}</AlertDescription>
        </Alert>
      ) : null}

      {payload?.latestByCountry?.length ? (
        <MarketsOverview
          latest={payload.latestByCountry.filter((item) => item.device === selection.device)}
          current={selection.country}
          onSelect={(code) => select({ country: code })}
        />
      ) : null}

      <AgentSheet
        open={agentOpen}
        onOpenChange={setAgentOpen}
        providers={providers}
        provider={chosenProvider}
        paths={payload?.agentPaths ?? { codex: "", claude: "" }}
      />
    </Page>
  );
}

function RunStatus({ run, language }: { run: AuditRun; language: string }) {
  const active = isActive(run);
  const stage = run.countries[0]?.status;
  const label = active && stage ? (STATUS_LABEL[stage] ?? STATUS_LABEL[run.status]) : STATUS_LABEL[run.status];
  const percent = run.progress.total ? Math.round((run.progress.completed / run.progress.total) * 100) : 0;
  return (
    <Card className="gap-3 py-4">
      <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Badge
          variant={run.status === "error" ? "destructive" : active ? "default" : "secondary"}
          className={cn(active && "animate-pulse motion-reduce:animate-none")}
        >
          {label}
        </Badge>
        <span className="text-sm font-medium">
          {countryFlag(run.country)} {run.country.toUpperCase()} · {language} · {deviceName(run.device)}
        </span>
        <span className="text-muted-foreground text-xs">
          {active ? "discovery → language → Apple → editor" : `Finished ${formatDateTime(run.completedAt)}`}
        </span>
        {active ? <Progress value={Math.max(8, percent)} className="basis-full" aria-label="Audit progress" /> : null}
      </CardContent>
    </Card>
  );
}

function MarketsOverview({
  latest,
  current,
  onSelect,
}: {
  latest: AuditLatest[];
  current: string;
  onSelect: (country: string) => void;
}) {
  if (!latest.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">All markets</CardTitle>
        <CardDescription>Latest audit per storefront on this device. Select one to open it.</CardDescription>
      </CardHeader>
      <CardContent className="px-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Storefront</TableHead>
              <TableHead>Score</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="pr-6">Audited</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {latest.map((item) => (
              <TableRow
                key={`${item.country}-${item.device}`}
                data-state={item.country === current ? "selected" : undefined}
              >
                <TableCell className="pl-6">
                  <button
                    type="button"
                    className="font-medium underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
                    onClick={() => onSelect(item.country)}
                  >
                    {countryFlag(item.country)} {item.countryName}
                  </button>
                </TableCell>
                <TableCell>
                  <span className="tabular-nums">{item.score ?? "—"}</span>
                  <span className="text-muted-foreground ml-2 text-xs">{scoreLabel(item.score)}</span>
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">{STATUS_LABEL[item.status] ?? item.status}</TableCell>
                <TableCell className="text-muted-foreground pr-6 text-sm">{relativeDays(item.completedAt ?? item.createdAt)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
