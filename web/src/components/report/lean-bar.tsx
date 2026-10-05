"use client";

import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/utils";

/** One bar for every signal (M11.1-FR-9): a track with a fixed centre tick. A bearish
 *  lean fills left in the bear colour, a bullish one fills right in the bull colour,
 *  and the fill's length is the confidence. A neutral reading is a grey marker on the
 *  tick; a flagged analyst is an amber "could not run" state, never a neutral one.
 *  `lean` runs from -1 to +1 and `label` is what a screen reader hears. */
export function LeanBar({
  lean,
  text,
  label,
  flagged = false,
}: {
  lean: number;
  text: string;
  label: string;
  flagged?: boolean;
}) {
  const reduced = useReducedMotion();
  const neutral = lean === 0;
  const tone = flagged ? "text-amber" : neutral ? "text-neutral-signal" : lean > 0 ? "text-bull" : "text-bear";
  return (
    <div className="flex items-center gap-3">
      <div
        role="img"
        aria-label={label}
        className={cn(
          "relative h-2 w-44 shrink-0 rounded-full bg-background",
          flagged && "border border-dashed border-amber/60 bg-transparent",
        )}
      >
        {!flagged && !neutral && (
          <motion.div
            className={cn(
              "absolute inset-y-0",
              lean > 0 ? "left-1/2 rounded-r-full bg-bull" : "right-1/2 rounded-l-full bg-bear",
            )}
            initial={{ width: reduced ? `${Math.abs(lean) * 50}%` : 0 }}
            animate={{ width: `${Math.abs(lean) * 50}%` }}
            transition={{ duration: reduced ? 0 : 0.25, ease: "easeOut" }}
          />
        )}
        <span aria-hidden className="absolute -inset-y-0.5 left-1/2 w-px bg-muted-foreground" />
        {!flagged && neutral && (
          <span
            aria-hidden
            className="absolute left-1/2 top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-neutral-signal"
          />
        )}
      </div>
      <span className={cn("num text-sm font-medium", tone)}>{text}</span>
    </div>
  );
}
