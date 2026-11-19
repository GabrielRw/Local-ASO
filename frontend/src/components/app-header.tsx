import { Smartphone, Tablet } from "lucide-react";
import type { ReactNode } from "react";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { countryFlag } from "@/lib/format";
import { useCurrentBootstrap } from "@/lib/queries";
import { useSelection } from "@/lib/selection";
import type { Device } from "@/lib/types";

/** Page title plus the storefront and device pickers shared by every app view. */
export function AppHeader({
  title,
  actions,
  storefrontPickers = true,
}: {
  title: string;
  actions?: ReactNode;
  storefrontPickers?: boolean;
}) {
  const { data } = useCurrentBootstrap();
  const [selection, select] = useSelection({ appId: data?.selectedAppId, country: data?.selectedCountry });
  const countries = (data?.countries ?? []).filter((country) => country.active);

  const pickers = storefrontPickers ? (
    <div className="flex items-center gap-2">
      <Select value={selection.country} onValueChange={(country) => select({ country })}>
        <SelectTrigger size="sm" className="w-[9.5rem]" aria-label="Storefront">
          <SelectValue />
        </SelectTrigger>
        <SelectContent align="end">
          {countries.map((country) => (
            <SelectItem key={country.code} value={country.code}>
              <span aria-hidden>{countryFlag(country.code)}</span> {country.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <ToggleGroup
        type="single"
        size="sm"
        variant="outline"
        value={selection.device}
        onValueChange={(device) => device && select({ device: device as Device })}
        aria-label="Device"
      >
        <ToggleGroupItem value="iphone" aria-label="iPhone results">
          <Smartphone /> <span className="hidden lg:inline">iPhone</span>
        </ToggleGroupItem>
        <ToggleGroupItem value="ipad" aria-label="iPad results">
          <Tablet /> <span className="hidden lg:inline">iPad</span>
        </ToggleGroupItem>
      </ToggleGroup>
    </div>
  ) : null;

  // One row on wide screens; on phones the storefront and device pickers wrap
  // onto a second row so the title and page actions keep their space.
  return (
    <header className="bg-background/80 supports-[backdrop-filter]:bg-background/70 sticky top-0 z-20 flex min-h-14 shrink-0 flex-wrap items-center gap-x-2 gap-y-2 border-b px-4 py-2.5 backdrop-blur">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-1 data-[orientation=vertical]:h-4" />
      <h1 className="min-w-0 flex-1 truncate text-sm font-semibold md:flex-none">{title}</h1>
      <div className="flex items-center gap-2 md:order-3">{actions}</div>
      {pickers ? <div className="order-last w-full md:order-4 md:w-auto">{pickers}</div> : null}
      <div className="hidden flex-1 md:order-2 md:block" aria-hidden />
    </header>
  );
}
