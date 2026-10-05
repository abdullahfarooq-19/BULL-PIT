"use client";

import { useState } from "react";
import { toast } from "sonner";

import { api, unwrap } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/** Cancel an order that is still waiting to fill (M11.1-FR-21), after a confirmation.
 *  If it filled as the cancel crossed, the API refuses and says to review the trade;
 *  either way `onDone` runs so the page shows what Alpaca now says. */
export function CancelOrderButton({
  requestId,
  onDone,
  className,
}: {
  requestId: string;
  onDone: () => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  const cancel = async () => {
    setOpen(false);
    try {
      await unwrap(api.POST("/trades/{request_id}/cancel", { params: { path: { request_id: requestId } } }));
      toast.success("Order cancelled");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not cancel the order.");
    }
    onDone();
  };

  return (
    <>
      <Button variant="outline" size="sm" className={className} onClick={() => setOpen(true)}>
        Cancel order
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel this order?</DialogTitle>
            <DialogDescription>
              Alpaca stops waiting for the price and the order is cancelled. If it has just filled, nothing is
              cancelled and the trade is shown as filled.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Keep it
            </Button>
            <Button onClick={() => void cancel()}>Cancel the order</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
