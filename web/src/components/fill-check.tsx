"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api, ApiError, unwrap } from "@/api/client";

type Status = "running" | "ok" | "error";

type FillCheckState = {
  status: Status;
  message?: string;
  /** Bumps after every completed check, so pages that show trades reload. */
  version: number;
  run: () => Promise<void>;
};

const FillCheckContext = createContext<FillCheckState | null>(null);

export function useFillCheck(): FillCheckState {
  const value = useContext(FillCheckContext);
  if (!value) throw new Error("useFillCheck needs a FillCheckProvider");
  return value;
}

/** Runs the fill check once when the dashboard opens (M8-FR-16) and on demand. */
export function FillCheckProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("running");
  const [message, setMessage] = useState<string>();
  const [version, setVersion] = useState(0);
  const started = useRef(false);

  const run = useCallback(async () => {
    setStatus("running");
    try {
      const result = await unwrap(api.POST("/fill-check"));
      setStatus("ok");
      setMessage(undefined);
      if (result.changed.length > 0) {
        toast.success(`${result.changed.length} trade(s) updated from Alpaca`);
      }
      result.warnings.forEach((warning) => toast.warning(warning));
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof ApiError ? error.message : "The fill check failed.");
    }
    setVersion((v) => v + 1);
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void run();
  }, [run]);

  return (
    <FillCheckContext.Provider value={{ status, message, version, run }}>
      {children}
    </FillCheckContext.Provider>
  );
}
