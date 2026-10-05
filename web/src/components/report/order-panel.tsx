"use client";

import { Minus, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { api, ApiError, startRequest, unwrap } from "@/api/client";
import type { Report, RequestDetail } from "@/api/client";
import { AnimatedMoney } from "@/components/report/animated-money";
import { BracketLadder } from "@/components/report/bracket-ladder";
import { HoldButton } from "@/components/report/hold-button";
import { StatusDot, ExpiryChip } from "@/components/status";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { money, pct, toCents } from "@/lib/format";

type Order = NonNullable<Report["order"]>;
type Confirmed = { stale: boolean; loss: boolean };
type Refusal = { code: string; message: string; maxShares?: number | null };

const REFUSALS_TO_CONFIRM = ["stale", "loss_warning", "rules", "price_unavailable"];

/** The suggested order beside the report: the bracket ladder, the numbers, and, while the
 *  report waits, the owner's controls (M8-FR-22). Shares can only go down; every check
 *  is made again by the API, whatever this panel sends. */
export function OrderPanel({
  report,
  order,
  detail,
  onChanged,
}: {
  report: Report;
  order: Order;
  detail: RequestDetail;
  onChanged: () => void;
}) {
  const router = useRouter();
  const waiting = detail.status === "awaiting_approval";
  const decided = detail.approval;
  const [shares, setShares] = useState(order.shares);
  const [text, setText] = useState(String(order.shares));
  const [confirmed, setConfirmed] = useState<Confirmed>({ stale: false, loss: false });
  const [refusal, setRefusal] = useState<Refusal>();
  const [failure, setFailure] = useState<string>();
  const [busy, setBusy] = useState(false);

  const shown = decided ? decided.approved_shares || decided.recommended_shares : shares;
  const cost = toCents(order.reference_price) * shown;
  const equityPct = report.order_pct_of_equity == null ? null : (Number(report.order_pct_of_equity) * shown) / order.shares;

  const choose = (value: number) => {
    const clamped = Math.min(order.shares, Math.max(1, value));
    setShares(clamped);
    setText(String(clamped));
  };

  const submit = async (decision: "approve" | "reject", flags: Confirmed = confirmed) => {
    setBusy(true);
    setFailure(undefined);
    try {
      await unwrap(
        api.POST("/requests/{request_id}/approval", {
          params: { path: { request_id: detail.id } },
          body: {
            decision,
            shares: decision === "approve" ? shares : null,
            confirm_stale: flags.stale,
            confirm_loss_warning: flags.loss,
            order_type: "market",
            seen_price: decision === "approve" ? order.reference_price : null,
            advanced: false,
            confirm_overrides: false,
          },
        }),
      );
      toast.success(decision === "approve" ? `Order placed: ${shares} ${order.ticker}` : "Report rejected");
      onChanged();
    } catch (error) {
      if (!(error instanceof ApiError)) return setFailure("The decision could not be sent.");
      if (REFUSALS_TO_CONFIRM.includes(error.code)) {
        setRefusal({ code: error.code, message: error.message, maxShares: error.details.max_shares });
      } else if (error.code === "expired" || error.code === "not_awaiting") {
        toast.error(error.message);
        onChanged();
      } else {
        setFailure(error.message);
        if (error.code === "broker_rejected") onChanged();
      }
    } finally {
      setBusy(false);
    }
  };

  const confirm = (kind: keyof Confirmed) => {
    const flags = { ...confirmed, [kind]: true };
    setConfirmed(flags);
    setRefusal(undefined);
    void submit("approve", flags);
  };

  const rerun = async () => {
    setRefusal(undefined);
    try {
      await unwrap(
        api.POST("/requests/{request_id}/approval", {
          params: { path: { request_id: detail.id } },
          body: {
            decision: "reject",
            confirm_stale: false,
            confirm_loss_warning: false,
            order_type: "market",
            advanced: false,
            confirm_overrides: false,
          },
        }),
      );
      router.push(`/requests/${await startRequest(order.ticker)}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not re-run the request.");
      onChanged();
    }
  };

  return (
    <aside aria-label="Suggested order" className="space-y-5 rounded-xl border border-line bg-surface p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Suggested order</h2>
        {waiting && detail.expires_at && <ExpiryChip expiresAt={detail.expires_at} />}
      </div>

      <BracketLadder order={order} shares={shown} />

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-muted-foreground">Order</dt>
        <dd className="num text-right">
          {shown} shares · <AnimatedMoney cents={cost} />
          {equityPct != null && <span className="text-muted-foreground"> · {pct(equityPct)}</span>}
        </dd>
        <dt className="text-muted-foreground">Stop-loss</dt>
        <dd className="num text-right">{money(order.stop_loss)}</dd>
        <dt className="text-muted-foreground">Take-profit</dt>
        <dd className="num text-right">{money(order.take_profit)}</dd>
        <dt className="text-muted-foreground">Exit style</dt>
        <dd className="text-right capitalize">{order.exit_style}</dd>
      </dl>

      {waiting && (
        <div className="space-y-4 border-t border-line pt-5">
          <div>
            <label htmlFor="shares" className="mb-1.5 block text-sm text-muted-foreground">
              Shares (up to {order.shares})
            </label>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="icon"
                aria-label="One share fewer"
                disabled={shares <= 1 || busy}
                onClick={() => choose(shares - 1)}
              >
                <Minus aria-hidden />
              </Button>
              <input
                id="shares"
                inputMode="numeric"
                value={text}
                disabled={busy}
                onChange={(event) => {
                  setText(event.target.value);
                  const value = Number.parseInt(event.target.value, 10);
                  if (Number.isInteger(value)) setShares(Math.min(order.shares, Math.max(1, value)));
                }}
                onBlur={() => setText(String(shares))}
                className="num h-9 w-full min-w-0 rounded-md border border-line bg-background px-3 text-center text-lg outline-none focus-visible:border-amber"
              />
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={shares >= order.shares ? 0 : -1}>
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label="One share more"
                      disabled={shares >= order.shares || busy}
                      onClick={() => choose(shares + 1)}
                    >
                      <Plus aria-hidden />
                    </Button>
                  </span>
                </TooltipTrigger>
                {shares >= order.shares && <TooltipContent>Shares can only go down</TooltipContent>}
              </Tooltip>
            </div>
          </div>

          {failure && (
            <p role="alert" className="text-sm text-bear">
              {failure}
            </p>
          )}
          <HoldButton
            label={`Approve ${shares} ${shares === 1 ? "share" : "shares"}`}
            disabled={busy}
            onComplete={() => void submit("approve")}
          />
          <Button variant="outline" className="w-full" disabled={busy} onClick={() => void submit("reject")}>
            Reject
          </Button>
        </div>
      )}

      {!waiting && <Outcome detail={detail} />}

      <Dialog open={refusal !== undefined} onOpenChange={(open) => !open && setRefusal(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{refusalTitle(refusal?.code)}</DialogTitle>
            <DialogDescription>{refusal?.message}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            {refusal?.code === "stale" && (
              <>
                <Button variant="outline" onClick={() => void rerun()}>
                  Re-run
                </Button>
                <Button onClick={() => confirm("stale")}>Confirm and approve</Button>
              </>
            )}
            {refusal?.code === "loss_warning" && (
              <>
                <Button
                  variant="outline"
                  onClick={() => {
                    setRefusal(undefined);
                    void submit("reject");
                  }}
                >
                  Reject
                </Button>
                <Button onClick={() => confirm("loss")}>Confirm and approve</Button>
              </>
            )}
            {refusal?.code === "rules" && (
              <>
                <Button variant="outline" onClick={() => setRefusal(undefined)}>
                  Close
                </Button>
                {refusal.maxShares ? (
                  <Button
                    onClick={() => {
                      choose(refusal.maxShares ?? 1);
                      setRefusal(undefined);
                    }}
                  >
                    Use {refusal.maxShares} {refusal.maxShares === 1 ? "share" : "shares"}
                  </Button>
                ) : null}
              </>
            )}
            {refusal?.code === "price_unavailable" && (
              <Button onClick={() => setRefusal(undefined)}>Close</Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </aside>
  );
}

function refusalTitle(code?: string): string {
  switch (code) {
    case "stale":
      return "The price moved";
    case "loss_warning":
      return "Loss warning";
    case "rules":
      return "The order no longer fits";
    default:
      return "Can't check the price";
  }
}

/** What happened to a report that is no longer waiting. */
function Outcome({ detail }: { detail: RequestDetail }) {
  const { approval, trade } = detail;
  if (approval) {
    return (
      <div className="space-y-2 border-t border-line pt-5 text-sm" role="status">
        <p className="font-medium">
          {approval.decision === "approved"
            ? `You approved ${approval.approved_shares} of ${approval.recommended_shares} shares`
            : "You rejected this report"}
        </p>
        {approval.confirmations.length > 0 && (
          <p className="text-muted-foreground">Confirmed: {approval.confirmations.join(", ").replace("_", " ")}</p>
        )}
        {trade && (
          <div className="flex items-center justify-between">
            <StatusDot status={trade.status} />
            <span className="num text-xs text-muted-foreground">{trade.order_id?.slice(0, 8)}</span>
          </div>
        )}
      </div>
    );
  }
  if (detail.status === "expired") {
    return <p className="border-t border-line pt-5 text-sm text-muted-foreground">{detail.status_reason}</p>;
  }
  return null;
}
