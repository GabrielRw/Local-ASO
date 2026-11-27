import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, ExternalLink, KeyRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { apiPost } from "@/lib/api";
import { LICENCE_KEY, useLicence, type LicenceStatus } from "@/lib/licence";

/** Licence key, version, and update checks for the Mac app. */
export function LicenceDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const client = useQueryClient();
  const licence = useLicence();
  const [key, setKey] = useState("");
  const save = (result: LicenceStatus) => client.setQueryData(LICENCE_KEY, result);

  const activate = useMutation({
    mutationFn: () => apiPost<LicenceStatus>("/api/licence", { key }),
    onSuccess: (result) => {
      save(result);
      setKey("");
      toast.success(`Licence activated for ${result.email}. Thank you!`);
    },
  });
  const remove = useMutation({
    mutationFn: () => apiPost<LicenceStatus>("/api/licence", { remove: true }),
    onSuccess: (result) => {
      save(result);
      toast.success("Licence removed from this Mac.");
    },
    onError: (error) => toast.error(error.message),
  });
  const updates = useMutation({
    mutationFn: (checkUpdates: boolean) => apiPost<LicenceStatus>("/api/desktop/settings", { checkUpdates }),
    onSuccess: save,
    onError: (error) => toast.error(error.message),
  });
  const data = licence.data;
  const paid = data?.paidEdition ?? false;

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{paid ? "Licence" : "Updates"}</DialogTitle>
          <DialogDescription>
            {paid
              ? `Research, tracking, audits, and local AI are free. A ${data?.price ?? "$9"} lifetime licence unlocks writing to App Store Connect: listing pushes and price changes.`
              : "Local ASO is free, with every feature included."}
          </DialogDescription>
        </DialogHeader>

        {!paid ? null : data?.licensed ? (
          <div className="flex items-start gap-3 rounded-lg border p-4">
            <BadgeCheck className="text-emerald-600 dark:text-emerald-400 mt-0.5 size-5 shrink-0" aria-hidden />
            <div className="grid gap-0.5 text-sm">
              <span className="font-medium">Licensed to {data.email}</span>
              <span className="text-muted-foreground">Lifetime licence, issued {data.issued}</span>
            </div>
            <Button size="sm" variant="ghost" className="ml-auto" disabled={remove.isPending} onClick={() => remove.mutate()}>
              Remove
            </Button>
          </div>
        ) : (
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (key.trim()) activate.mutate();
            }}
          >
            <Field data-invalid={Boolean(activate.error)}>
              <FieldLabel htmlFor="licence-key">Licence key</FieldLabel>
              <Textarea
                id="licence-key"
                rows={3}
                spellCheck={false}
                placeholder="LASO1-…"
                className="font-mono text-xs break-all"
                value={key}
                onChange={(event) => setKey(event.target.value)}
                aria-invalid={Boolean(activate.error)}
              />
              <FieldDescription>Checked on this Mac. Nothing is sent anywhere.</FieldDescription>
              {activate.error ? <FieldError>{activate.error.message}</FieldError> : null}
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={!key.trim() || activate.isPending}>
                <KeyRound />
                {activate.isPending ? "Checking…" : "Activate"}
              </Button>
              {data?.buyUrl ? (
                <Button variant="outline" asChild>
                  <a href={data.buyUrl} target="_blank" rel="noreferrer">
                    Buy lifetime licence ({data.price}) <ExternalLink />
                  </a>
                </Button>
              ) : null}
            </div>
          </form>
        )}

        {data ? (
          <div className="flex items-start justify-between gap-4 rounded-lg border p-4">
            <Label htmlFor="check-updates" className="grid gap-1 font-normal">
              <span className="font-medium">Check for updates at launch</span>
              <span className="text-muted-foreground text-xs">
                Reads the latest signed release from GitHub. Version {data.version}.
              </span>
            </Label>
            <Switch
              id="check-updates"
              checked={data.settings.checkUpdates}
              disabled={updates.isPending}
              onCheckedChange={(checked) => updates.mutate(checked)}
            />
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
