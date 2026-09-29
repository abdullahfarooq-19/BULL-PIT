"use client";

import { ArrowRight, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError, isTicker, startRequest, unwrap } from "@/api/client";
import { EmptyPanel, ErrorPanel, LoadingPanel, PageHeader } from "@/components/states";
import { StatusDot } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useLoad } from "@/lib/use-load";

const CHECK_POLL_MS = 1000;

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

export default function NewRequestPage() {
  const [ticker, setTicker] = useState("");
  const [message, setMessage] = useState<string>();
  const [starting, setStarting] = useState(false);
  const [checking, setChecking] = useState<string>();
  const recent = useLoad("recent", () => unwrap(api.GET("/requests", { params: { query: { limit: 5 } } })));

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

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="Research a stock"
        subtitle="Three analysts study it, a bull and a bear argue, and you decide. Nothing trades without your approval."
      />
      <form onSubmit={submit} noValidate className="space-y-3">
        <label htmlFor="ticker" className="text-sm text-muted-foreground">
          Ticker
        </label>
        <div className="flex gap-3">
          <input
            id="ticker"
            value={ticker}
            onChange={(event) => setTicker(event.target.value)}
            disabled={busy}
            autoFocus
            autoComplete="off"
            spellCheck={false}
            placeholder="AAPL"
            aria-invalid={message !== undefined}
            aria-describedby="ticker-message"
            className="num h-14 min-w-0 flex-1 rounded-lg border border-line bg-surface px-4 text-3xl font-semibold uppercase tracking-wider outline-none placeholder:text-muted-foreground/40 focus-visible:border-amber aria-invalid:border-bear"
          />
          <Button type="submit" size="lg" disabled={busy || !symbol} className="h-14 px-6">
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

      <h2 className="mb-3 mt-10 text-sm font-medium text-muted-foreground">Recent requests</h2>
      {recent.loading && <LoadingPanel rows={3} label="Loading recent requests" />}
      {recent.error && <ErrorPanel error={recent.error} retry={recent.reload} />}
      {recent.data?.length === 0 && <EmptyPanel text="No requests yet. Enter a ticker above." />}
      {recent.data && recent.data.length > 0 && (
        <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
          {recent.data.map((r) => (
            <li key={r.id}>
              <Link
                href={`/requests/${r.id}`}
                className="flex items-center gap-4 px-4 py-3 text-sm hover:bg-surface-2"
              >
                <span className="num w-16 font-semibold">{r.ticker}</span>
                <span className="num text-muted-foreground">{r.as_of}</span>
                <span className="ml-auto">
                  <StatusDot status={r.status} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
