"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use, useEffect } from "react";

import { api, unwrap } from "@/api/client";
import { OrderPanel } from "@/components/report/order-panel";
import { ProgressTimeline } from "@/components/report/progress-timeline";
import { ReportView } from "@/components/report/report-view";
import { ErrorPanel, LoadingPanel } from "@/components/states";
import { StatusDot } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useLoad } from "@/lib/use-load";

const POLL_MS = 2000;

/** Report and decide (M8-FR-22): progress while the request runs, then the report and,
 *  for a buy that waits, the owner's decision. The link back is on every state (M11.2-FR-17). */
export default function RequestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link href="/trades">
          <ArrowLeft aria-hidden /> Trades History
        </Link>
      </Button>
      <RequestView id={id} />
    </div>
  );
}

function RequestView({ id }: { id: string }) {
  const detail = useLoad(`detail-${id}`, () =>
    unwrap(api.GET("/requests/{request_id}", { params: { path: { request_id: id } } })),
  );
  const status = detail.data?.status;
  const hasReport = status !== undefined && status !== "running" && status !== "failed";
  const report = useLoad(hasReport ? `report-${id}` : "none", () =>
    hasReport
      ? unwrap(api.GET("/requests/{request_id}/report", { params: { path: { request_id: id } } }))
      : Promise.resolve(undefined),
  );

  const { reload } = detail;
  useEffect(() => {
    if (status !== "running") return;
    const timer = setInterval(reload, POLL_MS);
    return () => clearInterval(timer);
  }, [status, reload]);

  if (detail.loading) return <LoadingPanel rows={6} label="Loading the request" />;
  if (detail.error || !detail.data) {
    return <ErrorPanel error={detail.error ?? new Error("No such request.")} retry={detail.reload} />;
  }
  const request = detail.data;

  if (request.status === "running") {
    return (
      <div className="space-y-8">
        <div className="flex items-baseline gap-4">
          <h1 className="num text-5xl font-bold tracking-tight">{request.ticker}</h1>
          <StatusDot status="running" />
        </div>
        <ProgressTimeline stage={request.stage} debateRound={request.debate_round} />
      </div>
    );
  }

  if (request.status === "failed") {
    return (
      <div className="space-y-4">
        <h1 className="num text-5xl font-bold tracking-tight">{request.ticker}</h1>
        <ErrorPanel error={new Error(request.status_reason ?? "The request failed.")} />
        <Button asChild variant="outline">
          <Link href="/">Start another request</Link>
        </Button>
      </div>
    );
  }

  if (report.loading) return <LoadingPanel rows={6} label="Loading the report" />;
  if (report.error || !report.data) {
    return <ErrorPanel error={report.error ?? new Error("No report yet.")} retry={report.reload} />;
  }
  const order = report.data.order;

  return (
    <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <ReportView report={report.data} />
      {order && (
        <div className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto lg:overscroll-contain">
          <OrderPanel order={order} detail={request} onChanged={detail.reload} />
        </div>
      )}
    </div>
  );
}
