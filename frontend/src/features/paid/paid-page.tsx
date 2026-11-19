import { useMutation } from "@tanstack/react-query";
import { Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { DemandValue, MetricValue } from "@/components/metric";
import { Page } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiPost } from "@/lib/api";
import { countryFlag, deviceName, formatCompact, formatDate, formatMoney } from "@/lib/format";
import { useTrackKeywords } from "@/lib/mutations";
import { useCurrentBootstrap, useInvalidate } from "@/lib/queries";
import { useSelection } from "@/lib/selection";
import type { Device } from "@/lib/types";
import { usePaidCache, useAppleAds, type AppleAdsPayload, type PaidCampaign, type PaidSuggestion } from "./api";
import { PaidKeywordsCard } from "./paid-keywords";
import { ChooseAccount, CredentialSetup, DiscoverAccounts } from "./paid-setup";

export function PaidPage() {
  const bootstrap = useCurrentBootstrap();
  const [selection] = useSelection({
    appId: bootstrap.data?.selectedAppId,
    country: bootstrap.data?.selectedCountry,
  });
  const { appId, country, device } = selection;
  const ads = useAppleAds(appId, country, device);
  const cache = usePaidCache();
  const invalidate = useInvalidate();
  const data = ads.data;

  const sync = useMutation({
    mutationFn: () => apiPost<AppleAdsPayload>("/api/apple-ads/sync", { appId, country, device, days: 30 }),
    onSuccess: async (result) => {
      if (appId != null) cache.set(appId, country, device, result);
      toast.success(
        `Apple Ads synced: ${result.sync?.keywords ?? 0} keywords and ${result.sync?.suggestions ?? 0} suggestions`,
      );
      // Sync also refreshes Apple popularity for tracked keywords.
      await invalidate.bootstrap();
    },
    onError: (error) => toast.error(error.message),
  });
  const discover = useMutation({
    mutationFn: () => apiPost("/api/apple-ads/discover", {}),
    onSuccess: async () => {
      toast.success("Apple Ads accounts discovered");
      await cache.invalidate();
    },
    onError: (error) => toast.error(error.message),
  });
  const chooseAccount = useMutation({
    mutationFn: (adAccountId: number) => apiPost("/api/apple-ads/account", { adAccountId }),
    onSuccess: async () => {
      await cache.invalidate();
      sync.mutate();
    },
    onError: (error) => toast.error(error.message),
  });

  const accounts = data?.accounts ?? [];
  const selected = accounts.find((account) => account.id === data?.selectedAccountId);
  const ready = Boolean(data?.credentials.available && selected);
  const busy = sync.isPending || chooseAccount.isPending;

  const actions = ready ? (
    <>
      <Select
        value={String(selected?.id ?? "")}
        onValueChange={(value) => chooseAccount.mutate(Number(value))}
        disabled={busy}
      >
        <SelectTrigger size="sm" className="hidden w-[11rem] md:flex" aria-label="Apple Ads account">
          <SelectValue />
        </SelectTrigger>
        <SelectContent align="end">
          {accounts.map((account) => (
            <SelectItem key={account.id} value={String(account.id)}>
              {account.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button size="sm" onClick={() => sync.mutate()} disabled={!appId || busy}>
        {sync.isPending ? <Spinner /> : <RefreshCw />}
        <span className="hidden md:inline">{sync.isPending ? "Syncing…" : "Sync Apple Ads"}</span>
      </Button>
    </>
  ) : null;

  return (
    <Page title="Paid search" actions={actions}>
      {ads.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Apple Ads unavailable</AlertTitle>
          <AlertDescription>{ads.error.message}</AlertDescription>
        </Alert>
      ) : null}

      {!data && (ads.isLoading || bootstrap.isLoading) ? (
        <div className="grid gap-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {Array.from({ length: 5 }, (_, index) => (
              <Skeleton key={index} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-64" />
        </div>
      ) : null}

      {data && !data.credentials.available ? (
        <CredentialSetup credentials={data.credentials} pending={discover.isPending} onCheck={() => discover.mutate()} />
      ) : null}
      {data?.credentials.available && !accounts.length ? (
        <DiscoverAccounts pending={discover.isPending} onDiscover={() => discover.mutate()} />
      ) : null}
      {data?.credentials.available && accounts.length > 0 && !selected ? (
        <ChooseAccount accounts={accounts} pending={busy} onSelect={(id) => chooseAccount.mutate(id)} />
      ) : null}

      {data && ready && selected && appId != null ? (
        <>
          <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="text-foreground font-medium">{selected.name}</span>
            <span>
              {countryFlag(country)} {country.toUpperCase()} · {deviceName(device)} · last {data.window.days} completed
              days
            </span>
            <Badge variant="outline" className="font-normal">
              {selected.lastSyncedAt ? `Synced ${formatDate(selected.lastSyncedAt)}` : "Not synced yet"}
            </Badge>
            <span className="text-xs">Read-only: campaigns are never changed from here.</span>
          </div>
          {sync.isPending ? (
            <Alert>
              <Spinner />
              <AlertTitle>Syncing Apple Ads</AlertTitle>
              <AlertDescription>
                Importing campaigns, keywords, 30 days of reports, and suggestions. This can take a minute.
              </AlertDescription>
            </Alert>
          ) : null}
          <SummaryCards data={data} country={country} device={device} />
          <CampaignsCard campaigns={data.campaigns} />
          <PaidKeywordsCard groups={data.keywordCountries} appId={appId} country={country} device={device} />
          <SuggestionsCard suggestions={data.suggestions} appId={appId} country={country} device={device} />
        </>
      ) : null}
    </Page>
  );
}

function SummaryCards({ data, country, device }: { data: AppleAdsPayload; country: string; device: Device }) {
  const all = data.allMarketsSummary;
  const market = data.summary;
  const where = `${country.toUpperCase()} · ${deviceName(device)}`;
  const cards = [
    {
      label: `Spend · ${where}`,
      value: formatMoney(market.spend, market.currency),
      note: `${formatMoney(all.spend, all.currency)} across all markets`,
    },
    {
      label: "Impressions",
      value: formatCompact(market.impressions),
      note: `${formatCompact(all.impressions)} across all markets`,
    },
    {
      label: "Taps",
      value: formatCompact(market.taps),
      note: `${formatCompact(all.taps)} across all markets`,
    },
    {
      label: "Installs",
      value: formatCompact(market.tapInstalls),
      note: `Tap-through · ${formatCompact(market.totalInstalls)} total`,
    },
    {
      label: "Cost per tap",
      value: formatMoney(market.cpt, market.currency),
      note: "Apple-reported spend ÷ taps",
    },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
      {cards.map((card) => (
        <Card key={card.label} className="gap-1 py-4">
          <CardHeader className="px-4">
            <CardDescription className="text-xs">{card.label}</CardDescription>
            <CardTitle className="text-xl font-semibold tabular-nums">{card.value}</CardTitle>
          </CardHeader>
          <CardContent className="text-muted-foreground px-4 text-xs">{card.note}</CardContent>
        </Card>
      ))}
    </div>
  );
}

function CampaignsCard({ campaigns }: { campaigns: PaidCampaign[] }) {
  const enabled = campaigns.filter((item) => item.status === "ENABLED" && !item.deleted).length;
  return (
    <Card>
      <CardHeader>
        <CardDescription>Campaign overview · selected storefront and device</CardDescription>
        <CardTitle className="text-base">Campaigns promoting this app</CardTitle>
        <CardAction>
          <Badge variant="secondary" className="font-normal">
            {enabled} enabled
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="px-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Campaign</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Keywords</TableHead>
              <TableHead className="text-right">Spend</TableHead>
              <TableHead className="text-right">Impressions</TableHead>
              <TableHead className="text-right">Taps</TableHead>
              <TableHead className="pr-6 text-right">Installs</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {campaigns.length ? (
              campaigns.map((campaign) => (
                <TableRow key={campaign.id}>
                  <TableCell className="max-w-72 truncate pl-6 font-medium">{campaign.name}</TableCell>
                  <TableCell>
                    <Badge
                      variant={campaign.status === "ENABLED" ? "secondary" : "outline"}
                      className="font-normal capitalize"
                    >
                      {campaign.status.toLowerCase()}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {campaign.enabledKeywordCount}/{campaign.keywordCount}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMoney(campaign.summary.spend, campaign.summary.currency)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatCompact(campaign.summary.impressions)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatCompact(campaign.summary.taps)}</TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">
                    {formatCompact(campaign.summary.tapInstalls)}
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={7} className="text-muted-foreground py-8 pl-6 text-sm">
                  No campaigns promote this app in the selected account. Sync Apple Ads after creating one.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function SuggestionPopularity({ value, country }: { value: number | null; country: string }) {
  if (value == null) {
    return (
      <MetricValue
        value="—"
        tone="neutral"
        title={`Apple Ads returned no popularity for this exact keyword in ${country.toUpperCase()}.`}
      />
    );
  }
  return <DemandValue source={{ popularity: value, popularityStatus: "measured" }} market={country} />;
}

function SuggestionsCard({
  suggestions,
  appId,
  country,
  device,
}: {
  suggestions: PaidSuggestion[];
  appId: number;
  country: string;
  device: Device;
}) {
  const track = useTrackKeywords();
  const cache = usePaidCache();
  const shown = suggestions.slice(0, 30);
  return (
    <Card>
      <CardHeader>
        <CardDescription>Apple suggestions · {countryFlag(country)} {country.toUpperCase()}</CardDescription>
        <CardTitle className="text-base">Related keywords to target</CardTitle>
        <CardDescription className="text-pretty">
          Seeded by your best-ranking ASO keywords. Popularity is Apple Ads&rsquo; own 5&ndash;100 score, shown only
          where it was measured for that exact keyword; it is not search volume.
        </CardDescription>
        <CardAction>
          <Badge variant="secondary" className="font-normal">
            {suggestions.length} suggestions
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="px-0">
        {shown.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Keyword</TableHead>
                <TableHead>Popularity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="pr-6 text-right">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((item) => {
                const pending = track.isPending && track.variables?.keywords[0] === item.text;
                return (
                  <TableRow key={item.text}>
                    <TableCell className="max-w-72 truncate pl-6 font-medium">{item.text}</TableCell>
                    <TableCell>
                      <SuggestionPopularity value={item.popularity} country={country} />
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {item.inAsoTracker ? "Tracked in ASO" : item.inAppleAds ? "Already targeted" : "New opportunity"}
                    </TableCell>
                    <TableCell className="pr-6 text-right">
                      {item.inAsoTracker ? (
                        <span className="text-muted-foreground text-xs">Tracked</span>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={track.isPending}
                          onClick={() =>
                            track.mutate(
                              { appId, keywords: [item.text], countries: [country], devices: [device] },
                              { onSuccess: () => void cache.invalidate() },
                            )
                          }
                        >
                          {pending ? <Spinner /> : <Plus />} Track in ASO
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : (
          <div className="px-6">
            <Empty className="border">
              <EmptyHeader>
                <EmptyTitle>No suggestions synced for this market</EmptyTitle>
                <EmptyDescription>Sync Apple Ads to fetch suggestions seeded by your tracked keywords.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
