"use client";

import { useEffect, useRef } from "react";

/** Calls `tick` every `ms` while the tab is visible and `enabled`. It pauses while the tab
 *  is hidden and ticks once when the tab becomes visible again (M11.2-FR-3, FR-14). */
export function usePolling(tick: () => void, ms: number, enabled = true) {
  const latest = useRef(tick);
  useEffect(() => {
    latest.current = tick;
  });

  useEffect(() => {
    if (!enabled) return;
    let timer: ReturnType<typeof setInterval> | undefined;
    const start = () => {
      timer = setInterval(() => latest.current(), ms);
    };
    const stop = () => {
      if (timer !== undefined) clearInterval(timer);
      timer = undefined;
    };
    const onVisibility = () => {
      stop();
      if (!document.hidden) {
        latest.current();
        start();
      }
    };
    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [ms, enabled]);
}
