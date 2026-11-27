import { useState } from "react";
import { AppIcon } from "@/components/app-icon";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const RTL_LOCALES = new Set(["ar-SA", "he"]);

export interface PreviewFields {
  name?: string;
  subtitle?: string;
  keywords?: string;
  description?: string;
  promotionalText?: string;
  whatsNew?: string;
}

/**
 * How a localized listing reads on a store product page, from the draft's current
 * (possibly unsaved) text. A layout preview only: the real page also shows
 * media, ratings, and Apple's own chrome, which aren't drafted here.
 */
export function ListingPreview({
  fields,
  locale,
  artworkUrl,
  seller,
  genre,
}: {
  fields: PreviewFields;
  locale: string;
  artworkUrl: string | null | undefined;
  seller: string | null | undefined;
  genre: string | null | undefined;
}) {
  const [expanded, setExpanded] = useState(false);
  const dir = RTL_LOCALES.has(locale) ? "rtl" : "ltr";
  const description = (fields.description ?? "").trim();
  const long = description.length > 280 || description.split("\n").length > 4;

  return (
    <div className="grid gap-3 md:grid-cols-[minmax(0,24rem)_1fr]">
      <article
        lang={locale}
        dir={dir}
        aria-label={`Store page preview, ${locale}`}
        className="bg-background grid gap-4 rounded-2xl border p-5 shadow-xs"
      >
        <header className="flex items-start gap-4">
          <AppIcon artworkUrl={artworkUrl ?? null} name={fields.name ?? ""} className="size-20 rounded-[22%]" />
          <div className="grid min-w-0 flex-1 gap-0.5">
            <h4 className="text-lg leading-tight font-semibold text-pretty">{fields.name || "App name"}</h4>
            <p className="text-muted-foreground text-sm leading-snug text-pretty">{fields.subtitle || "Subtitle"}</p>
            {seller ? <p className="text-muted-foreground mt-1 truncate text-xs">{seller}</p> : null}
            <span className="bg-primary text-primary-foreground mt-2 w-fit rounded-full px-4 py-1 text-xs font-semibold">
              Get
            </span>
          </div>
        </header>

        {fields.promotionalText?.trim() ? (
          <p className="text-sm leading-relaxed text-pretty">{fields.promotionalText.trim()}</p>
        ) : null}

        {description ? (
          <section className="grid gap-1">
            <p className={cn("text-sm leading-relaxed whitespace-pre-line", !expanded && long && "line-clamp-4")}>
              {description}
            </p>
            {long ? (
              <Button variant="link" size="sm" className="h-auto w-fit p-0" onClick={() => setExpanded((value) => !value)}>
                {expanded ? "less" : "more"}
              </Button>
            ) : null}
          </section>
        ) : null}

        {fields.whatsNew?.trim() ? (
          <section className="grid gap-1 border-t pt-3">
            <h5 className="text-sm font-semibold">What’s New</h5>
            <p className="text-muted-foreground text-sm leading-relaxed whitespace-pre-line">{fields.whatsNew.trim()}</p>
          </section>
        ) : null}

        {genre ? <p className="text-muted-foreground border-t pt-3 text-xs">{genre}</p> : null}
      </article>

      <aside className="text-muted-foreground grid content-start gap-3 text-xs">
        <div className="grid gap-1">
          <span className="text-foreground font-medium">Keyword field</span>
          <span>Hidden from customers; used only for search.</span>
          <code className="bg-muted rounded-md p-2 break-words whitespace-pre-wrap">{fields.keywords || "—"}</code>
        </div>
        <p>
          Shows how the text fits, not the full page: Apple adds media, ratings, and its own layout. Nothing is
          uploaded until you approve and push this locale.
        </p>
      </aside>
    </div>
  );
}
