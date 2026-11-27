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
import { useAgentCheck, useAgentSignIn } from "@/lib/agent";
import type { AgentCheck, AgentPaths, AgentProvider } from "@/lib/types";

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
const NEWEST = "__newest__";

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
  const byId = new Map(providers.map((item) => [item.id, item]));
  const [checks, setChecks] = useState<Record<string, AgentCheck>>({});
  const [checking, setChecking] = useState<string | null>(null);
  const check = useAgentCheck((result) => setChecks((current) => ({ ...current, [result.provider]: result })));
  const signIn = useAgentSignIn();
  const runCheck = (id: string) => {
    setChecking(id);
    check.mutate(id, { onSettled: () => setChecking(null) });
  };

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
          <FieldSet>
            <FieldLegend variant="label">Command-line tools</FieldLegend>
            <FieldDescription>
              Each tool runs in an empty folder, so it never reads your projects. With Auto-detect, a tool that is
              signed out or fails is skipped for the next one.
            </FieldDescription>
            <FieldGroup className="gap-5">
              {CLI_PROVIDERS.map((item) => {
                const details = byId.get(item.id);
                const installs = details?.installs ?? [];
                const check = checks[item.id];
                return (
                  <Field key={item.id} className="gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <FieldLabel htmlFor={`agent-${item.id}`}>{item.label}</FieldLabel>
                      <CheckBadge available={Boolean(details?.available)} check={check} />
                      {details?.available ? (
                        <div className="ml-auto flex gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={checking === item.id}
                            onClick={() => runCheck(item.id)}
                          >
                            {checking === item.id ? "Checking…" : "Check"}
                          </Button>
                          {details.canSignIn ? (
                            <Button
                              size="sm"
                              variant={check?.signedIn === false ? "default" : "ghost"}
                              disabled={signIn.isPending}
                              onClick={() => signIn.mutate(item.id)}
                            >
                              Sign in
                            </Button>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                    {details?.path ? (
                      <FieldDescription className="break-all">
                        Uses {details.version || "unknown version"} · {details.path}
                      </FieldDescription>
                    ) : null}
                    {installs.length > 1 ? (
                      <Select
                        value={cliPaths[item.id] || NEWEST}
                        onValueChange={(value) =>
                          setCliPaths((current) => ({ ...current, [item.id]: value === NEWEST ? "" : value }))
                        }
                      >
                        <SelectTrigger id={`agent-${item.id}`} className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={NEWEST}>Newest copy (automatic)</SelectItem>
                          {installs.map((copy) => (
                            <SelectItem key={copy.path} value={copy.path}>
                              {copy.version || "unknown version"} · {copy.path}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <Input
                        id={`agent-${item.id}`}
                        value={cliPaths[item.id]}
                        onChange={(event) => setCliPaths((current) => ({ ...current, [item.id]: event.target.value }))}
                        placeholder={details?.available ? "Found automatically" : "Not found · enter a path"}
                        spellCheck={false}
                      />
                    )}
                    {check && !check.ok ? <FieldDescription className="text-destructive">{check.message}</FieldDescription> : null}
                  </Field>
                );
              })}
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

function CheckBadge({ available, check }: { available: boolean; check: AgentCheck | undefined }) {
  if (!available) return <Badge variant="outline">Not found</Badge>;
  if (!check) return <Badge variant="secondary">Found</Badge>;
  if (check.ok) return <Badge variant="secondary">Signed in</Badge>;
  if (check.signedIn === false) return <Badge variant="destructive">Signed out</Badge>;
  return <Badge variant="destructive">Not answering</Badge>;
}
