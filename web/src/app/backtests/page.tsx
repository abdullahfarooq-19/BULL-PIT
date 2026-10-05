"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, unwrap } from "@/api/client";
import { EmptyPanel, ErrorPanel, LoadingPanel, PageHeader } from "@/components/states";
import { StatusDot } from "@/components/status";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { money } from "@/lib/format";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

/** Backtest runs from the journal and M7's results page as it is: the numbers and the
 *  three charts are made once, by `bullpit eval`, and only shown here (dev-plan C6). */
export default function BacktestsPage() {
  const runs = useLoad("runs", () => unwrap(api.GET("/backtests")));
  const results = useLoad("results", async () => {
    try {
      return await unwrap(api.GET("/results"));
    } catch (error) {
      if (error instanceof Error && "code" in error && error.code === "not_found") return null;
      throw error;
    }
  });
  const [open, setOpen] = useState<string>();

  return (
    <>
      <PageHeader title="Backtests" subtitle="Simulated runs and the evaluation. Start them from the command line." />

      <h2 className="mb-3 text-sm font-medium text-muted-foreground">Runs</h2>
      {runs.loading && <LoadingPanel rows={3} label="Loading runs" />}
      {runs.error && <ErrorPanel error={runs.error} retry={runs.reload} />}
      {runs.data?.length === 0 && <EmptyPanel text="No backtest runs yet. Run `bullpit backtest` first." />}
      {runs.data && runs.data.length > 0 && (
        <div className="divide-y divide-line rounded-lg border border-line bg-surface">
          {runs.data.map((run) => (
            <div key={run.id}>
              <button
                type="button"
                aria-expanded={open === run.id}
                onClick={() => setOpen(open === run.id ? undefined : run.id)}
                className="flex w-full items-center gap-4 px-4 py-3 text-left text-sm hover:bg-surface-2"
              >
                <ChevronRight className={cn("size-4 transition-transform", open === run.id && "rotate-90")} aria-hidden />
                <span className="num font-semibold">{run.id}</span>
                <span className="capitalize text-muted-foreground">{run.policy.replace("_", " ")}</span>
                <span className="num text-muted-foreground">{run.tickers.join(", ")}</span>
                <span className="num hidden text-muted-foreground md:inline">
                  {run.start_date} to {run.end_date}
                </span>
                <span className="ml-auto flex items-center gap-4">
                  <span className="num">{run.last_equity ? money(run.last_equity) : "—"}</span>
                  <StatusDot status={run.status} />
                </span>
              </button>
              {open === run.id && <RunTrades id={run.id} />}
            </div>
          ))}
        </div>
      )}

      <h2 className="mb-3 mt-10 text-sm font-medium text-muted-foreground">Evaluation results</h2>
      {results.loading && <LoadingPanel rows={4} label="Loading results" />}
      {results.error && <ErrorPanel error={results.error} retry={results.reload} />}
      {results.data === null && <EmptyPanel text="No results page yet. Run `bullpit eval` to write one." />}
      {results.data && (
        <article className="space-y-4 rounded-xl border border-line bg-surface p-6 text-sm leading-relaxed">
          <Markdown remarkPlugins={[remarkGfm]} components={MARKDOWN}>
            {results.data.markdown}
          </Markdown>
        </article>
      )}
    </>
  );
}

function RunTrades({ id }: { id: string }) {
  const detail = useLoad(`run-${id}`, () =>
    unwrap(api.GET("/backtests/{run_id}/results", { params: { path: { run_id: id } } })),
  );
  return (
    <div className="border-t border-line bg-background p-4">
      {detail.loading && <LoadingPanel rows={2} label="Loading trades" />}
      {detail.error && <ErrorPanel error={detail.error} retry={detail.reload} />}
      {detail.data?.trades.length === 0 && <p className="text-sm text-muted-foreground">This run entered no trades.</p>}
      {detail.data && detail.data.trades.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ticker</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Shares</TableHead>
              <TableHead className="text-right">Entry</TableHead>
              <TableHead className="text-right">Exit</TableHead>
              <TableHead className="text-right">P&amp;L</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {detail.data.trades.map((t) => (
              <TableRow key={t.client_order_id}>
                <TableCell className="num font-semibold">{t.ticker}</TableCell>
                <TableCell>
                  <StatusDot status={t.status} />
                </TableCell>
                <TableCell className="num text-right">{t.shares}</TableCell>
                <TableCell className="num text-right">{t.entry_price ? money(t.entry_price) : "—"}</TableCell>
                <TableCell className="num text-right">{t.exit_price ? money(t.exit_price) : "—"}</TableCell>
                <TableCell className="num text-right">{t.pnl ? money(t.pnl) : "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

/** M7's Markdown in the app's typography; its charts are served by the API. */
const MARKDOWN = {
  h1: (p: React.ComponentProps<"h1">) => <h1 className="text-lg font-semibold" {...p} />,
  h2: (p: React.ComponentProps<"h2">) => <h2 className="pt-2 text-base font-semibold" {...p} />,
  ul: (p: React.ComponentProps<"ul">) => <ul className="list-disc space-y-1 pl-5" {...p} />,
  table: (p: React.ComponentProps<"table">) => (
    <div className="overflow-x-auto">
      <Table {...p} />
    </div>
  ),
  thead: (p: React.ComponentProps<"thead">) => <TableHeader {...p} />,
  tbody: (p: React.ComponentProps<"tbody">) => <TableBody {...p} />,
  tr: (p: React.ComponentProps<"tr">) => <TableRow {...p} />,
  th: (p: React.ComponentProps<"th">) => <TableHead className="whitespace-nowrap" {...p} />,
  td: (p: React.ComponentProps<"td">) => <TableCell className="num" {...p} />,
  img: ({ src, alt }: React.ComponentProps<"img">) => (
    // eslint-disable-next-line @next/next/no-img-element -- served by the API, sized by the file
    <img
      src={`/api/results/files/${String(src).split("/").pop()}`}
      alt={alt ?? ""}
      className="max-w-full rounded-lg border border-line"
    />
  ),
  code: (p: React.ComponentProps<"code">) => <code className="num rounded bg-surface-2 px-1" {...p} />,
};
