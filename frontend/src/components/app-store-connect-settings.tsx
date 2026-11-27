import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ChevronDown, PlugZap, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { apiPost } from "@/lib/api";
import type { AppStoreConnectStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Pushing needs saved credentials and a key file readable only by the current user. */
export function connectionReady(connection: AppStoreConnectStatus | undefined): boolean {
  return Boolean(connection?.ready || (connection?.configured && connection?.keyExists && connection?.keyModeSafe));
}

/**
 * App Store Connect API key settings, shared by the localization and
 * pricing studios. Only the key's path is stored; its contents never reach the browser.
 */
export function AppStoreConnectSettings({
  connection,
  onSaved,
  onTested,
  title = "App Store Connect settings",
}: {
  title?: string;
  connection: AppStoreConnectStatus;
  onSaved: (connection: AppStoreConnectStatus) => void;
  onTested: () => Promise<unknown>;
}) {
  const [open, setOpen] = useState(!connection.configured);
  const [issuerId, setIssuerId] = useState(connection.issuerId ?? "");
  const [keyId, setKeyId] = useState(connection.keyId ?? "");
  const [keyPath, setKeyPath] = useState(connection.keyPath ?? "");
  const body = { issuerId: issuerId.trim(), keyId: keyId.trim(), keyPath: keyPath.trim() };

  const save = useMutation({
    mutationFn: () => apiPost<AppStoreConnectStatus>("/api/app-store-connect/settings", body),
    onSuccess: (result) => {
      onSaved(result);
      toast.success("App Store Connect settings saved locally.");
    },
    onError: (error) => toast.error(error.message),
  });
  const test = useMutation({
    mutationFn: async () => {
      await apiPost("/api/app-store-connect/settings", body);
      return apiPost("/api/app-store-connect/test", {});
    },
    onSuccess: async () => {
      toast.success("App Store Connect connection verified.");
      await onTested();
    },
    onError: (error) => toast.error(error.message),
  });
  const busy = save.isPending || test.isPending;

  return (
    <div className="rounded-lg border">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="asc-settings"
        onClick={() => setOpen((value) => !value)}
        className="hover:bg-muted/50 focus-visible:ring-ring/50 flex w-full items-center gap-2 rounded-lg px-4 py-3 text-left text-sm font-medium focus-visible:ring-[3px] focus-visible:outline-none"
      >
        {title}
        {connection.configured && !connectionReady(connection) ? (
          <span className="text-destructive text-xs font-normal">
            {connection.keyExists ? "Key file must be readable only by you" : "Key file not found"}
          </span>
        ) : null}
        <ChevronDown className={cn("ml-auto size-4 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open ? (
        <div id="asc-settings" className="grid gap-4 border-t p-4">
          <FieldGroup className="grid gap-4 md:grid-cols-[1fr_12rem_1.5fr]">
            <Field>
              <FieldLabel htmlFor="asc-issuer">Issuer ID</FieldLabel>
              <Input id="asc-issuer" value={issuerId} autoComplete="off" onChange={(event) => setIssuerId(event.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="asc-key-id">Key ID</FieldLabel>
              <Input id="asc-key-id" value={keyId} autoComplete="off" onChange={(event) => setKeyId(event.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="asc-key-path">Private key path</FieldLabel>
              <Input
                id="asc-key-path"
                value={keyPath}
                autoComplete="off"
                spellCheck={false}
                placeholder="~/.local-aso-tracker/app-store-connect/AuthKey_XXXX.p8"
                onChange={(event) => setKeyPath(event.target.value)}
              />
            </Field>
          </FieldGroup>
          <FieldDescription>
            Enter the path to the .p8 file, not its contents. The private key is read locally, never returned to the
            browser, logged, or exported.
          </FieldDescription>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => save.mutate()} disabled={busy}>
              {save.isPending ? <Spinner /> : <Save />} Save connection
            </Button>
            <Button variant="outline" size="sm" onClick={() => test.mutate()} disabled={busy}>
              {test.isPending ? <Spinner /> : <PlugZap />} {test.isPending ? "Testing…" : "Test connection"}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

