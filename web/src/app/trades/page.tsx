"use client";

import { Loader2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, unwrap } from "@/api/client";
import type { HistoryRow } from "@/api/client";
import { CancelOrderButton } from "@/components/cancel-order";
import { useFillCheck } from "@/components/fill-check";
import { EmptyPanel, ErrorPanel, LoadingPanel, PageHeader } from "@/components/states";
import { ExpiryChip, OrderBadges, StatusDot } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { dateTime, money, signedMoney } from "@/lib/format";
import { useLoad } from "@/lib/use-load";
import { usePolling } from "@/lib/use-polling";
import { cn } from "@/lib/utils";

const POLL_MS = 5000;

type State = HistoryRow["state"];

/** Filter chips (M11.2-FR-13): each is the set of states it shows. */
const FILTERS: { label: string; states: State[] | null }[] = [
  { label: "All", states: null },
  { label: "Decision pending", states: ["decision_pending"] },
  { label: "Ongoing", states: ["order_placed", "waiting_at_limit", "open"] },
  { label: "Closed", states: ["closed"] },
  { label: "Rejected", states: ["rejected_by_you", "rejected_by_check"] },
  { label: "No trade", states: ["no_trade"] },
  { label: "Failed", states: ["failed"] },
];

/** Rows still moving: the table keeps reading while one of these is on screen. */
const MOVING: State[] = ["analysing", "decision_pending", "order_placed", "waiting_at_limit", "open"];
/** Rows whose numbers are the report's plan, not an order: shown muted. */
const PLAN_ONLY: State[] = ["decision_pending", "rejected_by_you", "expired", "no_decision"];
/** Rows whose entry has not filled: the owner may cancel the order. */
const WAITING: State[] = ["order_placed", "waiting_at_limit"];

function Price({ value, muted }: { value: string | null; muted: boolean }) {
  if (value === null) return <>—</>;
  return <span className={cn(muted && "text-muted-foreground")}>{money(value)}</span>;
}

function Entry({ row }: { row: HistoryRow }) {
  if (row.entry_price !== null) return <>{money(row.entry_price)}</>;
  if (row.state === "waiting_at_limit" && row.limit_price !== null) {
    return <>waiting at {money(row.limit_price)}</>;
  }
  if (row.plan_price !== null) {
    return <span className="text-muted-foreground">plan {money(row.plan_price)}</span>;
  }
  return <>—</>;
}

/** Realised P&L for a closed trade; for an open one the unrealised P&L, marked live, with
 *  the price it is measured at (M11.3-FR-2). */
function Pnl({ row }: { row: HistoryRow }) {
  if (row.pnl !== null) return <>{signedMoney(row.pnl)}</>;
  if (row.state !== "open") return <>—</>;
  if (row.unrealised_pnl === null || row.current_price === null) {
    return <span title="The current price could not be read">—</span>;
  }
  return (
    <>
      {signedMoney(row.unrealised_pnl)} <span className="text-xs font-normal text-muted-foreground">live</span>
      <div className="text-xs font-normal text-muted-foreground">now {money(row.current_price)}</div>
    </>
  );
}

/** Every live analysis, from "analysing" to "closed" (M11.2-FR-9 to FR-16). Reloads after
 *  every fill check and every five seconds while a row is still moving. */
export default function TradesHistoryPage() {
  const fills = useFillCheck();
  const history = useLoad(`history-${fills.version}`, () => unwrap(api.GET("/history")));
  const [filter, setFilter] = useState(0);
  const rows = history.data;

  const { reload } = history;
  usePolling(reload, POLL_MS, rows?.some((row) => MOVING.includes(row.state)) ?? false);

  const shown = rows?.filter((row) => {
    const states = FILTERS[filter].states;
    return states === null || states.includes(row.state);
  });

  return (
    <>
      <PageHeader
        title="Trades History"
        subtitle="Every analysis you have run, from analysing to closed. Open one to read its full analysis."
        actions={
          <Button variant="outline" onClick={() => void fills.run()} disabled={fills.status === "running"}>
            {fills.status === "running" ? <Loader2 className="animate-spin" aria-hidden /> : <RefreshCw aria-hidden />}
            Check fills
          </Button>
        }
      />
      {history.loading && <LoadingPanel rows={6} label="Loading trades history" />}
      {history.error && <ErrorPanel error={history.error} retry={history.reload} />}
      {rows?.length === 0 && (
        <EmptyPanel text="No analyses yet. Pick a stock to start one." action={{ label: "Account & Wallet", href: "/" }} />
      )}
      {rows && shown && rows.length > 0 && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
            {FILTERS.map((chip, index) => {
              const count =
                chip.states === null ? rows.length : rows.filter((r) => chip.states?.includes(r.state)).length;
              return (
                <Button
                  key={chip.label}
                  size="sm"
                  variant={filter === index ? "secondary" : "outline"}
                  aria-pressed={filter === index}
                  onClick={() => setFilter(index)}
                >
                  {chip.label} <span className="num text-muted-foreground">{count}</span>
                </Button>
              );
            })}
          </div>
          {shown.length === 0 ? (
            <EmptyPanel text="Nothing here for this filter." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Ticker</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Shares</TableHead>
                  <TableHead className="text-right">Entry</TableHead>
                  <TableHead className="text-right">TP</TableHead>
                  <TableHead className="text-right">SL</TableHead>
                  <TableHead className="text-right">P&amp;L</TableHead>
                  <TableHead className="text-right">Exit</TableHead>
                  <TableHead className="text-right">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {shown.map((row) => {
                  const plan = PLAN_ONLY.includes(row.state);
                  return (
                    <TableRow key={row.id}>
                      <TableCell className="num text-muted-foreground">{dateTime(row.created_at)}</TableCell>
                      <TableCell className="num font-semibold">
                        <Link href={`/requests/${row.id}`} className="underline-offset-4 hover:underline">
                          {row.ticker}
                        </Link>
                      </TableCell>
                      <TableCell title={row.cancel_reason ?? row.status_reason ?? undefined}>
                        <StatusDot status={row.state} />
                        <span className="ml-2">
                          <OrderBadges orderType={row.order_type} overrides={row.overrides} />
                        </span>
                        {row.state === "decision_pending" && row.expires_at && (
                          <div className="mt-1">
                            <ExpiryChip expiresAt={row.expires_at} />
                          </div>
                        )}
                      </TableCell>
                      <TableCell className={cn("num text-right", plan && "text-muted-foreground")}>
                        {row.shares ?? "—"}
                      </TableCell>
                      <TableCell className="num text-right">
                        <Entry row={row} />
                      </TableCell>
                      <TableCell className="num text-right">
                        <Price value={row.take_profit} muted={plan} />
                      </TableCell>
                      <TableCell className="num text-right">
                        <Price value={row.stop_loss} muted={plan} />
                      </TableCell>
                      <TableCell
                        className={cn(
                          "num text-right",
                          (row.pnl ?? row.unrealised_pnl) !== null &&
                            (Number(row.pnl ?? row.unrealised_pnl) >= 0 ? "text-bull" : "text-bear"),
                        )}
                      >
                        <Pnl row={row} />
                      </TableCell>
                      <TableCell className="num text-right">
                        {row.exit_price !== null ? (
                          <>
                            {money(row.exit_price)}
                            <div className="text-xs capitalize text-muted-foreground">
                              {row.exit_date} {row.exit_reason}
                            </div>
                          </>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {WAITING.includes(row.state) && (
                          <CancelOrderButton requestId={row.id} onDone={history.reload} />
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </div>
      )}
    </>
  );
}
