import { Page } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentBootstrap } from "@/lib/queries";
import { useSelection } from "@/lib/selection";
import { useCompetitorMatrix } from "./api";
import { CompetitorMatrixCard } from "./competitor-matrix";
import { ListingCompareCard } from "./listing-compare";

export function CompetitorsPage() {
  const bootstrap = useCurrentBootstrap();
  const [selection] = useSelection({
    appId: bootstrap.data?.selectedAppId,
    country: bootstrap.data?.selectedCountry,
  });
  const appId = selection.appId;
  const matrix = useCompetitorMatrix(appId, selection.country, selection.device);

  return (
    <Page title="Competitors">
      {matrix.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Competitor matrix unavailable</AlertTitle>
          <AlertDescription>{matrix.error.message}</AlertDescription>
        </Alert>
      ) : null}

      {appId && matrix.data ? (
        <CompetitorMatrixCard
          matrix={matrix.data}
          appId={appId}
          country={selection.country}
          device={selection.device}
        />
      ) : matrix.isLoading || bootstrap.isLoading ? (
        <Skeleton className="h-80" />
      ) : null}

      {appId ? (
        <ListingCompareCard appId={appId} country={selection.country} apps={bootstrap.data?.apps ?? []} />
      ) : null}
    </Page>
  );
}
