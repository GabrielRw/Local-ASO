import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, Check, CircleAlert, CircleCheck, CircleHelp, Pencil } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
  FieldTitle,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { apiPost } from "@/lib/api";
import { countryFlag, deviceName, rankLabel } from "@/lib/format";
import type { Country, Device, Listing, ListingMetadata } from "@/lib/types";
import { cn } from "@/lib/utils";
import { highlightContext, inferBrand, keywordFieldSegments, textSegments, toneLabel, toneMark, type TokenTone } from "./highlight";
import { CharCount, HighlightInput } from "./highlight-input";
import { usePatchBootstrapListing } from "./queries";
import type { CoverageAnalysis, CoverageGoal, ListingCoverageResult, StrategyAnalysis, StrategyPrinciple } from "./types";

export const COVERAGE_SECTION_ID = "listing-coverage";
export const COVERAGE_BRAND_INPUT_ID = "coverage-brand";

const SAVE_DELAY_MS = 550;
const STEPS = ["Goal & market", "Listing metadata", "Strategy audit"] as const;

const GOALS: { value: CoverageGoal; label: string; detail: string; route: string }[] = [
  {
    value: "aso_seo_aeo",
    label: "ASO / SEO / AEO",
    detail: "Lead with a generic keyword phrase, then close with the brand.",
    route: "Discovery-led",
  },
  {
    value: "ugc_ads",
    label: "UGC / Ads",
    detail: "Lead with the brand and prioritize ranking for branded searches.",
    route: "Brand-led",
  },
];

interface Draft {
  name: string;
  subtitle: string;
  keywords: string;
}

type SaveStatus = "saved" | "saving" | "error" | "name-required";

const SAVE_LABEL: Record<SaveStatus, string> = {
  saved: "Saved",
  saving: "Saving…",
  error: "Save failed",
  "name-required": "Name required",
};

function trimDraft(draft: Draft): Draft {
  return { name: draft.name.trim(), subtitle: draft.subtitle.trim(), keywords: draft.keywords.trim() };
}

/**
 * Three-step listing strategy audit: choose the growth goal and brand, paste the
 * indexed fields Apple does not expose publicly, then edit live with word
 * highlighting while every pause autosaves and re-audits locally.
 */
export function ListingCoverage({
  appId,
  device,
  listing,
  metadata,
  countries,
  currentCountry,
  loading,
  onCountryChange,
}: {
  appId: number;
  device: Device;
  listing: Listing;
  metadata: ListingMetadata | null;
  countries: Country[];
  currentCountry: string;
  /** True while the bootstrap for a newly chosen storefront is still loading. */
  loading: boolean;
  onCountryChange: (country: string) => void;
}) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [goal, setGoal] = useState<CoverageGoal>(metadata?.channelGoal ?? "aso_seo_aeo");
  const [brand, setBrand] = useState(() => metadata?.brandTerm || inferBrand(metadata?.name || listing.name || ""));
  // Follows the header storefront until the user confirms a main storefront in step 1.
  const [countryChoice, setCountry] = useState<string | null>(null);
  const country = countryChoice ?? currentCountry;
  const [draft, setDraft] = useState<Draft | null>(null);
  const [analysis, setAnalysis] = useState<CoverageAnalysis | null>(null);
  const [strategy, setStrategy] = useState<StrategyAnalysis | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const patchBootstrap = usePatchBootstrapListing();

  // The step-2 form starts from the saved metadata for the chosen storefront.
  const fields: Draft = draft ?? {
    name: metadata?.name || listing.name || "",
    subtitle: metadata?.subtitle || "",
    keywords: metadata?.keywords || "",
  };

  const requestBody = (values: Draft) => ({
    appId,
    country,
    device,
    ...trimDraft(values),
    goal,
    brandTerm: brand.trim(),
  });

  const apply = (result: ListingCoverageResult) => {
    setAnalysis(result.analysis);
    setStrategy(result.strategy);
    patchBootstrap(appId, country, result.metadata, result.health);
  };

  const analyse = useMutation({
    mutationFn: (values: Draft) => apiPost<ListingCoverageResult>("/api/listing-metadata", requestBody(values)),
    onSuccess: (result) => {
      apply(result);
      setDraft({ name: result.metadata.name, subtitle: result.metadata.subtitle, keywords: result.metadata.keywords });
      setGoal(result.metadata.channelGoal);
      setBrand(result.metadata.brandTerm);
      setSaveStatus("saved");
      setStep(3);
    },
    onError: (error) => toast.error(error.message),
  });

  // Live autosave: debounce, and drop responses that a newer edit superseded.
  const revision = useRef(0);
  const timer = useRef<number | undefined>(undefined);
  const pending = useRef<Draft | null>(null);
  // Latest render's body builder and cache patcher, for the debounced save.
  const latest = useRef({ requestBody, apply });
  useLayoutEffect(() => {
    latest.current = { requestBody, apply };
  });

  const saveLive = useCallback(async (values: Draft) => {
    pending.current = null;
    const current = ++revision.current;
    if (!values.name.trim()) {
      setSaveStatus("name-required");
      return;
    }
    setSaveStatus("saving");
    try {
      const result = await apiPost<ListingCoverageResult>("/api/listing-metadata", latest.current.requestBody(values));
      if (current !== revision.current) return;
      latest.current.apply(result);
      setSaveStatus("saved");
    } catch (error) {
      if (current !== revision.current) return;
      setSaveStatus("error");
      toast.error(error instanceof Error ? error.message : "Could not save the listing audit");
    }
  }, []);

  const cancelLiveSave = () => {
    window.clearTimeout(timer.current);
    pending.current = null;
    revision.current += 1;
  };

  // Flush an edit still waiting on the debounce when the view goes away.
  useEffect(
    () => () => {
      window.clearTimeout(timer.current);
      if (pending.current) void saveLive(pending.current);
    },
    [saveLive],
  );

  const editLive = (key: keyof Draft, value: string) => {
    const next = { ...fields, [key]: value };
    setDraft(next);
    pending.current = next;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void saveLive(next), SAVE_DELAY_MS);
  };

  const continueFromGoal = () => {
    if (!brand.trim()) {
      toast.error("Enter the app’s brand term before continuing.");
      document.getElementById(COVERAGE_BRAND_INPUT_ID)?.focus();
      return;
    }
    setDraft(null);
    setAnalysis(null);
    setStrategy(null);
    setCountry(country);
    setStep(2);
    if (country !== currentCountry) onCountryChange(country);
  };

  const submitMetadata = (event: FormEvent) => {
    event.preventDefault();
    if (!fields.name.trim()) {
      toast.error("Enter the listing name.");
      return;
    }
    analyse.mutate(fields);
  };

  const activeCountries = countries.filter((item) => item.active);
  const goalLabel = GOALS.find((item) => item.value === goal)?.label ?? goal;

  return (
    <Card id={COVERAGE_SECTION_ID} className="scroll-mt-20">
      <CardHeader>
        <CardTitle className="text-base">Keyword coverage</CardTitle>
        <CardDescription>
          Compare the metadata you plan to target with keywords already tracked for this app.
        </CardDescription>
        {step > 1 ? (
          <CardAction>
            <Badge variant="secondary" aria-live="polite">
              {step === 3 ? (
                <>
                  {saveStatus === "saving" ? <Spinner className="size-3" /> : null}
                  {SAVE_LABEL[saveStatus]}
                </>
              ) : (
                goalLabel
              )}
            </Badge>
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent className="grid gap-6">
        <StepIndicator step={step} />

        {step === 1 ? (
          <div className="grid gap-6">
            <FieldSet>
              <FieldLegend>What is your primary growth strategy?</FieldLegend>
              <FieldDescription>Choose how discovery should influence the title and the terms you prioritize.</FieldDescription>
              <RadioGroup
                value={goal}
                onValueChange={(value) => setGoal(value as CoverageGoal)}
                className="grid gap-3 sm:grid-cols-2"
                aria-label="Primary growth strategy"
              >
                {GOALS.map((option) => (
                  <FieldLabel key={option.value} htmlFor={`coverage-goal-${option.value}`}>
                    <Field orientation="horizontal">
                      <RadioGroupItem value={option.value} id={`coverage-goal-${option.value}`} />
                      <FieldContent>
                        <FieldTitle>
                          {option.label}
                          <Badge variant="outline" className="font-normal">
                            {option.route}
                          </Badge>
                        </FieldTitle>
                        <FieldDescription>{option.detail}</FieldDescription>
                      </FieldContent>
                    </Field>
                  </FieldLabel>
                ))}
              </RadioGroup>
            </FieldSet>
            <FieldGroup className="grid gap-6 md:grid-cols-[minmax(0,1fr)_16rem]">
              <Field>
                <FieldLabel htmlFor={COVERAGE_BRAND_INPUT_ID}>Brand term or branded phrase</FieldLabel>
                <Input
                  id={COVERAGE_BRAND_INPUT_ID}
                  value={brand}
                  maxLength={255}
                  required
                  placeholder="AstroLingo"
                  onChange={(event) => setBrand(event.target.value)}
                />
                <FieldDescription>Used only to verify title ordering. Punctuation and case are ignored.</FieldDescription>
              </Field>
              <Field>
                <FieldLabel htmlFor="coverage-country">Main listing storefront</FieldLabel>
                <Select value={country} onValueChange={setCountry}>
                  <SelectTrigger id="coverage-country" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {activeCountries.map((item) => (
                      <SelectItem key={item.code} value={item.code}>
                        {countryFlag(item.code)} {item.code.toUpperCase()} · {item.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </FieldGroup>
            <div className="flex justify-end">
              <Button onClick={continueFromGoal}>Continue to metadata</Button>
            </div>
          </div>
        ) : null}

        {step === 2 ? (
          <form className="grid gap-6" onSubmit={submitMetadata}>
            <p className="text-muted-foreground text-sm text-pretty">
              Apple’s public API supplies the app name. Subtitle and keyword field are not exposed publicly, so paste
              them from App Store Connect. They stay in your local database.
            </p>
            <FieldGroup>
              <PlainField
                id="coverage-name"
                label="Name"
                max={30}
                value={fields.name}
                required
                disabled={loading}
                onChange={(value) => setDraft({ ...fields, name: value })}
              />
              <PlainField
                id="coverage-subtitle"
                label="Subtitle"
                max={30}
                value={fields.subtitle}
                placeholder="Paste the localized subtitle"
                disabled={loading}
                onChange={(value) => setDraft({ ...fields, subtitle: value })}
              />
              <PlainField
                id="coverage-keywords"
                label="Keyword field"
                max={100}
                value={fields.keywords}
                placeholder="keyword one, keyword two, keyword three"
                description="Comma-separated. This is the App Store keyword field, not Apple search volume."
                disabled={loading}
                onChange={(value) => setDraft({ ...fields, keywords: value })}
              />
            </FieldGroup>
            <div className="flex flex-wrap justify-between gap-2">
              <Button type="button" variant="ghost" onClick={() => setStep(1)}>
                <ArrowLeft /> Back
              </Button>
              <Button type="submit" disabled={analyse.isPending || loading}>
                {analyse.isPending ? <Spinner /> : null} Analyse strategy
              </Button>
            </div>
          </form>
        ) : null}

        {step === 3 && analysis && strategy ? (
          <div className="grid gap-6">
            <p className="text-muted-foreground text-sm">
              {strategy.goal_label} · {countryFlag(country)} {country.toUpperCase()} · {deviceName(device)}
            </p>
            <LiveEditor draft={fields} brand={strategy.brand_term || brand} onEdit={editLive} />
            <CoverageResults analysis={analysis} strategy={strategy} />
            <div>
              <Button
                variant="ghost"
                onClick={() => {
                  cancelLiveSave();
                  setDraft(trimDraft(fields));
                  setStep(2);
                }}
              >
                <Pencil /> Edit metadata
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function StepIndicator({ step }: { step: number }) {
  return (
    <ol className="grid grid-cols-3 gap-2" aria-label="Listing audit progress">
      {STEPS.map((label, index) => {
        const number = index + 1;
        const done = step > number;
        const current = step === number;
        return (
          <li
            key={label}
            aria-current={current ? "step" : undefined}
            className={cn(
              "flex min-w-0 items-center gap-2 border-t-2 pt-2 text-xs",
              current ? "border-primary text-foreground font-medium" : done ? "border-primary/40 text-muted-foreground" : "text-muted-foreground",
            )}
          >
            <span
              className={cn(
                "grid size-5 shrink-0 place-items-center rounded-full border text-[11px] tabular-nums",
                current && "bg-primary text-primary-foreground border-primary",
                done && "border-primary/40",
              )}
            >
              {done ? <Check className="size-3" aria-label="Complete" /> : number}
            </span>
            <span className="truncate">{label}</span>
          </li>
        );
      })}
    </ol>
  );
}

function PlainField({
  id,
  label,
  max,
  value,
  onChange,
  placeholder,
  description,
  required,
  disabled,
}: {
  id: string;
  label: string;
  max: number;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  description?: string;
  required?: boolean;
  disabled?: boolean;
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id} className="flex w-full items-baseline">
        {label}
        <CharCount value={value} max={max} />
      </FieldLabel>
      <Input
        id={id}
        value={value}
        maxLength={max}
        required={required}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
      {description ? <FieldDescription>{description}</FieldDescription> : null}
    </Field>
  );
}

function LiveEditor({
  draft,
  brand,
  onEdit,
}: {
  draft: Draft;
  brand: string;
  onEdit: (key: keyof Draft, value: string) => void;
}) {
  const context = useMemo(
    () => highlightContext([draft.name, draft.subtitle, draft.keywords], brand),
    [draft.name, draft.subtitle, draft.keywords, brand],
  );
  return (
    <FieldGroup>
      <Field>
        <HighlightInput
          id="coverage-live-name"
          label="Name"
          max={30}
          required
          value={draft.name}
          segments={textSegments(draft.name, context)}
          onChange={(value) => onEdit("name", value)}
        />
      </Field>
      <Field>
        <HighlightInput
          id="coverage-live-subtitle"
          label="Subtitle"
          max={30}
          value={draft.subtitle}
          placeholder="Paste the localized subtitle"
          segments={textSegments(draft.subtitle, context)}
          onChange={(value) => onEdit("subtitle", value)}
        />
      </Field>
      <Field>
        <HighlightInput
          id="coverage-live-keywords"
          label="Keyword field"
          max={100}
          value={draft.keywords}
          placeholder="keyword one, keyword two"
          describedBy="coverage-live-keywords-help"
          segments={keywordFieldSegments(draft.keywords, context)}
          onChange={(value) => onEdit("keywords", value)}
        />
        <FieldDescription id="coverage-live-keywords-help">
          Changes recalculate the audit automatically and save locally after a short pause.
        </FieldDescription>
      </Field>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="Highlight legend">
        {(Object.keys(toneLabel) as TokenTone[]).map((tone) => (
          <li key={tone} className="flex items-center gap-1.5">
            <span className={cn("size-3 rounded-[3px]", toneMark[tone])} aria-hidden />
            <span className="text-muted-foreground">{toneLabel[tone]}</span>
          </li>
        ))}
      </ul>
    </FieldGroup>
  );
}

function PrincipleCard({ principle }: { principle: StrategyPrinciple }) {
  const state =
    principle.passed === true
      ? { icon: CircleCheck, label: "Pass", className: "text-emerald-600 dark:text-emerald-400" }
      : principle.passed === false
        ? { icon: CircleAlert, label: "Review", className: "text-amber-600 dark:text-amber-400" }
        : { icon: CircleHelp, label: "Needs input", className: "text-muted-foreground" };
  return (
    <div className="grid gap-1.5 rounded-lg border p-4">
      <div className="flex items-center gap-2">
        <state.icon className={cn("size-4 shrink-0", state.className)} aria-hidden />
        <p className="text-sm font-medium">{principle.label}</p>
        <span className={cn("ml-auto text-xs font-medium", state.className)}>{state.label}</span>
      </div>
      <p className="text-muted-foreground text-sm text-pretty">{principle.detail}</p>
    </div>
  );
}

function SummaryStat({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <div className="grid gap-0.5">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="text-2xl font-semibold tracking-tight tabular-nums">{value}</dd>
      <dd className="text-muted-foreground text-xs">{note}</dd>
    </div>
  );
}

export function CoverageResults({ analysis, strategy }: { analysis: CoverageAnalysis; strategy: StrategyAnalysis }) {
  const matched = analysis.matched ?? [];
  const untracked = analysis.untracked_matches ?? [];
  return (
    <div className="grid gap-6">
      <div className="grid gap-3 md:grid-cols-2">
        <PrincipleCard principle={strategy.no_repetition} />
        <PrincipleCard principle={strategy.title_order} />
      </div>
      <dl className="grid grid-cols-2 gap-4 rounded-lg border p-4 md:grid-cols-4">
        <SummaryStat label="Targeted terms" value={analysis.target_terms} note={`${analysis.keyword_field_terms} keyword-field entries`} />
        <SummaryStat label="Tracked in listing" value={analysis.tracked_matches} note="keywords found in metadata" />
        <SummaryStat label="Already ranking" value={analysis.ranked_keywords} note="with a returned position" />
        <SummaryStat label="Not ranking" value={analysis.unranked_keywords} note="outside the result window" />
      </dl>
      <div className="grid gap-6 md:grid-cols-2">
        <section className="grid content-start gap-2" aria-labelledby="coverage-tracked-title">
          <h3 id="coverage-tracked-title" className="flex items-center gap-2 text-sm font-medium">
            Tracked keyword matches <Badge variant="secondary">{matched.length}</Badge>
          </h3>
          {matched.length ? (
            <ul className="divide-y rounded-lg border">
              {matched.map((item) => {
                const rank = rankLabel({ rank: item.rank, found: item.found, resultLimit: item.result_limit });
                return (
                  <li key={item.keyword} className="flex items-center gap-3 px-3 py-2">
                    <div className="grid min-w-0 flex-1">
                      <span className="truncate text-sm">{item.keyword}</span>
                      <span className="text-muted-foreground text-xs">{item.sources.join(" · ")}</span>
                    </div>
                    <span
                      className={cn("text-sm font-medium tabular-nums", !item.found && "text-muted-foreground")}
                      title={item.found ? undefined : `Outside Apple’s top ${item.result_limit} results`}
                    >
                      {rank}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">No currently tracked keywords appear in this metadata.</p>
          )}
        </section>
        <section className="grid content-start gap-2" aria-labelledby="coverage-untracked-title">
          <h3 id="coverage-untracked-title" className="flex items-center gap-2 text-sm font-medium">
            Untracked keyword matches <Badge variant="secondary">{untracked.length}</Badge>
          </h3>
          {untracked.length ? (
            <ul className="divide-y rounded-lg border">
              {untracked.map((item) => (
                <li key={item.keyword} className="flex items-center gap-3 px-3 py-2">
                  <div className="grid min-w-0 flex-1">
                    <span className="truncate text-sm">{item.keyword}</span>
                    <span className="text-muted-foreground text-xs">{item.sources.join(" · ")}</span>
                  </div>
                  <Badge variant="outline" className="font-normal">
                    Untracked
                  </Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">Every detected metadata term is already tracked.</p>
          )}
        </section>
      </div>
    </div>
  );
}
