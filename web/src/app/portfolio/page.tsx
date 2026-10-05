"use client";

import { api, unwrap } from "@/api/client";
import { EquityChart } from "@/components/equity-chart";
import { useFillCheck } from "@/components/fill-check";
import { ErrorPanel, LoadingPanel, PageHeader } from "@/components/states";
import { signedMoney } from "@/lib/format";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

function Stat({ label, value, tone }: { label: string; value: string; tone?: "bull" | "bear" }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className={cn("num mt-1 text-2xl font-semibold", tone === "bull" && "text-bull", tone === "bear" && "text-bear")}>
        {value}
      </p>
    </div>
  );
}

/** The equity chart and the realised statistics of the live journal (M11.2-FR-18 to FR-20).
 *  Reloads after every fill check. */
export default function PortfolioPage() {
  const fills = useFillCheck();
  const key = `portfolio-${fills.version}`;
  const stats = useLoad(key, () => unwrap(api.GET("/portfolio")));
  const equity = useLoad(key, () => unwrap(api.GET("/equity")));
  const trades = useLoad(key, () => unwrap(api.GET("/trades")));
  const error = stats.error ?? equity.error ?? trades.error;
  const retry = () => {
    stats.reload();
    equity.reload();
    trades.reload();
  };

  return (
    <>
      <PageHeader
        title="Portfolio"
        subtitle="Realised results of the trades you approved. Gains and losses on open positions are in the balance on Account & Wallet."
      />
      {error && <ErrorPanel error={error} retry={retry} />}
      {(stats.loading || equity.loading || trades.loading) && !error && (
        <LoadingPanel rows={5} label="Loading the portfolio" />
      )}
      {stats.data && equity.data && trades.data && (
        <div className="space-y-8">
          <EquityChart points={equity.data} trades={trades.data} />
          <section aria-label="Statistics" className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Approved trades" value={String(stats.data.approved)} />
            <Stat label="Rejected" value={String(stats.data.rejected)} />
            <Stat label="Ongoing trades" value={String(stats.data.ongoing)} />
            <Stat label="Closed trades" value={String(stats.data.closed)} />
            <Stat label="Total profit" value={signedMoney(stats.data.total_profit)} tone={Number(stats.data.total_profit) > 0 ? "bull" : undefined} />
            <Stat label="Total loss" value={signedMoney(stats.data.total_loss)} tone={Number(stats.data.total_loss) < 0 ? "bear" : undefined} />
            <Stat
              label="Net P&L"
              value={signedMoney(stats.data.net_pnl)}
              tone={Number(stats.data.net_pnl) === 0 ? undefined : Number(stats.data.net_pnl) > 0 ? "bull" : "bear"}
            />
          </section>
          <section className="space-y-3 border-t border-line pt-6">
            <h2 className="text-base font-semibold">About Bull Pit</h2>
            <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">
              Bull Pit is a research desk for one stock at a time. Three analysts study its price trend, its company
              filings and its news, then a bull and a bear argue the case. A trader and a risk manager turn the result
              into a sized order with a stop-loss and a take-profit. Code does every calculation, AI only judges and
              explains, and nothing trades until you approve it. Orders go to a paper account with simulated money.
            </p>
            <p className="max-w-3xl text-xs text-muted-foreground">
              AI can make mistakes. Bull Pit is a research tool, not financial advice. It trades simulated money on a
              paper account. Always check the numbers and the reasoning before you decide.
            </p>
          </section>
        </div>
      )}
    </>
  );
}
