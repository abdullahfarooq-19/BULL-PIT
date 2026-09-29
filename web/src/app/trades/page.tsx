"use client";

import { Loader2, RefreshCw } from "lucide-react";
import Link from "next/link";

import { api, unwrap } from "@/api/client";
import { EquityChart } from "@/components/equity-chart";
import { useFillCheck } from "@/components/fill-check";
import { EmptyPanel, ErrorPanel, LoadingPanel, PageHeader } from "@/components/states";
import { StatusDot } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { money } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

/** Live trades and the live equity chart (M8-FR-22). Reloads after every fill check. */
export default function TradesPage() {
  const fills = useFillCheck();
  const key = `trades-${fills.version}`;
  const trades = useLoad(key, () => unwrap(api.GET("/trades")));
  const equity = useLoad(key, () => unwrap(api.GET("/equity")));
  const error = trades.error ?? equity.error;

  return (
    <>
      <PageHeader
        title="Trades"
        subtitle="Live orders on the Alpaca paper account, as the fill check last recorded them."
        actions={
          <Button variant="outline" onClick={() => void fills.run()} disabled={fills.status === "running"}>
            {fills.status === "running" ? <Loader2 className="animate-spin" aria-hidden /> : <RefreshCw aria-hidden />}
            Check fills
          </Button>
        }
      />
      {error && <ErrorPanel error={error} retry={() => { trades.reload(); equity.reload(); }} />}
      {(trades.loading || equity.loading) && !error && <LoadingPanel rows={5} label="Loading trades" />}
      {trades.data && equity.data && (
        <div className="space-y-6">
          <EquityChart points={equity.data} trades={trades.data} />
          {trades.data.length === 0 ? (
            <EmptyPanel text="No trades yet. Start a request and approve a buy." action={{ label: "New request", href: "/" }} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ticker</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Shares</TableHead>
                  <TableHead className="text-right">Entry</TableHead>
                  <TableHead className="text-right">Exit</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead className="text-right">P&amp;L</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trades.data.map((t) => (
                  <TableRow key={t.client_order_id}>
                    <TableCell className="num font-semibold">
                      <Link href={`/requests/${t.request_id}`} className="underline-offset-4 hover:underline">
                        {t.ticker}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <StatusDot status={t.status} />
                    </TableCell>
                    <TableCell className="num text-right">{t.shares}</TableCell>
                    <TableCell className="num text-right">
                      {t.entry_price ? `${money(t.entry_price)} ${t.entry_date}` : "—"}
                    </TableCell>
                    <TableCell className="num text-right">
                      {t.exit_price ? `${money(t.exit_price)} ${t.exit_date}` : "—"}
                    </TableCell>
                    <TableCell className="capitalize">{t.exit_reason ?? t.cancel_reason ?? "—"}</TableCell>
                    <TableCell
                      className={`num text-right ${t.pnl ? (Number(t.pnl) >= 0 ? "text-bull" : "text-bear") : ""}`}
                    >
                      {t.pnl ? money(t.pnl) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}
    </>
  );
}
