import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { apiPost } from "@/lib/api";
import { useInvalidate } from "@/lib/queries";
import type { AgentProvider } from "@/lib/types";

/** Local Codex/Claude CLI paths, a connection test, and the default provider. */
export function AgentSheet({
  open,
  onOpenChange,
  providers,
  provider,
  paths,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  providers: AgentProvider[];
  provider: string;
  paths: { codex: string; claude: string };
}) {
  const [codexPath, setCodexPath] = useState(paths.codex);
  const [claudePath, setClaudePath] = useState(paths.claude);
  const invalidate = useInvalidate();

  useEffect(() => {
    if (open) {
      setCodexPath(paths.codex);
      setClaudePath(paths.claude);
    }
  }, [open, paths.codex, paths.claude]);

  const body = { provider, codexPath: codexPath.trim(), claudePath: claudePath.trim() };
  const test = useMutation({
    mutationFn: () => apiPost<{ provider: string; available: boolean; version: string | null }>("/api/agent/test", body),
    onSuccess: (result) =>
      result.available
        ? toast.success(`${result.provider} responded${result.version ? ` · ${result.version}` : ""}`)
        : toast.error(`${result.provider} is not reachable with these settings`),
    onError: (error) => toast.error(error.message),
  });
  const save = useMutation({
    mutationFn: () => apiPost("/api/settings/agent", body),
    onSuccess: async () => {
      toast.success("Local agent saved");
      await invalidate.audit();
      onOpenChange(false);
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Local AI agent</SheetTitle>
          <SheetDescription>
            Keyword discovery, the native-language review, and the findings editor run through a CLI on this Mac.
            Apple and the local database supply every measured number.
          </SheetDescription>
        </SheetHeader>
        <div className="grid gap-6 px-4">
          <div className="flex flex-wrap gap-2">
            {providers.map((item) => (
              <Badge key={item.id} variant={item.available ? "secondary" : "outline"}>
                {item.label} · {item.available ? "detected" : "not found"}
              </Badge>
            ))}
          </div>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="agent-claude">Claude executable</FieldLabel>
              <Input
                id="agent-claude"
                value={claudePath}
                onChange={(event) => setClaudePath(event.target.value)}
                placeholder="Auto-detect"
              />
              <FieldDescription>Leave empty to search PATH and common install folders.</FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="agent-codex">Codex executable</FieldLabel>
              <Input
                id="agent-codex"
                value={codexPath}
                onChange={(event) => setCodexPath(event.target.value)}
                placeholder="Auto-detect"
              />
            </Field>
          </FieldGroup>
        </div>
        <SheetFooter className="flex-row justify-end">
          <Button variant="outline" onClick={() => test.mutate()} disabled={test.isPending}>
            {test.isPending ? "Testing…" : "Test connection"}
          </Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            Save
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
