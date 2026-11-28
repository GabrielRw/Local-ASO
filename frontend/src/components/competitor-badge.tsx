import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** Marks a keyword the user flagged as another app's name: an Apple Ads target only. */
export function CompetitorBadge() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className="shrink-0 cursor-help text-[10px] font-medium tracking-wide text-amber-700 uppercase dark:text-amber-400">
          Competitor
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-64 text-pretty">
        Marked as a competitor&rsquo;s name. App Review keeps other apps&rsquo; names out of your metadata, so this
        search can only be won with Apple Ads.
      </TooltipContent>
    </Tooltip>
  );
}
