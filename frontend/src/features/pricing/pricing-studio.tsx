import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeDollarSign, Lock, PlugZap, RefreshCw, Send, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { connectionReady } from "@/components/app-store-connect-settings";
import { useDialogs } from "@/components/dialogs";
import { useWritesLocked } from "@/lib/licence";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiGet, apiPost } from "@/lib/api";
import { formatDateTime, formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useLocalizationStudio } from "@/features/optimize/queries";
import { changeLabel, changeable, defaultSelection, parsePercent, percentInput } from "./plan";
import type { PricedItem, PriceSuggestions, PricePushResult, PricingData } from "./types";

const KIND_LABEL: Record<PricedItem["kind"], string> = { app: "App", iap: "In-app purchase", subscription: "Subscription" };
const itemKey = (item: Pick<PricedItem, "kind" | "id">) => `${item.kind}:${item.id}`;

/**
 * Purchasing-power price suggestions: Apple's equalized price per territory, scaled by
 * the bundled World Bank price level ratio and snapped to a real Apple price point.
 * Nothing changes in App Store Connect until each territory is confirmed.
 */
export function PricingStudio({ appId, country }: { appId: number; country: string }) {
  const client = useQueryClient();
  const pricing = useQuery({
    queryKey: ["pricing", appId],
    queryFn: ({ signal }) => apiGet<PricingData>("/api/pricing", { appId }, signal),
    staleTime: 60_000,
  });
  const localization = useLocalizationStudio(appId, country);

  const [items, setItems] = useState<PricedItem[] | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [scope, setScope] = useState<"tracked" | "all">("tracked");
  const [floorText, setFloorText] = useState<string | null>(null);
  const [ceilingText, setCeilingText] = useState<string | null>(null);
  const [result, setResult] = useState<PriceSuggestions | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [preserve, setPreserve] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const locked = useWritesLocked();
  const dialogs = useDialogs();

  const onError = (error: Error) => toast.error(error.message);
  const load = useMutation({
    mutationFn: () => apiPost<{ items: PricedItem[] }>("/api/pricing/items", { appId }),
    onSuccess: ({ items: found }) => {
      setItems(found);
      setSelectedKey((current) => current ?? (found[0] ? itemKey(found[0]) : null));
    },
    onError,
  });

  const data = pricing.data;
  const floor = parsePercent(floorText ?? percentInput(data?.defaults.floor ?? 0.35));
  const ceiling = parsePercent(ceilingText ?? percentInput(data?.defaults.ceiling ?? 1));
  const boundsValid = floor != null && ceiling != null && floor <= ceiling;
  const item = items?.find((entry) => itemKey(entry) === selectedKey) ?? null;

  const suggest = useMutation({
    mutationFn: () =>
      apiPost<PriceSuggestions>("/api/pricing/suggest", { appId, kind: item?.kind, id: item?.id, scope, floor, ceiling }),
    onSuccess: (suggestions) => {
      setResult(suggestions);
      setChosen(defaultSelection(suggestions.rows));
    },
    onError,
  });

  const push = useMutation({
    mutationFn: () => {
      if (!result || !item) throw new Error("Load suggestions first");
      const changes = result.rows
        .filter((row) => chosen.has(row.territory) && changeable(row))
        .map((row) => ({ territory: row.territory, pricePointId: row.suggestedPointId, price: row.suggestedPrice, currency: row.currency }));
      return apiPost<PricePushResult>("/api/pricing/push", {
        appId,
        kind: item.kind,
        id: item.id,
        name: item.name,
        changes,
        preserveCurrentPrice: preserve,
      });
    },
    onSuccess: async (outcome) => {
      const failed = outcome.results.filter((entry) => entry.error);
      if (failed.length) toast.error(failed[0]?.error ?? "Some prices were not changed. See the price log.");
      else toast.success(`${outcome.results.length} territory prices changed in App Store Connect.`);
      await client.invalidateQueries({ queryKey: ["pricing", appId] });
      suggest.mutate();
    },
    onError,
  });

  if (pricing.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Could not load pricing</AlertTitle>
        <AlertDescription>{pricing.error.message}</AlertDescription>
      </Alert>
    );
  }
  if (!data) return <Skeleton className="h-60" />;

  const connection = localization.data?.connection;
  const ready = connectionReady(connection);
  const resultMatches = result && item && result.kind === item.kind && result.id === item.id;
  const rows = resultMatches ? result.rows : [];
  const pending = rows.filter((row) => chosen.has(row.territory) && changeable(row));
  const toggle = (territory: string, on: boolean) =>
    setChosen((current) => {
      const next = new Set(current);
      if (on) next.add(territory);
      else next.delete(territory);
      return next;
    });

  return (
    <Card>
      <CardHeader>
        <CardDescription>Country pricing</CardDescription>
        <CardTitle className="text-base">Purchasing-power prices</CardTitle>
        <CardAction>
          <Badge variant={ready ? "secondary" : "outline"}>
            {ready ? <ShieldCheck /> : <PlugZap />}
            {ready ? "App Store Connect ready" : "App Store Connect not ready"}
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-6">
        <p className="text-muted-foreground text-sm text-pretty">
          Suggestions start from Apple’s equalized price in each territory and scale it by that country’s price
          level relative to your base territory, then snap to a real Apple price point. Price levels come from the{" "}
          <span className="text-foreground">World Bank ({data.ppp.latestYear ?? "latest"})</span>, bundled with the app
          on {data.ppp.retrieved}. They are not sales or demand data.
        </p>

        {!ready ? (
          <Alert>
            <PlugZap />
            <AlertTitle>Connect App Store Connect to read prices</AlertTitle>
            <AlertDescription>
              Add an App Store Connect API key in the listing localization studio above. Reading prices needs any
              role; changing them needs Admin or App Manager.
            </AlertDescription>
          </Alert>
        ) : (
          <>
            <div className="grid items-end gap-4 md:grid-cols-[minmax(0,1fr)_10rem_6rem_6rem_auto]">
              <Field>
                <FieldLabel htmlFor="pricing-item">Product</FieldLabel>
                {items ? (
                  <Select value={selectedKey ?? undefined} onValueChange={setSelectedKey}>
                    <SelectTrigger id="pricing-item" className="w-full">
                      <SelectValue placeholder="Choose a product" />
                    </SelectTrigger>
                    <SelectContent>
                      {items.map((entry) => (
                        <SelectItem key={itemKey(entry)} value={itemKey(entry)}>
                          {KIND_LABEL[entry.kind]} · {entry.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Button id="pricing-item" variant="outline" className="justify-start" disabled={load.isPending} onClick={() => load.mutate()}>
                    {load.isPending ? <Spinner /> : <RefreshCw />}
                    Load app, IAPs and subscriptions
                  </Button>
                )}
              </Field>
              <Field>
                <FieldLabel htmlFor="pricing-scope">Territories</FieldLabel>
                <Select value={scope} onValueChange={(value) => setScope(value === "all" ? "all" : "tracked")}>
                  <SelectTrigger id="pricing-scope" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="tracked">Tracked ({data.trackedTerritories.length})</SelectItem>
                    <SelectItem value="all">All territories</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="pricing-floor">Floor %</FieldLabel>
                <Input
                  id="pricing-floor"
                  inputMode="numeric"
                  value={floorText ?? percentInput(data.defaults.floor)}
                  aria-invalid={!boundsValid}
                  onChange={(event) => setFloorText(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="pricing-ceiling">Ceiling %</FieldLabel>
                <Input
                  id="pricing-ceiling"
                  inputMode="numeric"
                  value={ceilingText ?? percentInput(data.defaults.ceiling)}
                  aria-invalid={!boundsValid}
                  onChange={(event) => setCeilingText(event.target.value)}
                />
              </Field>
              <Button disabled={!item || !boundsValid || suggest.isPending} onClick={() => suggest.mutate()}>
                {suggest.isPending ? <Spinner /> : <BadgeDollarSign />}
                Suggest prices
              </Button>
            </div>
            <FieldDescription>
              The floor and ceiling bound each territory’s price relative to the base territory’s equalized price.
              Reading prices makes no changes.
            </FieldDescription>

            {resultMatches ? (
              <div className="grid gap-3">
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span>
                    Base: {result.baseTerritory} at {formatMoney(result.basePrice, result.baseCurrency)}
                  </span>
                  {item?.kind === "subscription" ? (
                    <Label className="ml-auto flex items-center gap-2 font-normal">
                      <Switch checked={preserve} onCheckedChange={setPreserve} />
                      Existing subscribers keep their price
                    </Label>
                  ) : null}
                </div>
                {rows.length ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-8">
                          <span className="sr-only">Include</span>
                        </TableHead>
                        <TableHead>Territory</TableHead>
                        <TableHead className="text-right">Current</TableHead>
                        <TableHead className="text-right">Apple equalized</TableHead>
                        <TableHead className="text-right">Price level</TableHead>
                        <TableHead className="text-right">Suggested</TableHead>
                        <TableHead className="text-right">Change</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rows.map((row) => {
                        const canChange = changeable(row);
                        return (
                          <TableRow key={row.territory} className={cn(!canChange && "text-muted-foreground")}>
                            <TableCell>
                              <Checkbox
                                aria-label={`Change the price in ${row.territory}`}
                                checked={canChange && chosen.has(row.territory)}
                                disabled={!canChange}
                                onCheckedChange={(checked) => toggle(row.territory, checked === true)}
                              />
                            </TableCell>
                            <TableCell>
                              {row.territory}
                              {row.manual ? (
                                <Badge variant="outline" className="ml-2">
                                  Manual
                                </Badge>
                              ) : null}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">{formatMoney(row.currentPrice, row.currency)}</TableCell>
                            <TableCell className="text-right tabular-nums">{formatMoney(row.equalizedPrice, row.currency)}</TableCell>
                            <TableCell className="text-right tabular-nums">
                              {row.pppRatio == null ? (
                                <span title="No World Bank price level for this territory">No data</span>
                              ) : (
                                <>
                                  {row.pppRatio.toFixed(2)}
                                  {row.ratio != null && Math.abs(row.ratio - row.pppRatio) > 0.005 ? (
                                    <span className="text-muted-foreground"> → {row.ratio.toFixed(2)}</span>
                                  ) : null}
                                </>
                              )}
                            </TableCell>
                            <TableCell className="text-right font-medium tabular-nums">{formatMoney(row.suggestedPrice, row.currency)}</TableCell>
                            <TableCell
                              className={cn(
                                "text-right tabular-nums",
                                row.changePercent != null && row.changePercent < 0 && "text-emerald-600 dark:text-emerald-400",
                              )}
                            >
                              {changeLabel(row.changePercent)}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="text-muted-foreground text-sm">No territories to suggest for. Track more storefronts or choose all territories.</p>
                )}
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-muted-foreground text-xs">
                    Price level is the World Bank ratio relative to {result.baseTerritory}; an arrow shows where the floor or ceiling applied.
                  </span>
                  <Button
                    className="ml-auto"
                    disabled={!pending.length || push.isPending}
                    onClick={() => (locked ? dialogs.open("licence") : setConfirming(true))}
                  >
                    {push.isPending ? <Spinner /> : locked ? <Lock /> : <Send />}
                    {locked ? "Licence required to push" : `Review ${pending.length} ${pending.length === 1 ? "change" : "changes"}`}
                  </Button>
                </div>
              </div>
            ) : null}
          </>
        )}

        {data.events.length ? (
          <section aria-labelledby="pricing-log" className="grid gap-2">
            <h3 id="pricing-log" className="text-sm font-medium">
              Price log
            </h3>
            <ul className="grid gap-1 text-sm">
              {data.events.slice(0, 30).map((event, index) => (
                <li key={`${event.createdAt}-${event.territory}-${index}`} className="flex flex-wrap items-center gap-2">
                  <Badge variant={event.status === "success" ? "secondary" : "destructive"}>{event.status === "success" ? "Changed" : "Failed"}</Badge>
                  <span>
                    {event.itemName} · {event.territory}: {formatMoney(event.beforePrice, event.currency || null)} →{" "}
                    {formatMoney(event.afterPrice, event.currency || null)}
                  </span>
                  <span className="text-muted-foreground text-xs">{formatDateTime(event.createdAt)}</span>
                  {event.error ? <span className="text-destructive w-full text-xs">{event.error}</span> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </CardContent>

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent className="sm:max-w-lg">
          <AlertDialogHeader>
            <AlertDialogTitle>Change {pending.length} prices in App Store Connect?</AlertDialogTitle>
            <AlertDialogDescription>
              {item ? `${KIND_LABEL[item.kind]} · ${item.name}. ` : ""}
              New prices start immediately and customers see them. Every other manual price is kept.
              {item?.kind === "subscription"
                ? preserve
                  ? " Existing subscribers keep their current price."
                  : " Existing subscribers move to the new price, and Apple may notify them."
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ul className="grid max-h-72 gap-1 overflow-y-auto rounded-md border p-2 text-sm">
            {pending.map((row) => (
              <li key={row.territory} className="flex items-center gap-2 tabular-nums">
                <span className="w-12 font-medium">{row.territory}</span>
                <span className="text-muted-foreground">{formatMoney(row.currentPrice, row.currency)}</span>→
                <span>{formatMoney(row.suggestedPrice, row.currency)}</span>
                <span className="text-muted-foreground ml-auto text-xs">{changeLabel(row.changePercent)}</span>
              </li>
            ))}
          </ul>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => push.mutate()}>Change prices</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
