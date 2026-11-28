import { useMemo, useState } from "react";
import { CircleAlert, CircleCheck, Info, Lightbulb, Plus, Search, TriangleAlert } from "lucide-react";
import { DemandValue, DifficultyValue, OpportunityValue } from "@/components/metric";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardAction } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { countryFlag, demand, rankLabel } from "@/lib/format";
import { useTrackKeywords } from "@/lib/mutations";
import type { AuditCountry, AuditFinding, AuditKeyword, Device, Ranking } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ScoreGauge, scoreLabel } from "@/components/score-gauge";

const SUB_SCORES = [
  { key: "rankingScore", label: "Ranking visibility", weight: 40 },
  { key: "listingScore", label: "Listing intent coverage", weight: 30 },
  { key: "localizationScore", label: "Localization", weight: 20 },
  { key: "competitionScore", label: "Competition opportunity", weight: 10 },
] as const;

export function ScoreCard({ country }: { country: AuditCountry }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>
          {countryFlag(country.code)} {country.name} audit
        </CardDescription>
        <CardTitle className="text-base">{scoreLabel(country.score)}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-5">
        <ScoreGauge score={country.score} />
        <dl className="grid gap-2.5">
          {SUB_SCORES.map((item) => {
            const value = country[item.key];
            return (
              <div key={item.key} className="grid gap-1">
                <div className="flex items-baseline justify-between text-xs">
                  <dt className="text-muted-foreground">
                    {item.label} <span className="text-muted-foreground/70">· {item.weight}%</span>
                  </dt>
                  <dd className="font-medium tabular-nums">{value ?? "—"}</dd>
                </div>
                <div className="bg-muted h-1.5 overflow-hidden rounded-full" aria-hidden>
                  <div className="bg-primary/80 h-full rounded-full" style={{ width: `${value ?? 0}%` }} />
                </div>
              </div>
            );
          })}
        </dl>
      </CardContent>
    </Card>
  );
}

const toneIcon = {
  positive: { icon: CircleCheck, className: "text-emerald-600 dark:text-emerald-400" },
  info: { icon: Info, className: "text-sky-600 dark:text-sky-400" },
  warning: { icon: TriangleAlert, className: "text-amber-600 dark:text-amber-400" },
  danger: { icon: CircleAlert, className: "text-rose-600 dark:text-rose-400" },
} as const;

/** A keyword mentioned in a finding, with its verified evidence on hover. */
function TermChip({
  term,
  country,
  device,
  audited,
  tracked,
}: {
  term: string;
  country: string;
  device: Device;
  audited: Map<string, AuditKeyword>;
  tracked: Ranking[];
}) {
  const key = term.toLocaleLowerCase();
  const fromAudit = audited.get(key);
  const fromTracking = tracked.find(
    (row) => row.country === country && row.device === device && row.keyword.toLocaleLowerCase() === key,
  );
  const source = fromAudit ?? fromTracking;
  const chip = (
    <Badge variant="secondary" className="font-normal">
      {term}
    </Badge>
  );
  if (!source) return chip;
  const value = demand(fromAudit ?? fromTracking, country);
  const difficulty = fromAudit?.difficulty ?? fromTracking?.difficultyEstimate;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" className="rounded-md focus-visible:ring-ring/50 focus-visible:ring-[3px] focus-visible:outline-none">
          {chip}
        </button>
      </TooltipTrigger>
      <TooltipContent className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5 text-xs">
        <span className="opacity-70">Rank</span>
        <span className="tabular-nums">{rankLabel(source)}</span>
        <span className="opacity-70">{value.label}</span>
        <span className="tabular-nums">{value.value}</span>
        <span className="opacity-70">Difficulty</span>
        <span className="tabular-nums">{difficulty ?? "—"}</span>
        {fromAudit?.opportunity != null ? (
          <>
            <span className="opacity-70">Opportunity</span>
            <span className="tabular-nums">{fromAudit.opportunity}</span>
          </>
        ) : null}
      </TooltipContent>
    </Tooltip>
  );
}

export function FindingsCard({
  country,
  device,
  tracked,
}: {
  country: AuditCountry;
  device: Device;
  tracked: Ranking[];
}) {
  const audited = useMemo(
    () => new Map(country.keywords.map((item) => [item.keyword.toLocaleLowerCase(), item])),
    [country.keywords],
  );
  return (
    <Card>
      <CardHeader>
        <CardDescription>Grounded in your listing, tracked ranks, and Apple search results</CardDescription>
        <CardTitle className="text-base">What to fix next</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {country.summary ? <p className="text-muted-foreground text-sm text-pretty">{country.summary}</p> : null}
        {country.findings.length ? (
          <ol className="grid gap-1">
            {country.findings.slice(0, 6).map((finding: AuditFinding, index) => {
              const tone = toneIcon[finding.tone] ?? toneIcon.info;
              return (
                <li key={`${finding.position}-${finding.title}`} className="hover:bg-muted/50 flex gap-3 rounded-lg p-3 transition-colors">
                  <span className="text-muted-foreground mt-0.5 w-4 shrink-0 text-xs tabular-nums">{index + 1}</span>
                  <tone.icon className={cn("mt-0.5 size-4 shrink-0", tone.className)} aria-label={finding.tone} />
                  <div className="grid min-w-0 gap-1.5">
                    <p className="text-sm font-medium text-pretty">{finding.title}</p>
                    <p className="text-muted-foreground text-sm text-pretty">{finding.detail}</p>
                    {finding.terms.length ? (
                      <div className="flex flex-wrap gap-1.5 pt-0.5">
                        {finding.terms.map((term) => (
                          <TermChip
                            key={term}
                            term={term}
                            country={country.code}
                            device={device}
                            audited={audited}
                            tracked={tracked}
                          />
                        ))}
                      </div>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="text-muted-foreground text-sm">No findings were saved for this market.</p>
        )}
      </CardContent>
    </Card>
  );
}

function byOpportunity(left: AuditKeyword, right: AuditKeyword): number {
  const a = left.opportunity;
  const b = right.opportunity;
  if (a != null || b != null) {
    if (a == null) return 1;
    if (b == null) return -1;
    if (a !== b) return b - a;
  }
  return left.keyword.localeCompare(right.keyword);
}

export function RecommendedKeywords({
  appId,
  country,
  device,
  tracked,
}: {
  appId: number;
  country: AuditCountry;
  device: Device;
  tracked: Ranking[];
}) {
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const track = useTrackKeywords();
  const rows = useMemo(() => [...country.keywords].sort(byOpportunity), [country.keywords]);
  const trackedSet = useMemo(
    () =>
      new Set(
        tracked
          .filter((row) => row.country === country.code && row.device === device)
          .map((row) => row.keyword.toLocaleLowerCase()),
      ),
    [tracked, country.code, device],
  );
  const trackKeywords = (keywords: string[]) =>
    track.mutate(
      { appId, keywords, countries: [country.code], devices: [device] },
      { onSuccess: () => setPicked(new Set()) },
    );

  if (!rows.length) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyTitle>No keyword results yet</EmptyTitle>
          <EmptyDescription>Completed market results appear here with Apple ranks and popularity.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Recommended keywords</CardTitle>
        <CardDescription>
          Checked against Apple. Popularity is Apple Ads&rsquo; score for the exact query; values with ~ are local
          ratings-based estimates, shown only without Apple Ads. Sorted by opportunity.
        </CardDescription>
        <CardAction>
          <Button
            size="sm"
            disabled={!picked.size || track.isPending}
            onClick={() => trackKeywords([...picked])}
          >
            <Plus /> Track {picked.size ? picked.size : ""} selected
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="px-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10 pl-6">
                <span className="sr-only">Select</span>
              </TableHead>
              <TableHead>Keyword</TableHead>
              <TableHead>Rank</TableHead>
              <TableHead>Popularity</TableHead>
              <TableHead>Difficulty</TableHead>
              <TableHead>Opportunity</TableHead>
              <TableHead className="pr-6 text-right">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item) => {
              const isTracked = trackedSet.has(item.keyword.toLocaleLowerCase());
              return (
                <TableRow key={item.id}>
                  <TableCell className="pl-6">
                    <Checkbox
                      aria-label={`Select ${item.keyword}`}
                      checked={picked.has(item.keyword)}
                      disabled={isTracked}
                      onCheckedChange={(checked) =>
                        setPicked((current) => {
                          const next = new Set(current);
                          if (checked) next.add(item.keyword);
                          else next.delete(item.keyword);
                          return next;
                        })
                      }
                    />
                  </TableCell>
                  <TableCell className="max-w-72">
                    <div className="truncate font-medium">{item.keyword}</div>
                    <div className="text-muted-foreground truncate text-xs" title={item.rationale}>
                      {item.intent}
                    </div>
                  </TableCell>
                  <TableCell className="tabular-nums">{rankLabel(item)}</TableCell>
                  <TableCell>
                    <DemandValue source={item} market={country.code} />
                  </TableCell>
                  <TableCell>
                    <DifficultyValue value={item.difficulty} />
                  </TableCell>
                  <TableCell>
                    <OpportunityValue value={item.opportunity} />
                  </TableCell>
                  <TableCell className="pr-6 text-right">
                    {isTracked ? (
                      <span className="text-muted-foreground text-xs">Tracked</span>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={track.isPending}
                        onClick={() => trackKeywords([item.keyword])}
                      >
                        Track
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function CompetitorNameKeywords({
  appId,
  country,
  device,
}: {
  appId: number;
  country: AuditCountry;
  device: Device;
}) {
  const track = useTrackKeywords();
  if (!country.paidKeywords?.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Competitor names people search</CardTitle>
        <CardDescription>
          Apple Ads only. App Store rules forbid other apps&rsquo; names in your title, subtitle, and keyword field;
          bid on these in Apple Ads instead. Tracking the rank shows whether Apple already lists you.
        </CardDescription>
      </CardHeader>
      <CardContent className="px-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Search</TableHead>
              <TableHead>Searches for</TableHead>
              <TableHead>Your rank</TableHead>
              <TableHead>Popularity</TableHead>
              <TableHead className="pr-6 text-right">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {country.paidKeywords.map((item) => (
              <TableRow key={item.keyword}>
                <TableCell className="pl-6 font-medium">{item.keyword}</TableCell>
                <TableCell className="text-muted-foreground max-w-64 truncate">{item.brandOwner ?? "Another app"}</TableCell>
                <TableCell className="tabular-nums">{rankLabel(item)}</TableCell>
                <TableCell>
                  <DemandValue source={item} market={country.code} />
                </TableCell>
                <TableCell className="pr-6 text-right">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={track.isPending}
                    onClick={() =>
                      track.mutate({ appId, keywords: [item.keyword], countries: [country.code], devices: [device] })
                    }
                  >
                    Track rank
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function DiscoverMore({
  disabled,
  pending,
  onDiscover,
}: {
  disabled: boolean;
  pending: boolean;
  onDiscover: (instruction: string) => void;
}) {
  const [instruction, setInstruction] = useState("");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Lightbulb className="size-4" /> Find more keywords
        </CardTitle>
        <CardDescription>
          Each round uses the app, earlier phrases, tracked ranks, measured Apple demand, and your instruction. New
          phrases are checked against Apple before they are added; earlier ones are kept.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (instruction.trim()) onDiscover(instruction.trim());
          }}
        >
          <div className="relative flex-1">
            <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
            <input
              className="border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 h-9 w-full rounded-md border pr-3 pl-8 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
              maxLength={500}
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder="e.g. 5 short phrases for couples who live apart"
              aria-label="Discovery instruction"
            />
          </div>
          <Button type="submit" disabled={disabled || pending || !instruction.trim()}>
            {pending ? "Discovering…" : "Discover more"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
