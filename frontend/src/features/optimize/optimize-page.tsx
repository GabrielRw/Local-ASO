import { AppWindow } from "lucide-react";
import { Page } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentBootstrap } from "@/lib/queries";
import { useSelection } from "@/lib/selection";
import { AppHero } from "./app-hero";
import { HEALTH_SECTION_ID, HealthScore, HealthSuggestions } from "./health-card";
import { coverageConfigured } from "./highlight";
import { COVERAGE_BRAND_INPUT_ID, COVERAGE_SECTION_ID, ListingCoverage } from "./listing-coverage";
import { LocalizationStudio } from "./localization-studio";
import { ScreenshotsCard } from "./screenshots-card";

function scrollToSection(id: string, focusId?: string) {
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  document.getElementById(id)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  if (focusId) document.getElementById(focusId)?.focus({ preventScroll: true });
}

export function OptimizePage() {
  const bootstrap = useCurrentBootstrap();
  const data = bootstrap.data;
  const [selection, select] = useSelection({ appId: data?.selectedAppId, country: data?.selectedCountry });
  const appId = selection.appId;
  const listing = data?.listing;
  const unlocked = coverageConfigured(data?.listingMetadata);

  return (
    <Page title="Optimize">
      {bootstrap.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load this app</AlertTitle>
          <AlertDescription>{bootstrap.error.message}</AlertDescription>
        </Alert>
      ) : null}

      {!data && bootstrap.isLoading ? (
        <>
          <Skeleton className="h-36" />
          <Skeleton className="h-96" />
        </>
      ) : null}

      {data && !appId ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <AppWindow />
            </EmptyMedia>
            <EmptyTitle>No app selected</EmptyTitle>
            <EmptyDescription>Add an App Store app by its numerical ID to optimize its listing.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {data && appId && !listing ? (
        <Alert variant="destructive">
          <AlertTitle>Listing unavailable</AlertTitle>
          <AlertDescription>{data.listingError || "Apple did not return listing metadata for this storefront."}</AlertDescription>
        </Alert>
      ) : null}

      {data && appId && listing ? (
        <>
          <AppHero
            listing={listing}
            health={data.health}
            scoreUnlocked={unlocked}
            country={selection.country}
            device={selection.device}
            onOpenScore={() => scrollToSection(HEALTH_SECTION_ID)}
          />
          <ListingCoverage
            key={data.selectedAppId ?? appId}
            appId={appId}
            device={selection.device}
            listing={listing}
            metadata={data.listingMetadata}
            countries={data.countries}
            currentCountry={selection.country}
            loading={bootstrap.isPlaceholderData}
            onCountryChange={(country) => select({ country })}
          />
          <HealthScore
            health={data.health}
            unlocked={unlocked}
            listingError={data.listingError}
            country={selection.country}
            onSetUp={() => scrollToSection(COVERAGE_SECTION_ID, COVERAGE_BRAND_INPUT_ID)}
          />
          {unlocked && data.health ? <HealthSuggestions health={data.health} /> : null}
          <ScreenshotsCard listing={listing} />
        </>
      ) : null}

      {data && appId ? <LocalizationStudio key={appId} appId={appId} country={selection.country} /> : null}
    </Page>
  );
}
