import { cn } from "@/lib/utils";

export function scoreLabel(score: number | null | undefined): string {
  if (score == null) return "Not audited";
  if (score >= 75) return "Strong";
  if (score >= 50) return "Needs work";
  return "Needs attention";
}

function scoreStroke(score: number | null | undefined): string {
  if (score == null) return "stroke-muted-foreground/30";
  if (score >= 75) return "stroke-emerald-500";
  if (score >= 50) return "stroke-amber-500";
  return "stroke-rose-500";
}

/** Half-circle 0–100 gauge. */
export function ScoreGauge({ score, className }: { score: number | null | undefined; className?: string }) {
  return (
    <div className={cn("relative mx-auto w-44", className)}>
      <svg viewBox="0 0 180 100" className="w-full" aria-hidden>
        <path
          d="M 18 92 A 72 72 0 0 1 162 92"
          pathLength={100}
          className="stroke-muted fill-none"
          strokeWidth={12}
          strokeLinecap="round"
        />
        <path
          d="M 18 92 A 72 72 0 0 1 162 92"
          pathLength={100}
          className={cn("fill-none transition-[stroke-dasharray] duration-700 motion-reduce:transition-none", scoreStroke(score))}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={`${score ?? 0} 100`}
        />
      </svg>
      <div className="absolute inset-x-0 bottom-0 flex flex-col items-center">
        <span className="text-4xl font-semibold tracking-tight tabular-nums">{score ?? "—"}</span>
        <span className="text-muted-foreground text-xs">of 100</span>
      </div>
    </div>
  );
}
