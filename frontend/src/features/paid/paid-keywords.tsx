import { Fragment, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { apiPost } from "@/lib/api";
import { countryFlag, formatCompact, formatMoney } from "@/lib/format";
import { useInvalidate } from "@/lib/queries";
import type { Device } from "@/lib/types";
import { cn } from "@/lib/utils";
import { usePaidCache, type PaidKeyword, type PaidKeywordCountry } from "./api";
import {
  asoRankView,
  bidLabel,
  filterByStatus,
  nextSort,
  paidRowsSummary,
  visiblePaidGroups,
  type PaidSort,
  type PaidSortField,
} from "./keywords";

const COLUMNS: { field: PaidSortField; label: string; numeric?: boolean }[] = [
  { field: "keyword", label: "Keyword" },
  { field: "matchTypes", label: "Match" },
  { field: "status", label: "Status" },
  { field: "campaignCount", label: "Campaigns", numeric: true },
  { field: "asoRank", label: "ASO rank" },
  { field: "bid", label: "Bid", numeric: true },
  { field: "spend", label: "Spend", numeric: true },
  { field: "impressions", label: "Impr.", numeric: true },
  { field: "taps", label: "Taps", numeric: true },
  { field: "installs", label: "Installs", numeric: true },
];

interface RankCheckResult {
  keyword: string;
  country: string;
  automaticCheck?: { failures: number } | null;
  rankCheck?: { rank: number | null; found: boolean; resultLimit: number; status: string } | null;
}

function rankCheckMessage(result: RankCheckResult): { text: string; failed: boolean } {
  const failures = result.automaticCheck?.failures ?? 0;
  if (failures) {
    return {
      text: `Rank search for “${result.keyword}” finished with ${failures} failed Apple request${failures === 1 ? "" : "s"}`,
      failed: true,
    };
  }
  const check = result.rankCheck;
  const outcome =
    check?.status === "error"
      ? "the Apple request failed"
      : check?.found && check.rank
        ? `rank #${check.rank}`
        : check
          ? `not in Apple’s top ${check.resultLimit}`
          : "no ranking result";
  return {
    text: `“${result.keyword}” in ${result.country.toUpperCase()}: ${outcome}`,
    failed: check?.status === "error",
  };
}

export function PaidKeywordsCard({
  groups,
  appId,
  country,
  device,
}: {
  groups: PaidKeywordCountry[];
  appId: number;
  country: string;
  device: Device;
}) {
  const [countryFilter, setCountryFilter] = useState("all");
  const [showPaused, setShowPaused] = useState(false);
  const [sort, setSort] = useState<PaidSort>({ field: "spend", direction: "desc" });
  const cache = usePaidCache();
  const invalidate = useInvalidate();

  const codes = useMemo(() => new Set(groups.map((group) => group.code)), [groups]);
  const activeFilter = countryFilter !== "all" && !codes.has(countryFilter) ? "all" : countryFilter;
  const statusGroups = useMemo(() => filterByStatus(groups, showPaused), [groups, showPaused]);
  const visible = useMemo(
    () => visiblePaidGroups(groups, { country: activeFilter, showPaused }, sort),
    [groups, activeFilter, showPaused, sort],
  );
  const total = statusGroups.reduce((count, group) => count + group.keywords.length, 0);
  const visibleCount = visible.reduce((count, group) => count + group.keywords.length, 0);

  const check = useMutation({
    mutationFn: (row: PaidKeyword) =>
      apiPost<RankCheckResult>("/api/keywords/check-rank", {
        appId,
        keyword: row.text,
        country: row.country,
        countryName: row.countryName,
        device,
      }),
    onSuccess: async (result) => {
      const message = rankCheckMessage(result);
      if (message.failed) toast.warning(message.text);
      else toast.success(message.text);
      await Promise.all([cache.invalidate(), invalidate.bootstrap()]);
    },
    onError: (error) => toast.error(error.message),
  });
  const checkingKey = check.isPending && check.variables ? `${check.variables.country}:${check.variables.text}` : null;

  return (
    <Card>
      <CardHeader>
        <CardDescription>Current targeting</CardDescription>
        <CardTitle className="text-base">Apple Ads keywords by country</CardTitle>
        <CardDescription>
          The selected storefront comes first. Select an ASO rank to search Apple for this app&rsquo;s organic position
          on that keyword; it is then tracked in ASO.
        </CardDescription>
        <CardAction className="flex items-center gap-2">
          <Checkbox id="paid-show-paused" checked={showPaused} onCheckedChange={(value) => setShowPaused(value === true)} />
          <Label htmlFor="paid-show-paused" className="text-sm font-normal">
            Show paused
          </Label>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-4 px-0">
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          spacing={1}
          value={activeFilter}
          onValueChange={(value) => value && setCountryFilter(value)}
          aria-label="Filter by country"
          className="flex-wrap px-6"
        >
          <ToggleGroupItem value="all">
            All <span className="text-muted-foreground tabular-nums">{total}</span>
          </ToggleGroupItem>
          {statusGroups.map((group) => (
            <ToggleGroupItem key={group.code} value={group.code} aria-label={`${group.name}, ${group.keywords.length} keywords`}>
              <span aria-hidden>{countryFlag(group.code)}</span> {group.name}{" "}
              <span className="text-muted-foreground tabular-nums">{group.keywords.length}</span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <Table>
          <TableHeader>
            <TableRow>
              {COLUMNS.map((column, index) => {
                const active = sort.field === column.field;
                const Icon = !active ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown;
                return (
                  <TableHead
                    key={column.field}
                    aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
                    className={cn(index === 0 && "pl-6", index === COLUMNS.length - 1 && "pr-6", column.numeric && "text-right")}
                  >
                    <button
                      type="button"
                      onClick={() => setSort((current) => nextSort(current, column.field))}
                      className={cn(
                        "hover:text-foreground focus-visible:ring-ring/50 inline-flex items-center gap-1 rounded-sm focus-visible:ring-[3px] focus-visible:outline-none",
                        active ? "text-foreground" : "text-muted-foreground",
                      )}
                    >
                      {column.label}
                      <Icon className={cn("size-3", !active && "opacity-50")} aria-hidden />
                    </button>
                  </TableHead>
                );
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.length ? (
              visible.map((group) => {
                const summary = paidRowsSummary(group.keywords);
                return (
                  <Fragment key={group.code}>
                    <TableRow
                      className={cn("bg-muted/40 hover:bg-muted/40", group.code === country.toUpperCase() && "bg-primary/5")}
                    >
                      <TableCell colSpan={COLUMNS.length} className="px-6 py-2">
                        <div className="flex flex-wrap items-baseline gap-x-3">
                          <span className="text-sm font-medium">
                            <span aria-hidden>{countryFlag(group.code)}</span> {group.name}
                          </span>
                          <span className="text-muted-foreground text-xs tabular-nums">
                            {formatMoney(summary.spend, summary.currency)} spend · {formatCompact(summary.taps)} taps ·{" "}
                            {group.keywords.length} keyword{group.keywords.length === 1 ? "" : "s"}
                          </span>
                        </div>
                      </TableCell>
                    </TableRow>
                    {group.keywords.map((row) => (
                      <KeywordRow
                        key={`${row.country}:${row.text}`}
                        row={row}
                        checking={checkingKey === `${row.country}:${row.text}`}
                        disabled={check.isPending}
                        onCheck={() => check.mutate(row)}
                      />
                    ))}
                  </Fragment>
                );
              })
            ) : (
              <TableRow>
                <TableCell colSpan={COLUMNS.length} className="text-muted-foreground py-8 pl-6 text-sm whitespace-normal">
                  {groups.length
                    ? "No enabled keywords match. Turn on Show paused or choose another country."
                    : "No targeting keywords have been synced for this app yet."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {visible.length ? (
          <p className="text-muted-foreground px-6 text-xs tabular-nums">
            {visibleCount} of {total} keyword rows
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

const rankStyle = {
  found: "text-foreground",
  outside: "text-muted-foreground",
  error: "text-rose-600 dark:text-rose-400",
  unchecked: "text-muted-foreground",
} as const;

function KeywordRow({
  row,
  checking,
  disabled,
  onCheck,
}: {
  row: PaidKeyword;
  checking: boolean;
  disabled: boolean;
  onCheck: () => void;
}) {
  const rank = asoRankView(row);
  const metrics = row.metrics;
  return (
    <TableRow>
      <TableCell className="max-w-64 truncate pl-6 font-medium">{row.text}</TableCell>
      <TableCell>
        <div className="flex gap-1">
          {row.matchTypes.map((type) => (
            <Badge key={type} variant="outline" className="font-normal capitalize">
              {type.toLowerCase()}
            </Badge>
          ))}
        </div>
      </TableCell>
      <TableCell>
        <Badge variant={row.status === "ENABLED" ? "secondary" : "outline"} className="font-normal capitalize">
          {row.status.toLowerCase()}
        </Badge>
      </TableCell>
      <TableCell className="text-right tabular-nums">
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-help">{row.campaignCount}</span>
          </TooltipTrigger>
          <TooltipContent className="max-w-64">{row.campaigns.join(", ") || "No campaign names"}</TooltipContent>
        </Tooltip>
      </TableCell>
      <TableCell>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="xs"
              className={cn("tabular-nums", rankStyle[rank.state])}
              onClick={onCheck}
              disabled={disabled}
              aria-label={rank.title}
            >
              {checking ? <Spinner /> : rank.state === "unchecked" ? <Search /> : null}
              {rank.label}
            </Button>
          </TooltipTrigger>
          <TooltipContent className="max-w-64">{rank.title}</TooltipContent>
        </Tooltip>
      </TableCell>
      <TableCell className="text-right tabular-nums">{bidLabel(row)}</TableCell>
      <TableCell className="text-right tabular-nums">{formatMoney(metrics.spend, metrics.currency)}</TableCell>
      <TableCell className="text-right tabular-nums">{formatCompact(metrics.impressions)}</TableCell>
      <TableCell className="text-right tabular-nums">{formatCompact(metrics.taps)}</TableCell>
      <TableCell className="pr-6 text-right tabular-nums">{formatCompact(metrics.tapInstalls)}</TableCell>
    </TableRow>
  );
}
