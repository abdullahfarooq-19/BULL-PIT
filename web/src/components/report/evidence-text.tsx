"use client";

import type { Report } from "@/api/client";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const EVIDENCE_ID = /\b([A-Z]\d+)\b/g;

/** The evidence facts of a report, by ID (T1, F2, S3). */
export function evidenceFacts(signals: Report["signals"]): Map<string, string> {
  return new Map(signals.flatMap((s) => s.evidence.map((e) => [e.id, e.fact] as const)));
}

/** Text with each evidence ID it cites turned into a chip that shows the fact on hover
 *  or focus. An ID the report doesn't know stays plain text. */
export function EvidenceText({ text, facts }: { text: string; facts: Map<string, string> }) {
  const parts = text.split(EVIDENCE_ID);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 && facts.has(part) ? (
          <Tooltip key={index}>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="num mx-0.5 rounded border border-line bg-surface-2 px-1.5 text-xs text-amber hover:border-amber/60"
              >
                {part}
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">{facts.get(part)}</TooltipContent>
          </Tooltip>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}
