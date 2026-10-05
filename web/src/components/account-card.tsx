"use client";

import { useCallback, useEffect, useState } from "react";

import { api, unwrap } from "@/api/client";
import type { AccountOut } from "@/api/client";
import { Skeleton } from "@/components/ui/skeleton";
import { money, signedMoney } from "@/lib/format";
import { usePolling } from "@/lib/use-polling";
import { cn } from "@/lib/utils";

const POLL_MS = 5000;

/** Alpaca's account figures, read every five seconds while the tab is visible. A failed
 *  read keeps the last good figures and records the error, so the card can mark them stale. */
export function useAccount() {
  const [account, setAccount] = useState<AccountOut>();
  const [error, setError] = useState<Error>();
  const [updatedAt, setUpdatedAt] = useState<Date>();
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(() => {
    unwrap(api.GET("/account")).then(
      (data) => {
        setAccount(data);
        setUpdatedAt(new Date());
        setError(undefined);
        setLoaded(true);
      },
      (failure: Error) => {
        setError(failure);
        setLoaded(true);
      },
    );
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);
  usePolling(refresh, POLL_MS);

  return { account, error, updatedAt, loaded };
}

export type AccountState = ReturnType<typeof useAccount>;

/** Broker, Demo badge and the live balance (M11.2-FR-1 to FR-3), read by `useAccount`. */
export function AccountCard({ state }: { state: AccountState }) {
  const { account, error, updatedAt, loaded } = state;

  if (!loaded) return <Skeleton role="status" aria-label="Loading the account" className="h-36 w-full" />;
  if (!account) {
    return (
      <div role="alert" className="rounded-lg border border-bear/40 bg-bear/5 p-4 text-sm">
        <p className="font-medium text-bear">Balance unavailable</p>
        <p className="mt-1 text-muted-foreground">{error?.message}</p>
      </div>
    );
  }

  const change = Number(account.day_change);
  const tone = change === 0 ? "" : change > 0 ? "text-bull" : "text-bear";
  const percent = account.day_change_pct === null ? "" : ` (${change >= 0 ? "+" : ""}${Number(account.day_change_pct).toFixed(2)}%)`;

  return (
    <section aria-label="Account" className="rounded-lg border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="font-semibold">{account.broker}</span>
        <span className="num text-muted-foreground">{account.account_number}</span>
        <span className="text-muted-foreground">{account.status.toLowerCase()}</span>
        <span className="rounded border border-amber/50 px-1.5 py-0.5 text-xs text-amber">Demo account</span>
      </div>
      <p className="mt-4 text-sm text-muted-foreground">Balance</p>
      <p className="num text-4xl font-semibold tracking-tight">{money(account.equity)}</p>
      <p className={cn("num mt-1 text-sm", tone)}>
        {signedMoney(account.day_change)}
        {percent} <span className="text-muted-foreground">today</span>
      </p>
      <p className="num mt-3 text-sm text-muted-foreground">Cash {money(account.cash)}</p>
      <p className="mt-3 text-xs text-muted-foreground" role="status">
        {error
          ? `Could not refresh: ${error.message} Showing the balance from ${updatedAt?.toLocaleTimeString("en-GB")}.`
          : `Updated ${updatedAt?.toLocaleTimeString("en-GB")}. Refreshes every 5 seconds.`}
      </p>
    </section>
  );
}
