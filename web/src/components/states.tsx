import { AlertTriangle } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/** Page title with an optional line under it and actions on the right. */
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

/** Skeleton rows shaped like the content they stand in for, so nothing jumps. */
export function LoadingPanel({ rows = 4, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-2">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  );
}

/** The API's own message, with a way to try again. */
export function ErrorPanel({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-lg border border-bear/40 bg-bear/5 p-4 text-sm"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-bear" aria-hidden />
      <div className="flex-1">
        <p className="font-medium text-bear">Something went wrong</p>
        <p className="mt-1 text-muted-foreground">{error.message}</p>
      </div>
      {retry && (
        <Button variant="outline" size="sm" onClick={retry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** One sentence and one action; no illustration. */
export function EmptyPanel({
  text,
  action,
}: {
  text: string;
  action?: { label: string; href: string };
}) {
  return (
    <div className="rounded-lg border border-dashed border-line p-8 text-center text-sm">
      <p className="text-muted-foreground">{text}</p>
      {action && (
        <Button asChild variant="outline" size="sm" className="mt-3">
          <Link href={action.href}>{action.label}</Link>
        </Button>
      )}
    </div>
  );
}
