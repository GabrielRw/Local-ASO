import { useState } from "react";
import { ChevronDown, ChevronUp, Pin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { countryFlag, deviceName } from "@/lib/format";
import type { Device } from "@/lib/types";
import { cn } from "@/lib/utils";
import { reducedStorefronts, type StorefrontSummary } from "./keyword-utils";

const BANDS = [
  { key: "top10", label: "Top 10", className: "bg-emerald-500" },
  { key: "top50", label: "11–50", className: "bg-emerald-500/45" },
  { key: "ranked", label: "51+", className: "bg-muted-foreground/35" },
] as const;

// Reduced or not, and the pinned storefronts, are remembered on this Mac, like the theme.
const COLLAPSED_KEY = "local-aso-storefronts-collapsed";
const PINNED_KEY = "local-aso-storefronts-pinned";

function read<T>(key: string, parse: (value: string | null) => T, fallback: T): T {
  try {
    return parse(window.localStorage.getItem(key));
  } catch {
    return fallback;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage can be unavailable; the choice then lasts for this session.
  }
}

function parsePinned(value: string | null): string[] {
  const parsed: unknown = value ? JSON.parse(value) : [];
  return Array.isArray(parsed) ? parsed.filter((code): code is string => typeof code === "string") : [];
}

function share(count: number, total: number): string {
  return `${((100 * count) / Math.max(total, 1)).toFixed(2)}%`;
}

/**
 * Every storefront at a glance, one bar each: the share of its tracked keywords in the
 * top 10, at 11–50 and at 51+; the empty rest of the track is "not ranked". Picks the storefront.
 * Reduced, it keeps the selected storefront and the pinned ones.
 */
export function StorefrontOverview({
  summaries,
  selected,
  device,
  onSelect,
}: {
  summaries: StorefrontSummary[];
  selected: string;
  device: Device;
  onSelect: (code: string) => void;
}) {
  const [collapsed, setCollapsed] = useState(() => read(COLLAPSED_KEY, (value) => value === "1", false));
  const [pinned, setPinned] = useState(() => read(PINNED_KEY, parsePinned, [] as string[]));
  const toggle = () =>
    setCollapsed((current) => {
      write(COLLAPSED_KEY, current ? "0" : "1");
      return !current;
    });
  const togglePin = (code: string) =>
    setPinned((current) => {
      const next = current.includes(code) ? current.filter((item) => item !== code) : [...current, code];
      write(PINNED_KEY, JSON.stringify(next));
      return next;
    });
  const shown = collapsed ? reducedStorefronts(summaries, selected, pinned) : summaries;
  const hidden = summaries.length - shown.length;
  const withTop10 = summaries.filter((item) => item.top10 > 0).length;
  const withTop50 = summaries.filter((item) => item.top50 > 0).length;

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-base">Storefronts</CardTitle>
        <CardAction>
          <Button size="sm" variant="ghost" onClick={toggle} aria-expanded={!collapsed} aria-controls="storefront-overview">
            {collapsed ? <ChevronDown /> : <ChevronUp />}
            {collapsed ? `Show all ${summaries.length}` : "Reduce"}
          </Button>
        </CardAction>
        <CardDescription className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {collapsed ? (
            <span>
              {summaries.length} storefronts on {deviceName(device)} ·{" "}
              <span className="text-emerald-600 dark:text-emerald-400">{withTop10} with a top 10</span> · {withTop50} with a
              top 50{hidden ? ` · ${hidden} hidden` : ""}
            </span>
          ) : (
            <span>
              {deviceName(device)} · share of tracked keywords by rank. Pick one to see its keywords; pin the ones to keep
              when reduced.
            </span>
          )}
          <span className="flex items-center gap-3 text-xs" aria-hidden>
            {BANDS.map((band) => (
              <span key={band.key} className="inline-flex items-center gap-1">
                <i className={cn("size-2 rounded-sm", band.className)} />
                {band.label}
              </span>
            ))}
            <span className="inline-flex items-center gap-1">
              <i className="bg-muted size-2 rounded-sm" />
              Not ranked
            </span>
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent id="storefront-overview" className="grid gap-x-6 gap-y-0.5 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((item) => (
          <StorefrontRow
            key={item.code}
            item={item}
            device={device}
            selected={item.code === selected}
            pinned={pinned.includes(item.code)}
            onSelect={onSelect}
            onTogglePin={togglePin}
          />
        ))}
      </CardContent>
    </Card>
  );
}

function StorefrontRow({
  item,
  device,
  selected,
  pinned,
  onSelect,
  onTogglePin,
}: {
  item: StorefrontSummary;
  device: Device;
  selected: boolean;
  pinned: boolean;
  onSelect: (code: string) => void;
  onTogglePin: (code: string) => void;
}) {
  const best = item.best ? `best #${item.best.rank} “${item.best.keyword}”` : "no ranked keyword";
  const summary = `${item.name}: ${item.top10} in the top 10, ${item.top50 - item.top10} at 11–50, ${item.ranked - item.top50} at 51+, ${item.tracked - item.ranked} not ranked, of ${item.tracked} ${deviceName(device)} keywords · ${best}`;
  return (
    <div className={cn("group hover:bg-muted grid grid-cols-[minmax(0,1fr)_auto] items-center rounded-md", selected && "bg-muted ring-border ring-1")}>
      <button
        type="button"
        disabled={!item.active}
        aria-pressed={selected}
        aria-label={summary}
        title={summary}
        onClick={() => onSelect(item.code)}
        className="focus-visible:ring-ring grid grid-cols-[minmax(0,8.5rem)_1fr_auto] items-center gap-3 rounded-md py-1 pl-2 text-left text-sm focus-visible:ring-2 focus-visible:outline-none disabled:opacity-50"
      >
        <span className={cn("flex min-w-0 items-center gap-1.5", !item.top10 && !selected && "text-muted-foreground")}>
          <span aria-hidden>{countryFlag(item.code)}</span>
          <span className="truncate">{item.name}</span>
        </span>
        <span className="bg-muted flex h-2 overflow-hidden rounded-full" aria-hidden>
          <i className={BANDS[0].className} style={{ width: share(item.top10, item.tracked) }} />
          <i className={BANDS[1].className} style={{ width: share(item.top50 - item.top10, item.tracked) }} />
          <i className={BANDS[2].className} style={{ width: share(item.ranked - item.top50, item.tracked) }} />
        </span>
        <span className="text-muted-foreground text-xs tabular-nums">
          <strong className={cn("font-semibold", item.top10 ? "text-emerald-600 dark:text-emerald-400" : "text-foreground")}>
            {item.top10}
          </strong>
          /{item.tracked}
        </span>
      </button>
      <Button
        size="icon-xs"
        variant="ghost"
        aria-pressed={pinned}
        aria-label={pinned ? `Unpin ${item.name}` : `Pin ${item.name}: keep it when the list is reduced`}
        title={pinned ? "Pinned: kept when the list is reduced. Click to unpin" : "Pin: keep it when the list is reduced"}
        onClick={() => onTogglePin(item.code)}
        className={cn(
          "mx-1",
          pinned ? "text-sky-600 dark:text-sky-400" : "text-muted-foreground opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
        )}
      >
        <Pin className={cn(pinned && "fill-current")} />
      </Button>
    </div>
  );
}
