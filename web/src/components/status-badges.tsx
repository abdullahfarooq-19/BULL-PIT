"use client";

import { useCallback, useEffect, useState } from "react";

import { api, unwrap } from "@/api/client";
import type { MarketOut } from "@/api/client";
import type { AccountState } from "@/components/account-card";
import { usePolling } from "@/lib/use-polling";
import { cn } from "@/lib/utils";

const MARKET_POLL_MS = 30_000;

type Tone = "bull" | "bear" | "idle";

/** A small pill: a green or red dot and its words. Colour is never the only signal. */
function Badge({ tone, title, children }: { tone: Tone; title?: string; children: React.ReactNode }) {
  return (
    <span
      role="status"
      title={title}
      className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-sm"
    >
      <span
        className={cn(
          "size-2.5 rounded-full",
          tone === "bull" && "bg-bull",
          tone === "bear" && "bg-bear",
          tone === "idle" && "bg-muted-foreground",
        )}
        aria-hidden
      />
      {children}
    </span>
  );
}

/** The next market change in the browser's time zone, with the weekday when it is not
 *  today, and exchange time for a tooltip. */
function when(iso: string): { local: string; exchange: string } {
  const moment = new Date(iso);
  const today = moment.toDateString() === new Date().toDateString();
  const time = moment.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const day = moment.toLocaleDateString("en-GB", { weekday: "short" });
  const exchange = moment.toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "2-digit",
  });
  return { local: today ? time : `${day} ${time}`, exchange: `${exchange} ET` };
}

function useMarket() {
  const [market, setMarket] = useState<MarketOut>();
  const [failed, setFailed] = useState(false);
  const refresh = useCallback(() => {
    unwrap(api.GET("/market")).then(
      (data) => {
        setMarket(data);
        setFailed(false);
      },
      () => setFailed(true),
    );
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);
  usePolling(refresh, MARKET_POLL_MS);
  return { market, failed };
}

/** Green dot and "Market open, closes at", or red dot and "Market closed, opens at"
 *  (M11.3-FR-12, FR-13). */
export function MarketBadge() {
  const { market, failed } = useMarket();
  if (!market) {
    return <Badge tone="idle">{failed ? "Market status unavailable" : "Checking the market"}</Badge>;
  }
  const next = when(market.is_open ? market.next_close : market.next_open);
  return (
    <Badge tone={market.is_open ? "bull" : "bear"} title={`${next.exchange}${failed ? ". Could not refresh." : ""}`}>
      <span className="font-medium">{market.is_open ? "Market open" : "Market closed"}</span>
      <span className="text-muted-foreground">
        {market.is_open ? "closes at" : "opens at"} <span className="num">{next.local}</span>
      </span>
    </Badge>
  );
}

/** Green "Connected" while the Alpaca account can be read, red "Offline" when it can't. It
 *  follows the account card's own five-second read. */
export function ConnectionBadge({ state }: { state: AccountState }) {
  if (!state.loaded) {
    return (
      <Badge tone="idle">
        <span className="font-medium">Alpaca</span>
        <span className="text-muted-foreground">Checking</span>
      </Badge>
    );
  }
  const online = state.error === undefined;
  return (
    <Badge tone={online ? "bull" : "bear"} title={online ? "The Alpaca paper account answered" : state.error?.message}>
      <span className="font-medium">Alpaca</span>
      <span className={online ? "text-bull" : "text-bear"}>{online ? "Connected" : "Offline"}</span>
    </Badge>
  );
}
