import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { countryFlag, deviceName } from "@/lib/format";
import type { Device, MetricTrendSet } from "@/lib/types";
import { cn } from "@/lib/utils";
import { trendChip, type DailySnapshot, type RankSummary, type TrendChip } from "./keyword-utils";
import { TooltipDate, TrendChart } from "./trend-chart";

type Series = "top10" | "top50" | "averageRank";

const SERIES: Record<Series, { label: string; note: string; color: string }> = {
  top10: { label: "Top 10", note: "Defend visibility", color: "var(--color-emerald-500)" },
  top50: { label: "Top 50", note: "Growth range", color: "var(--primary)" },
  averageRank: { label: "Average rank", note: "Found keywords only", color: "var(--color-amber-500)" },
};

const chipTone: Record<TrendChip["tone"], string> = {
  better: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  worse: "bg-rose-500/10 text-rose-700 dark:text-rose-400",
  flat: "bg-muted text-muted-foreground",
};

function Chip({ chip }: { chip: TrendChip | null }) {
  if (!chip) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn("inline-flex items-baseline gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium tabular-nums", chipTone[chip.tone])}
        >
          {chip.text}
          <span className="text-[10px] opacity-70">{chip.period}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64 text-pretty">{chip.title}</TooltipContent>
    </Tooltip>
  );
}

export function MetricCards({
  summary,
  trends,
  trends30d,
  snapshots,
  country,
  device,
}: {
  summary: RankSummary;
  trends: Partial<MetricTrendSet>;
  trends30d: Partial<MetricTrendSet>;
  snapshots: DailySnapshot[];
  country: string;
  device: Device;
}) {
  const [open, setOpen] = useState<Series | null>(null);
  const values: Record<Series, string> = {
    top10: String(summary.top10),
    top50: String(summary.top50),
    averageRank: summary.averageRank == null ? "—" : `#${summary.averageRank.toFixed(1)}`,
  };

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-3">
        {(Object.keys(SERIES) as Series[]).map((series) => (
          <div
            key={series}
            className="bg-card text-card-foreground ring-foreground/10 hover:bg-muted/40 relative grid gap-2 rounded-xl p-4 ring-1 transition-colors"
          >
            <button
              type="button"
              onClick={() => setOpen(series)}
              className="flex items-center justify-between text-left text-sm font-medium after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none focus-visible:after:ring-[3px] focus-visible:after:ring-ring/50"
              aria-label={`View ${SERIES[series].label} history`}
            >
              <span className="text-muted-foreground">{SERIES[series].label}</span>
              <ChevronRight className="text-muted-foreground size-4" aria-hidden />
            </button>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-2xl font-semibold tabular-nums">{values[series]}</span>
              {/* Chips sit above the card-wide button so their tooltips stay reachable. */}
              <span className="relative z-10 flex gap-1.5">
                <Chip chip={trendChip(trends[series], 7)} />
                <Chip chip={trendChip(trends30d[series], 30)} />
              </span>
            </div>
            <span className="text-muted-foreground text-xs">{SERIES[series].note}</span>
          </div>
        ))}
      </div>
      <MetricHistoryDialog
        series={open}
        onOpenChange={(value) => !value && setOpen(null)}
        snapshots={snapshots}
        country={country}
        device={device}
      />
    </>
  );
}

function MetricHistoryDialog({
  series,
  onOpenChange,
  snapshots,
  country,
  device,
}: {
  series: Series | null;
  onOpenChange: (open: boolean) => void;
  snapshots: DailySnapshot[];
  country: string;
  device: Device;
}) {
  const rank = series === "averageRank";
  const points = (rank ? snapshots.filter((point) => point.averageRank != null) : snapshots).map((point) => ({
    ...point,
    time: point.timestamp,
    value: series ? point[series] : null,
  }));
  const latest = points.at(-1)?.value ?? null;
  const market = `${countryFlag(country)} ${country.toUpperCase()} · ${deviceName(device)}`;
  const meta = series ? SERIES[series] : SERIES.top10;
  const threshold = series === "top50" ? 50 : 10;

  return (
    <Dialog open={series != null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{rank ? "Average rank evolution" : `Top ${threshold} evolution`}</DialogTitle>
          <DialogDescription className="text-pretty">
            {rank
              ? `Daily average rank of found keywords for ${market}. Missing apps are excluded. Each keyword contributes its latest check that day.`
              : `Daily count of tracked keywords ranking in the Top ${threshold} for ${market}. Each keyword contributes its latest check that day.`}
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-semibold tabular-nums">
            {latest == null ? "—" : rank ? `#${latest.toFixed(1)}` : latest}
          </span>
          <span className="text-muted-foreground text-xs">
            {rank ? "average rank" : `keywords in Top ${threshold}`}
            {points.length ? ` · ${points.length} daily data point${points.length === 1 ? "" : "s"}` : ""}
          </span>
        </div>
        {points.length ? (
          <TrendChart
            data={points}
            rank={rank}
            color={meta.color}
            label={meta.label}
            className="h-64"
            ariaLabel={rank ? "Average keyword rank over time; higher is better" : `Top ${threshold} keyword count over time`}
            tooltip={(point) => (
              <>
                <TooltipDate time={point.time} />
                <span className="tabular-nums">
                  {rank
                    ? `Avg #${point.averageRank?.toFixed(1)} · ${point.found}/${point.tracked} found`
                    : `${point.value} keyword${point.value === 1 ? "" : "s"} in Top ${threshold}`}
                </span>
              </>
            )}
          />
        ) : (
          <p className="text-muted-foreground bg-muted/40 rounded-lg p-6 text-center text-sm">
            Run checks over multiple days to build this trend.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
