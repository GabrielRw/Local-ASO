import { cn } from "@/lib/utils";
import { initials } from "@/lib/format";

/** App Store artwork (served by Apple's mzstatic CDN, allowed by the CSP) or initials. */
export function AppIcon({
  name,
  artworkUrl,
  className,
}: {
  name: string;
  artworkUrl?: string | null;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "bg-muted text-muted-foreground inline-flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-[22%] text-[11px] font-semibold ring-1 ring-black/5 dark:ring-white/10",
        className,
      )}
    >
      {artworkUrl ? (
        <img src={artworkUrl} alt="" loading="lazy" className="size-full object-cover" />
      ) : (
        initials(name)
      )}
    </span>
  );
}
