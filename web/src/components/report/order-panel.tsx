"use client";

import { Minus, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { api, ApiError, startRequest, unwrap } from "@/api/client";
import type { OrderPreviewBody, Report, RequestDetail } from "@/api/client";
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
import { money, pct } from "@/lib/format";
import { useOrderPreview } from "@/lib/use-order-preview";
import { cn } from "@/lib/utils";

type Order = NonNullable<Report["order"]>;
type Mode = "market" | "limit";
type Confirmed = { stale: boolean; loss: boolean; overrides: boolean };
type Refusal = { code: string; message: string; maxShares?: number | null; overrides?: string[] | null };

const REFUSALS_TO_CONFIRM = [
  "stale",
  "loss_warning",
  "rules",
  "price_unavailable",
  "override_not_confirmed",
  "limit_invalid",
  "exits_invalid",
];

const OVERRIDE_LABEL: Record<string, string> = {
  custom_exits: "A stop-loss or take-profit you set yourself",
  size_above_plan: "More shares than Bull Pit recommended",
  above_cap: "More than the per-stock cap of the plan",
  above_risk_limit: "A maximum loss above the plan's risk limit",
};

const ADVANCED_WARNING = "You are overriding Bull Pit's risk rules. Losses can exceed the planned 1% of equity.";

/** The order box beside the report (M11.1-FR-10 to FR-21): the live price, buy now or at a
 *  price you set, and, off by default, your own stop, take-profit and size. Every number
 *  shown is the API's; the page does no order maths, and the API re-checks everything on
 *  approval, whatever this panel sends. */
export function OrderPanel({
  order,
  detail,
  onChanged,
}: {
  order: Order;
  detail: RequestDetail;
  onChanged: () => void;
}) {
  const router = useRouter();
  const waiting = detail.status === "awaiting_approval";
  const [mode, setMode] = useState<Mode>("market");
  const [limitText, setLimitText] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [shares, setShares] = useState(order.shares);
  const [sharesText, setSharesText] = useState(String(order.shares));
  const [stopText, setStopText] = useState("");
  const [targetText, setTargetText] = useState("");
  const [confirmed, setConfirmed] = useState<Confirmed>({ stale: false, loss: false, overrides: false });
  const [refusal, setRefusal] = useState<Refusal>();
  const [failure, setFailure] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const limitOk = Number(limitText) > 0;
  const body: OrderPreviewBody | null =
    waiting && (mode === "market" || limitOk)
      ? {
          order_type: mode,
          limit_price: mode === "limit" ? limitText : null,
          advanced,
          shares,
          stop_loss: advanced && stopText ? stopText : null,
          take_profit: advanced && targetText ? targetText : null,
        }
      : null;
  const { preview, error: previewError } = useOrderPreview(detail.id, waiting, body, onChanged);

  const entry = preview?.entry_price ?? order.reference_price;
  const stop = preview?.stop_loss ?? order.stop_loss;
  const target = preview?.take_profit ?? order.take_profit;
  const maxShares = preview?.max_shares ?? (advanced ? null : order.shares);
  const atMax = maxShares != null && shares >= maxShares;
  const canApprove = preview?.entry_price != null && !busy;

  const choose = (value: number) => {
    const floor = Math.max(1, value);
    const next = maxShares != null ? Math.min(maxShares, floor) : floor;
    setShares(next);
    setSharesText(String(next));
  };
  const switchMode = (next: Mode) => {
    setMode(next);
    setStopText("");
    setTargetText("");
  };
  const toggleAdvanced = (on: boolean) => {
    setAdvanced(on);
    setStopText("");
    setTargetText("");
    setConfirmed((flags) => ({ ...flags, overrides: false }));
  };

  const submit = async (decision: "approve" | "reject", flags: Confirmed = confirmed) => {
    setBusy(true);
    setFailure(undefined);
    try {
      await unwrap(
        api.POST("/requests/{request_id}/approval", {
          params: { path: { request_id: detail.id } },
          body:
            decision === "approve"
              ? {
                  decision,
                  shares,
                  confirm_stale: flags.stale,
                  confirm_loss_warning: flags.loss,
                  confirm_overrides: flags.overrides,
                  order_type: mode,
                  limit_price: mode === "limit" ? limitText : null,
                  seen_price: mode === "market" ? (preview?.entry_price ?? null) : null,
                  advanced,
                  stop_loss: advanced && stopText ? stopText : null,
                  take_profit: advanced && targetText ? targetText : null,
                }
              : {
                  decision,
                  confirm_stale: false,
                  confirm_loss_warning: false,
                  confirm_overrides: false,
                  order_type: "market",
                  advanced: false,
                },
        }),
      );
      toast.success(
        decision === "reject"
          ? "Report rejected"
          : mode === "limit"
            ? `Limit order placed: ${shares} ${order.ticker} at ${money(limitText)}`
            : `Order placed: ${shares} ${order.ticker}`,
      );
      onChanged();
    } catch (error) {
      if (!(error instanceof ApiError)) return setFailure("The decision could not be sent.");
      if (REFUSALS_TO_CONFIRM.includes(error.code)) {
        setRefusal({
          code: error.code,
          message: error.message,
          maxShares: error.details.max_shares,
          overrides: error.details.overrides,
        });
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
            confirm_overrides: false,
            order_type: "market",
            advanced: false,
          },
        }),
      );
      router.push(`/requests/${await startRequest(order.ticker)}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not re-run the request.");
      onChanged();
    }
  };

  const cancelOrder = async () => {
    setCancelling(false);
    try {
      await unwrap(
        api.POST("/trades/{request_id}/cancel", { params: { path: { request_id: detail.id } } }),
      );
      toast.success("Order cancelled");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not cancel the order.");
    }
    onChanged();
  };

  const sharesLabel = `${shares} ${shares === 1 ? "share" : "shares"}`;

  return (
    <aside aria-label="Order box" className="space-y-5 rounded-xl border border-line bg-surface p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Order box</h2>
        {waiting && detail.expires_at && <ExpiryChip expiresAt={detail.expires_at} />}
      </div>

      {waiting && (
        <div className="space-y-3">
          <div role="radiogroup" aria-label="How to buy" className="grid grid-cols-2 gap-1 rounded-lg bg-background p-1">
            {(
              [
                ["market", "Buy now"],
                ["limit", "Buy at a price"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={mode === value}
                onClick={() => switchMode(value)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm transition-colors",
                  mode === value ? "bg-surface-2 font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <PriceLine preview={preview} failed={previewError !== undefined} />
          {mode === "limit" && (
            <div>
              <label htmlFor="limit-price" className="mb-1.5 block text-sm text-muted-foreground">
                Limit price
              </label>
              <div className="flex items-center rounded-md border border-line bg-background focus-within:border-amber">
                <span className="pl-3 text-muted-foreground" aria-hidden>
                  $
                </span>
                <input
                  id="limit-price"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={limitText}
                  onChange={(event) => setLimitText(event.target.value.replace(/[^0-9.]/g, ""))}
                  className="num h-9 w-full min-w-0 bg-transparent px-2 text-lg outline-none"
                />
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                The order waits on Alpaca until the price reaches this, or you cancel it.
              </p>
            </div>
          )}
        </div>
      )}

      <BracketLadder
        entry={entry}
        entryLabel={mode === "limit" ? "Limit" : "Entry"}
        stop={stop}
        target={target}
        gain={preview?.max_gain ?? null}
        loss={preview?.max_loss ?? null}
      />

      <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-muted-foreground">Entry</dt>
        <dd className="num text-right">{money(entry)}</dd>
        <dt className="text-muted-foreground">Take-profit</dt>
        <dd className="num text-right">
          {waiting && advanced ? (
            <PriceInput label="Take-profit" value={targetText} shown={target} onChange={setTargetText} />
          ) : (
            money(target)
          )}
        </dd>
        <dt className="text-muted-foreground">Stop-loss</dt>
        <dd className="num text-right">
          {waiting && advanced ? (
            <PriceInput label="Stop-loss" value={stopText} shown={stop} onChange={setStopText} />
          ) : (
            money(stop)
          )}
        </dd>
        <dt className="text-muted-foreground">Exit style</dt>
        <dd className="text-right capitalize">{order.exit_style}</dd>
        {preview?.cost && (
          <>
            <dt className="text-muted-foreground">Order</dt>
            <dd className="num text-right">
              {preview.shares} {preview.shares === 1 ? "share" : "shares"} · {money(preview.cost)}
              {preview.pct_of_equity && (
                <span className="text-muted-foreground"> · {pct(preview.pct_of_equity)}</span>
              )}
            </dd>
            {preview.max_loss && preview.loss_pct_of_equity && (
              <>
                <dt className="text-muted-foreground">Maximum loss</dt>
                <dd className="num text-right">
                  {money(preview.max_loss)}
                  <span className="text-muted-foreground"> · {pct(preview.loss_pct_of_equity)} of equity</span>
                </dd>
              </>
            )}
          </>
        )}
      </dl>

      {waiting && (
        <div className="space-y-4 border-t border-line pt-5">
          <div>
            <label htmlFor="shares" className="mb-1.5 block text-sm text-muted-foreground">
              Shares{" "}
              {maxShares != null &&
                (advanced ? `(up to ${maxShares} for your cash)` : `(up to ${maxShares})`)}
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
                value={sharesText}
                disabled={busy}
                onChange={(event) => {
                  setSharesText(event.target.value);
                  const value = Number.parseInt(event.target.value, 10);
                  if (Number.isInteger(value)) choose(value);
                }}
                onBlur={() => setSharesText(String(shares))}
                className="num h-9 w-full min-w-0 rounded-md border border-line bg-background px-3 text-center text-lg outline-none focus-visible:border-amber"
              />
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={atMax ? 0 : -1}>
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label="One share more"
                      disabled={atMax || busy}
                      onClick={() => choose(shares + 1)}
                    >
                      <Plus aria-hidden />
                    </Button>
                  </span>
                </TooltipTrigger>
                {atMax && (
                  <TooltipContent>
                    {advanced ? "That is all your cash buys" : "Shares can only go down"}
                  </TooltipContent>
                )}
              </Tooltip>
            </div>
          </div>

          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={advanced}
              onChange={(event) => toggleAdvanced(event.target.checked)}
              className="mt-0.5 size-4 accent-amber"
            />
            <span>Edit stop, take-profit and size</span>
          </label>
          {advanced && (
            <div role="alert" className="space-y-1 rounded-lg border border-bear/50 bg-bear/10 p-3 text-sm text-bear">
              <p className="font-medium">{ADVANCED_WARNING}</p>
              <p className="text-xs text-muted-foreground">
                The report above refers to the original plan, not to these edits. Your cash is still the limit.
              </p>
            </div>
          )}

          {preview && preview.warnings.length > 0 && (
            <ul className="space-y-1 text-sm" aria-label="Warnings">
              {preview.warnings.map((warning) => (
                <li
                  key={warning.code}
                  className={warning.code.startsWith("above_") ? "text-bear" : "text-amber"}
                >
                  {warning.message}
                </li>
              ))}
            </ul>
          )}
          {failure && (
            <p role="alert" className="text-sm text-bear">
              {failure}
            </p>
          )}
          <HoldButton
            label={mode === "limit" ? `Place limit order, ${sharesLabel}` : `Approve ${sharesLabel}`}
            disabled={!canApprove || (mode === "limit" && !limitOk)}
            onComplete={() => void submit("approve")}
          />
          <Button variant="outline" className="w-full" disabled={busy} onClick={() => void submit("reject")}>
            Reject
          </Button>
        </div>
      )}

      {!waiting && <Outcome detail={detail} onCancel={() => setCancelling(true)} />}

      <Dialog open={cancelling} onOpenChange={setCancelling}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel this order?</DialogTitle>
            <DialogDescription>
              Alpaca stops waiting for the price and the order is cancelled. If it has just filled, nothing is
              cancelled and the trade is shown as filled.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelling(false)}>
              Keep it
            </Button>
            <Button onClick={() => void cancelOrder()}>Cancel the order</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={refusal !== undefined} onOpenChange={(open) => !open && setRefusal(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{refusalTitle(refusal?.code)}</DialogTitle>
            <DialogDescription>{refusal?.message}</DialogDescription>
          </DialogHeader>
          {refusal?.code === "override_not_confirmed" && (
            <div className="space-y-2 text-sm">
              <p className="text-bear">{ADVANCED_WARNING}</p>
              <ul className="list-disc space-y-1 pl-5">
                {(refusal.overrides ?? []).map((flag) => (
                  <li key={flag}>{OVERRIDE_LABEL[flag] ?? flag}</li>
                ))}
              </ul>
              {preview?.warnings
                .filter((warning) => warning.code.startsWith("above_"))
                .map((warning) => (
                  <p key={warning.code} className="text-bear">
                    {warning.message}
                  </p>
                ))}
            </div>
          )}
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
            {refusal?.code === "override_not_confirmed" && (
              <>
                <Button variant="outline" onClick={() => setRefusal(undefined)}>
                  Go back
                </Button>
                <Button onClick={() => confirm("overrides")}>I understand and approve</Button>
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
            {(refusal?.code === "price_unavailable" ||
              refusal?.code === "limit_invalid" ||
              refusal?.code === "exits_invalid") && <Button onClick={() => setRefusal(undefined)}>Close</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </aside>
  );
}

function PriceLine({
  preview,
  failed,
}: {
  preview: ReturnType<typeof useOrderPreview>["preview"];
  failed: boolean;
}) {
  if (!preview) {
    return <p className="text-sm text-muted-foreground">Reading the latest price…</p>;
  }
  return (
    <div className="space-y-0.5 text-sm" role="status">
      {preview.price ? (
        <p>
          <span className="text-muted-foreground">Last trade </span>
          <span className="num font-medium">{money(preview.price)}</span>
          <span className="num text-xs text-muted-foreground">
            {" "}
            (fetched {new Date(preview.fetched_at).toLocaleTimeString("en-GB")})
          </span>
        </p>
      ) : (
        <p className="text-amber">The latest price isn&rsquo;t available right now.</p>
      )}
      {failed && <p className="text-xs text-amber">Couldn&rsquo;t refresh just now; showing the last numbers.</p>}
    </div>
  );
}

/** An exit you may overwrite. Left blank it follows the live price, shown as the
 *  placeholder; typing a value fixes it. */
function PriceInput({
  label,
  value,
  shown,
  onChange,
}: {
  label: string;
  value: string;
  shown: string;
  onChange: (value: string) => void;
}) {
  return (
    <input
      aria-label={label}
      inputMode="decimal"
      placeholder={shown}
      value={value}
      onChange={(event) => onChange(event.target.value.replace(/[^0-9.]/g, ""))}
      className="num h-8 w-28 rounded-md border border-line bg-background px-2 text-right outline-none placeholder:text-foreground focus-visible:border-amber"
    />
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
    case "override_not_confirmed":
      return "You are overriding the rules";
    case "limit_invalid":
      return "Check the limit price";
    case "exits_invalid":
      return "Check the stop-loss and take-profit";
    default:
      return "Can't check the price";
  }
}

/** What happened to a report that is no longer waiting. A pending order can be cancelled. */
function Outcome({ detail, onCancel }: { detail: RequestDetail; onCancel: () => void }) {
  const { approval, trade } = detail;
  if (approval) {
    const limit = trade?.order_type === "limit" || approval.order_type === "limit";
    return (
      <div className="space-y-2 border-t border-line pt-5 text-sm" role="status">
        <p className="font-medium">
          {approval.decision === "approved"
            ? `You approved ${approval.approved_shares} of ${approval.recommended_shares} shares${limit ? ` at a limit of ${money(approval.limit_price ?? "0")}` : ""}`
            : "You rejected this report"}
        </p>
        {approval.overrides.length > 0 && (
          <p>
            <span className="rounded border border-bear/50 px-1.5 py-0.5 text-xs text-bear">Override</span>{" "}
            <span className="text-muted-foreground">
              {approval.overrides.map((flag) => OVERRIDE_LABEL[flag] ?? flag).join("; ")}
            </span>
          </p>
        )}
        {approval.confirmations.length > 0 && (
          <p className="text-muted-foreground">Confirmed: {approval.confirmations.join(", ").replace("_", " ")}</p>
        )}
        {trade && (
          <div className="flex items-center justify-between">
            <StatusDot status={trade.status} />
            <span className="num text-xs text-muted-foreground">{trade.order_id?.slice(0, 8)}</span>
          </div>
        )}
        {trade?.status === "pending" && (
          <Button variant="outline" className="w-full" onClick={onCancel}>
            Cancel order
          </Button>
        )}
      </div>
    );
  }
  if (detail.status === "expired") {
    return <p className="border-t border-line pt-5 text-sm text-muted-foreground">{detail.status_reason}</p>;
  }
  return null;
}
