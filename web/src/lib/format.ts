/** Number formats for the report, matching the CLI's (M5-FR-3): money `$5,824.00`,
 *  percentages to one decimal, other numbers to two. Prices arrive as decimal strings. */

const TWO = { minimumFractionDigits: 2, maximumFractionDigits: 2 } as const;

export function money(value: string | number): string {
  return `$${Number(value).toLocaleString("en-US", TWO)}`;
}

export function pct(value: string | number): string {
  return `${Number(value).toFixed(1)}%`;
}

export function num(value: number | null | undefined): string {
  return value == null ? "not available" : value.toLocaleString("en-US", TWO);
}

/** Exact cents from a two-decimal price string, so share maths never touches floats. */
export function toCents(price: string): number {
  return Math.round(Number(price) * 100);
}

export function moneyFromCents(cents: number): string {
  return money(cents / 100);
}

/** `+2.8%` from a signed fraction such as "0.028". */
export function signedPct(fraction: string | number): string {
  const value = Number(fraction) * 100;
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "5 h 12 m" until `iso`, or null once it has passed. */
export function untilText(iso: string, now: number): { text: string; hours: number } | null {
  const ms = new Date(iso).getTime() - now;
  if (ms <= 0) return null;
  const minutes = Math.floor(ms / 60_000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const text =
    days > 0 ? `${days} d ${hours} h` : hours > 0 ? `${hours} h ${minutes % 60} m` : `${minutes} m`;
  return { text, hours: ms / 3_600_000 };
}
