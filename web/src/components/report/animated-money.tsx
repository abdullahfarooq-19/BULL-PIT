"use client";

import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { moneyFromCents } from "@/lib/format";

/** A dollar amount that counts to its new value (150-250 ms, ease-out); instant under
 *  reduced motion. Amounts are exact cents. */
export function AnimatedMoney({ cents }: { cents: number }) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(cents);
  const from = useRef(cents);

  useEffect(() => {
    const controls = animate(from.current, cents, {
      duration: reduced ? 0 : 0.2,
      ease: "easeOut",
      onUpdate: (value) => {
        from.current = value;
        setShown(value);
      },
    });
    return () => controls.stop();
  }, [cents, reduced]);

  return <span className="num">{moneyFromCents(Math.round(shown))}</span>;
}
