import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { apiPost } from "@/lib/api";
import { countryFlag } from "@/lib/format";
import { useCurrentBootstrap, useInvalidate } from "@/lib/queries";
import { useSelection } from "@/lib/selection";

/** Searchable list of App Store storefronts not yet in the workspace. */
export function AddStorefrontDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data } = useCurrentBootstrap();
  const [, select] = useSelection({ appId: data?.selectedAppId, country: data?.selectedCountry });
  const invalidate = useInvalidate();
  const [query, setQuery] = useState("");
  const active = new Set((data?.countries ?? []).filter((item) => item.active).map((item) => item.code));
  const candidates = useMemo(() => {
    const text = query.trim().toLocaleLowerCase();
    return (data?.markets ?? []).filter(
      (item) =>
        !active.has(item.code) &&
        (!text ||
          item.name.toLocaleLowerCase().includes(text) ||
          item.language.toLocaleLowerCase().includes(text) ||
          item.code === text),
    );
  }, [data?.markets, query, active]);

  const add = useMutation({
    mutationFn: (code: string) =>
      apiPost<{ created: boolean; country: { code: string; name: string } }>("/api/countries", { code }),
    onSuccess: async (result) => {
      toast.success(`${countryFlag(result.country.code)} ${result.country.name} added`);
      await invalidate.bootstrap();
      select({ country: result.country.code });
      setQuery("");
      onClose();
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="gap-3 sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add a storefront</DialogTitle>
          <DialogDescription>
            Research keywords in another App Store country. Audits and translations use its own language.
          </DialogDescription>
        </DialogHeader>
        <div className="relative">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search countries or languages"
            className="pl-8"
            aria-label="Search storefronts"
          />
        </div>
        <ScrollArea className="h-72 rounded-md border">
          <ul className="p-1">
            {candidates.map((item) => (
              <li key={item.code}>
                <button
                  type="button"
                  disabled={add.isPending}
                  onClick={() => add.mutate(item.code)}
                  className="hover:bg-accent focus-visible:bg-accent flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm outline-none disabled:opacity-50"
                >
                  <span aria-hidden>{countryFlag(item.code)}</span>
                  <span className="flex-1 truncate">{item.name}</span>
                  <span className="text-muted-foreground text-xs">{item.language}</span>
                </button>
              </li>
            ))}
            {!candidates.length ? (
              <li className="text-muted-foreground px-2 py-6 text-center text-sm">No other storefronts match.</li>
            ) : null}
          </ul>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
