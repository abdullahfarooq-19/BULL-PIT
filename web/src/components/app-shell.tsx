"use client";

import { ChartPie, Command as CommandIcon, History, Loader2, Wallet } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { useFillCheck } from "@/components/fill-check";
import { Logo } from "@/components/logo";
import { Palette } from "@/components/palette";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";

const NAV = [
  { label: "Account & Wallet", href: "/", icon: Wallet },
  { label: "Trades History", href: "/trades", icon: History },
  { label: "Portfolio", href: "/portfolio", icon: ChartPie },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

/** The fill check's state, in words: the owner should know when the journal was last synced. */
function FillCheckStatus() {
  const { status, message, run } = useFillCheck();
  if (status === "running") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground" role="status">
        <Loader2 className="size-3 animate-spin" aria-hidden /> Checking fills
      </span>
    );
  }
  if (status === "error") {
    return (
      <Button variant="ghost" size="xs" onClick={() => void run()} title={message}>
        Fill check failed. Retry
      </Button>
    );
  }
  return <span className="text-xs text-muted-foreground">Fills up to date</span>;
}

/** Sidebar, header and the command palette around every page (dev-plan C10: one theme). */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [paletteOpen, setPaletteOpen] = useState(false);

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader className="px-3 py-4">
          <Link href="/" aria-label="Bull Pit" className="flex items-center gap-2 font-mono text-sm font-semibold tracking-widest">
            <Logo className="size-6 shrink-0" />
            <span className="group-data-[collapsible=icon]:hidden">BULL PIT</span>
          </Link>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive(pathname, item.href)}
                      tooltip={item.label}
                    >
                      <Link href={item.href}>
                        <item.icon aria-hidden />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarRail />
      </Sidebar>
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-12 items-center gap-3 border-b border-line bg-background/95 px-4 backdrop-blur-sm">
          <SidebarTrigger aria-label="Toggle the sidebar" />
          <div className="ml-auto flex items-center gap-4">
            <FillCheckStatus />
            <Button variant="outline" size="sm" onClick={() => setPaletteOpen(true)}>
              <CommandIcon aria-hidden /> <span className="num">Ctrl K</span>
            </Button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">{children}</main>
      </SidebarInset>
      <Palette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </SidebarProvider>
  );
}
