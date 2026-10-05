"use client";

import { useEffect, useState } from "react";

import { untilText } from "@/lib/format";
import { cn } from "@/lib/utils";

const TONES: Record<string, { dot: string; label: string }> = {
  // Trades History's one-label lifecycle (M11.2-FR-10); the keys are the API's `state`.
  analysing: { dot: "bg-amber animate-pulse", label: "Analysing" },
  decision_pending: { dot: "bg-amber", label: "Decision pending" },
  rejected_by_you: { dot: "bg-muted-foreground", label: "Rejected by you" },
  order_placed: { dot: "bg-amber", label: "Order placed" },
  waiting_at_limit: { dot: "bg-amber", label: "Waiting at limit" },
  no_decision: { dot: "bg-muted-foreground", label: "No decision" },
  no_trade: { dot: "bg-neutral-signal", label: "No trade" },
  rejected_by_check: { dot: "bg-bear", label: "Rejected by check" },
  running: { dot: "bg-amber animate-pulse", label: "Running" },
  awaiting_approval: { dot: "bg-amber", label: "Waiting for you" },
  completed: { dot: "bg-neutral-signal", label: "Completed" },
  rejected: { dot: "bg-bear", label: "Rejected" },
  failed: { dot: "bg-bear", label: "Failed" },
  expired: { dot: "bg-muted-foreground", label: "Expired" },
  pending: { dot: "bg-amber", label: "Pending" },
  open: { dot: "bg-bull", label: "Open" },
  closed: { dot: "bg-neutral-signal", label: "Closed" },
  cancelled: { dot: "bg-muted-foreground", label: "Cancelled" },
  open_at_end: { dot: "bg-bull", label: "Open at end" },
};

/** A small coloured dot and a word. Colour is never the only signal. */
export function StatusDot({ status }: { status: string }) {
  const tone = TONES[status] ?? { dot: "bg-muted-foreground", label: status };
  return (
    <span className="inline-flex items-center gap-2 text-sm">
      <span className={cn("size-2 rounded-full", tone.dot)} aria-hidden />
      {tone.label}
    </span>
  );
}

export function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

/** "Expires in 5 h 12 m" in amber, red in the last hour, muted once it has passed. */
export function ExpiryChip({ expiresAt }: { expiresAt: string }) {
  const now = useNow();
  const left = untilText(expiresAt, now);
  const tone = !left
    ? "border-line text-muted-foreground"
    : left.hours < 1
      ? "border-bear/50 text-bear"
      : "border-amber/50 text-amber";
  return (
    <span className={cn("num inline-flex rounded-md border px-2 py-0.5 text-xs", tone)}>
      {left ? `Expires in ${left.text}` : "Expired"}
    </span>
  );
}

/** The order type of an approved order, and an "Override" badge when the owner stepped
 *  outside the plan's rules (M11.1-FR-19). */
export function OrderBadges({ orderType, overrides }: { orderType?: string | null; overrides: string[] }) {
  return (
    <>
      {orderType === "limit" && (
        <span className="rounded border border-line px-1.5 py-0.5 text-xs text-muted-foreground">Limit</span>
      )}
      {overrides.length > 0 && (
        <span
          title={overrides.join(", ").replaceAll("_", " ")}
          className="rounded border border-bear/50 px-1.5 py-0.5 text-xs text-bear"
        >
          Override
        </span>
      )}
    </>
  );
}
