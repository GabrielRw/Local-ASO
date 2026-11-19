import { ArrowUp, Lightbulb, Lock, Search } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { ScoreGauge } from "@/components/score-gauge";
import type { Health } from "@/lib/types";
import { cn } from "@/lib/utils";

export const HEALTH_SECTION_ID = "listing-health";

function bandFill(percent: number): string {
  if (percent < 40) return "bg-rose-500";
  if (percent < 75) return "bg-amber-500";
  return "bg-emerald-500";
}

/**
 * The strategy audit score. Hidden until the listing audit is saved, because
 * it is computed only from the saved repetition and title-order checks.
 */
export function HealthScore({
  health,
  unlocked,
  listingError,
  country,
  onSetUp,
}: {
  health: Health | undefined;
  unlocked: boolean;
  listingError: string | undefined;
  country: string;
  onSetUp: () => void;
}) {
  if (!unlocked) {
    return (
      <Empty id={HEALTH_SECTION_ID} className="scroll-mt-20 border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Lock />
          </EmptyMedia>
          <EmptyTitle>Complete keyword coverage to unlock scoring</EmptyTitle>
          <EmptyDescription>
            Set your growth strategy, brand term, title, subtitle, and keyword field in the listing audit above. The
            health score stays hidden until your audit is saved.
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button onClick={onSetUp}>
            <ArrowUp /> Set up listing audit
          </Button>
        </EmptyContent>
      </Empty>
    );
  }

  if (!health) {
    return (
      <Alert id={HEALTH_SECTION_ID} variant="destructive" className="scroll-mt-20">
        <AlertTitle>Listing unavailable</AlertTitle>
        <AlertDescription>{listingError || "Apple did not return listing metadata."}</AlertDescription>
      </Alert>
    );
  }

  if (health.score == null) {
    return (
      <Empty id={HEALTH_SECTION_ID} className="scroll-mt-20 border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Search />
          </EmptyMedia>
          <EmptyTitle>Complete the strategy audit</EmptyTitle>
          <EmptyDescription>
            The score is calculated only from saved keyword repetition and title-order checks.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div id={HEALTH_SECTION_ID} className="grid scroll-mt-20 items-start gap-6 lg:grid-cols-[20rem_1fr]">
      <Card>
        <CardHeader>
          <CardDescription>Strategy audit score</CardDescription>
          <CardTitle className="text-base">{health.label}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          <ScoreGauge score={health.score} />
          <p className="text-muted-foreground text-xs text-pretty">
            Calculated only from the saved listing strategy audit for {country.toUpperCase()}. Public listing fields
            are shown separately and do not affect this score.
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardDescription>Saved strategy audit</CardDescription>
          <CardTitle className="text-base">Score breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-4">
            {health.items.map((item) => {
              const available = item.available !== false;
              const percent = item.maximum ? Math.round((item.score / item.maximum) * 100) : 0;
              return (
                <li key={item.key} className="grid gap-1.5">
                  <div className="flex items-baseline justify-between gap-4">
                    <p className="text-sm font-medium">{item.label}</p>
                    <p className={cn("text-sm tabular-nums", !available && "text-muted-foreground")}>
                      {available ? `${item.score}/${item.maximum}` : "N/A"}
                    </p>
                  </div>
                  {available ? (
                    <div
                      className="bg-muted h-1.5 overflow-hidden rounded-full"
                      role="progressbar"
                      aria-label={item.label}
                      aria-valuemin={0}
                      aria-valuemax={item.maximum}
                      aria-valuenow={item.score}
                    >
                      <div className={cn("h-full rounded-full", bandFill(percent))} style={{ width: `${percent}%` }} />
                    </div>
                  ) : (
                    <p className="text-muted-foreground text-xs">Not exposed</p>
                  )}
                  <p className="text-muted-foreground text-xs text-pretty">{item.detail}</p>
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

export function HealthSuggestions({ health }: { health: Health }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>Listing improvements</CardDescription>
        <CardTitle className="text-base">Recommended next moves</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {health.suggestions.length ? (
          <ul className="grid gap-1">
            {health.suggestions.map((item) => (
              <li key={item} className="hover:bg-muted/50 flex gap-3 rounded-lg p-3 transition-colors">
                <Lightbulb className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden />
                <p className="text-sm text-pretty">{item}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">No suggestions right now.</p>
        )}
        {health.methodology ? (
          <p className="text-muted-foreground text-xs text-pretty">{health.methodology}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
