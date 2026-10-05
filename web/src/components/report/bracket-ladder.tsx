"use client";

import { AnimatedMoney } from "@/components/report/animated-money";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { money, moneyFromCents, signedPct, toCents } from "@/lib/format";

const HEIGHT = 240;

/** The bracket order drawn to proportion: take-profit on top, the entry price in the
 *  middle, the stop at the bottom. The bull zone and the bear zone are as tall as the
 *  reward and the risk, so the reward-to-risk is visible. It draws the numbers the API
 *  priced (M11.1-FR-10); the gain and loss are the API's totals for the chosen size. */
export function BracketLadder({
  entry,
  entryLabel,
  stop,
  target,
  gain,
  loss,
}: {
  entry: string;
  entryLabel: string;
  stop: string;
  target: string;
  gain: string | null;
  loss: string | null;
}) {
  const reference = toCents(entry);
  const stopCents = toCents(stop);
  const targetCents = toCents(target);
  const rewardShare = ((targetCents - reference) / (targetCents - stopCents)) * 100;

  return (
    <figure
      className="space-y-2"
      aria-label={`Bracket order: take-profit ${money(target)}, ${entryLabel.toLowerCase()} ${money(entry)}, stop-loss ${money(stop)}`}
    >
      <div className="flex flex-col overflow-hidden rounded-lg border border-line" style={{ height: HEIGHT }}>
        <Zone
          tone="bull"
          height={`${rewardShare}%`}
          title="Take-profit"
          price={target}
          perShare={targetCents - reference}
          fromReference={(targetCents - reference) / reference}
          tip={gain ? <>Maximum gain: <AnimatedMoney cents={toCents(gain)} /></> : "Waiting for a price"}
        />
        <div className="flex items-center justify-between border-y border-dashed border-muted-foreground/50 bg-surface-2 px-3 py-1 text-xs">
          <span className="text-muted-foreground">{entryLabel}</span>
          <span className="num font-medium">{money(entry)}</span>
        </div>
        <Zone
          tone="bear"
          height={`${100 - rewardShare}%`}
          title="Stop-loss"
          price={stop}
          perShare={stopCents - reference}
          fromReference={(stopCents - reference) / reference}
          tip={loss ? <>Maximum loss: <AnimatedMoney cents={toCents(loss)} /></> : "Waiting for a price"}
        />
      </div>
      <figcaption className="grid grid-cols-2 gap-3 text-sm">
        <span className="text-bull">
          Gain <span className="num font-medium">{gain ? money(gain) : "—"}</span>
        </span>
        <span className="text-right text-bear">
          Loss <span className="num font-medium">{loss ? money(loss) : "—"}</span>
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
