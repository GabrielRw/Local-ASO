import { ArrowDown, ArrowUp, ArrowUpDown, LoaderCircle, Plus, Star, Swords, X } from "lucide-react";
import { AppIcon } from "@/components/app-icon";
import { CompetitorBadge } from "@/components/competitor-badge";
import { InfoTip } from "@/components/info-tip";
import { DemandValue, DifficultyValue, OpportunityValue } from "@/components/metric";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatCompact, formatDate, rankLabel, shortOpportunity } from "@/lib/format";
import type { Ranking, TopApp } from "@/lib/types";
import { cn } from "@/lib/utils";
import { COLUMN_INFO } from "./column-info";
import { changeTone, type SortDirection, type SortField } from "./keyword-utils";

export interface SortState {
  field: SortField;
  direction: SortDirection;
}

const changeClass: Record<ReturnType<typeof changeTone>, string> = {
  new: "text-sky-600 dark:text-sky-400",
  lost: "text-rose-600 dark:text-rose-400",
  up: "text-emerald-600 dark:text-emerald-400",
  down: "text-rose-600 dark:text-rose-400",
  flat: "text-muted-foreground",
};

function signalClass(signal: string): string {
  if (signal.startsWith("Defend")) return "text-emerald-600 dark:text-emerald-400";
  if (signal.includes("Growth")) return "text-amber-600 dark:text-amber-400";
  return "text-muted-foreground";
}

function SortHead({
  field,
  label,
  sort,
  onSort,
  className,
}: {
  field: SortField;
  label: string;
  sort: SortState;
  onSort: (field: SortField) => void;
  className?: string;
}) {
  const active = sort.field === field;
  const Icon = !active ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown;
  const info = COLUMN_INFO[field];
  return (
    <TableHead
      className={className}
      aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
    >
      <span className="inline-flex items-center gap-0.5">
        <button
          type="button"
          onClick={() => onSort(field)}
          className={cn(
            "hover:text-foreground focus-visible:ring-ring/50 -mx-1 inline-flex items-center gap-1 rounded-sm px-1 focus-visible:ring-[3px] focus-visible:outline-none",
            active ? "text-foreground" : "text-muted-foreground",
          )}
        >
          {label}
          <Icon className={cn("size-3.5", !active && "opacity-50")} aria-hidden />
        </button>
        {info ? <InfoTip info={info} /> : null}
      </span>
    </TableHead>
  );
}

function RankCell({ row, state }: { row: Ranking; state: "checking" | "queued" | null }) {
  if (state === "checking") {
    return (
      <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs">
        <LoaderCircle className="size-3.5 animate-spin motion-reduce:animate-none" aria-hidden /> Checking
      </span>
    );
  }
  if (state === "queued") return <span className="text-muted-foreground text-xs">Queued</span>;
  if (row.status === "error") {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} className="text-destructive cursor-help text-xs font-medium focus-visible:underline focus-visible:outline-none">
            Check failed
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-64 text-pretty">{row.error || "Apple check failed"}</TooltipContent>
      </Tooltip>
    );
  }
  const top = row.found && row.rank != null && row.rank <= 10;
  return (
    <span className={cn("font-medium tabular-nums", top ? "text-emerald-600 dark:text-emerald-400" : !row.found && "text-muted-foreground")}>
      {rankLabel(row)}
    </span>
  );
}

function ratingText(app: TopApp): string {
  if (app.averageRating == null && app.ratingCount == null) return "Rating unavailable";
  const rating = app.averageRating != null ? app.averageRating.toFixed(1) : "—";
  const count =
    app.ratingCount != null ? `${formatCompact(app.ratingCount)} ${app.ratingCount === 1 ? "rating" : "ratings"}` : "no rating count";
  return `★ ${rating} · ${count}`;
}

function TopApps({
  apps,
  ownAppleId,
  onAddCompetitor,
  adding,
}: {
  apps: TopApp[];
  ownAppleId: number | null;
  onAddCompetitor: (app: TopApp) => void;
  adding: boolean;
}) {
  if (!apps.length) return <span className="text-muted-foreground">—</span>;
  return (
    <div className="flex -space-x-1.5">
      {apps.slice(0, 5).map((app) => {
        const own = app.appId === ownAppleId;
        return (
          <Popover key={`${app.position}-${app.appId}`}>
            <Tooltip>
              <TooltipTrigger asChild>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    aria-label={`Top result ${app.position}: ${app.name}. Open competitor actions.`}
                    className={cn(
                      "ring-background focus-visible:ring-ring relative rounded-[22%] ring-2 transition-transform hover:z-10 hover:-translate-y-0.5 focus-visible:z-10 focus-visible:outline-none motion-reduce:transition-none",
                      own && "ring-primary",
                    )}
                  >
                    <AppIcon name={app.name} artworkUrl={app.artworkUrl} className="size-7" />
                  </button>
                </PopoverTrigger>
              </TooltipTrigger>
              <TooltipContent className="grid gap-0.5 text-xs">
                <span className="font-medium">
                  #{app.position} {app.name}
                </span>
                <span className="opacity-80">{ratingText(app)}</span>
              </TooltipContent>
            </Tooltip>
            <PopoverContent align="start" className="grid w-64 gap-3">
              <div className="flex items-center gap-3">
                <AppIcon name={app.name} artworkUrl={app.artworkUrl} className="size-10" />
                <div className="grid min-w-0 gap-0.5">
                  <span className="truncate text-sm font-medium">{app.name}</span>
                  <span className="text-muted-foreground inline-flex items-center gap-1 text-xs">
                    <Star className="size-3" aria-hidden /> {ratingText(app).replace("★ ", "")}
                  </span>
                </div>
              </div>
              <Button size="sm" variant={own ? "secondary" : "default"} disabled={own || adding} onClick={() => onAddCompetitor(app)}>
                {own ? (
                  "Current primary app"
                ) : (
                  <>
                    <Plus /> Add to competitors
                  </>
                )}
              </Button>
            </PopoverContent>
          </Popover>
        );
      })}
    </div>
  );
}

export function RankingsTable({
  rows,
  sort,
  onSort,
  selectedId,
  onSelect,
  checkingId,
  queued,
  ownAppleId,
  onAddCompetitor,
  addingCompetitor,
  onStopTracking,
  onToggleCompetitor,
  busy,
  showOpportunity,
}: {
  /** Apple Ads connected: the Opportunity score. Otherwise the rank-based Signal. */
  showOpportunity: boolean;
  rows: Ranking[];
  sort: SortState;
  onSort: (field: SortField) => void;
  selectedId: number | null;
  onSelect: (targetId: number) => void;
  checkingId: number | null;
  queued: ReadonlySet<number>;
  ownAppleId: number | null;
  onAddCompetitor: (app: TopApp) => void;
  addingCompetitor: boolean;
  onStopTracking: (row: Ranking) => void;
  onToggleCompetitor: (row: Ranking) => void;
  busy: boolean;
}) {
  const head = { sort, onSort };
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortHead field="keyword" label="Keyword" className="pl-6" {...head} />
          <SortHead field="rank" label="Rank" {...head} />
          <SortHead field="popularity" label="Popularity" {...head} />
          <SortHead field="difficulty" label="Difficulty" {...head} />
          {showOpportunity ? (
            <SortHead field="opportunity" label="Opportunity" {...head} />
          ) : (
            <SortHead field="signal" label="Signal" {...head} />
          )}
          <SortHead field="top5" label="Top 5" {...head} />
          <SortHead field="change" label="Change" {...head} />
          <SortHead field="updated" label="Updated" {...head} />
          <TableHead className="pr-6 text-right">
            <span className="sr-only">Actions</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const selected = row.targetId === selectedId;
          const state = row.targetId === checkingId ? "checking" : queued.has(row.targetId) ? "queued" : null;
          return (
            <TableRow key={row.targetId} data-state={selected ? "selected" : undefined}>
              <TableCell className="max-w-64 pl-6">
                <div className="flex min-w-0 items-center gap-2">
                  <button
                    type="button"
                    aria-pressed={selected}
                    aria-label={`Show rank history for ${row.keyword}`}
                    title={row.keyword}
                    onClick={() => onSelect(row.targetId)}
                    className="block min-w-0 truncate text-left font-medium underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
                  >
                    {row.keyword}
                  </button>
                  {row.competitorBrand ? <CompetitorBadge /> : null}
                </div>
              </TableCell>
              <TableCell>
                <RankCell row={row} state={state} />
              </TableCell>
              <TableCell>
                <DemandValue source={row} market={row.country} />
              </TableCell>
              <TableCell>
                <DifficultyValue value={row.difficultyEstimate} />
              </TableCell>
              {showOpportunity ? (
                <TableCell>
                  <OpportunityValue value={row.opportunity} />
                </TableCell>
              ) : (
                <TableCell className={cn("text-sm", row.signal ? signalClass(row.signal) : "text-muted-foreground")}>
                  {row.signal ? shortOpportunity(row.signal) : "—"}
                </TableCell>
              )}
              <TableCell>
                <TopApps
                  apps={row.topApps ?? []}
                  ownAppleId={ownAppleId}
                  onAddCompetitor={onAddCompetitor}
                  adding={addingCompetitor}
                />
              </TableCell>
              <TableCell className={cn("text-sm font-medium tabular-nums", changeClass[changeTone(row.change)])}>
                {row.change}
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">{formatDate(row.checkedAt)}</TableCell>
              <TableCell className="pr-6 text-right whitespace-nowrap">
                <Button
                  size="icon-sm"
                  variant="ghost"
                  disabled={busy}
                  aria-pressed={row.competitorBrand}
                  aria-label={
                    row.competitorBrand
                      ? `${row.keyword} is not a competitor's name`
                      : `Mark ${row.keyword} as a competitor's name`
                  }
                  title={
                    row.competitorBrand
                      ? "Not a competitor's name: unmark it in every storefront"
                      : "Mark as a competitor's name (Apple Ads only), in every storefront"
                  }
                  className={row.competitorBrand ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground"}
                  onClick={() => onToggleCompetitor(row)}
                >
                  <Swords />
                </Button>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  disabled={busy}
                  aria-label={`Stop tracking ${row.keyword}`}
                  title="Stop tracking"
                  onClick={() => onStopTracking(row)}
                >
                  <X />
                </Button>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
