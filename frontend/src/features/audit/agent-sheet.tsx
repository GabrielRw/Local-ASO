import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet, FieldLegend } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { apiPost } from "@/lib/api";
import { useInvalidate } from "@/lib/queries";
import type { AgentPaths, AgentProvider } from "@/lib/types";

const CLI_PROVIDERS = [
  { id: "claude", label: "Claude" },
  { id: "codex", label: "Codex" },
  { id: "gemini", label: "Gemini" },
  { id: "opencode", label: "OpenCode" },
] as const;
type CliId = (typeof CLI_PROVIDERS)[number]["id"];

const EMPTY: AgentPaths = {
  claude: "",
  codex: "",
  gemini: "",
  opencode: "",
  ollama: { url: "http://127.0.0.1:11434", model: "", models: [] },
};
const FIRST_MODEL = "__first__";

/** Local AI providers: CLI paths, the local Ollama model, a connection test, and saving. */
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
  paths: AgentPaths | undefined;
}) {
  const saved = paths ?? EMPTY;
  const [cliPaths, setCliPaths] = useState<Record<CliId, string>>(() => pickPaths(saved));
  const [ollamaUrl, setOllamaUrl] = useState(saved.ollama.url);
  const [ollamaModel, setOllamaModel] = useState(saved.ollama.model);
  const invalidate = useInvalidate();

  useEffect(() => {
    if (!open) return;
    setCliPaths(pickPaths(saved));
    setOllamaUrl(saved.ollama.url);
    setOllamaModel(saved.ollama.model);
    // Reset from the server values each time the sheet opens.
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const body = {
    provider,
    paths: Object.fromEntries(CLI_PROVIDERS.map((item) => [item.id, cliPaths[item.id].trim()])),
    ollamaUrl: ollamaUrl.trim(),
    ollamaModel,
  };
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
      toast.success("Local AI settings saved");
      await invalidate.all();
      onOpenChange(false);
    },
    onError: (error) => toast.error(error.message),
  });
  const available = new Map(providers.map((item) => [item.id, item.available]));

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Local AI</SheetTitle>
          <SheetDescription>
            Audits, keyword research, and translations run through an AI already on this Mac: a command-line tool
            you&rsquo;re signed in to, or a model in Ollama. Apple and the local database supply every measured
            number.
          </SheetDescription>
        </SheetHeader>
        <div className="grid gap-6 px-4">
          <div className="flex flex-wrap gap-1.5">
            {providers.map((item) => (
              <Badge key={item.id} variant={item.available ? "secondary" : "outline"}>
                {item.label} · {item.available ? "ready" : "not found"}
              </Badge>
            ))}
          </div>
          <FieldSet>
            <FieldLegend variant="label">Command-line tools</FieldLegend>
            <FieldDescription>Leave a path empty to search your PATH and common install folders.</FieldDescription>
            <FieldGroup className="gap-4">
              {CLI_PROVIDERS.map((item) => (
                <Field key={item.id}>
                  <FieldLabel htmlFor={`agent-${item.id}`}>
                    {item.label}
                    {available.get(item.id) ? <span className="text-muted-foreground font-normal">· found</span> : null}
                  </FieldLabel>
                  <Input
                    id={`agent-${item.id}`}
                    value={cliPaths[item.id]}
                    onChange={(event) => setCliPaths((current) => ({ ...current, [item.id]: event.target.value }))}
                    placeholder="Auto-detect"
                    spellCheck={false}
                  />
                </Field>
              ))}
            </FieldGroup>
          </FieldSet>
          <FieldSet>
            <FieldLegend variant="label">Ollama</FieldLegend>
            <FieldDescription>
              Runs a model on this Mac; prompts never leave it. Only a local address is accepted.
            </FieldDescription>
            <FieldGroup className="gap-4">
              <Field>
                <FieldLabel htmlFor="agent-ollama-url">Address</FieldLabel>
                <Input
                  id="agent-ollama-url"
                  value={ollamaUrl}
                  onChange={(event) => setOllamaUrl(event.target.value)}
                  spellCheck={false}
                />
              </Field>
              <Field>
                <FieldLabel>Model</FieldLabel>
                {saved.ollama.models.length ? (
                  <Select
                    value={ollamaModel || FIRST_MODEL}
                    onValueChange={(value) => setOllamaModel(value === FIRST_MODEL ? "" : value)}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={FIRST_MODEL}>First installed model</SelectItem>
                      {saved.ollama.models.map((model) => (
                        <SelectItem key={model} value={model}>
                          {model}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <FieldDescription>
                    Ollama isn&rsquo;t running or has no models. Install it, then run{" "}
                    <code className="bg-muted rounded px-1">ollama pull llama3.1</code>.
                  </FieldDescription>
                )}
              </Field>
            </FieldGroup>
          </FieldSet>
        </div>
        <SheetFooter className="flex-row justify-end">
          <Button variant="outline" onClick={() => test.mutate()} disabled={test.isPending}>
            {test.isPending ? "Testing…" : "Test selected"}
          </Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            Save
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function pickPaths(paths: AgentPaths): Record<CliId, string> {
  return { claude: paths.claude, codex: paths.codex, gemini: paths.gemini, opencode: paths.opencode };
}
