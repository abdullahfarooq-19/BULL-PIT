"use client";

import Link from "next/link";

import { api, unwrap } from "@/api/client";
import { EmptyPanel, ErrorPanel, LoadingPanel, PageHeader } from "@/components/states";
import { ExpiryChip, StatusDot } from "@/components/status";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { dateTime } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

/** Past live requests, newest first, each linking to its report (M8-FR-22). */
export default function HistoryPage() {
  const requests = useLoad("history", () => unwrap(api.GET("/requests", { params: { query: { limit: 200 } } })));

  return (
    <>
      <PageHeader title="History" subtitle="Every live request, newest first." />
      {requests.loading && <LoadingPanel rows={6} label="Loading requests" />}
      {requests.error && <ErrorPanel error={requests.error} retry={requests.reload} />}
      {requests.data?.length === 0 && (
        <EmptyPanel text="No requests yet. Start one to see it here." action={{ label: "New request", href: "/" }} />
      )}
      {requests.data && requests.data.length > 0 && (
        <Table>
          <TableHeader className="sticky top-12 bg-background">
            <TableRow>
              <TableHead>Ticker</TableHead>
              <TableHead>As of</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Outcome</TableHead>
              <TableHead>Decision</TableHead>
              <TableHead className="text-right">Expiry</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {requests.data.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="num font-semibold">
                  <Link href={`/requests/${r.id}`} className="underline-offset-4 hover:underline">
                    {r.ticker}
                  </Link>
                </TableCell>
                <TableCell className="num">{r.as_of}</TableCell>
                <TableCell className="num text-muted-foreground">{dateTime(r.created_at)}</TableCell>
                <TableCell>
                  <StatusDot status={r.status} />
                </TableCell>
                <TableCell className="capitalize">{r.outcome?.replace("_", " ") ?? "—"}</TableCell>
                <TableCell className="capitalize">{r.decision ?? "—"}</TableCell>
                <TableCell className="text-right">{r.expires_at && <ExpiryChip expiresAt={r.expires_at} />}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}
