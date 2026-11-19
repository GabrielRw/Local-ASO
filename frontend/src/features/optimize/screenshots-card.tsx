import { ExternalLink, ImageOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import type { Listing } from "@/lib/types";

/**
 * Screenshots Apple's public lookup returned. When it returns none, that is a
 * gap in the API, not an empty listing, so nothing here is scored as zero.
 */
export function ScreenshotsCard({ listing }: { listing: Listing }) {
  const screenshots = listing.screenshots ?? [];
  const status = screenshots.length
    ? `${screenshots.length} returned`
    : listing.screenshotStatus === "not_exposed"
      ? "Not exposed by API"
      : "Unavailable";

  return (
    <Card>
      <CardHeader>
        <CardDescription>Apple listing media</CardDescription>
        <CardTitle className="text-base">Screenshot preview</CardTitle>
        <CardAction>
          <Badge variant={screenshots.length ? "secondary" : "outline"}>{status}</Badge>
        </CardAction>
      </CardHeader>
      <CardContent>
        {screenshots.length ? (
          <ul className="-mx-1 flex snap-x gap-3 overflow-x-auto px-1 pb-2" aria-label="App Store screenshots">
            {screenshots.map((url, index) => (
              <li key={url} className="shrink-0 snap-start">
                <figure className="grid gap-1.5">
                  <img
                    src={url}
                    loading="lazy"
                    alt={`App Store screenshot ${index + 1} for ${listing.name || "this app"}`}
                    className="bg-muted h-80 w-auto rounded-lg border object-contain sm:h-96"
                  />
                  <figcaption className="text-muted-foreground text-xs">Screenshot {index + 1}</figcaption>
                </figure>
              </li>
            ))}
          </ul>
        ) : (
          <Empty className="border">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <ImageOff />
              </EmptyMedia>
              <EmptyTitle>Screenshot data is not publicly exposed</EmptyTitle>
              <EmptyDescription>
                Apple’s public iTunes API returned no screenshot URLs. This does not mean the listing has no
                screenshots, and it is not scored as zero.
              </EmptyDescription>
            </EmptyHeader>
            {listing.url ? (
              <EmptyContent>
                <Button variant="outline" size="sm" asChild>
                  <a href={listing.url} target="_blank" rel="noreferrer">
                    Verify on App Store <ExternalLink />
                  </a>
                </Button>
              </EmptyContent>
            ) : null}
          </Empty>
        )}
      </CardContent>
    </Card>
  );
}
