"use client";

import { animate, motion, useMotionValue } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

const HOLD_MS = 1200; // the one irreversible action should feel deliberate (M8 sec9.6)

/** Press and hold to confirm: a ring fills for 1.2 s and letting go early cancels.
 *  Keyboard: hold Space or Enter for the same time. */
export function HoldButton({
  label,
  disabled,
  onComplete,
}: {
  label: string;
  disabled?: boolean;
  onComplete: () => void;
}) {
  const progress = useMotionValue(0);
  const running = useRef<ReturnType<typeof animate> | null>(null);
  const [holding, setHolding] = useState(false);

  const cancel = () => {
    if (!running.current) return;
    running.current.stop();
    running.current = null;
    setHolding(false);
    animate(progress, 0, { duration: 0.15, ease: "easeOut" });
  };

  const start = () => {
    if (disabled || running.current) return;
    setHolding(true);
    running.current = animate(progress, 1, {
      duration: HOLD_MS / 1000,
      ease: "linear",
      onComplete: () => {
        running.current = null;
        setHolding(false);
        progress.set(0);
        onComplete();
      },
    });
  };

  useEffect(() => () => running.current?.stop(), []);

  return (
    <div>
      <button
        type="button"
        disabled={disabled}
        aria-describedby="hold-hint"
        onPointerDown={(event) => {
          if (event.button === 0) start();
        }}
        onPointerUp={cancel}
        onPointerLeave={cancel}
        onPointerCancel={cancel}
        onBlur={cancel}
        onContextMenu={(event) => event.preventDefault()}
        onKeyDown={(event) => {
          if ((event.key === " " || event.key === "Enter") && !event.repeat) {
            event.preventDefault();
            start();
          }
        }}
        onKeyUp={(event) => {
          if (event.key === " " || event.key === "Enter") cancel();
        }}
        className={cn(
          "relative flex h-12 w-full touch-none items-center justify-center gap-3 rounded-lg bg-amber px-4 font-semibold text-background select-none",
          "transition-transform active:scale-[0.99] disabled:opacity-50",
        )}
      >
        <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
          <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
          <motion.circle
            cx="12"
            cy="12"
            r="10"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            style={{ pathLength: progress, rotate: -90, transformOrigin: "12px 12px" }}
          />
        </svg>
        {label}
      </button>
      <p id="hold-hint" className="mt-1.5 text-center text-xs text-muted-foreground" aria-live="polite">
        {holding ? "Keep holding, release to cancel" : "Press and hold for 1.2 seconds"}
      </p>
    </div>
  );
}
