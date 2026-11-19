import { Star } from "lucide-react";
import { AppIcon } from "@/components/app-icon";
import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { countryFlag, deviceName, formatCompact, formatDateTime, rankLabel } from "@/lib/format";
import type { Device, HistoryPoint, Ranking } from "@/lib/types";
import type { DailySnapshot, LosingToApp } from "./keyword-utils";
import { TooltipDate, TrendChart } from "./trend-chart";

function ChartEmpty({ children }: { children: string }) {
  return <p className="text-muted-foreground bg-muted/40 rounded-lg p-6 text-center text-sm">{children}</p>;
}

/** Rank history for the keyword selected in the table. Missing ranks are gaps, not numbers. */
export function KeywordHistoryCard({ ranking, history }: { ranking: Ranking | null; history: HistoryPoint[] }) {
  if (!ranking) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Keyword rank history</CardTitle>
          <CardDescription>Select a keyword in the table to see how its rank moved.</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  const points = history
    .filter((point) => point.targetId === ranking.targetId)
    .map((point) => ({
      ...point,
      time: +new Date(point.checkedAt),
      value: point.found && point.rank != null ? point.rank : null,
    }))
    .filter((point) => Number.isFinite(point.time))
    .sort((left, right) => left.time - right.time);
  const missing = points.filter((point) => point.value == null).length;
  const hasRank = points.some((point) => point.value != null);

  return (
    <Card>
      <CardHeader>
        <CardDescription>
          {countryFlag(ranking.country)} {ranking.country.toUpperCase()} · {deviceName(ranking.device)}
        </CardDescription>
        <CardTitle className="truncate text-base">{ranking.keyword}</CardTitle>
        <CardAction>
          <span className="text-lg font-semibold tabular-nums">{rankLabel(ranking)}</span>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-2">
        {hasRank ? (
          <>
            <TrendChart
              data={points}
              rank
              color="var(--primary)"
              label="Rank"
              className="h-56"
              ariaLabel={`Rank history for ${ranking.keyword}; higher is better`}
              tooltip={(point) => (
                <>
                  <div className="font-medium">{formatDateTime(point.checkedAt)}</div>
                  <span className="tabular-nums">{rankLabel(point)}</span>
                </>
              )}
            />
            {missing ? (
              <p className="text-muted-foreground text-xs">
                {missing} check{missing === 1 ? "" : "s"} outside Apple&rsquo;s returned results; shown as gaps.
              </p>
            ) : null}
          </>
        ) : (
          <ChartEmpty>
            {points.length
              ? `Not in Apple's top ${ranking.resultLimit || 200} in any stored check yet.`
              : "Run another check later to build a rank history."}
          </ChartEmpty>
        )}
      </CardContent>
    </Card>
  );
}

/** Daily average rank across the storefront's keywords (found keywords only). */
export function OverallRankCard({
  snapshots,
  country,
  device,
}: {
  snapshots: DailySnapshot[];
  country: string;
  device: Device;
}) {
  const points = snapshots
    .filter((point) => point.averageRank != null)
    .map((point) => ({ ...point, time: point.timestamp, value: point.averageRank }));
  const latest = points.at(-1)?.averageRank;
  return (
    <Card>
      <CardHeader>
        <CardDescription>
          {countryFlag(country)} {country.toUpperCase()} · {deviceName(device)} · found keywords only
        </CardDescription>
        <CardTitle className="text-base">Average rank trend</CardTitle>
        <CardAction>
          <span className="text-lg font-semibold tabular-nums">{latest == null ? "—" : `#${latest.toFixed(1)}`}</span>
        </CardAction>
      </CardHeader>
      <CardContent>
        {points.length ? (
          <TrendChart
            data={points}
            rank
            color="var(--color-emerald-500)"
            label="Average rank"
            className="h-56"
            ariaLabel="Average rank across tracked keywords; higher is better"
            tooltip={(point) => (
              <>
                <TooltipDate time={point.time} />
                <span className="tabular-nums">
                  Avg #{point.averageRank?.toFixed(1)} · {point.found}/{point.tracked} found
                </span>
              </>
            )}
          />
        ) : (
          <ChartEmpty>Run checks on more than one day to build an overall rank trend.</ChartEmpty>
        )}
      </CardContent>
    </Card>
  );
}

function RatingLine({ app }: { app: LosingToApp }) {
  const hasRating = app.averageRating != null && Number.isFinite(app.averageRating);
  const hasCount = app.ratingCount != null && Number.isFinite(app.ratingCount);
  if (!hasRating && !hasCount) {
    return <span className="text-muted-foreground text-xs">Rating unavailable</span>;
  }
  return (
    <span className="text-muted-foreground inline-flex items-center gap-1 text-xs tabular-nums">
      <Star className="size-3 fill-current" aria-hidden />
      <span className="sr-only">Rating</span>
      {hasRating ? app.averageRating?.toFixed(1) : "—"}
      <span aria-hidden>·</span>
      {hasCount
        ? `${formatCompact(app.ratingCount)} ${app.ratingCount === 1 ? "rating" : "ratings"}`
        : "rating count unavailable"}
    </span>
  );
}

/** Top-5 apps that rank above the selected app across the current keyword set. */
export function LosingToCard({ apps, country, device }: { apps: LosingToApp[]; country: string; device: Device }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>
          {countryFlag(country)} {country.toUpperCase()} · {deviceName(device)} · Top 5 apps ranking above you
        </CardDescription>
        <CardTitle className="text-base">Losing to</CardTitle>
        <CardAction>
          <Badge variant="secondary" className="tabular-nums">
            {apps.length}
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent>
        {apps.length ? (
          <ul className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
            {apps.slice(0, 6).map((app) => (
              <li key={app.appId}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div
                      tabIndex={0}
                      className="hover:bg-muted/50 focus-visible:ring-ring/50 flex items-center gap-3 rounded-lg p-2 transition-colors focus-visible:ring-[3px] focus-visible:outline-none"
                    >
                      <AppIcon name={app.name} artworkUrl={app.artworkUrl} className="size-9" />
                      <div className="grid min-w-0 flex-1 gap-0.5">
                        <span className="truncate text-sm font-medium">{app.name}</span>
                        <RatingLine app={app} />
                      </div>
                      <div className="grid shrink-0 justify-items-end">
                        <span className="text-sm font-semibold tabular-nums">{app.count}</span>
                        <span className="text-muted-foreground text-[11px]">ahead</span>
                      </div>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-72 text-pretty">
                    Ahead in: {app.keywords.join(", ")}
                  </TooltipContent>
                </Tooltip>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">
            No Top 5 competitors are currently ahead of this app in the selected market.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
