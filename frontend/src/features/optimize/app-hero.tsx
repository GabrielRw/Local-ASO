import { ExternalLink, Star } from "lucide-react";
import { AppIcon } from "@/components/app-icon";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { countryFlag, deviceName, formatBytes, formatCompact, relativeDays } from "@/lib/format";
import type { Device, Health, Listing } from "@/lib/types";
import { cn } from "@/lib/utils";

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className={cn("grid min-w-0 gap-0.5", className)}>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="truncate text-sm font-medium">{value}</dd>
    </div>
  );
}

/** Public App Store facts for the selected app, plus a shortcut to the saved strategy score. */
export function AppHero({
  listing,
  health,
  scoreUnlocked,
  country,
  device,
  onOpenScore,
}: {
  listing: Listing;
  health: Health | undefined;
  scoreUnlocked: boolean;
  country: string;
  device: Device;
  onOpenScore: () => void;
}) {
  const score = scoreUnlocked ? (health?.score ?? null) : null;
  const ratingWord = listing.ratingCount === 1 ? "rating" : "ratings";
  const rating = listing.averageRating
    ? `${listing.averageRating.toFixed(1)} (${formatCompact(listing.ratingCount)} ${ratingWord})`
    : "No rating yet";
  const updated = listing.updatedAt ? `Updated ${relativeDays(listing.updatedAt)}` : "No update date";

  return (
    <Card className="gap-4 py-5">
      <CardContent className="grid gap-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
        <div className="flex min-w-0 items-center gap-4">
          <AppIcon name={listing.name} artworkUrl={listing.artworkUrl} className="size-16 text-base" />
          <div className="grid min-w-0 gap-0.5">
            <h2 className="truncate text-lg font-semibold tracking-tight">{listing.name}</h2>
            <p className="text-muted-foreground truncate text-sm">
              {listing.seller || listing.bundleId || "Apple App Store"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-6">
          <dl className="grid flex-1 grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
            <Stat label="Genre" value={listing.genre || "—"} />
            <Stat label="Version" value={listing.version || "—"} />
            <Stat label="Size" value={formatBytes(listing.fileSizeBytes)} />
            <Stat label="Price" value={listing.price || "—"} />
          </dl>
          <button
            type="button"
            onClick={onOpenScore}
            aria-label={score != null ? `Strategy audit score ${score}. Open the score breakdown` : "Complete the listing audit to unlock the score"}
            className="focus-visible:ring-ring/50 hover:bg-muted/60 grid size-16 shrink-0 place-items-center rounded-full border-4 transition-colors focus-visible:ring-[3px] focus-visible:outline-none"
          >
            <span className={cn("text-sm font-semibold tabular-nums", score != null && "text-lg")}>
              {score != null ? score : "Audit"}
            </span>
          </button>
        </div>
      </CardContent>
      <Separator />
      <CardContent className="text-muted-foreground flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-xs">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="inline-flex items-center gap-1">
            <Star className="size-3.5 fill-current" aria-hidden /> {rating}
          </span>
          <span>{updated}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span>
            {countryFlag(country)} {country.toUpperCase()} · {deviceName(device)} rankings
          </span>
          {listing.url ? (
            <a
              href={listing.url}
              target="_blank"
              rel="noreferrer"
              className="text-foreground inline-flex items-center gap-1 font-medium underline-offset-4 hover:underline"
            >
              View on App Store <ExternalLink className="size-3" aria-hidden />
            </a>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
