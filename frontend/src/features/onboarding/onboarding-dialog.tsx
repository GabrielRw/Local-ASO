import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { apiPost } from "@/lib/api";
import { parseAppleId } from "@/lib/apple-id";
import { countryFlag } from "@/lib/format";
import type { AddKeywordsResult } from "@/lib/mutations";
import { useCurrentBootstrap, useInvalidate } from "@/lib/queries";
import { useSelection } from "@/lib/selection";
import type { Device } from "@/lib/types";
import { cn } from "@/lib/utils";

const STEPS = [
  {
    label: "Your app",
    title: "A little setup, then a clearer view",
    intro: "Choose your app and first storefront. Everything stays on this Mac.",
  },
  {
    label: "Keywords",
    title: "Start tracking your keywords",
    intro: "Add a few search terms and Local ASO runs the first ranking check right away.",
  },
  {
    label: "AI agent",
    title: "Choose your local AI agent",
    intro: "Audits and keyword research run through a CLI already on this Mac. You can change this anytime.",
  },
];

const NEW_APP = "__new__";

/** The three-step setup guide shown on first launch and from Settings. */
export function OnboardingDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data } = useCurrentBootstrap();
  const [selection, select] = useSelection({ appId: data?.selectedAppId, country: data?.selectedCountry });
  const invalidate = useInvalidate();
  const apps = (data?.apps ?? []).filter((app) => app.active);
  const countries = (data?.countries ?? []).filter((country) => country.active);
  const providers = data?.agentProviders ?? [];

  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [existing, setExisting] = useState<string>(NEW_APP);
  const [link, setLink] = useState("");
  const [country, setCountry] = useState(selection.country);
  const [keywords, setKeywords] = useState("");
  const [device, setDevice] = useState<Device>(selection.device);
  const [agent, setAgent] = useState("auto");

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setError(null);
    setLink("");
    setKeywords("");
    setExisting(apps.some((app) => app.appleAppId === selection.appId) ? String(selection.appId) : apps[0] ? String(apps[0].appleAppId) : NEW_APP);
    setCountry(selection.country);
    setDevice(selection.device);
    setAgent(data?.defaultAgentProvider || "auto");
    // Reset only when the dialog opens, not on every background refetch.
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const finish = async () => {
    await apiPost("/api/onboarding/complete", {});
    await invalidate.bootstrap();
  };

  const dismiss = async () => {
    if (busy) return;
    try {
      await finish();
    } catch {
      // Closing the guide must never block the dashboard.
    }
    onClose();
  };

  const submit = async () => {
    setError(null);
    try {
      if (step === 0) {
        const appleId = existing !== NEW_APP ? Number(existing) : parseAppleId(link);
        if (!appleId) throw new Error("Enter the App Store link (apps.apple.com/…/id123456789) or the numeric app ID.");
        if (existing === NEW_APP) {
          setBusy("Finding app…");
          await apiPost("/api/apps", { appleId, country });
        }
        select({ appId: appleId, country });
        await invalidate.bootstrap();
        setStep(1);
      } else if (step === 1) {
        setStep(2);
      } else {
        setBusy(keywords.trim() ? "Checking keywords…" : "Saving…");
        let result: AddKeywordsResult | null = null;
        if (keywords.trim() && selection.appId) {
          result = await apiPost<AddKeywordsResult>("/api/keywords", {
            appId: selection.appId,
            keywords: keywords.trim(),
            countries: [country],
            devices: [device],
          });
        }
        await apiPost("/api/settings/agent", { provider: agent });
        await finish();
        select({ device });
        onClose();
        if (result) {
          const failures = result.automaticCheck?.failures ?? 0;
          const message = `${result.keywordsRequested} keyword${result.keywordsRequested === 1 ? "" : "s"} added. ${
            failures ? `${failures} Apple searches failed; use Run check to retry.` : "Your first rankings are ready."
          }`;
          if (failures) toast.warning(message);
          else toast.success(message);
        } else {
          toast.success("Your local workspace is ready.");
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  };

  const current = STEPS[step];
  const appName = apps.find((app) => app.appleAppId === selection.appId)?.name ?? "Your app";

  return (
    <Dialog open={open} onOpenChange={(next) => !next && void dismiss()}>
      <DialogContent className="sm:max-w-lg" aria-busy={busy != null}>
        <form
          className="grid gap-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (!busy) void submit();
          }}
        >
          <ol className="flex items-center gap-2 text-xs" aria-label="Setup progress">
            {STEPS.map((item, index) => (
              <li
                key={item.label}
                aria-current={index === step ? "step" : undefined}
                className={cn("flex items-center gap-1.5", index === step ? "text-foreground" : "text-muted-foreground")}
              >
                <span
                  className={cn(
                    "inline-flex size-5 items-center justify-center rounded-full border text-[11px] tabular-nums",
                    index < step && "bg-primary text-primary-foreground border-primary",
                    index === step && "border-foreground",
                  )}
                >
                  {index < step ? <Check className="size-3" /> : index + 1}
                </span>
                {item.label}
                {index < STEPS.length - 1 ? <span className="bg-border mx-1 h-px w-6" aria-hidden /> : null}
              </li>
            ))}
          </ol>

          <DialogHeader>
            <DialogTitle>{current.title}</DialogTitle>
            <DialogDescription>{current.intro}</DialogDescription>
          </DialogHeader>

          {step === 0 ? (
            <FieldGroup>
              {apps.length ? (
                <Field>
                  <FieldLabel>App</FieldLabel>
                  <Select value={existing} onValueChange={setExisting} disabled={busy != null}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {apps.map((app) => (
                        <SelectItem key={app.appleAppId} value={String(app.appleAppId)}>
                          {app.name}
                        </SelectItem>
                      ))}
                      <SelectItem value={NEW_APP}>Add a different app…</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              ) : null}
              {existing === NEW_APP ? (
                <Field>
                  <FieldLabel htmlFor="setup-link">App Store link or app ID</FieldLabel>
                  <Input
                    id="setup-link"
                    autoFocus
                    autoComplete="off"
                    value={link}
                    onChange={(event) => setLink(event.target.value)}
                    placeholder="https://apps.apple.com/…/id123456789"
                    disabled={busy != null}
                  />
                  <FieldDescription>Copy the link from your app&rsquo;s App Store page, or enter the number after &ldquo;id&rdquo;.</FieldDescription>
                </Field>
              ) : null}
              <Field>
                <FieldLabel>First storefront</FieldLabel>
                <Select value={country} onValueChange={setCountry} disabled={busy != null}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {countries.map((item) => (
                      <SelectItem key={item.code} value={item.code}>
                        {countryFlag(item.code)} {item.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldDescription>Add more storefronts and switch between iPhone and iPad later.</FieldDescription>
              </Field>
            </FieldGroup>
          ) : null}

          {step === 1 ? (
            <FieldGroup>
              <p className="bg-muted/60 rounded-md px-3 py-2 text-sm">
                <span className="font-medium">{appName}</span>
                <span className="text-muted-foreground">
                  {" "}
                  · {countryFlag(country)} {country.toUpperCase()} storefront · public App Store rankings
                </span>
              </p>
              <Field>
                <FieldLabel htmlFor="setup-keywords">
                  First keywords <span className="text-muted-foreground font-normal">(optional)</span>
                </FieldLabel>
                <Textarea
                  id="setup-keywords"
                  rows={3}
                  value={keywords}
                  onChange={(event) => setKeywords(event.target.value)}
                  placeholder="keyword, another keyword, search phrase"
                />
                <FieldDescription>Separate terms with commas or new lines.</FieldDescription>
              </Field>
              <Field>
                <FieldLabel>Device</FieldLabel>
                <ToggleGroup
                  type="single"
                  variant="outline"
                  value={device}
                  onValueChange={(value) => value && setDevice(value as Device)}
                  className="justify-start"
                >
                  <ToggleGroupItem value="iphone">iPhone</ToggleGroupItem>
                  <ToggleGroupItem value="ipad">iPad</ToggleGroupItem>
                </ToggleGroup>
              </Field>
            </FieldGroup>
          ) : null}

          {step === 2 ? (
            <RadioGroup value={agent} onValueChange={setAgent} aria-label="Local AI agent" className="gap-2">
              {[{ id: "auto", label: "Auto-detect", available: true }, ...providers].map((item) => (
                <label
                  key={item.id}
                  className={cn(
                    "has-[[data-state=checked]]:border-primary flex items-center gap-3 rounded-lg border p-3 text-sm",
                    item.available ? "cursor-pointer" : "opacity-60",
                  )}
                >
                  <RadioGroupItem value={item.id} disabled={!item.available} />
                  <span className="grid gap-0.5">
                    <span className="font-medium">{item.label}</span>
                    <span className="text-muted-foreground text-xs">
                      {item.id === "auto"
                        ? "Use the first available CLI"
                        : item.available
                          ? "Found on this Mac"
                          : "CLI not found"}
                    </span>
                  </span>
                </label>
              ))}
            </RadioGroup>
          ) : null}

          {error ? <FieldError>{error}</FieldError> : null}

          <DialogFooter>
            {step > 0 ? (
              <Button type="button" variant="ghost" onClick={() => setStep(step - 1)} disabled={busy != null}>
                Back
              </Button>
            ) : null}
            <Button type="submit" disabled={busy != null}>
              {busy ?? (step === 2 ? "Open dashboard" : "Continue")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
