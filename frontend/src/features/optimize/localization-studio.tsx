import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Languages, PlugZap, RefreshCw, Save, Send, ShieldCheck, Sparkles } from "lucide-react";
import { toast } from "sonner";
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
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { apiPost } from "@/lib/api";
import { countryFlag, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { AppStoreConnectSettings } from "@/components/app-store-connect-settings";
import { FastlaneExportButton } from "./fastlane-export";
import { CharCount } from "./highlight-input";
import { replaceDraft, useLocalizationStudio, usePatchStudio } from "./queries";
import { connectionReady, selectableTargets } from "./studio";
import type {
  LocalizationCountry,
  LocalizationDraft,
  LocalizationFieldKey,
  LocalizationStudio as Studio,
} from "./types";

const DRAFT_FIELDS: { key: LocalizationFieldKey; label: string; max: number; multiline?: boolean }[] = [
  { key: "name", label: "Name", max: 30 },
  { key: "subtitle", label: "Subtitle", max: 30 },
  { key: "keywords", label: "Keyword field", max: 100 },
  { key: "description", label: "Description", max: 4000, multiline: true },
  { key: "promotionalText", label: "Promotional text", max: 170, multiline: true },
  { key: "whatsNew", label: "What’s New", max: 4000, multiline: true },
];

const STATUS_LABEL: Record<string, string> = {
  needs_review: "Needs review",
  approved: "Approved",
  pushed: "Pushed",
  failed: "Push failed",
};

/** A POST that answers with the updated draft, which replaces the cached one. */
function useDraftAction(appId: number, path: string, success: string) {
  const patch = usePatchStudio(appId);
  return useMutation({
    mutationFn: (body: { draftId: number; fields?: Record<string, string> }) => apiPost<LocalizationDraft>(path, body),
    onSuccess: (draft) => {
      patch((current) => replaceDraft(current, draft));
      toast.success(success);
    },
    onError: (error) => toast.error(error.message),
  });
}

function providerName(studio: Studio, id: string): string {
  if (id === "auto") return "Auto-detect";
  return studio.providers.find((item) => item.id === id)?.label ?? id;
}

/**
 * Generate localized App Store text from the confirmed main listing with the
 * local agent, review and approve each locale, then write it to an editable App
 * Store Connect version. Nothing is ever submitted for review from here.
 */
export function LocalizationStudio({ appId, country }: { appId: number; country: string }) {
  const studio = useLocalizationStudio(appId, country);
  const patch = usePatchStudio(appId);
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: ["localization-studio", appId] });
  const [targets, setTargets] = useState<string[]>([]);
  const [provider, setProvider] = useState<string | null>(null);
  const [pushId, setPushId] = useState<number | null>(null);

  const data = studio.data;
  const chosenProvider = provider ?? data?.defaultProvider ?? "auto";
  const valid = data ? selectableTargets(data) : new Set<string>();
  const selected = targets.filter((code) => valid.has(code));

  const setMain = useMutation({
    mutationFn: (code: string) => apiPost<Studio>("/api/localization-studio/main", { appId, country: code }),
    onSuccess: (result) => {
      patch(() => result);
      setTargets([]);
    },
    onError: (error) => toast.error(error.message),
  });

  const generate = useMutation({
    mutationFn: (input: { targetCountries: string[]; draftId?: number }) =>
      apiPost<{ drafts: LocalizationDraft[]; iterations: number }>("/api/localization-studio/generate", {
        appId,
        mainCountry: data?.mainCountry ?? country,
        targetCountries: input.targetCountries,
        provider: chosenProvider,
      }),
    onSuccess: async (_result, input) => {
      toast.success(input.draftId ? "Localization regenerated and audited." : "Localized listing drafts generated.");
      if (!input.draftId) setTargets([]);
      await refresh();
    },
    onError: (error) => toast.error(error.message),
  });

  const update = useDraftAction(appId, "/api/localization-studio/update", "Localization saved and audited.");
  const approve = useDraftAction(appId, "/api/localization-studio/approve", "Localization approved for push.");
  const push = useDraftAction(appId, "/api/localization-studio/push", "Localized metadata pushed to App Store Connect.");

  if (studio.isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Generate localized App Store listings</CardTitle>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <AlertTitle>Could not load localizations</AlertTitle>
            <AlertDescription className="flex flex-wrap items-center gap-3">
              {studio.error.message}
              <Button size="sm" variant="outline" onClick={() => void studio.refetch()}>
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (!data) return <Skeleton className="h-72" />;

  const ready = connectionReady(data.connection);
  const pushDraft = data.drafts.find((item) => item.id === pushId);
  const generating = generate.isPending;

  return (
    <Card>
      <CardHeader>
        <CardDescription>Listing localization</CardDescription>
        <CardTitle className="text-base">Generate localized App Store listings</CardTitle>
        <CardAction className="flex flex-wrap items-center justify-end gap-2">
          <FastlaneExportButton appId={appId} />
          <Badge variant={ready ? "secondary" : "outline"}>
            {ready ? <ShieldCheck /> : <PlugZap />}
            {ready ? "App Store Connect ready" : "App Store Connect not ready"}
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-6">
        <p className="text-muted-foreground text-sm text-pretty">
          Use one confirmed main listing as the source, choose target countries, then review and approve each
          localized field before pushing.
        </p>

        <div className="grid items-end gap-4 md:grid-cols-[14rem_minmax(0,1fr)_12rem_auto]">
          <Field>
            <FieldLabel htmlFor="localization-main">Main listing</FieldLabel>
            <Select value={data.mainCountry} onValueChange={(code) => setMain.mutate(code)} disabled={setMain.isPending}>
              <SelectTrigger id="localization-main" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {data.countries.map((item) => (
                  <SelectItem key={item.code} value={item.code}>
                    {countryFlag(item.code)} {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <div className="grid min-w-0 gap-0.5 pb-1">
            <span className="text-sm font-medium">{data.sourceLanguage}</span>
            <span className="text-muted-foreground truncate text-xs">
              {data.sourceLocale} source · {data.sourceFields?.name || "No saved metadata"}
            </span>
          </div>
          <Field>
            <FieldLabel htmlFor="localization-provider">Local agent</FieldLabel>
            <Select value={chosenProvider} onValueChange={setProvider}>
              <SelectTrigger id="localization-provider" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto-detect</SelectItem>
                {data.providers.map((item) => (
                  <SelectItem key={item.id} value={item.id} disabled={!item.available}>
                    {item.label}
                    {item.available ? "" : " · unavailable"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Button
            onClick={() => generate.mutate({ targetCountries: selected })}
            disabled={!selected.length || generating}
          >
            {generating && !generate.variables?.draftId ? <Spinner /> : <Sparkles />}
            {generating && !generate.variables?.draftId ? "Generating…" : "Generate selected"}
          </Button>
        </div>

        {generating ? (
          <p className="text-muted-foreground text-xs" aria-live="polite">
            The local agent is writing and reviewing each locale. This can take a few minutes.
          </p>
        ) : null}

        <AppStoreConnectSettings
          connection={data.connection}
          onSaved={(connection) => patch((current) => ({ ...current, connection }))}
          onTested={refresh}
        />

        <TargetPicker
          countries={data.countries}
          sourceLocale={data.sourceLocale}
          selected={selected}
          onChange={setTargets}
        />

        <p className="text-muted-foreground text-xs">
          Text metadata only. Existing screenshots and previews stay unchanged in App Store Connect.
        </p>

        {data.drafts.length ? (
          <div className="grid gap-4">
            {data.drafts.map((draft) => (
              <DraftCard
                key={`${draft.id}-${draft.updatedAt ?? ""}`}
                draft={draft}
                countries={data.countries}
                providerLabel={providerName(data, draft.provider)}
                connectionReady={ready}
                busy={{
                  update: update.isPending && update.variables?.draftId === draft.id,
                  approve: approve.isPending && approve.variables?.draftId === draft.id,
                  regenerate: generating && generate.variables?.draftId === draft.id,
                  push: push.isPending && pushId === draft.id,
                }}
                generating={generating}
                onSave={(fields) => update.mutate({ draftId: draft.id, fields })}
                onApprove={() => approve.mutate({ draftId: draft.id })}
                onRegenerate={() => generate.mutate({ targetCountries: draft.targetCountries, draftId: draft.id })}
                onPush={() => setPushId(draft.id)}
              />
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">
            No localized listings yet. Choose target markets and generate the first drafts.
          </p>
        )}
      </CardContent>

      <AlertDialog
        open={pushId != null}
        onOpenChange={(open) => {
          if (!open && !push.isPending) setPushId(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Push this localization?</AlertDialogTitle>
            <AlertDialogDescription>
              Write the approved {pushDraft?.targetLocale ?? ""} metadata to App Store Connect? The default product
              page will be updated for every storefront using this locale. Fields are written to an editable App Store
              Connect version only; nothing is submitted for review, and changes still go through App Review when you
              submit.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={push.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={push.isPending || pushId == null}
              onClick={(event) => {
                event.preventDefault();
                if (pushId == null) return;
                push.mutate({ draftId: pushId }, { onSuccess: () => setPushId(null) });
              }}
            >
              {push.isPending ? <Spinner /> : <Send />}
              {push.isPending ? "Pushing…" : "Push to Apple"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function TargetPicker({
  countries,
  sourceLocale,
  selected,
  onChange,
}: {
  countries: LocalizationCountry[];
  sourceLocale: string;
  selected: string[];
  onChange: (codes: string[]) => void;
}) {
  const toggle = (code: string, checked: boolean) =>
    onChange(checked ? [...new Set([...selected, code])] : selected.filter((item) => item !== code));
  return (
    <fieldset className="grid gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <legend className="text-sm font-medium">
          Generate these markets
          <span className="text-muted-foreground ml-2 text-xs font-normal">
            Countries sharing an App Store locale are generated once.
          </span>
        </legend>
        <span className="text-muted-foreground text-xs tabular-nums" aria-live="polite">
          {selected.length} selected
        </span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {countries.map((item) => {
          const sameLocale = item.locale === sourceLocale;
          const disabled = item.isMain || sameLocale;
          const checked = selected.includes(item.code);
          const id = `localization-target-${item.code}`;
          return (
            <label
              key={item.code}
              htmlFor={id}
              className={cn(
                "has-[:focus-visible]:ring-ring/50 flex items-center gap-3 rounded-lg border px-3 py-2 transition-colors has-[:focus-visible]:ring-[3px]",
                checked && "border-primary/60 bg-primary/5",
                disabled ? "cursor-not-allowed opacity-60" : "hover:bg-muted/50 cursor-pointer",
              )}
            >
              <Checkbox
                id={id}
                checked={checked}
                disabled={disabled}
                onCheckedChange={(value) => toggle(item.code, value === true)}
              />
              <span aria-hidden>{countryFlag(item.code)}</span>
              <span className="grid min-w-0 flex-1">
                <span className="truncate text-sm">{item.name}</span>
                <span className="text-muted-foreground truncate text-xs">
                  {item.locale} · {item.language}
                </span>
              </span>
              {item.isMain ? (
                <Badge variant="secondary">Main</Badge>
              ) : sameLocale ? (
                <Badge variant="outline" className="font-normal">
                  Main locale
                </Badge>
              ) : null}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function DraftCard({
  draft,
  countries,
  providerLabel,
  connectionReady: ready,
  busy,
  generating,
  onSave,
  onApprove,
  onRegenerate,
  onPush,
}: {
  draft: LocalizationDraft;
  countries: LocalizationCountry[];
  providerLabel: string;
  connectionReady: boolean;
  busy: { update: boolean; approve: boolean; regenerate: boolean; push: boolean };
  generating: boolean;
  onSave: (fields: Record<string, string>) => void;
  onApprove: () => void;
  onRegenerate: () => void;
  onPush: () => void;
}) {
  const [fields, setFields] = useState<Record<string, string>>(() =>
    Object.fromEntries(DRAFT_FIELDS.map((item) => [item.key, String(draft.fields?.[item.key] ?? "")])),
  );
  const issues = draft.validation?.issues ?? [];
  const errors = issues.filter((issue) => issue.severity === "error").length;
  const names = draft.targetCountries
    .map((code) => {
      const match = countries.find((item) => item.code === code);
      return match ? `${countryFlag(code)} ${match.name}` : countryFlag(code);
    })
    .join(" · ");
  const anyBusy = busy.update || busy.approve || busy.regenerate || busy.push;
  const statusVariant =
    draft.status === "failed" ? "destructive" : draft.status === "pushed" || draft.status === "approved" ? "secondary" : "outline";

  return (
    <article className="grid gap-4 rounded-lg border p-4" aria-labelledby={`draft-${draft.id}-title`}>
      <div className="flex flex-wrap items-start gap-3">
        <Badge variant="outline" className="font-mono">
          <Languages /> {draft.targetLocale}
        </Badge>
        <div className="grid min-w-0 flex-1 gap-0.5">
          <h3 id={`draft-${draft.id}-title`} className="text-sm font-medium text-pretty">
            {names || draft.targetLocale}
          </h3>
          <p className="text-muted-foreground text-xs">
            {draft.language} · {draft.iterationCount} review round{draft.iterationCount === 1 ? "" : "s"} ·{" "}
            {providerLabel}
            {draft.pushedAt ? ` · pushed ${formatDateTime(draft.pushedAt)}` : ""}
          </p>
        </div>
        <Badge variant={statusVariant}>{STATUS_LABEL[draft.status] ?? draft.status.replaceAll("_", " ")}</Badge>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={cn("font-medium", errors ? "text-destructive" : "text-muted-foreground")}>
          {errors
            ? `${errors} blocking issue${errors === 1 ? "" : "s"}`
            : `Audit score ${draft.validation?.score ?? "—"}/100`}
        </span>
        {issues.map((issue, index) => (
          <Badge
            key={`${issue.field ?? ""}-${index}`}
            variant={issue.severity === "error" ? "destructive" : "outline"}
            className="h-auto font-normal whitespace-normal"
          >
            {issue.message}
          </Badge>
        ))}
      </div>

      {draft.error ? (
        <Alert variant="destructive">
          <AlertTitle>Last push failed</AlertTitle>
          <AlertDescription>{draft.error}</AlertDescription>
        </Alert>
      ) : null}

      <FieldGroup className="grid gap-4 md:grid-cols-3">
        {DRAFT_FIELDS.map((item) => {
          const id = `draft-${draft.id}-${item.key}`;
          const value = fields[item.key] ?? "";
          return (
            <Field key={item.key} className={cn(item.multiline && "md:col-span-3")}>
              <FieldLabel htmlFor={id} className="flex w-full items-baseline">
                {item.label}
                <CharCount value={value} max={item.max} />
              </FieldLabel>
              {item.multiline ? (
                <Textarea
                  id={id}
                  value={value}
                  maxLength={item.max}
                  rows={3}
                  className="max-h-60"
                  onChange={(event) => setFields((current) => ({ ...current, [item.key]: event.target.value }))}
                />
              ) : (
                <Input
                  id={id}
                  value={value}
                  maxLength={item.max}
                  onChange={(event) => setFields((current) => ({ ...current, [item.key]: event.target.value }))}
                />
              )}
            </Field>
          );
        })}
      </FieldGroup>

      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={() => onSave(fields)} disabled={anyBusy}>
          {busy.update ? <Spinner /> : <Save />} Save &amp; re-audit
        </Button>
        <Button variant="outline" size="sm" onClick={onRegenerate} disabled={anyBusy || generating}>
          {busy.regenerate ? <Spinner /> : <RefreshCw />} {busy.regenerate ? "Regenerating…" : "Regenerate with agent"}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onApprove}
          disabled={anyBusy || draft.status !== "needs_review" || Boolean(draft.validation?.hasErrors)}
        >
          {busy.approve ? <Spinner /> : null} Approve
        </Button>
        <Button
          size="sm"
          className="sm:ml-auto"
          onClick={onPush}
          disabled={anyBusy || draft.status !== "approved" || !ready}
          title={!ready ? "Set up App Store Connect push settings first" : undefined}
        >
          <Send /> Push to Apple
        </Button>
      </div>
    </article>
  );
}
