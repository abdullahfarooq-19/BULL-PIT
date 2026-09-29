"use client";

import type { Order } from "@/api/client";
import { AnimatedMoney } from "@/components/report/animated-money";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { money, moneyFromCents, signedPct, toCents } from "@/lib/format";

const HEIGHT = 240;

/** The bracket order drawn to proportion: take-profit on top, the reference price in
 *  the middle, the stop at the bottom. The bull zone and the bear zone are as tall as
 *  the reward and the risk, so the 1.5 reward-to-risk is visible. The ladder never moves
 *  when the share count changes; only the dollar figures do. */
export function BracketLadder({ order, shares }: { order: Order; shares: number }) {
  const reference = toCents(order.reference_price);
  const stop = toCents(order.stop_loss);
  const target = toCents(order.take_profit);
  const rewardShare = ((target - reference) / (target - stop)) * 100;
  const gain = (target - reference) * shares;
  const loss = (reference - stop) * shares;

  return (
    <figure
      className="space-y-2"
      aria-label={`Bracket order: take-profit ${money(order.take_profit)}, reference ${money(order.reference_price)}, stop-loss ${money(order.stop_loss)}`}
    >
      <div className="flex flex-col overflow-hidden rounded-lg border border-line" style={{ height: HEIGHT }}>
        <Zone
          tone="bull"
          height={`${rewardShare}%`}
          title="Take-profit"
          price={order.take_profit}
          perShare={target - reference}
          fromReference={(target - reference) / reference}
          tip={<>Maximum gain at {shares} shares: <AnimatedMoney cents={gain} /></>}
        />
        <div className="flex items-center justify-between border-y border-dashed border-muted-foreground/50 bg-surface-2 px-3 py-1 text-xs">
          <span className="text-muted-foreground">Reference</span>
          <span className="num font-medium">{money(order.reference_price)}</span>
        </div>
        <Zone
          tone="bear"
          height={`${100 - rewardShare}%`}
          title="Stop-loss"
          price={order.stop_loss}
          perShare={stop - reference}
          fromReference={(stop - reference) / reference}
          tip={<>Maximum loss at {shares} shares: <AnimatedMoney cents={loss} /></>}
        />
      </div>
      <figcaption className="grid grid-cols-2 gap-3 text-sm">
        <span className="text-bull">
          Gain <span className="font-medium"><AnimatedMoney cents={gain} /></span>
        </span>
        <span className="text-right text-bear">
          Loss <span className="font-medium"><AnimatedMoney cents={loss} /></span>
        </span>
      </figcaption>
    </figure>
  );
}

function Zone({
  tone,
  height,
  title,
  price,
  perShare,
  fromReference,
  tip,
}: {
  tone: "bull" | "bear";
  height: string;
  title: string;
  price: string;
  perShare: number;
  fromReference: number;
  tip: React.ReactNode;
}) {
  const style =
    tone === "bull" ? "bg-bull/15 text-bull" : "bg-bear/15 text-bear";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          tabIndex={0}
          style={{ flexBasis: height }}
          className={`flex min-h-0 flex-col justify-between px-3 py-2 text-xs ${style}`}
        >
          <div className="flex items-baseline justify-between">
            <span>{title}</span>
            <span className="num text-sm font-semibold">{money(price)}</span>
          </div>
          <div className="num text-right opacity-90">
            {perShare >= 0 ? "+" : "-"}
            {moneyFromCents(Math.abs(perShare))} per share · {signedPct(fromReference)}
          </div>
        </div>
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  );
}
