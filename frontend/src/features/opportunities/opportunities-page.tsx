import { Fragment, useImperativeHandle, useMemo, useRef, useState, type ReactNode, type Ref } from "react";
import { flushSync } from "react-dom";
import { useLocation, useNavigate } from "react-router";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ChevronRight, Lightbulb, Megaphone, Search, Store } from "lucide-react";
import { AppIcon } from "@/components/app-icon";
import { CompetitorBadge } from "@/components/competitor-badge";
import { InfoTip, type MetricExplanation } from "@/components/info-tip";
import { DemandValue, DifficultyValue, OpportunityValue } from "@/components/metric";
import { Page } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { changeTone } from "@/features/keywords/keyword-utils";
import { countryFlag, deviceName, rankLabel } from "@/lib/format";
import { useCurrentBootstrap } from "@/lib/queries";
import { useSelection } from "@/lib/selection";
import type { Ranking } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  actionPlan,
  FIRST_DIRECTION,
  filterGroups,
  groupByKeyword,
  SCOPES,
  sortGroups,
  type GroupSortField,
  type KeywordGroup,
  type Limits,
  type Scope,
} from "./opportunity-utils";

const PAGE_SIZE = 50;

const INFO: Partial<Record<GroupSortField, MetricExplanation>> = {
  opportunity: {
    title: "Opportunity",
    summary: "The keyword's opportunity added up over every storefront that tracks it.",
    formula: "Σ popularity × (100 − difficulty) ÷ 100 × (1 − rank^−1.2)",
    details: ["Storefronts without Apple Ads popularity or a difficulty estimate add nothing."],
  },
  market: {
    title: "Best market",
    summary: "The storefront with the most opportunity left for this keyword, and its score there.",
  },
  coverage: {
    title: "Top 10 · 50",
    summary: "In how many of its storefronts the app is in the top 10, then in the top 50, out of those that track it.",
  },
  difficulty: {
    title: "Difficulty",
    summary: "Median difficulty over its storefronts, with the lowest and highest below when they differ.",
  },
  change: {
    title: "Change",
    summary: "Storefronts where the rank went up ▲ (or entered Apple's results) and down ▼ (or dropped out) at the last check.",
  },
};

export function OpportunitiesPage() {
  const bootstrap = useCurrentBootstrap();
  const data = bootstrap.data;
  const [selection] = useSelection({ appId: data?.selectedAppId, country: data?.selectedCountry });
  const { appId, device } = selection;
  const navigate = useNavigate();
  const location = useLocation();

  const rows = useMemo(() => (data?.rankings ?? []).filter((row) => row.device === device), [data?.rankings, device]);
  const plan = useMemo(() => actionPlan(rows), [rows]);
  const groups = useMemo(() => groupByKeyword(rows), [rows]);
  const names = useMemo(
    () => new Map((data?.countries ?? []).map((country) => [country.code, country.name])),
    [data?.countries],
  );
  const countryName = (code: string) => names.get(code) ?? code.toUpperCase();

  const openKeyword = (row: Ranking) => {
    const params = new URLSearchParams({ country: row.country, device: row.device, focus: String(row.targetId) });
    if (appId) params.set("app", String(appId));
    navigate(`/keywords?${params}`);
  };

  const scored = rows.some((row) => row.opportunity != null);
  // A keyword picked in Best opportunities opens in All keywords, storefront by storefront.
  const overview = useRef<OverviewHandle>(null);
  const reveal = (keyword: string) => overview.current?.reveal(keyword);

  return (
    <Page title="Opportunities" countryPicker={false}>
      {bootstrap.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load opportunities</AlertTitle>
          <AlertDescription>{bootstrap.error.message}</AlertDescription>
        </Alert>
      ) : null}

      {!data && bootstrap.isLoading ? (
        <>
          <Skeleton className="h-72" />
          <Skeleton className="h-96" />
        </>
      ) : null}

      {data && !rows.length ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Lightbulb />
            </EmptyMedia>
            <EmptyTitle>No checked keywords on {deviceName(device)}</EmptyTitle>
            <EmptyDescription>Track keywords and run a check: opportunities are built from their ranks.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {data && rows.length ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Best opportunities</CardTitle>
              <CardDescription>
                Apple popularity still to win, discounted by difficulty · {deviceName(device)}. One entry per keyword,
                added up over the storefronts where it fits: one change to a keyword can pay off in several stores at
                once.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {scored ? (
                <div className="grid gap-4 lg:grid-cols-3">
                  <PlanColumn
                    title="Quick wins"
                    note="Ranked 11–50: metadata work should pay off soon"
                    empty="No keyword ranked 11–50 with something left to win."
                  >
                    {plan.quickWins.map((group) => (
                      <GroupItem key={group.keyword} group={group} ranks countryName={countryName} onReveal={reveal} />
                    ))}
                  </PlanColumn>
                  <PlanColumn title="Big bets" note="Popular, not in the top 50 yet" empty="Nothing left to win outside the top 50.">
                    {plan.bigBets.map((group) => (
                      <GroupItem key={group.keyword} group={group} countryName={countryName} onReveal={reveal} />
                    ))}
                  </PlanColumn>
                  <PlanColumn
                    title="Apple Ads only"
                    note="Competitor names, kept out of metadata"
                    empty="No competitor name with an opportunity. Mark one with ⚔ in Keywords."
                  >
                    {plan.appleAds.map((group) => (
                      <GroupItem key={group.keyword} group={group} countryName={countryName} onReveal={reveal} />
                    ))}
                  </PlanColumn>
                </div>
              ) : (
                <Alert>
                  <Megaphone />
                  <AlertTitle>Connect Apple Ads to see opportunities</AlertTitle>
                  <AlertDescription className="grid gap-3">
                    <p>
                      Opportunity scores use Apple&rsquo;s own search popularity, read-only from your Apple Ads account. The
                      ratings-based estimate is never used for them. Ranks and coverage below work without it.
                    </p>
                    <Button size="sm" variant="outline" className="w-fit" onClick={() => navigate({ pathname: "/paid", search: location.search })}>
                      Set up in Paid search
                    </Button>
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          <KeywordOverview ref={overview} groups={groups} device={device} countryName={countryName} onOpen={openKeyword} />
        </>
      ) : null}
    </Page>
  );
}

function PlanColumn({ title, note, empty, children }: { title: string; note: string; empty: string; children: ReactNode[] }) {
  return (
    <div className="grid content-start gap-2 rounded-lg border p-3">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-muted-foreground text-xs">{note}</p>
      </div>
      <div className="grid gap-0.5">
        {children.length ? children : <p className="text-muted-foreground py-2 text-xs">{empty}</p>}
      </div>
    </div>
  );
}

/** How many storefronts an entry adds up, loud when it is more than one. */
function StoresPill({ count }: { count: number }) {
  if (count < 2) return null;
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full bg-sky-500/15 px-1.5 py-0.5 text-[11px] font-semibold text-sky-700 tabular-nums dark:text-sky-300"
      title={`Adds up ${count} storefronts: one change to this keyword pays off in all of them`}
    >
      <Store className="size-3" aria-hidden />
      {count} stores
    </span>
  );
}

const SHOWN_MARKETS = 5;

function GroupItem({
  group,
  ranks = false,
  countryName,
  onReveal,
}: {
  group: KeywordGroup;
  /** Show each storefront's rank (quick wins) instead of its code. */
  ranks?: boolean;
  countryName: (code: string) => string;
  onReveal: (keyword: string) => void;
}) {
  const shown = group.markets.slice(0, SHOWN_MARKETS);
  const rest = group.markets.length - shown.length;
  return (
    <button
      type="button"
      onClick={() => onReveal(group.keyword)}
      title={`Show “${group.keyword}” in All keywords below, storefront by storefront`}
      className="hover:bg-muted focus-visible:ring-ring grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-md px-2 py-1.5 text-left focus-visible:ring-2 focus-visible:outline-none"
    >
      <span className="flex min-w-0 items-center gap-2">
        <span className="truncate text-sm font-medium">{group.keyword}</span>
        <StoresPill count={group.markets.length} />
      </span>
      <span className="row-span-2 text-sm font-semibold text-emerald-600 tabular-nums dark:text-emerald-400">
        {group.total}
      </span>
      <span className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
        {shown.map((row) => (
          <span
            key={row.targetId}
            className="whitespace-nowrap tabular-nums"
            title={`${countryName(row.country)}${row.found && row.rank != null ? ` · #${row.rank}` : ""} · ${row.opportunity ?? 0} to win`}
          >
            <span aria-hidden>{countryFlag(row.country)}</span> {ranks && row.rank != null ? `#${row.rank}` : row.country.toUpperCase()}
          </span>
        ))}
        {rest > 0 ? <span>+{rest}</span> : null}
        {!ranks && group.popularity != null ? <span>· popularity {group.popularity}</span> : null}
      </span>
    </button>
  );
}

function SortHead({
  field,
  label,
  sort,
  onSort,
  className,
}: {
  field: GroupSortField;
  label: string;
  sort: { field: GroupSortField; direction: "asc" | "desc" };
  onSort: (field: GroupSortField) => void;
  className?: string;
}) {
  const active = sort.field === field;
  const Icon = active ? (sort.direction === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
  const info = INFO[field];
  return (
    <TableHead className={className} aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}>
      <span className="inline-flex items-center gap-0.5">
        <button
          type="button"
          onClick={() => onSort(field)}
          className={cn(
            "hover:text-foreground inline-flex items-center gap-1 whitespace-nowrap focus-visible:underline focus-visible:outline-none",
            active && "text-foreground",
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

function Where({ row, countryName }: { row: Ranking; countryName: (code: string) => string }) {
  return (
    <span className="text-muted-foreground text-xs whitespace-nowrap" title={countryName(row.country)}>
      <span aria-hidden>{countryFlag(row.country)}</span> {row.country.toUpperCase()}
    </span>
  );
}

function ChangeCounts({ up, down }: { up: number; down: number }) {
  if (!up && !down) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="inline-flex gap-2 text-sm font-medium tabular-nums">
      {up ? <span className="text-emerald-600 dark:text-emerald-400">▲{up}</span> : null}
      {down ? <span className="text-rose-600 dark:text-rose-400">▼{down}</span> : null}
    </span>
  );
}

export interface OverviewHandle {
  /** Opens a keyword's row (clearing filters that hide it) and scrolls to it. */
  reveal: (keyword: string) => void;
}

function KeywordOverview({
  ref,
  groups,
  device,
  countryName,
  onOpen,
}: {
  ref?: Ref<OverviewHandle>;
  groups: KeywordGroup[];
  device: Ranking["device"];
  countryName: (code: string) => string;
  onOpen: (row: Ranking) => void;
}) {
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState<Scope>("all");
  const [limits, setLimits] = useState<Limits>({});
  const [sort, setSort] = useState<{ field: GroupSortField; direction: "asc" | "desc" }>({
    field: "opportunity",
    direction: "desc",
  });
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set());

  const shown = useMemo(
    () => sortGroups(filterGroups(groups, scope, search, limits), sort.field, sort.direction),
    [groups, scope, search, limits, sort],
  );
  const rows = useRef(new Map<string, HTMLTableRowElement>());
  useImperativeHandle(
    ref,
    () => ({
      reveal(keyword) {
        const visible = shown.some((group) => group.keyword === keyword);
        const list = visible ? shown : sortGroups(groups, sort.field, sort.direction);
        const index = list.findIndex((group) => group.keyword === keyword);
        if (index < 0) return;
        flushSync(() => {
          if (!visible) {
            setSearch("");
            setScope("all");
            setLimits({});
          }
          setLimit((current) => Math.max(current, Math.ceil((index + 1) / PAGE_SIZE) * PAGE_SIZE));
          setOpen((current) => new Set(current).add(keyword));
        });
        rows.current.get(keyword)?.scrollIntoView({ behavior: "smooth", block: "start" });
      },
    }),
    [shown, groups, sort],
  );
  const filtering = scope !== "all" || search.trim() !== "" || Object.keys(limits).length > 0;
  const peak = Math.max(1, ...shown.map((group) => group.total ?? 0));
  const page = shown.slice(0, limit);
  const head = {
    sort,
    onSort: (field: GroupSortField) =>
      setSort((current) =>
        current.field === field
          ? { field, direction: current.direction === "asc" ? "desc" : "asc" }
          : { field, direction: FIRST_DIRECTION[field] },
      ),
  };
  const setLimitValue = (key: keyof Limits, raw: string) =>
    setLimits((current) => {
      const next = { ...current };
      const value = Number.parseInt(raw, 10);
      if (raw.trim() === "" || !Number.isFinite(value)) delete next[key];
      else next[key] = value;
      return next;
    });
  const toggle = (keyword: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(keyword)) next.delete(keyword);
      else next.add(keyword);
      return next;
    });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">All keywords</CardTitle>
        <CardDescription>
          One row per keyword: every storefront that tracks it on {deviceName(device)}, added up. Open a row for each
          storefront.
        </CardDescription>
        <CardAction>
          <Badge variant="secondary" className="tabular-nums">
            {filtering ? `${shown.length} / ${groups.length}` : groups.length}
          </Badge>
        </CardAction>
      </CardHeader>
      <div className="flex flex-wrap items-center gap-2 px-6">
        <div className="relative">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" aria-hidden />
          <Input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Filter keywords"
            aria-label="Filter keywords"
            className="h-8 w-44 pl-8"
          />
        </div>
        <Select value={scope} onValueChange={(value) => setScope(value as Scope)}>
          <SelectTrigger size="sm" className="w-44" aria-label="Show">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SCOPES.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <LimitInput label="Popularity ≥" value={limits.popularity} onChange={(raw) => setLimitValue("popularity", raw)} />
        <LimitInput label="Difficulty ≤" value={limits.difficulty} onChange={(raw) => setLimitValue("difficulty", raw)} />
        <LimitInput label="Opportunity ≥" value={limits.opportunity} onChange={(raw) => setLimitValue("opportunity", raw)} />
        {filtering ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setSearch("");
              setScope("all");
              setLimits({});
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </div>
      <CardContent className="px-0">
        {shown.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <SortHead field="keyword" label="Keyword" className="pl-6" {...head} />
                <SortHead field="popularity" label="Popularity" {...head} />
                <SortHead field="opportunity" label="Opportunity" {...head} />
                <SortHead field="market" label="Best market" {...head} />
                <SortHead field="rank" label="Best rank" {...head} />
                <SortHead field="coverage" label="Top 10 · 50" {...head} />
                <SortHead field="difficulty" label="Difficulty" {...head} />
                <SortHead field="change" label="Change" className="pr-6" {...head} />
              </TableRow>
            </TableHeader>
            <TableBody>
              {page.map((group) => {
                const expanded = open.has(group.keyword);
                return (
                  <Fragment key={group.keyword}>
                    <TableRow
                      ref={(element) => {
                        if (element) rows.current.set(group.keyword, element);
                        else rows.current.delete(group.keyword);
                      }}
                      data-state={expanded ? "selected" : undefined}
                      className="scroll-mt-20"
                    >
                      <TableCell className="max-w-72 pl-6">
                        <div className="flex min-w-0 items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => toggle(group.keyword)}
                            aria-expanded={expanded}
                            aria-label={`${expanded ? "Hide" : "Show"} ${group.keyword} in each storefront`}
                            className="hover:text-foreground text-muted-foreground flex min-w-0 items-center gap-1 focus-visible:underline focus-visible:outline-none"
                          >
                            {expanded ? <ChevronDown className="size-4 shrink-0" /> : <ChevronRight className="size-4 shrink-0" />}
                            <span className="text-foreground truncate font-medium">{group.keyword}</span>
                          </button>
                          {group.competitorBrand ? <CompetitorBadge /> : null}
                        </div>
                      </TableCell>
                      <TableCell>
                        <DemandValue
                          source={{
                            popularity: group.popularity,
                            popularityStatus: group.popularity != null ? "measured" : group.markets[0].popularityStatus,
                            volumeEstimate: null,
                          }}
                        />
                      </TableCell>
                      <TableCell>
                        {group.total == null ? (
                          <OpportunityValue value={null} />
                        ) : (
                          <span className="inline-flex items-center gap-2">
                            <span className="bg-muted hidden h-1.5 w-20 overflow-hidden rounded-full sm:block" aria-hidden>
                              <span
                                className="block h-full rounded-full bg-emerald-500"
                                style={{ width: `${Math.max(2, (100 * group.total) / peak)}%` }}
                              />
                            </span>
                            <span className="text-sm font-semibold tabular-nums">{group.total}</span>
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        {group.topMarket ? (
                          <span className="inline-flex items-center gap-1.5">
                            <Where row={group.topMarket} countryName={countryName} />
                            <OpportunityValue value={group.topMarket.opportunity} />
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {group.best ? (
                          <span className="inline-flex items-center gap-1.5">
                            <span
                              className={cn(
                                "text-sm font-medium tabular-nums",
                                (group.best.rank ?? 99) <= 10 && "text-emerald-600 dark:text-emerald-400",
                              )}
                            >
                              #{group.best.rank}
                            </span>
                            <Where row={group.best} countryName={countryName} />
                          </span>
                        ) : (
                          <span className="text-muted-foreground text-sm">not ranked</span>
                        )}
                      </TableCell>
                      <TableCell
                        className="text-sm tabular-nums"
                        title={`Top 10 in ${group.top10} and top 50 in ${group.top50} of the ${group.markets.length} storefronts that track it`}
                      >
                        <span className={cn("font-semibold", group.top10 ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground")}>
                          {group.top10}
                        </span>
                        <span className="text-muted-foreground"> · </span>
                        <span className={cn("font-semibold", group.top50 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground")}>
                          {group.top50}
                        </span>
                        <span className="text-muted-foreground"> / {group.markets.length}</span>
                      </TableCell>
                      <TableCell>
                        <span className="inline-flex items-center gap-1.5">
                          <DifficultyValue value={group.difficulty} />
                          {group.difficultyRange && group.difficultyRange[0] !== group.difficultyRange[1] ? (
                            <span className="text-muted-foreground text-xs tabular-nums" title="Lowest and highest over its storefronts">
                              {group.difficultyRange[0]}–{group.difficultyRange[1]}
                            </span>
                          ) : null}
                        </span>
                      </TableCell>
                      <TableCell className="pr-6">
                        <ChangeCounts up={group.up} down={group.down} />
                      </TableCell>
                    </TableRow>
                    {expanded ? (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={8} className="bg-muted/30 px-6 py-3">
                          <MarketDetail group={group} countryName={countryName} onOpen={onOpen} />
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        ) : (
          <p className="text-muted-foreground px-6 py-8 text-center text-sm">No matching keywords. Try other filters.</p>
        )}
        {shown.length > PAGE_SIZE ? (
          <div className="text-muted-foreground flex items-center justify-center gap-2 px-6 pt-3 text-sm">
            <span>
              {page.length} of {shown.length} keywords
            </span>
            {page.length < shown.length ? (
              <>
                <Button size="sm" variant="ghost" onClick={() => setLimit((value) => value + PAGE_SIZE)}>
                  Show {Math.min(PAGE_SIZE, shown.length - page.length)} more
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setLimit(shown.length)}>
                  Show all
                </Button>
              </>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setLimit(PAGE_SIZE)}>
                Show fewer
              </Button>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function LimitInput({ label, value, onChange }: { label: string; value?: number; onChange: (raw: string) => void }) {
  return (
    <label className="text-muted-foreground flex h-8 items-center gap-1.5 rounded-md border px-2 text-xs">
      <span className="whitespace-nowrap">{label}</span>
      <input
        type="number"
        inputMode="numeric"
        min={0}
        max={label.startsWith("Opportunity") ? undefined : 100}
        placeholder="any"
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
        aria-label={label.replace("≥", "at least").replace("≤", "at most")}
        className="text-foreground w-12 bg-transparent tabular-nums outline-none placeholder:text-muted-foreground/60"
      />
    </label>
  );
}

function MarketDetail({
  group,
  countryName,
  onOpen,
}: {
  group: KeywordGroup;
  countryName: (code: string) => string;
  onOpen: (row: Ranking) => void;
}) {
  return (
    <table className="w-full text-sm">
      <thead className="text-muted-foreground text-xs">
        <tr className="text-left">
          <th className="py-1 font-medium">Storefront</th>
          <th className="py-1 font-medium">Rank</th>
          <th className="py-1 font-medium">Change</th>
          <th className="py-1 font-medium">Popularity</th>
          <th className="py-1 font-medium">Difficulty</th>
          <th className="py-1 font-medium">Opportunity</th>
          <th className="py-1 font-medium">Top 5</th>
          <th className="py-1" />
        </tr>
      </thead>
      <tbody>
        {group.markets.map((row) => {
          const tone = changeTone(row.change);
          return (
            <tr key={row.targetId} className="border-t">
              <td className="py-1.5 whitespace-nowrap">
                <span aria-hidden>{countryFlag(row.country)}</span> {countryName(row.country)}
              </td>
              <td
                className={cn(
                  "py-1.5 font-medium tabular-nums",
                  row.found && (row.rank ?? 99) <= 10 ? "text-emerald-600 dark:text-emerald-400" : !row.found && "text-muted-foreground",
                )}
              >
                {rankLabel(row)}
              </td>
              <td
                className={cn(
                  "py-1.5 tabular-nums",
                  tone === "up" || tone === "new"
                    ? "text-emerald-600 dark:text-emerald-400"
                    : tone === "down" || tone === "lost"
                      ? "text-rose-600 dark:text-rose-400"
                      : "text-muted-foreground",
                )}
              >
                {row.change}
              </td>
              <td className="py-1.5">
                <DemandValue source={row} market={row.country} />
              </td>
              <td className="py-1.5">
                <DifficultyValue value={row.difficultyEstimate} />
              </td>
              <td className="py-1.5">
                <OpportunityValue value={row.opportunity} />
              </td>
              <td className="py-1.5">
                <span className="flex -space-x-1">
                  {(row.topApps ?? []).slice(0, 5).map((app) => (
                    <span key={`${app.position}-${app.appId}`} title={`#${app.position} ${app.name}`}>
                      <AppIcon name={app.name} artworkUrl={app.artworkUrl} className="ring-background size-6 rounded-[22%] ring-2" />
                    </span>
                  ))}
                </span>
              </td>
              <td className="py-1.5 text-right">
                <Button size="xs" variant="ghost" onClick={() => onOpen(row)}>
                  Open →
                </Button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
