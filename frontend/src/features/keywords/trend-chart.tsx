import type { ReactNode } from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart";
import { cn } from "@/lib/utils";

export interface TrendPoint {
  time: number;
  /** null leaves a gap: a rank Apple did not return is never plotted as a number. */
  value: number | null;
}

const DAY = 86_400_000;
const shortDate = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });

/**
 * A single-series line over time. Rank series are inverted so #1 sits at the top.
 * Missing values break the line instead of being drawn.
 */
export function TrendChart<T extends TrendPoint>({
  data,
  rank,
  color,
  label,
  ariaLabel,
  tooltip,
  className,
}: {
  data: T[];
  rank: boolean;
  color: string;
  label: string;
  ariaLabel: string;
  tooltip: (point: T) => ReactNode;
  className?: string;
}) {
  const config = { value: { label, color } } satisfies ChartConfig;
  const values = data.map((point) => point.value).filter((value): value is number => value != null);
  const max = rank ? Math.max(10, ...values.map((value) => Math.ceil(value))) : Math.max(1, ...values);
  const showDots = data.length <= 40;

  return (
    <div role="img" aria-label={ariaLabel} className={cn("w-full", className)}>
      <ChartContainer config={config} className="aspect-auto h-full w-full" aria-hidden>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} accessibilityLayer={false}>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="time"
            type="number"
            scale="time"
            domain={([min, max]: readonly number[]) => (min === max ? [min - DAY, max + DAY] : [min, max])}
            tickFormatter={(value: number) => shortDate.format(new Date(value))}
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            minTickGap={28}
          />
          <YAxis
            reversed={rank}
            domain={rank ? [1, max] : [0, max]}
            allowDecimals={false}
            tickFormatter={(value: number) => (rank ? `#${value}` : String(value))}
            tickLine={false}
            axisLine={false}
            width={44}
          />
          <ChartTooltip
            cursor={{ strokeDasharray: "3 3" }}
            content={({ active, payload }) => {
              const point = payload?.[0]?.payload as T | undefined;
              if (!active || !point) return null;
              return (
                <div className="bg-background border-border/50 grid gap-1 rounded-lg border px-2.5 py-1.5 text-xs shadow-xl">
                  {tooltip(point)}
                </div>
              );
            }}
          />
          <Line
            dataKey="value"
            type="monotone"
            stroke="var(--color-value)"
            strokeWidth={2}
            connectNulls={false}
            dot={showDots ? { r: 3, fill: "var(--color-value)", strokeWidth: 0 } : false}
            activeDot={{ r: 5 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ChartContainer>
    </div>
  );
}

export function TooltipDate({ time }: { time: number }) {
  return (
    <div className="font-medium">
      {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(time))}
    </div>
  );
}
