import { KeyRound, Search, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import type { AdAccount, PaidCredentials } from "./api";

/** No usable credential: show where the signed client secret belongs, never its contents. */
export function CredentialSetup({
  credentials,
  pending,
  onCheck,
}: {
  credentials: PaidCredentials;
  pending: boolean;
  onCheck: () => void;
}) {
  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardDescription className="flex items-center gap-1.5">
          <ShieldCheck className="size-3.5" /> Read-only Apple Ads
        </CardDescription>
        <CardTitle className="text-base">Connect your local Apple Ads credential</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        <p className="text-muted-foreground text-pretty">
          Save the signed client secret for your Apple Ads API user as{" "}
          <code className="bg-muted rounded px-1 py-0.5 font-mono text-xs">client-secret.jwt</code> at this path. Local
          ASO Tracker only reads campaigns and reports; it never displays, logs, exports, or changes the secret or your
          campaigns.
        </p>
        <div className="grid gap-1.5">
          <span className="text-muted-foreground text-xs">Credential path on this Mac</span>
          <code className="bg-muted block overflow-x-auto rounded-md px-3 py-2 font-mono text-xs break-all select-all">
            {credentials.path || "Unavailable"}
          </code>
        </div>
        <p className="text-destructive text-sm">
          {credentials.reason || "The Apple Ads client secret is missing or has expired."}
        </p>
      </CardContent>
      <CardFooter>
        <Button size="sm" onClick={onCheck} disabled={pending}>
          {pending ? <Spinner /> : <KeyRound />} Check connection
        </Button>
      </CardFooter>
    </Card>
  );
}

export function DiscoverAccounts({ pending, onDiscover }: { pending: boolean; onDiscover: () => void }) {
  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardDescription className="flex items-center gap-1.5">
          <ShieldCheck className="size-3.5" /> Read-only Apple Ads
        </CardDescription>
        <CardTitle className="text-base">Discover your ad accounts</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-muted-foreground text-sm text-pretty">
          The local credential is valid. Discover the ad accounts it can read, then choose the one that runs campaigns
          for this app.
        </p>
      </CardContent>
      <CardFooter>
        <Button size="sm" onClick={onDiscover} disabled={pending}>
          {pending ? <Spinner /> : <Search />} Discover accounts
        </Button>
      </CardFooter>
    </Card>
  );
}

export function ChooseAccount({
  accounts,
  pending,
  onSelect,
}: {
  accounts: AdAccount[];
  pending: boolean;
  onSelect: (id: number) => void;
}) {
  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardDescription className="flex items-center gap-1.5">
          <ShieldCheck className="size-3.5" /> Read-only Apple Ads
        </CardDescription>
        <CardTitle className="text-base">Choose the ad account</CardTitle>
        <CardDescription>
          Your credential can read more than one ad account. Choose the one with this app&rsquo;s campaigns; Local ASO
          then syncs the last 30 days.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2 sm:grid-cols-2">
        {accounts.map((account) => (
          <button
            key={account.id}
            type="button"
            disabled={pending}
            onClick={() => onSelect(account.id)}
            className="hover:bg-muted/60 focus-visible:ring-ring/50 grid gap-1 rounded-lg border p-3 text-left transition-colors focus-visible:ring-[3px] focus-visible:outline-none disabled:opacity-50"
          >
            <span className="truncate text-sm font-medium">{account.name}</span>
            <span className="text-muted-foreground font-mono text-xs">{account.id}</span>
            <span className="flex flex-wrap gap-1 pt-1">
              {account.roles.length ? (
                account.roles.map((role) => (
                  <Badge key={role} variant="secondary" className="font-normal">
                    {role}
                  </Badge>
                ))
              ) : (
                <span className="text-muted-foreground text-xs">No role reported</span>
              )}
            </span>
          </button>
        ))}
      </CardContent>
      {pending ? (
        <CardFooter className="text-muted-foreground gap-2 text-sm">
          <Spinner /> Selecting the account and syncing Apple Ads…
        </CardFooter>
      ) : null}
    </Card>
  );
}
