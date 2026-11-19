import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Bot, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Page } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { apiPost } from "@/lib/api";
import { countryFlag } from "@/lib/format";
import { useNiche, useNicheCache, type NichePayload } from "./api";
import { checkSummary } from "./cells";
import { NicheBoardCard, ProviderSelect } from "./niche-board";

function notify(message: { text: string; failed: boolean }) {
  if (message.failed) toast.warning(message.text);
  else toast.success(message.text);
}

export function NichePage() {
  const [boardId, setBoardId] = useState<number | null>(null);
  const niche = useNiche(boardId);
  const store = useNicheCache();
  const [brief, setBrief] = useState("");
  const [provider, setProvider] = useState<string | null>(null);

  const data = niche.data;
  const board = data?.board ?? null;
  const providers = data?.providers ?? [];
  const anyProvider = providers.some((item) => item.available);
  const chosenProvider = provider ?? data?.defaultProvider ?? "auto";

  const receive = (result: NichePayload) => {
    store(result);
    setBoardId(result.selectedBoardId);
  };

  const generate = useMutation({
    mutationFn: (text: string) =>
      apiPost<NichePayload>("/api/niche/generate", { brief: text, provider: chosenProvider }),
    onSuccess: (result) => {
      receive(result);
      setBrief("");
      const failures = result.generation?.check.failures ?? 0;
      notify({
        text: `${result.generation?.keywords.length ?? 0} keywords from ${result.generation?.provider ?? "the agent"}, checked across ${result.board?.countries.length ?? 0} markets${failures ? `; ${failures} checks failed` : ""}`,
        failed: failures > 0,
      });
    },
    onError: (error) => toast.error(error.message),
  });
  const check = useMutation({
    mutationFn: (id: number) => apiPost<NichePayload>("/api/niche/check", { boardId: id }),
    onSuccess: (result) => {
      receive(result);
      notify(checkSummary(result.check));
    },
    onError: (error) => toast.error(error.message),
  });
  const askAgent = useMutation({
    mutationFn: (input: { boardId: number; instruction: string }) =>
      apiPost<NichePayload>("/api/niche/agent-keywords", { ...input, provider: chosenProvider }),
    onSuccess: (result) => {
      receive(result);
      const added = result.agent?.keywords.length ?? 0;
      const failures = result.agent?.check?.failures ?? 0;
      notify({
        text: `${added} keyword${added === 1 ? "" : "s"} added with ${result.agent?.provider ?? "the agent"}${failures ? `; ${failures} checks failed` : ""}`,
        failed: failures > 0,
      });
    },
    onError: (error) => toast.error(error.message),
  });
  const addCountry = useMutation({
    mutationFn: (input: { boardId: number; country: string }) =>
      apiPost<NichePayload>("/api/niche/countries/add", input),
    onSuccess: (result, input) => {
      receive(result);
      const failures = result.countryChange?.check?.failures ?? 0;
      notify({
        text: `${countryFlag(input.country)} ${input.country.toUpperCase()} added${failures ? `; ${failures} checks failed` : " and checked"}`,
        failed: failures > 0,
      });
    },
    onError: (error) => toast.error(error.message),
  });
  const removeCountry = useMutation({
    mutationFn: (input: { boardId: number; country: string }) =>
      apiPost<NichePayload>("/api/niche/countries/remove", input),
    onSuccess: (result, input) => {
      receive(result);
      toast.success(`${countryFlag(input.country)} ${input.country.toUpperCase()} removed from this board`);
    },
    onError: (error) => toast.error(error.message),
  });

  const busy =
    generate.isPending || check.isPending || askAgent.isPending || addCountry.isPending || removeCountry.isPending;

  const actions = (
    <>
      {data?.boards.length ? (
        <Select
          value={String(data.selectedBoardId ?? "")}
          onValueChange={(value) => setBoardId(Number(value))}
          disabled={busy}
        >
          <SelectTrigger size="sm" className="w-[12rem]" aria-label="Niche board">
            <SelectValue placeholder="Choose a board" />
          </SelectTrigger>
          <SelectContent align="end">
            {data.boards.map((item) => (
              <SelectItem key={item.id} value={String(item.id)}>
                <span className="max-w-64 truncate">{item.name}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : null}
      <Button size="sm" onClick={() => board && check.mutate(board.id)} disabled={!board || busy}>
        {check.isPending ? <Spinner /> : <RefreshCw />}
        <span className="hidden md:inline">{check.isPending ? "Checking…" : "Check now"}</span>
      </Button>
    </>
  );

  return (
    <Page title="Niche research" actions={actions} storefrontPickers={false}>
      {niche.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load niche research</AlertTitle>
          <AlertDescription>{niche.error.message}</AlertDescription>
        </Alert>
      ) : null}

      {data && !anyProvider ? (
        <Alert>
          <Bot />
          <AlertTitle>Set up a local AI agent to brainstorm keywords</AlertTitle>
          <AlertDescription>
            Install and sign in to the Claude, Codex, Gemini, or OpenCode CLI, or run Ollama; set it up from the Audit page&rsquo;s
            agent settings. Existing boards can still be checked against Apple.
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardDescription>Independent of your apps · stays on this Mac</CardDescription>
          <CardTitle className="text-base">Brainstorm a niche</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              const text = brief.trim();
              if (!text) {
                toast.error("Describe the niche first");
                return;
              }
              generate.mutate(text);
            }}
          >
            <Field>
              <FieldLabel htmlFor="niche-brief">Describe the niche</FieldLabel>
              <Textarea
                id="niche-brief"
                value={brief}
                onChange={(event) => setBrief(event.target.value)}
                placeholder="e.g. a calm habit tracker for people with ADHD"
                maxLength={1000}
                rows={3}
                disabled={generate.isPending}
              />
              <FieldDescription>
                The local agent suggests 10 keywords, then each is searched on Apple in up to five of your storefronts
                to estimate audience and difficulty. This takes a minute or two.
              </FieldDescription>
            </Field>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <ProviderSelect providers={providers} value={chosenProvider} onChange={setProvider} />
              <Button type="submit" size="sm" disabled={!brief.trim() || !anyProvider || busy}>
                {generate.isPending ? <Spinner /> : <Sparkles />}
                {generate.isPending ? "Generating and checking…" : "Generate board"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {!data && niche.isLoading ? <Skeleton className="h-80" /> : null}

      {data && !board ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Sparkles />
            </EmptyMedia>
            <EmptyTitle>No niche boards yet</EmptyTitle>
            <EmptyDescription>
              Describe an idea above to get a keyword &times; market board with local audience and difficulty
              estimates. Boards are saved locally and don&rsquo;t need an app.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {data && board ? (
        <NicheBoardCard
          board={board}
          availableCountries={data.availableCountries}
          providers={providers}
          provider={chosenProvider}
          onProviderChange={setProvider}
          busy={busy}
          checking={check.isPending}
          addingCountry={addCountry.isPending}
          removingCountry={removeCountry.isPending ? (removeCountry.variables?.country ?? null) : null}
          askingAgent={askAgent.isPending}
          onAddCountry={(country) => addCountry.mutate({ boardId: board.id, country })}
          onRemoveCountry={(country) => removeCountry.mutate({ boardId: board.id, country })}
          onAskAgent={(instruction) => askAgent.mutateAsync({ boardId: board.id, instruction })}
        />
      ) : null}
    </Page>
  );
}
