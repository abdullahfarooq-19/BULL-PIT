"use client";

import { MotionConfig } from "motion/react";

import { FillCheckProvider } from "@/components/fill-check";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

/** Reduced motion is honoured everywhere: animations become instant. */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider>
        <FillCheckProvider>{children}</FillCheckProvider>
        <Toaster position="bottom-right" />
      </TooltipProvider>
    </MotionConfig>
  );
}
