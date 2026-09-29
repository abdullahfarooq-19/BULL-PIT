"use client";

import { useCallback, useEffect, useState } from "react";

type Loaded<T> = { key: string; data?: T; error?: Error };

/** Loads data for `key` (reloaded when it changes or `reload()` is called).
 *  `loading` is true until the first answer for the current key; an earlier
 *  answer for the same key stays on screen while a reload is in flight. */
export function useLoad<T>(key: string, load: () => Promise<T>) {
  const [state, setState] = useState<Loaded<T>>({ key: "" });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    load().then(
      (data) => live && setState({ key, data }),
      (error: Error) => live && setState({ key, error }),
    );
    return () => {
      live = false;
    };
    // `load` is a fresh closure every render; `key` and `tick` say when to reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const current = state.key === key;
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: !current,
    reload,
  };
}
