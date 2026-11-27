import { useState, type ReactNode } from "react";
import { GitCompareArrows } from "lucide-react";
import { AppIcon } from "@/components/app-icon";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { countryFlag, formatCompact, formatDate } from "@/lib/format";
import type { AppSummary } from "@/lib/types";
import { useCompare, type CompareListing, type ComparePayload } from "./api";

const NOT_EXPOSED = <span className="text-muted-foreground">Not exposed</span>;

function text(value: string | null | undefined): ReactNode {
  return value ? value : NOT_EXPOSED;
}

function rating(app: CompareListing): ReactNode {
  if (!app.averageRating) return <span className="text-muted-foreground">No rating returned</span>;
  return (
    <span className="tabular-nums">
      ★ {app.averageRating.toFixed(1)}{" "}
      <span className="text-muted-foreground">· {formatCompact(app.ratingCount)} ratings</span>
    </span>
  );
}

function health(value: ComparePayload["primaryHealth"]): ReactNode {
  if (value?.score == null) return <span className="text-muted-foreground">Not scored</span>;
  return (
    <span>
      <span className="font-medium tabular-nums">{value.score}</span>{" "}
      <span className="text-muted-foreground">{value.label}</span>
    </span>
  );
}

type Field = { label: string; render: (app: CompareListing) => ReactNode };

const FIELDS: Field[] = [
  { label: "Title", render: (app) => <span className="font-medium">{app.name}</span> },
  { label: "Seller", render: (app) => text(app.seller) },
  { label: "Bundle ID", render: (app) => <span className="font-mono text-xs">{text(app.bundleId)}</span> },
  { label: "Genre", render: (app) => text(app.genre) },
  { label: "Version", render: (app) => text(app.version) },
  { label: "Rating", render: rating },
  {
    label: "Description length",
    render: (app) =>
      app.descriptionLength != null ? (
        <span className="tabular-nums">{formatCompact(app.descriptionLength)} characters</span>
      ) : (
        NOT_EXPOSED
      ),
  },
  {
    label: "Languages returned",
    render: (app) => (app.languages ? <span className="tabular-nums">{app.languages.length}</span> : NOT_EXPOSED),
  },
  { label: "Last update", render: (app) => (app.updatedAt ? formatDate(app.updatedAt) : NOT_EXPOSED) },
  {
    label: "Description",
    render: (app) =>
      app.description ? (
        <p className="text-muted-foreground line-clamp-6 max-w-prose text-xs whitespace-pre-line">{app.description}</p>
      ) : (
        NOT_EXPOSED
      ),
  },
];

function compareRows(data: ComparePayload): [string, ReactNode, ReactNode][] {
  return [
    ["Listing health", health(data.primaryHealth), health(data.competitorHealth)],
    ...FIELDS.map((field): [string, ReactNode, ReactNode] => [
      field.label,
      field.render(data.primary),
      field.render(data.competitor),
    ]),
  ];
}

/** Compare the selected app's public App Store listing with another configured app. */
export function ListingCompareCard({
  appId,
  country,
  apps,
}: {
  appId: number;
  country: string;
  apps: AppSummary[];
}) {
  const options = apps.filter((app) => app.active && app.appleAppId !== appId);
  const [picked, setPicked] = useState<string>("");
  const [compareId, setCompareId] = useState<number | null>(null);
  const compare = useCompare(appId, compareId, country);
  const data = compare.data;

  return (
    <Card>
      <CardHeader>
        <CardDescription>
          {countryFlag(country)} {country.toUpperCase()} · public iTunes listing data
        </CardDescription>
        <CardTitle className="text-base">Listing compare</CardTitle>
        <CardAction className="flex items-center gap-2">
          <Select value={picked} onValueChange={setPicked} disabled={!options.length}>
            <SelectTrigger size="sm" className="w-44 sm:w-56" aria-label="App to compare">
              <SelectValue placeholder={options.length ? "Choose an app" : "Add another app first"} />
            </SelectTrigger>
            <SelectContent align="end">
              {options.map((app) => (
                <SelectItem key={app.appleAppId} value={String(app.appleAppId)}>
                  {app.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            variant="outline"
            disabled={!picked || compare.isFetching}
            onClick={() => setCompareId(Number(picked))}
          >
            {compare.isFetching ? <Spinner /> : <GitCompareArrows />} Compare
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="px-0">
        {!compareId ? (
          <p className="text-muted-foreground px-6 text-sm">
            {options.length
              ? "Pick one of your other apps to put both listings side by side. Values Apple does not return are marked Not exposed, never scored as zero."
              : "Listing compare works between apps you have added to Local ASO Tracker. Add another app from the sidebar to compare."}
          </p>
        ) : compare.isError ? (
          <div className="px-6">
            <Alert variant="destructive">
              <AlertTitle>Could not compare these listings</AlertTitle>
              <AlertDescription>{compare.error.message}</AlertDescription>
            </Alert>
          </div>
        ) : !data ? (
          <div className="grid gap-2 px-6">
            <Skeleton className="h-10" />
            <Skeleton className="h-48" />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-44 pl-6">
                  <span className="sr-only">Field</span>
                </TableHead>
                <CompareHead app={data.primary} />
                <CompareHead app={data.competitor} last />
              </TableRow>
            </TableHeader>
            <TableBody>
              {compareRows(data).map(([label, primary, competitor]) => (
                <TableRow key={label}>
                  <TableHead scope="row" className="text-muted-foreground pl-6 align-top text-xs font-normal">
                    {label}
                  </TableHead>
                  <TableCell className="min-w-56 align-top text-sm whitespace-normal">{primary}</TableCell>
                  <TableCell className="min-w-56 pr-6 align-top text-sm whitespace-normal">{competitor}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function CompareHead({ app, last }: { app: CompareListing; last?: boolean }) {
  return (
    <TableHead className={last ? "h-auto py-3 pr-6" : "h-auto py-3"}>
      <div className="flex items-center gap-3">
        <AppIcon name={app.name} artworkUrl={app.artworkUrl} className="size-10" />
        <div className="grid min-w-0">
          <span className="truncate font-medium">{app.name}</span>
          <span className="text-muted-foreground truncate text-xs font-normal">
            {app.seller || app.bundleId || "App Store"}
          </span>
        </div>
      </div>
    </TableHead>
  );
}
