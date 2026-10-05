"use client";

import { ArrowRight, CandlestickChart, ChartPie, History, Wallet } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api, isTicker, startRequest, unwrap } from "@/api/client";
import {
  Command,
  CommandDialog,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useLoad } from "@/lib/use-load";

const PAGES = [
  { label: "Account & Wallet", href: "/", icon: Wallet },
  { label: "Trades History", href: "/trades", icon: History },
  { label: "Portfolio", href: "/portfolio", icon: ChartPie },
];

/** Ctrl+K: start a request for a typed ticker, or jump to a past request or a page. */
export function Palette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const recent = useLoad(open ? "open" : "closed", () =>
    open ? unwrap(api.GET("/requests", { params: { query: { limit: 8 } } })) : Promise.resolve([]),
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const ticker = query.trim().toUpperCase();
  const needle = query.trim().toLowerCase();
  const past = (recent.data ?? []).filter(
    (r) => !needle || r.ticker.toLowerCase().includes(needle) || r.id.toLowerCase().includes(needle),
  );

  const go = (href: string) => {
    onOpenChange(false);
    setQuery("");
    router.push(href);
  };

  const start = () => {
    onOpenChange(false);
    setQuery("");
    startRequest(ticker).then(
      (id) => router.push(`/requests/${id}`),
      (error: Error) => toast.error(error.message),
    );
  };

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Command palette"
      description="Start a request for a ticker or jump to a page or a past request."
    >
      <Command shouldFilter={false}>
        <CommandInput
          value={query}
          onValueChange={setQuery}
          placeholder="Type a ticker to research, or search past requests"
        />
        <CommandList>
          {isTicker(ticker) && (
            <CommandGroup heading="Research">
              <CommandItem value={`start-${ticker}`} onSelect={start}>
                <CandlestickChart aria-hidden />
                Start a request for <span className="num font-semibold">{ticker}</span>
                <ArrowRight className="ml-auto" aria-hidden />
              </CommandItem>
            </CommandGroup>
          )}
          {past.length > 0 && (
            <CommandGroup heading="Past requests">
              {past.map((r) => (
                <CommandItem key={r.id} value={r.id} onSelect={() => go(`/requests/${r.id}`)}>
                  <span className="num font-semibold">{r.ticker}</span>
                  <span className="num text-muted-foreground">{r.as_of}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{r.status.replace("_", " ")}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          <CommandGroup heading="Pages">
            {PAGES.filter((p) => !needle || p.label.toLowerCase().includes(needle)).map((p) => (
              <CommandItem key={p.href} value={p.href} onSelect={() => go(p.href)}>
                <p.icon aria-hidden />
                {p.label}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
