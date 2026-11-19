import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { Languages, Plus } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { apiPost } from "@/lib/api";
import { countryFlag } from "@/lib/format";
import { describeAddKeywords, type AddKeywordsResult } from "@/lib/mutations";
import { useInvalidate } from "@/lib/queries";
import type { Country, Device } from "@/lib/types";

interface LocalizedGroup {
  language_code: string;
  language: string;
  countries: string[];
  keywords: string[];
}

interface Localization {
  groups: LocalizedGroup[];
  warnings: { keyword: string }[];
}

const DEVICES: { code: Device; name: string }[] = [
  { code: "iphone", name: "iPhone" },
  { code: "ipad", name: "iPad" },
];

export function AddKeywordsDialog({
  open,
  onOpenChange,
  appId,
  countries,
  defaultCountry,
  defaultDevice,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  appId: number;
  countries: Country[];
  defaultCountry: string;
  defaultDevice: Device;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        {/* Remount the form on each open so it starts from the current storefront and device. */}
        {open ? (
          <AddKeywordsForm
            appId={appId}
            countries={countries}
            defaultCountry={defaultCountry}
            defaultDevice={defaultDevice}
            onDone={() => onOpenChange(false)}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function toggle<T>(set: Set<T>, value: T, on: boolean): Set<T> {
  const next = new Set(set);
  if (on) next.add(value);
  else next.delete(value);
  return next;
}

function AddKeywordsForm({
  appId,
  countries,
  defaultCountry,
  defaultDevice,
  onDone,
}: {
  appId: number;
  countries: Country[];
  defaultCountry: string;
  defaultDevice: Device;
  onDone: () => void;
}) {
  const invalidate = useInvalidate();
  const [text, setText] = useState("");
  const [selectedCountries, setSelectedCountries] = useState<Set<string>>(() => new Set([defaultCountry]));
  const [devices, setDevices] = useState<Set<Device>>(() => new Set([defaultDevice]));
  const [localization, setLocalization] = useState<Localization | null>(null);
  const allSelected = countries.length > 0 && countries.every((country) => selectedCountries.has(country.code));

  const localize = useMutation({
    mutationFn: () =>
      apiPost<Localization>("/api/keywords/localize", { keywords: text.trim(), countries: [...selectedCountries] }),
    onSuccess: (result) => {
      if (!result.groups.length) {
        setLocalization(null);
        toast.error("No curated translations were found for the selected languages.");
        return;
      }
      setLocalization(result);
    },
    onError: (error) => toast.error(error.message),
  });

  const submit = useMutation({
    mutationFn: () =>
      apiPost<AddKeywordsResult>(
        "/api/keywords",
        localization
          ? { appId, groups: localization.groups, devices: [...devices] }
          : { appId, keywords: text, countries: [...selectedCountries], devices: [...devices] },
      ),
    onSuccess: async (result) => {
      const failed = result.automaticCheck?.failures ?? 0;
      if (failed) toast.warning(describeAddKeywords(result));
      else toast.success(describeAddKeywords(result));
      onDone();
      await invalidate.bootstrap();
    },
    onError: (error) => toast.error(error.message),
  });

  // Any change to the inputs invalidates a localization preview.
  const resetPreview = () => setLocalization(null);

  const validate = (): boolean => {
    if (!text.trim()) {
      toast.error("Enter at least one keyword.");
      return false;
    }
    if (!selectedCountries.size) {
      toast.error("Select at least one storefront.");
      return false;
    }
    return true;
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!validate()) return;
    if (!devices.size) {
      toast.error("Select at least one device.");
      return;
    }
    submit.mutate();
  };

  const warnings = localization ? [...new Set(localization.warnings.map((item) => item.keyword))] : [];

  return (
    <form onSubmit={onSubmit} className="grid gap-5">
      <DialogHeader>
        <DialogTitle>Add keywords</DialogTitle>
        <DialogDescription>
          Track exact App Store searches. Apple is checked right away for each storefront and device.
        </DialogDescription>
      </DialogHeader>

      <Field>
        <FieldLabel htmlFor="keyword-input">Keywords</FieldLabel>
        <Textarea
          id="keyword-input"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            resetPreview();
          }}
          rows={4}
          placeholder={"habit tracker\ndaily planner, focus timer"}
          required
        />
        <FieldDescription>Separate keywords with commas or new lines.</FieldDescription>
      </Field>

      <FieldSet>
        <div className="flex items-center justify-between">
          <FieldLegend variant="label" className="mb-0">
            Storefronts
          </FieldLegend>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setSelectedCountries(allSelected ? new Set() : new Set(countries.map((country) => country.code)));
              resetPreview();
            }}
          >
            {allSelected ? "Clear all" : "Select all"}
          </Button>
        </div>
        <div className="max-h-44 overflow-y-auto rounded-lg border">
          <div className="grid gap-1 p-2 sm:grid-cols-2">
            {countries.map((country) => (
              <Field key={country.code} orientation="horizontal" className="rounded-md px-1.5 py-1">
                <Checkbox
                  id={`kw-country-${country.code}`}
                  checked={selectedCountries.has(country.code)}
                  onCheckedChange={(checked) => {
                    setSelectedCountries((current) => toggle(current, country.code, checked === true));
                    resetPreview();
                  }}
                />
                <FieldLabel htmlFor={`kw-country-${country.code}`} className="font-normal">
                  <span aria-hidden>{countryFlag(country.code)}</span>
                  <span className="font-medium">{country.code.toUpperCase()}</span>
                  <span className="text-muted-foreground truncate">{country.name}</span>
                </FieldLabel>
              </Field>
            ))}
          </div>
        </div>
      </FieldSet>

      <FieldSet>
        <FieldLegend variant="label">Devices</FieldLegend>
        <div className="flex gap-6">
          {DEVICES.map((device) => (
            <Field key={device.code} orientation="horizontal" className="w-auto">
              <Checkbox
                id={`kw-device-${device.code}`}
                checked={devices.has(device.code)}
                onCheckedChange={(checked) => setDevices((current) => toggle(current, device.code, checked === true))}
              />
              <FieldLabel htmlFor={`kw-device-${device.code}`} className="font-normal">
                {device.name}
              </FieldLabel>
            </Field>
          ))}
        </div>
      </FieldSet>

      {localization ? (
        <section aria-label="Localization preview" className="bg-muted/40 grid gap-3 rounded-lg border p-3">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-sm font-medium">Localization preview</span>
            <span className="text-muted-foreground text-xs">Review before adding</span>
          </div>
          {localization.groups.map((group) => (
            <div key={group.language_code} className="grid gap-1.5">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="font-medium">{group.language}</span>
                <span aria-label={group.countries.map((code) => code.toUpperCase()).join(", ")}>
                  {group.countries.map(countryFlag).join(" ")}
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {group.keywords.map((keyword) => (
                  <Badge key={keyword} variant="secondary" className="font-normal">
                    {keyword}
                  </Badge>
                ))}
              </div>
            </div>
          ))}
          {warnings.length ? (
            <p className="text-xs text-amber-700 text-pretty dark:text-amber-400">
              {warnings.length} uncurated phrase{warnings.length === 1 ? "" : "s"} skipped outside English:{" "}
              {warnings.join(", ")}.
            </p>
          ) : null}
        </section>
      ) : null}

      <DialogFooter>
        <Button
          type="button"
          variant="outline"
          disabled={localize.isPending || submit.isPending}
          onClick={() => validate() && localize.mutate()}
        >
          <Languages /> Localize
        </Button>
        <Button type="submit" disabled={submit.isPending}>
          <Plus /> {localization ? "Add localized keywords" : "Add keywords"}
        </Button>
      </DialogFooter>
    </form>
  );
}
