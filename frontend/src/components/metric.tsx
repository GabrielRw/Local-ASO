import type { ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { demand, difficultyTone, toneFill, toneText, type Tone } from "@/lib/format";
import type { PopularityStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

/** A small value with an optional bar, used in tables (popularity, difficulty, opportunity). */
export function MetricValue({
  value,
  bar,
  tone,
  title,
  className,
}: {
  value: ReactNode;
  bar?: number | null;
  tone: Tone;
  title?: string;
  className?: string;
}) {
  const content = (
    <span className={cn("inline-flex items-center gap-2 tabular-nums", className)}>
      <span className={cn("min-w-7 text-sm font-medium", toneText[tone])}>{value}</span>
      {bar != null ? (
        <span className="bg-muted hidden h-1 w-10 overflow-hidden rounded-full sm:block" aria-hidden>
          <span className={cn("block h-full rounded-full", toneFill[tone])} style={{ width: `${Math.max(4, Math.min(100, bar))}%` }} />
        </span>
      ) : null}
    </span>
  );
  if (!title) return content;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="cursor-help">{content}</span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64 text-pretty">{title}</TooltipContent>
    </Tooltip>
  );
}

export function DemandValue({
  source,
  market,
}: {
  source: { popularity?: number | null; popularityStatus?: PopularityStatus; volume?: number | null; volumeEstimate?: number | null };
  market?: string;
}) {
  const value = demand(source, market);
  return <MetricValue value={value.value} bar={value.score} tone={value.tone} title={value.title} />;
}

export function DifficultyValue({ value }: { value: number | null | undefined }) {
  return (
    <MetricValue
      value={value ?? "—"}
      bar={value}
      tone={difficultyTone(value)}
      title="Local estimate of top-10 competition from matching apps' ratings; higher is harder."
    />
  );
}

export function OpportunityValue({ value }: { value: number | null | undefined }) {
  const tone: Tone = value == null ? "neutral" : value >= 10 ? "good" : value >= 4 ? "mid" : "low";
  return (
    <MetricValue
      value={value ?? "—"}
      tone={tone}
      title="Apple Ads popularity still to win: discounted by the difficulty estimate and by the attention your current rank already captures."
    />
  );
}
