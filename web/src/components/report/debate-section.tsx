"use client";

import { useState } from "react";

import type { Report } from "@/api/client";
import { EvidenceText } from "@/components/report/evidence-text";
import { num } from "@/lib/format";
import { cn } from "@/lib/utils";

type Debate = NonNullable<Report["debate"]>;
type Turn = NonNullable<Report["debate_turns"]>[number];

const HEADING = "mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground";

/** The debate (M11.1-FR-4, FR-5): a plain-language paragraph per round and how it reached
 *  its conclusion, the two conviction bars, then every turn on request. A report from
 *  before M11.1 has no paragraphs or turns and says so in one line. */
export function DebateSection({
  report,
  debate,
  facts,
}: {
  report: Report;
  debate: Debate;
  facts: Map<string, string>;
}) {
  const narrative = report.debate_narrative;
  return (
    <>
      {narrative ? (
        <div className="mb-5 space-y-4">
          {narrative.rounds.map((paragraph, index) => (
            <div key={index}>
              <h3 className={HEADING}>Round {index + 1}</h3>
              <p className="text-sm leading-relaxed">
                <EvidenceText text={paragraph} facts={facts} />
              </p>
            </div>
          ))}
          <div>
            <h3 className={HEADING}>How it reached its conclusion</h3>
            <p className="text-sm leading-relaxed">
              <EvidenceText text={narrative.conclusion} facts={facts} />
            </p>
          </div>
        </div>
      ) : (
        <p className="mb-5 text-sm text-muted-foreground">
          This report has no plain-language account of the debate; the strongest points are below.
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Side tone="bull" title="Bull" text={debate.strongest_bull} conviction={debate.bull_conviction} facts={facts} />
        <Side tone="bear" title="Bear" text={debate.strongest_bear} conviction={debate.bear_conviction} facts={facts} />
      </div>
      <dl className="mt-4 space-y-2 text-sm">
        {debate.bull_conceded && (
          <div>
            <dt className="inline text-muted-foreground">The bull conceded: </dt>
            <dd className="inline italic">
              <EvidenceText text={debate.bull_conceded} facts={facts} />
            </dd>
          </div>
        )}
        {debate.unresolved && (
          <div>
            <dt className="inline text-muted-foreground">Unresolved: </dt>
            <dd className="inline">{debate.unresolved}</dd>
          </div>
        )}
        <div className="text-xs text-muted-foreground">
          Points without valid evidence: <span className="num">{debate.unsupported_points}</span>
        </div>
      </dl>

      {report.debate_turns && report.debate_turns.length > 0 && (
        <FullTurns turns={report.debate_turns} facts={facts} />
      )}
    </>
  );
}

function Side({
  tone,
  title,
  text,
  conviction,
  facts,
}: {
  tone: "bull" | "bear";
  title: string;
  text: string;
  conviction: number | null;
  facts: Map<string, string>;
}) {
  const colour = tone === "bull" ? "border-bull/40 text-bull" : "border-bear/40 text-bear";
  const bar = tone === "bull" ? "bg-bull" : "bg-bear";
  return (
    <div className={cn("rounded-lg border bg-surface-2 p-4", colour.split(" ")[0])}>
      <div className="mb-2 flex items-center justify-between">
        <h3 className={cn("text-sm font-semibold", colour.split(" ")[1])}>{title}</h3>
        <span className="num text-xs text-muted-foreground">
          conviction {conviction == null ? "n/a" : num(conviction)}
        </span>
      </div>
      <div className="mb-3 h-1 overflow-hidden rounded-full bg-background" aria-hidden>
        <div className={cn("h-full", bar)} style={{ width: `${(conviction ?? 0) * 100}%` }} />
      </div>
      <p className="text-sm leading-relaxed text-foreground">
        <EvidenceText text={text} facts={facts} />
      </p>
    </div>
  );
}

/** Every turn: its claims with their evidence chips, a claim without valid evidence struck
 *  through and tagged, concessions in italics, and the conviction. */
function FullTurns({ turns, facts }: { turns: Turn[]; facts: Map<string, string> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-5 border-t border-line pt-4">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="text-sm text-amber underline-offset-4 hover:underline"
      >
        {open ? "Hide the full turns" : `Show the full turns (${turns.length})`}
      </button>
      {open && (
        <ol className="mt-4 space-y-3">
          {turns.map((turn, index) => (
            <li
              key={index}
              className={cn(
                "rounded-lg border bg-surface-2 p-3 text-sm",
                turn.side === "bull" ? "border-bull/30" : "border-bear/30",
              )}
            >
              <div className="mb-2 flex items-center justify-between">
                <span className={cn("font-medium", turn.side === "bull" ? "text-bull" : "text-bear")}>
                  {turn.side === "bull" ? "Bull" : "Bear"} · round <span className="num">{turn.round}</span>
                </span>
                <span className="num text-xs text-muted-foreground">conviction {num(turn.conviction)}</span>
              </div>
              <ul className="space-y-1.5">
                {turn.claims.map((claim, i) => (
                  <li key={i}>
                    {claim.unsupported ? (
                      <>
                        <span className="text-muted-foreground line-through">{claim.text}</span>{" "}
                        <span className="rounded border border-bear/40 px-1 text-xs text-bear">unsupported</span>
                      </>
                    ) : (
                      <>
                        {claim.text} <EvidenceText text={claim.evidence_ids.join(" ")} facts={facts} />
                      </>
                    )}
                  </li>
                ))}
              </ul>
              {turn.concessions.length > 0 && (
                <ul className="mt-2 space-y-1 italic text-muted-foreground">
                  {turn.concessions.map((c, i) => (
                    <li key={i}>Concedes: {c}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
