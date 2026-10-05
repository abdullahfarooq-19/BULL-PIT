"use client";

import { ArrowRight, Loader2, Star } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { toast } from "sonner";

import { api, ApiError, isTicker, startRequest, unwrap } from "@/api/client";
import type { WatchlistStock } from "@/api/client";
import { AccountCard, useAccount } from "@/components/account-card";
import { Logo } from "@/components/logo";
import { EmptyPanel, ErrorPanel, LoadingPanel, PageHeader } from "@/components/states";
import { ConnectionBadge, MarketBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

const CHECK_POLL_MS = 1000;
const MOTTO = "Argue first. Trade second.";

/** After Start the page waits for the request check: a rejection is shown here,
 *  anything else opens the report page (M8-FR-22). */
function useCheckedRequest(id: string | undefined, onRejected: (message: string) => void) {
  const router = useRouter();
  useEffect(() => {
    if (!id) return;
    let live = true;
    const tick = async () => {
      try {
        const detail = await unwrap(api.GET("/requests/{request_id}", { params: { path: { request_id: id } } }));
        if (!live) return;
        if (detail.status === "rejected") return onRejected(detail.status_reason ?? "The request was rejected.");
        if (detail.stage !== "starting" && detail.stage !== "checking") return router.push(`/requests/${id}`);
      } catch {
        if (live) return router.push(`/requests/${id}`); // the report page shows the error
      }
      if (live) timer = setTimeout(tick, CHECK_POLL_MS);
    };
    let timer = setTimeout(tick, CHECK_POLL_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [id, onRejected, router]);
}

function StarButton({ stock, onToggle }: { stock: WatchlistStock; onToggle: (stock: WatchlistStock) => void }) {
  return (
    <button
      type="button"
      aria-pressed={stock.liked}
      aria-label={`${stock.liked ? "Unlike" : "Like"} ${stock.symbol}`}
      onClick={() => onToggle(stock)}
      className="rounded p-1 text-muted-foreground outline-none hover:text-amber focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Star className={cn("size-4", stock.liked && "fill-amber text-amber")} aria-hidden />
    </button>
  );
}

/** The account, a ticker box with Start, the owner's liked stocks and the S&P 100 watchlist
 *  (M11.2-FR-1 to FR-8). Picking a stock only fills the ticker box. */
export default function AccountAndWalletPage() {
  const [ticker, setTicker] = useState("");
  const [message, setMessage] = useState<string>();
  const [starting, setStarting] = useState(false);
  const [checking, setChecking] = useState<string>();
  const [filter, setFilter] = useState("");
  const startButton = useRef<HTMLButtonElement>(null);
  const account = useAccount();
  const watchlist = useLoad("watchlist", () => unwrap(api.GET("/watchlist")));

  useCheckedRequest(checking, (reason) => {
    setChecking(undefined);
    setMessage(reason);
  });

  const busy = starting || checking !== undefined;
  const symbol = ticker.trim().toUpperCase();

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage(undefined);
    if (!isTicker(symbol)) return setMessage("Enter a ticker such as AAPL or BRK.B.");
    setStarting(true);
    try {
      setChecking(await startRequest(symbol));
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Could not start the request.");
    } finally {
      setStarting(false);
    }
  };

  const select = (stock: WatchlistStock) => {
    flushSync(() => {
      setTicker(stock.symbol);
      setMessage(undefined);
    });
    startButton.current?.focus(); // enabled only once the ticker is set
  };

  const toggle = async (stock: WatchlistStock) => {
    try {
      const path = { params: { path: { symbol: stock.symbol } } };
      await unwrap(stock.liked ? api.DELETE("/watchlist/{symbol}", path) : api.PUT("/watchlist/{symbol}", path));
      watchlist.reload();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update your liked stocks.");
    }
  };

  const stocks = watchlist.data ?? [];
  const liked = stocks
    .filter((stock) => stock.liked)
    .sort((a, b) => (a.liked_at ?? "").localeCompare(b.liked_at ?? ""));
  const needle = filter.trim().toLowerCase();
  const matches = stocks.filter(
    (stock) => !needle || stock.symbol.toLowerCase().includes(needle) || stock.name.toLowerCase().includes(needle),
  );

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-4 border-b border-line pb-5">
        <div className="flex items-center gap-3">
          <Logo className="size-10 shrink-0" />
          <div>
            <p className="font-mono text-base font-semibold tracking-widest">BULL PIT</p>
            <p className="text-sm text-muted-foreground">{MOTTO}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <MarketBadge />
          <ConnectionBadge state={account} />
        </div>
      </header>
      <PageHeader
        title="Account & Wallet"
        subtitle="Three analysts study a stock, a bull and a bear argue, and you decide. Nothing trades without your approval."
      />
      <AccountCard state={account} />

      <form onSubmit={submit} noValidate className="space-y-3">
        <label htmlFor="ticker" className="text-sm text-muted-foreground">
          Research a stock
        </label>
        <div className="flex gap-3">
          <input
            id="ticker"
            value={ticker}
            onChange={(event) => setTicker(event.target.value)}
            disabled={busy}
            autoComplete="off"
            spellCheck={false}
            placeholder="AAPL"
            aria-invalid={message !== undefined}
            aria-describedby="ticker-message"
            className="num h-14 min-w-0 flex-1 rounded-lg border border-line bg-surface px-4 text-3xl font-semibold uppercase tracking-wider outline-none placeholder:text-muted-foreground/40 focus-visible:border-amber aria-invalid:border-bear"
          />
          <Button ref={startButton} type="submit" size="lg" disabled={busy || !symbol} className="h-14 px-6">
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : <ArrowRight aria-hidden />}
            {checking ? "Checking" : "Start"}
          </Button>
        </div>
        <p id="ticker-message" role="alert" className="min-h-5 text-sm text-bear">
          {message}
        </p>
        <p className="text-sm text-muted-foreground">
          A request takes about a minute. You can also press <span className="num">Ctrl K</span> anywhere.
        </p>
      </form>

      {watchlist.loading && <LoadingPanel rows={4} label="Loading the watchlist" />}
      {watchlist.error && <ErrorPanel error={watchlist.error} retry={watchlist.reload} />}
      {watchlist.data && (
        <>
          <section aria-label="Liked stocks">
            <h2 className="mb-3 text-sm font-medium text-muted-foreground">Liked stocks</h2>
            {liked.length === 0 ? (
              <EmptyPanel text="No liked stocks yet. Press the star next to a stock in the watchlist to keep it here." />
            ) : (
              <ul className="flex flex-wrap gap-2">
                {liked.map((stock) => (
                  <li key={stock.symbol} className="flex items-center rounded-lg border border-line bg-surface pl-3">
                    <button
                      type="button"
                      onClick={() => select(stock)}
                      title={stock.name}
                      className="num py-1.5 text-sm font-semibold outline-none hover:text-amber focus-visible:underline"
                    >
                      {stock.symbol}
                    </button>
                    <StarButton stock={stock} onToggle={toggle} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-label="Watchlist">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-sm font-medium text-muted-foreground">Watchlist</h2>
              <input
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                aria-label="Filter the watchlist"
                placeholder="Filter by name or symbol"
                autoComplete="off"
                className="h-8 w-56 rounded-md border border-line bg-surface px-3 text-sm outline-none placeholder:text-muted-foreground/60 focus-visible:border-amber"
              />
            </div>
            {matches.length === 0 ? (
              <EmptyPanel text="No stock matches that filter." />
            ) : (
              <ul className="max-h-96 divide-y divide-line overflow-y-auto rounded-lg border border-line bg-surface">
                {matches.map((stock) => (
                  <li key={stock.symbol} className="flex items-center pr-2 hover:bg-surface-2">
                    <button
                      type="button"
                      onClick={() => select(stock)}
                      className="flex min-w-0 flex-1 items-center gap-4 px-4 py-2.5 text-left text-sm outline-none focus-visible:underline"
                    >
                      <span className="num w-16 shrink-0 font-semibold">{stock.symbol}</span>
                      <span className="truncate text-muted-foreground">{stock.name}</span>
                    </button>
                    <StarButton stock={stock} onToggle={toggle} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
