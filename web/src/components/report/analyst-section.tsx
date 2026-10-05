"use client";

import { useState } from "react";

import type { Report } from "@/api/client";
import { EvidenceText } from "@/components/report/evidence-text";
import { LeanBar } from "@/components/report/lean-bar";
import { num, signed } from "@/lib/format";
import { cn } from "@/lib/utils";

type Signal = Report["signals"][number];

const ORDER = ["technical", "fundamentals", "sentiment"];
const FACTS_SHOWN = 6;

const DIRECTION = {
  bullish: { label: "Bullish", sign: 1, badge: "border-bull/40 bg-bull/10 text-bull" },
  bearish: { label: "Bearish", sign: -1, badge: "border-bear/40 bg-bear/10 text-bear" },
  neutral: { label: "Neutral", sign: 0, badge: "border-line bg-surface text-neutral-signal" },
} as const;

/** What each analyst found (M11.1-FR-1, FR-2): its reading as a lean bar, a plain-language
 *  paragraph, then every fact. A flagged analyst says it could not run, and its facts, if
 *  any, are still listed. The overall bar shows the signals board's score. */
export function AnalystSection({ report, facts }: { report: Report; facts: Map<string, string> }) {
  const signals = ORDER.flatMap((name) => report.signals.filter((s) => s.analyst === name));
  const score = report.board_score;
  return (
    <div className="space-y-4">
      {score != null && (
        <div className="rounded-lg border border-line bg-surface-2 p-4">
          <h3 className="mb-2 text-sm font-semibold">All three together</h3>
          <LeanBar
            lean={score}
            text={`Board score ${signed(score)}`}
            label={`Signals board: score ${signed(score)} on a scale from -1 to +1`}
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Calculated by code from the three confidences, from -1 (all bearish) to +1 (all bullish).
          </p>
        </div>
      )}
      {signals.map((signal) => (
        <Analyst key={signal.analyst} signal={signal} summary={report.analyst_summaries?.[signal.analyst]} facts={facts} />
      ))}
      <p className="text-xs text-muted-foreground">
        Direction and confidence are the model&rsquo;s judgment of these facts, not a calculation.
      </p>
    </div>
  );
}

function Analyst({ signal, summary, facts }: { signal: Signal; summary?: string; facts: Map<string, string> }) {
  const direction = DIRECTION[signal.direction];
  const shown = `${direction.label} ${num(signal.confidence)}`;
  return (
    <article aria-label={`${signal.analyst} analyst`} className="rounded-lg border border-line bg-surface-2 p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold capitalize">{signal.analyst}</h3>
        {signal.flagged ? (
          <span className="rounded-md border border-amber/50 px-2 py-0.5 text-xs text-amber">Could not run</span>
        ) : (
          <span className={cn("rounded-md border px-2 py-0.5 text-xs font-medium", direction.badge)}>
            {direction.label}
          </span>
        )}
      </header>

      {signal.flagged ? (
        <p role="status" className="mt-3 text-sm text-amber">
          This analyst could not run{signal.note ? `: ${signal.note}` : "."}
        </p>
      ) : (
        <>
          <div className="mt-3">
            <LeanBar
              lean={direction.sign * signal.confidence}
              text={shown}
              label={`${signal.analyst}: ${signal.direction}, confidence ${num(signal.confidence)}`}
            />
          </div>
          {summary ? (
            <p className="mt-3 text-sm leading-relaxed">
              <EvidenceText text={summary} facts={facts} />
            </p>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">No written summary for this report; the facts are below.</p>
          )}
        </>
      )}

      <FactList evidence={signal.evidence} />
    </article>
  );
}

/** Every fact with its ID chip; a long list (headlines) shows the first few. */
function FactList({ evidence }: { evidence: Signal["evidence"] }) {
  const [all, setAll] = useState(false);
  if (evidence.length === 0) return null;
  const shown = all ? evidence : evidence.slice(0, FACTS_SHOWN);
  return (
    <div className="mt-4 border-t border-line pt-3">
      <ul className="space-y-1.5 text-sm text-muted-foreground">
        {shown.map((e) => (
          <li key={e.id} className="flex gap-2">
            <span className="num shrink-0 text-amber">{e.id}</span>
            <span>{e.fact}</span>
          </li>
        ))}
      </ul>
      {evidence.length > FACTS_SHOWN && (
        <button
          type="button"
          onClick={() => setAll(!all)}
          aria-expanded={all}
          className="mt-2 text-xs text-amber underline-offset-4 hover:underline"
        >
          {all ? "Show fewer" : `Show all ${evidence.length}`}
        </button>
      )}
    </div>
  );
}
