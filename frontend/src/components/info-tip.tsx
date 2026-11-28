import { Info } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/** How a metric is calculated: a short text, an optional formula, and its terms or scale. */
export interface MetricExplanation {
  title: string;
  summary: string;
  formula?: string;
  details?: string[];
}

/** An (i) button that opens the explanation of a metric, for column headers and cards. */
export function InfoTip({ info, className }: { info: MetricExplanation; className?: string }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`How ${info.title} is calculated`}
          className={cn(
            "text-muted-foreground hover:text-foreground focus-visible:ring-ring/50 inline-flex size-5 items-center justify-center rounded-full focus-visible:ring-[3px] focus-visible:outline-none",
            className,
          )}
        >
          <Info className="size-3.5" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 gap-2 text-xs leading-relaxed font-normal">
        <p className="text-foreground text-sm font-medium">{info.title}</p>
        <p className="text-muted-foreground text-pretty">{info.summary}</p>
        {info.formula ? (
          <code className="bg-muted text-foreground block rounded-md px-2 py-1.5 font-mono text-[11px] text-pretty">
            {info.formula}
          </code>
        ) : null}
        {info.details?.length ? (
          <ul className="text-muted-foreground grid list-disc gap-1 pl-4 text-pretty">
            {info.details.map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ul>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
