import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

const STEPS = [
  { stage: "checking", label: "Check" },
  { stage: "analysts", label: "Analysts" },
  { stage: "debate", label: "Debate" },
  { stage: "trader", label: "Trader" },
  { stage: "risk", label: "Risk" },
  { stage: "report", label: "Report" },
];

/** Where a running request is; the debate step shows its round. */
export function ProgressTimeline({ stage, debateRound }: { stage: string; debateRound: number | null }) {
  const current = Math.max(
    0,
    STEPS.findIndex((step) => step.stage === stage),
  );
  return (
    <ol aria-label="Progress" className="flex flex-wrap items-center gap-x-2 gap-y-3">
      {STEPS.map((step, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <li
            key={step.stage}
            aria-current={active ? "step" : undefined}
            className={cn("flex items-center gap-2 text-sm", !done && !active && "text-muted-foreground")}
          >
            <span
              className={cn(
                "flex size-5 items-center justify-center rounded-full border text-[10px]",
                done && "border-bull bg-bull/15 text-bull",
                active && "animate-pulse border-amber bg-amber/15 text-amber",
                !done && !active && "border-line",
              )}
              aria-hidden
            >
              {done ? <Check className="size-3" /> : index + 1}
            </span>
            {step.label}
            {active && step.stage === "debate" && debateRound != null && (
              <span className="num text-xs text-muted-foreground">round {debateRound}</span>
            )}
            {index < STEPS.length - 1 && <span className="mx-1 h-px w-6 bg-line" aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}
