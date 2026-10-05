"use client";

import { useEffect, useRef, useState } from "react";

import { api, ApiError, unwrap } from "@/api/client";
import type { OrderPreview, OrderPreviewBody } from "@/api/client";

const POLL_MS = 5000;
const DEBOUNCE_MS = 400;

/** The order the box would place, priced by the API (M11.1-FR-10). It asks on open,
 *  again whenever `body` changes (after a short pause in typing), and about every five
 *  seconds while the tab is visible and the request is waiting. A `null` body means the
 *  inputs aren't complete, so nothing is asked.
 *
 *  A read that couldn't price the order (no price) keeps the last priced numbers on screen
 *  and takes only the new warnings, so the box never shows an invented price. */
export function useOrderPreview(
  requestId: string,
  active: boolean,
  body: OrderPreviewBody | null,
  onNotWaiting: () => void,
) {
  const [latest, setLatest] = useState<OrderPreview>();
  const [lastPriced, setLastPriced] = useState<OrderPreview>();
  const [error, setError] = useState<Error>();
  const key = JSON.stringify(body);
  const notWaiting = useRef(onNotWaiting);
  useEffect(() => {
    notWaiting.current = onNotWaiting;
  });

  useEffect(() => {
    const current: OrderPreviewBody | null = JSON.parse(key);
    if (!active || current === null) return;
    let live = true;
    let timer: ReturnType<typeof setInterval> | undefined;

    const ask = async () => {
      try {
        const preview = await unwrap(
          api.POST("/requests/{request_id}/order-preview", {
            params: { path: { request_id: requestId } },
            body: current,
          }),
        );
        if (!live) return;
        setLatest(preview);
        setError(undefined);
        if (preview.entry_price !== null) setLastPriced(preview);
      } catch (failure) {
        if (!live) return;
        if (failure instanceof ApiError && failure.code === "not_awaiting") {
          notWaiting.current();
          return;
        }
        setError(failure instanceof Error ? failure : new Error("The preview failed."));
      }
    };

    const start = () => {
      void ask();
      timer = setInterval(() => void ask(), POLL_MS);
    };
    const stop = () => {
      if (timer !== undefined) clearInterval(timer);
      timer = undefined;
    };
    const onVisibility = () => {
      stop();
      if (!document.hidden) start();
    };

    const pause = setTimeout(() => !document.hidden && start(), DEBOUNCE_MS);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      live = false;
      clearTimeout(pause);
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [requestId, active, key]);

  const priced = latest && latest.entry_price !== null ? latest : undefined;
  const view =
    priced ?? (latest && lastPriced ? { ...lastPriced, warnings: latest.warnings } : latest);
  return { preview: view, error };
}
