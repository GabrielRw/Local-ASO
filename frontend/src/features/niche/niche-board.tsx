import { useState } from "react";
import { Bot, Plus, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { countryFlag, formatDateTime, toneText } from "@/lib/format";
import type { AgentProvider } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { NicheBoard, NicheCountry, NicheMetric } from "./api";
import { latestCheckedAt, nicheCellView, type NicheCellTone } from "./cells";

const cellTone: Record<NicheCellTone, string> = {
  good: "bg-emerald-500/10 ring-emerald-500/25",
  mixed: "bg-amber-500/10 ring-amber-500/25",
  hard: "bg-rose-500/10 ring-rose-500/25",
  mid: "bg-muted/60 ring-border",
  low: "bg-muted/40 ring-border",
};

/** Agent provider picker shared by the brainstorm and ask-agent forms. */
export function ProviderSelect({
  id,
  providers,
  value,
  onChange,
  className,
}: {
  id?: string;
  providers: AgentProvider[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id} size="sm" className={cn("w-[8.5rem]", className)} aria-label="Local agent">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="auto">Auto-detect</SelectItem>
        {providers.map((item) => (
          <SelectItem key={item.id} value={item.id} disabled={!item.available}>
            {item.label}
            {item.available ? "" : " · not found"}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Shows which phrase was searched in this market (its own language), or that it wasn't translated. */
function TermCaption({ metric }: { metric: NicheMetric | undefined }) {
  if (metric?.term) {
    return (
      <span className="text-muted-foreground mt-1 block max-w-36 truncate text-[11px]" title={`Searched as “${metric.term}”`}>
        “{metric.term}”
      </span>
    );
  }
  if (metric?.untranslated) {
    return (
      <span
        className="mt-1 block text-[11px] text-amber-600 dark:text-amber-400"
        title="No local AI translated this phrase yet, so this market was searched as written. Check again once an AI provider is set up."
      >
        Not translated
      </span>
    );
  }
  return null;
}

function MetricCell({ metric, pending }: { metric: NicheMetric | undefined; pending: boolean }) {
  const view = nicheCellView(metric);
  if (view.kind !== "rated") {
    return (
      <TableCell className={cn("text-center", pending && "animate-pulse motion-reduce:animate-none")}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              tabIndex={0}
              className={cn(
                "inline-block cursor-help rounded-md px-2 py-1 text-xs focus-visible:ring-ring/50 focus-visible:ring-[3px] focus-visible:outline-none",
                view.kind === "error" ? "text-rose-600 dark:text-rose-400" : "text-muted-foreground",
              )}
            >
              {view.label}
            </span>
          </TooltipTrigger>
          <TooltipContent className="max-w-64 text-pretty">{view.title}</TooltipContent>
        </Tooltip>
        <TermCaption metric={metric} />
      </TableCell>
    );
  }
  return (
    <TableCell className={cn("text-center", pending && "animate-pulse motion-reduce:animate-none")}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            tabIndex={0}
            aria-label={view.title}
            className={cn(
              "inline-grid cursor-help grid-cols-2 gap-3 rounded-md px-2.5 py-1 text-left ring-1 tabular-nums focus-visible:ring-ring/50 focus-visible:ring-[3px] focus-visible:outline-none",
              cellTone[view.tone],
            )}
          >
            <span className="grid leading-tight">
              <span className="text-muted-foreground text-[10px] uppercase">Vol</span>
              <span className={cn("text-sm font-medium", toneText[view.volumeTone])}>~{view.volume}</span>
            </span>
            <span className="grid leading-tight">
              <span className="text-muted-foreground text-[10px] uppercase">Diff</span>
              <span className={cn("text-sm font-medium", toneText[view.difficultyTone])}>~{view.difficulty}</span>
            </span>
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-64 text-pretty">{view.title}</TooltipContent>
      </Tooltip>
      <TermCaption metric={metric} />
    </TableCell>
  );
}

export function NicheBoardCard({
  board,
  availableCountries,
  providers,
  provider,
  onProviderChange,
  busy,
  checking,
  addingCountry,
  removingCountry,
  askingAgent,
  onAddCountry,
  onRemoveCountry,
  onAskAgent,
}: {
  board: NicheBoard;
  availableCountries: NicheCountry[];
  providers: AgentProvider[];
  provider: string;
  onProviderChange: (value: string) => void;
  busy: boolean;
  checking: boolean;
  addingCountry: boolean;
  removingCountry: string | null;
  askingAgent: boolean;
  onAddCountry: (country: string) => void;
  onRemoveCountry: (country: string) => void;
  onAskAgent: (instruction: string) => Promise<unknown>;
}) {
  const [country, setCountry] = useState("");
  const [instruction, setInstruction] = useState("");
  const used = new Set(board.countries.map((item) => item.code));
  const addable = availableCountries.filter((item) => !used.has(item.code));
  const checked = latestCheckedAt(board);
  const anyProvider = providers.some((item) => item.available);

  return (
    <Card>
      <CardHeader>
        <CardDescription>
          {board.keywords.length} keyword{board.keywords.length === 1 ? "" : "s"} · {board.countries.length} market
          {board.countries.length === 1 ? "" : "s"} · {checked ? `Checked ${formatDateTime(checked)}` : "Not checked yet"}
        </CardDescription>
        <CardTitle className="text-base">{board.name}</CardTitle>
        {board.brief && board.brief !== board.name ? (
          <CardDescription className="text-pretty">{board.brief}</CardDescription>
        ) : null}
        <CardAction className="flex items-center gap-2">
          <Select value={country} onValueChange={setCountry} disabled={!addable.length || busy}>
            <SelectTrigger size="sm" className="w-[10rem]" aria-label="Storefront to add">
              <SelectValue placeholder={addable.length ? "Add a market" : "All markets added"} />
            </SelectTrigger>
            <SelectContent align="end">
              {addable.map((item) => (
                <SelectItem key={item.code} value={item.code}>
                  <span aria-hidden>{countryFlag(item.code)}</span> {item.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            variant="outline"
            disabled={!country || busy}
            onClick={() => {
              onAddCountry(country);
              setCountry("");
            }}
          >
            {addingCountry ? <Spinner /> : <Plus />} Add
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-3 px-0">
        <p className="text-muted-foreground px-6 text-xs text-pretty">
          Vol and Diff are local 0&ndash;100 estimates from the public ratings of apps Apple returns for each search,
          marked with ~. They are not Apple search volume or downloads.
        </p>
        <Table aria-busy={checking}>
          <TableHeader>
            <TableRow>
              <TableHead className="bg-card sticky left-0 z-10 min-w-44 pl-6">Keyword</TableHead>
              {board.countries.map((item, index) => (
                <TableHead
                  key={item.code}
                  className={cn("min-w-32 text-center", index === board.countries.length - 1 && "pr-6")}
                >
                  <span className="inline-flex items-center gap-1">
                    <span aria-hidden>{countryFlag(item.code)}</span>
                    <span title={item.name}>{item.code.toUpperCase()}</span>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          className="text-muted-foreground size-5"
                          aria-label={`Remove ${item.name} from this board`}
                          disabled={busy || board.countries.length <= 1}
                          onClick={() => onRemoveCountry(item.code)}
                        >
                          {removingCountry === item.code ? <Spinner className="size-3" /> : <X className="size-3" />}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Remove {item.name}</TooltipContent>
                    </Tooltip>
                  </span>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {board.keywords.length ? (
              board.keywords.map((keyword) => (
                <TableRow key={keyword.id}>
                  <TableHead scope="row" className="bg-card sticky left-0 z-10 max-w-56 truncate pl-6 font-medium">
                    {keyword.keyword}
                  </TableHead>
                  {board.countries.map((item, index) => (
                    <MetricCell key={item.code} metric={keyword.metrics[index]} pending={checking} />
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={board.countries.length + 1} className="text-muted-foreground py-8 pl-6 text-sm">
                  No keywords on this board yet. Ask the agent below for some.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
      <CardFooter className="border-t">
        <form
          className="flex w-full flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const text = instruction.trim();
            if (!text) return;
            void onAskAgent(text).then(() => setInstruction(""), () => undefined);
          }}
        >
          <Badge variant="outline" className="hidden font-normal sm:inline-flex">
            <Bot /> Ask the agent
          </Badge>
          <Input
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            placeholder="e.g. 5 long-tail keywords about offline use"
            aria-label="Keywords to add with the local agent"
            maxLength={500}
            className="h-8 min-w-48 flex-1"
            disabled={busy}
          />
          <ProviderSelect providers={providers} value={provider} onChange={onProviderChange} />
          <Button size="sm" type="submit" disabled={!instruction.trim() || !anyProvider || busy}>
            {askingAgent ? <Spinner /> : <Plus />} {askingAgent ? "Adding…" : "Add keywords"}
          </Button>
        </form>
      </CardFooter>
    </Card>
  );
}
