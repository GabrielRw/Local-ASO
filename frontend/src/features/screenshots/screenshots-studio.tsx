import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, ImagePlus, Images, Languages, PlugZap, Send, ShieldCheck, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { connectionReady } from "@/components/app-store-connect-settings";
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { apiGet, apiPost, apiPostImage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { CharCount } from "@/features/optimize/highlight-input";
import { useLocalizationStudio } from "@/features/optimize/queries";
import { CAPTION_LIMITS, missingCaptions, renderCounts, renderJobs } from "./plan";
import { canvasToPng, isRtl, loadImage, renderScreenshot, type ScreenshotStyle } from "./render";
import type {
  ScreenshotDeviceId,
  ScreenshotPushResult,
  ScreenshotSource,
  ScreenshotStudioData,
} from "./types";

const DEVICE_IDS: ScreenshotDeviceId[] = ["iphone", "ipad"];
const STYLE_FIELDS: { key: keyof ScreenshotStyle; label: string }[] = [
  { key: "background", label: "Top" },
  { key: "backgroundTo", label: "Bottom" },
  { key: "text", label: "Headline" },
  { key: "accent", label: "Subline" },
];

const studioKey = (appId: number) => ["screenshot-studio", appId] as const;

/** A JSON action whose answer is the whole updated studio. */
function useStudioAction(appId: number, path: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: object) => apiPost<ScreenshotStudioData>(path, { appId, ...body }),
    onSuccess: (data) => client.setQueryData(studioKey(appId), data),
    onError: (error) => toast.error(error.message),
  });
}

const imageCache = new Map<string, Promise<HTMLImageElement>>();
function cachedImage(url: string): Promise<HTMLImageElement> {
  let image = imageCache.get(url);
  if (!image) {
    image = loadImage(url);
    imageCache.set(url, image);
    image.catch(() => imageCache.delete(url));
  }
  return image;
}

/**
 * Captioned, localized App Store screenshots: import raw captures, write or draft
 * captions, translate them, render every locale on a canvas at Apple's sizes, and
 * replace the screenshot sets of an editable App Store Connect version after a
 * confirmation that lists every change.
 */
export function ScreenshotsStudio({ appId, country }: { appId: number; country: string }) {
  const client = useQueryClient();
  const studio = useQuery({
    queryKey: studioKey(appId),
    queryFn: ({ signal }) => apiGet<ScreenshotStudioData>("/api/screenshots", { appId }, signal),
    staleTime: 30_000,
  });
  const localization = useLocalizationStudio(appId, country);
  const setData = (data: ScreenshotStudioData) => client.setQueryData(studioKey(appId), data);

  const [locale, setLocale] = useState<string | null>(null);
  const [provider, setProvider] = useState<string | null>(null);
  const [style, setStyle] = useState<ScreenshotStyle | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [pushOpen, setPushOpen] = useState(false);
  const [pushLocales, setPushLocales] = useState<string[]>([]);
  const [pushDevices, setPushDevices] = useState<ScreenshotDeviceId[]>(["iphone"]);
  const fileInput = useRef<HTMLInputElement>(null);

  const data = studio.data;
  const activeLocale = locale && data?.locales.some((item) => item.locale === locale) ? locale : (data?.mainLocale ?? "en-US");
  const activeStyle = style ?? data?.style;
  const chosenProvider = provider ?? localization.data?.defaultProvider ?? "auto";

  const onError = (error: Error) => toast.error(error.message);
  const remove = useStudioAction(appId, "/api/screenshots/delete");
  const reorder = useStudioAction(appId, "/api/screenshots/reorder");
  const caption = useStudioAction(appId, "/api/screenshots/caption");
  const settings = useStudioAction(appId, "/api/screenshots/settings");
  const saveSettings = settings.mutate;

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      let latest: ScreenshotStudioData | null = null;
      for (const file of files) latest = await apiPostImage<ScreenshotStudioData>("/api/screenshots/sources", { appId, name: file.name }, file);
      return latest;
    },
    onSuccess: (result) => {
      if (result) setData(result);
    },
    onError,
  });

  const draft = useMutation({
    mutationFn: () => apiPost<ScreenshotStudioData>("/api/screenshots/draft", { appId, country, provider: chosenProvider }),
    onSuccess: (result) => {
      setData(result);
      toast.success("Captions drafted. Edit any of them before rendering.");
    },
    onError,
  });

  const translate = useMutation({
    mutationFn: (locales: string[]) => apiPost<ScreenshotStudioData>("/api/screenshots/translate", { appId, locales, provider: chosenProvider }),
    onSuccess: (result) => {
      setData(result);
      toast.success("Captions translated. Captions you wrote yourself were kept.");
    },
    onError,
  });

  const render = useMutation({
    mutationFn: async () => {
      if (!data || !activeStyle) return;
      const jobs = renderJobs(data, DEVICE_IDS);
      const canvas = document.createElement("canvas");
      setProgress({ done: 0, total: jobs.length });
      for (const [index, job] of jobs.entries()) {
        const source = data.sources.find((item) => item.id === job.sourceId);
        const text = source?.captions[job.locale];
        if (!source || !text) continue;
        const device = data.devices[job.device];
        renderScreenshot(canvas, {
          image: await cachedImage(source.url),
          width: device.width,
          height: device.height,
          headline: text.headline,
          subline: text.subline,
          style: activeStyle,
          locale: job.locale,
        });
        await apiPostImage(
          "/api/screenshots/rendered",
          { appId, locale: job.locale, device: job.device, position: job.position },
          await canvasToPng(canvas),
        );
        setProgress({ done: index + 1, total: jobs.length });
      }
      return jobs.length;
    },
    onSuccess: async (count) => {
      await client.invalidateQueries({ queryKey: studioKey(appId) });
      toast.success(`${count ?? 0} screenshots rendered.`);
    },
    onError,
    onSettled: () => setProgress(null),
  });

  const push = useMutation({
    mutationFn: () => apiPost<ScreenshotPushResult>("/api/screenshots/push", { appId, locales: pushLocales, devices: pushDevices }),
    onSuccess: async (result) => {
      const failed = result.results.filter((item) => item.error);
      if (failed.length) toast.error(`${failed.length} of ${result.results.length} uploads failed. See the push log.`);
      else toast.success(`Screenshots uploaded for ${result.results.length} locale and device sets.`);
      await client.invalidateQueries({ queryKey: studioKey(appId) });
    },
    onError,
  });

  // Save style changes shortly after the last colour change.
  useEffect(() => {
    if (!style || !data || JSON.stringify(style) === JSON.stringify(data.style)) return;
    const timer = window.setTimeout(() => saveSettings({ style }), 600);
    return () => window.clearTimeout(timer);
  }, [style, data, saveSettings]);

  if (studio.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Could not load the screenshot studio</AlertTitle>
        <AlertDescription>{studio.error.message}</AlertDescription>
      </Alert>
    );
  }
  if (!data || !activeStyle) return <Skeleton className="h-72" />;

  const connection = localization.data?.connection;
  const ready = connectionReady(connection);
  const counts = renderCounts(data.renders, data.sources.length);
  const otherLocales = data.locales.filter((item) => !item.isMain).map((item) => item.locale);
  const busy = upload.isPending || draft.isPending || translate.isPending || render.isPending || push.isPending;
  const renderableLocales = data.locales.filter((item) => counts.has(item.locale));
  const pushRows = pushLocales.flatMap((code) =>
    pushDevices.map((device) => ({ locale: code, device, count: counts.get(code)?.[device] ?? 0 })),
  );

  const move = (source: ScreenshotSource, step: number) => {
    const order = data.sources.map((item) => item.id);
    const index = order.indexOf(source.id);
    order.splice(index, 1);
    order.splice(index + step, 0, source.id);
    reorder.mutate({ order });
  };

  return (
    <Card>
      <CardHeader>
        <CardDescription>Localized screenshots</CardDescription>
        <CardTitle className="text-base">Screenshot studio</CardTitle>
        <CardAction>
          <Badge variant={ready ? "secondary" : "outline"}>
            {ready ? <ShieldCheck /> : <PlugZap />}
            {ready ? "App Store Connect ready" : "App Store Connect not ready"}
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-6">
        <p className="text-muted-foreground text-sm text-pretty">
          Import raw captures, caption them in your main language, translate, then render iPhone 6.9" and iPad 13"
          screenshots for every market you track.
        </p>

        <div className="grid items-end gap-4 md:grid-cols-[14rem_12rem_minmax(0,1fr)]">
          <Field>
            <FieldLabel htmlFor="screenshot-main-locale">Main caption language</FieldLabel>
            <Select value={data.mainLocale} onValueChange={(value) => settings.mutate({ mainLocale: value })}>
              <SelectTrigger id="screenshot-main-locale" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {data.locales.map((item) => (
                  <SelectItem key={item.locale} value={item.locale}>
                    {item.language} · {item.locale}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="screenshot-provider">Local agent</FieldLabel>
            <Select value={chosenProvider} onValueChange={setProvider}>
              <SelectTrigger id="screenshot-provider" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto-detect</SelectItem>
                {(localization.data?.providers ?? []).map((item) => (
                  <SelectItem key={item.id} value={item.id} disabled={!item.available}>
                    {item.label}
                    {item.available ? "" : " · unavailable"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <fieldset className="flex flex-wrap items-end gap-3">
            <legend className="sr-only">Colours</legend>
            {STYLE_FIELDS.map((field) => (
              <label key={field.key} className="grid gap-1 text-xs">
                <span className="text-muted-foreground">{field.label}</span>
                <Input
                  type="color"
                  className="h-9 w-14 p-1"
                  value={activeStyle[field.key]}
                  onChange={(event) => setStyle({ ...activeStyle, [field.key]: event.target.value })}
                />
              </label>
            ))}
          </fieldset>
        </div>

        <section aria-labelledby="screenshot-sources" className="grid gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id="screenshot-sources" className="text-sm font-medium">
              Screenshots ({data.sources.length}/10)
            </h3>
            <input
              ref={fileInput}
              type="file"
              accept="image/png,image/jpeg"
              multiple
              className="sr-only"
              tabIndex={-1}
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                event.target.value = "";
                if (files.length) upload.mutate(files);
              }}
            />
            <Button
              size="sm"
              variant="outline"
              className="ml-auto"
              disabled={busy || data.sources.length >= 10}
              onClick={() => fileInput.current?.click()}
            >
              {upload.isPending ? <Spinner /> : <ImagePlus />}
              Import
            </Button>
          </div>
          {data.sources.length ? (
            <ol className="-mx-1 flex snap-x gap-3 overflow-x-auto px-1 pb-2">
              {data.sources.map((source, index) => (
                <li key={source.id} className="grid shrink-0 snap-start gap-1.5">
                  <img
                    src={source.url}
                    alt={`Screenshot ${source.position}${source.name ? `, ${source.name}` : ""}`}
                    className="bg-muted h-48 w-auto rounded-md border object-contain"
                  />
                  <div className="flex items-center gap-1">
                    <span className="text-muted-foreground mr-auto text-xs tabular-nums">#{source.position}</span>
                    <Button size="icon-sm" variant="ghost" aria-label={`Move screenshot ${source.position} left`} disabled={index === 0 || busy} onClick={() => move(source, -1)}>
                      <ArrowLeft />
                    </Button>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      aria-label={`Move screenshot ${source.position} right`}
                      disabled={index === data.sources.length - 1 || busy}
                      onClick={() => move(source, 1)}
                    >
                      <ArrowRight />
                    </Button>
                    <Button size="icon-sm" variant="ghost" aria-label={`Delete screenshot ${source.position}`} disabled={busy} onClick={() => remove.mutate({ sourceId: source.id })}>
                      <Trash2 />
                    </Button>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <Empty className="border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Images />
                </EmptyMedia>
                <EmptyTitle>No screenshots imported</EmptyTitle>
                <EmptyDescription>Import up to 10 PNG or JPEG captures of your app. They stay on this Mac.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
        </section>

        {data.sources.length ? (
          <section aria-labelledby="screenshot-captions" className="grid gap-3">
            <div className="flex flex-wrap items-end gap-2">
              <Field className="w-56">
                <FieldLabel id="screenshot-captions" htmlFor="screenshot-locale">
                  Captions for
                </FieldLabel>
                <Select value={activeLocale} onValueChange={setLocale}>
                  <SelectTrigger id="screenshot-locale" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {data.locales.map((item) => {
                      const missing = missingCaptions(data, item.locale);
                      return (
                        <SelectItem key={item.locale} value={item.locale}>
                          {item.language} · {item.locale}
                          {item.isMain ? " · main" : missing ? ` · ${missing} missing` : ""}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
              </Field>
              <div className="ml-auto flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={busy} onClick={() => draft.mutate()}>
                  {draft.isPending ? <Spinner /> : <Sparkles />}
                  Draft main captions
                </Button>
                <Button size="sm" variant="outline" disabled={busy || !otherLocales.length} onClick={() => translate.mutate(otherLocales)}>
                  {translate.isPending ? <Spinner /> : <Languages />}
                  Translate to {otherLocales.length} {otherLocales.length === 1 ? "language" : "languages"}
                </Button>
              </div>
            </div>
            {draft.isPending || translate.isPending ? (
              <p className="text-muted-foreground text-xs" aria-live="polite">
                The local agent is writing captions. This can take a minute.
              </p>
            ) : null}
            <ol className="grid gap-4 lg:grid-cols-2">
              {data.sources.map((source) => {
                return (
                  <CaptionRow
                    key={`${source.id}-${activeLocale}`}
                    source={source}
                    locale={activeLocale}
                    style={activeStyle}
                    phone={data.devices.iphone}
                    disabled={busy}
                    onSave={(headline, subline) => caption.mutate({ sourceId: source.id, locale: activeLocale, headline, subline })}
                  />
                );
              })}
            </ol>
          </section>
        ) : null}

        {data.sources.length ? (
          <section aria-labelledby="screenshot-renders" className="grid gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <h3 id="screenshot-renders" className="text-sm font-medium">
                Rendered sets
              </h3>
              <div className="ml-auto flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={busy} onClick={() => render.mutate()}>
                  {render.isPending ? <Spinner /> : <Images />}
                  Render all
                </Button>
                <Button
                  size="sm"
                  disabled={busy || !ready || !renderableLocales.length}
                  onClick={() => {
                    setPushLocales(renderableLocales.map((item) => item.locale));
                    setPushOpen(true);
                  }}
                >
                  <Send />
                  Upload to App Store Connect
                </Button>
              </div>
            </div>
            {progress ? (
              <div className="grid gap-1" aria-live="polite">
                <Progress value={(progress.done / Math.max(progress.total, 1)) * 100} aria-label="Rendering progress" />
                <span className="text-muted-foreground text-xs tabular-nums">
                  {progress.done} of {progress.total} rendered
                </span>
              </div>
            ) : null}
            <ul className="grid gap-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
              {data.locales.map((item) => {
                const entry = counts.get(item.locale) ?? {};
                return (
                  <li key={item.locale} className="flex items-center gap-2 rounded-md border px-3 py-2">
                    <span className="mr-auto truncate">
                      {item.language} <span className="text-muted-foreground text-xs">{item.locale}</span>
                    </span>
                    {DEVICE_IDS.map((device) => (
                      <Badge key={device} variant={entry[device] ? "secondary" : "outline"} className="tabular-nums">
                        {device === "iphone" ? "iPhone" : "iPad"} {entry[device] ?? 0}
                      </Badge>
                    ))}
                  </li>
                );
              })}
            </ul>
            <p className="text-muted-foreground text-xs">
              Rendered files are also included in the fastlane export under <code>screenshots/</code>.
              {ready ? "" : " To upload, add an App Store Connect API key in the listing localization studio above."}
            </p>
          </section>
        ) : null}


        {data.pushEvents.length ? (
          <section aria-labelledby="screenshot-push-log" className="grid gap-2">
            <h3 id="screenshot-push-log" className="text-sm font-medium">
              Upload log
            </h3>
            <ul className="grid gap-1 text-sm">
              {data.pushEvents.map((event, index) => (
                <li key={`${event.createdAt}-${index}`} className="flex flex-wrap items-center gap-2">
                  <Badge variant={event.status === "success" ? "secondary" : "destructive"}>{event.status === "success" ? "Uploaded" : "Failed"}</Badge>
                  <span>
                    {event.locale} · {event.device === "iphone" ? "iPhone" : "iPad"}
                    {event.status === "success" ? ` · ${event.uploaded} screenshots` : ""}
                  </span>
                  <span className="text-muted-foreground text-xs">{formatDateTime(event.createdAt)}</span>
                  {event.error ? <span className="text-destructive w-full text-xs">{event.error}</span> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </CardContent>

      <AlertDialog open={pushOpen} onOpenChange={setPushOpen}>
        <AlertDialogContent className="sm:max-w-lg">
          <AlertDialogHeader>
            <AlertDialogTitle>Replace screenshots in App Store Connect?</AlertDialogTitle>
            <AlertDialogDescription>
              For each set below, the existing screenshots on your editable App Store version are deleted and replaced.
              Nothing is submitted for review.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="grid gap-3 text-sm">
            <div className="flex flex-wrap gap-4">
              {DEVICE_IDS.map((device) => (
                <label key={device} className="flex items-center gap-2">
                  <Checkbox
                    checked={pushDevices.includes(device)}
                    onCheckedChange={(checked) =>
                      setPushDevices((current) => (checked ? [...current, device] : current.filter((item) => item !== device)))
                    }
                  />
                  {data.devices[device].label}
                </label>
              ))}
            </div>
            <ul className="grid max-h-64 gap-1 overflow-y-auto rounded-md border p-2">
              {renderableLocales.map((item) => (
                <li key={item.locale}>
                  <label className="flex items-center gap-2">
                    <Checkbox
                      checked={pushLocales.includes(item.locale)}
                      onCheckedChange={(checked) =>
                        setPushLocales((current) => (checked ? [...current, item.locale] : current.filter((code) => code !== item.locale)))
                      }
                    />
                    <span className="mr-auto">
                      {item.language} <span className="text-muted-foreground text-xs">{item.locale}</span>
                    </span>
                    {pushDevices.map((device) => (
                      <span key={device} className="text-muted-foreground text-xs tabular-nums">
                        {device === "iphone" ? "iPhone" : "iPad"} {counts.get(item.locale)?.[device] ?? 0}
                      </span>
                    ))}
                  </label>
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground text-xs">
              {pushRows.filter((row) => row.count).length} sets, {pushRows.reduce((sum, row) => sum + row.count, 0)} screenshots.
              Sets with no renders are skipped.
            </p>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={!pushRows.some((row) => row.count)} onClick={() => push.mutate()}>
              Replace screenshots
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function CaptionRow({
  source,
  locale,
  style,
  phone,
  disabled,
  onSave,
}: {
  source: ScreenshotSource;
  locale: string;
  style: ScreenshotStyle;
  phone: { width: number; height: number };
  disabled: boolean;
  onSave: (headline: string, subline: string) => void;
}) {
  const saved = source.captions[locale];
  const [headline, setHeadline] = useState(saved?.headline ?? "");
  const [subline, setSubline] = useState(saved?.subline ?? "");
  // Take server-side changes (AI drafts, translations) field by field, without
  // touching a field the user is still typing in.
  const [seen, setSeen] = useState({ headline: saved?.headline ?? "", subline: saved?.subline ?? "" });
  const nextHeadline = saved?.headline ?? "";
  const nextSubline = saved?.subline ?? "";
  if (nextHeadline !== seen.headline || nextSubline !== seen.subline) {
    if (nextHeadline !== seen.headline) setHeadline(nextHeadline);
    if (nextSubline !== seen.subline) setSubline(nextSubline);
    setSeen({ headline: nextHeadline, subline: nextSubline });
  }
  const dirty = headline !== (saved?.headline ?? "") || subline !== (saved?.subline ?? "");
  const save = () => {
    if (dirty) onSave(headline, subline);
  };
  const dir = isRtl(locale) ? "rtl" : "ltr";
  const headlineId = `caption-${source.id}-headline`;
  const sublineId = `caption-${source.id}-subline`;

  return (
    <li className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3 rounded-lg border p-3">
      <Preview source={source} headline={headline} subline={subline} style={style} locale={locale} size={phone} />
      <div className="grid content-start gap-3">
        <div className="flex items-center gap-2 text-xs">
          <span className="font-medium">Screenshot {source.position}</span>
          {saved ? <Badge variant="outline">{saved.origin === "ai" ? "AI draft" : "Edited"}</Badge> : <Badge variant="outline">No caption</Badge>}
        </div>
        <Field>
          <FieldLabel htmlFor={headlineId} className="flex">
            Headline <CharCount value={headline} max={CAPTION_LIMITS.headline} />
          </FieldLabel>
          <Input id={headlineId} dir={dir} value={headline} disabled={disabled} maxLength={60} onChange={(event) => setHeadline(event.target.value)} onBlur={save} />
        </Field>
        <Field>
          <FieldLabel htmlFor={sublineId} className="flex">
            Subline <CharCount value={subline} max={CAPTION_LIMITS.subline} />
          </FieldLabel>
          <Input id={sublineId} dir={dir} value={subline} disabled={disabled} maxLength={120} onChange={(event) => setSubline(event.target.value)} onBlur={save} />
        </Field>
      </div>
    </li>
  );
}

/** A live, scaled-down canvas preview of one rendered screenshot. */
function Preview({
  source,
  headline,
  subline,
  style,
  locale,
  size,
}: {
  source: ScreenshotSource;
  headline: string;
  subline: string;
  style: ScreenshotStyle;
  locale: string;
  size: { width: number; height: number };
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void cachedImage(source.url).then((image) => {
        if (cancelled || !canvas.current) return;
        // Preview at a third of Apple's size; layout is proportional, so it matches the export.
        renderScreenshot(canvas.current, {
          image,
          width: Math.round(size.width / 3),
          height: Math.round(size.height / 3),
          headline,
          subline,
          style,
          locale,
        });
      });
    }, 150);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [source.url, headline, subline, style, locale, size.width, size.height]);

  return (
    <canvas
      ref={canvas}
      role="img"
      aria-label={`Preview of screenshot ${source.position}: ${headline || "no caption"}`}
      width={Math.round(size.width / 3)}
      height={Math.round(size.height / 3)}
      className="bg-muted h-auto w-full rounded-md border"
    />
  );
}
