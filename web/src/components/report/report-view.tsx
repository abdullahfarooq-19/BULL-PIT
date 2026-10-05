"use client";

import { motion } from "motion/react";

import type { Report } from "@/api/client";
import { AnalystSection } from "@/components/report/analyst-section";
import { DebateSection } from "@/components/report/debate-section";
import { EvidenceText, evidenceFacts } from "@/components/report/evidence-text";
import { dateTime, money, num, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

const OUTCOME = {
  buy: { label: "Buy", style: "border-bull/50 bg-bull/10 text-bull" },
  no_trade: { label: "No trade", style: "border-line bg-surface-2 text-neutral-signal" },
  rejected: { label: "Rejected", style: "border-bear/50 bg-bear/10 text-bear" },
} as const;

/** A titled block that rises into place once, staggered by its position. */
function Section({ title, index, children }: { title: string; index: number; children: React.ReactNode }) {
  return (
    <motion.section
      aria-label={title}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut", delay: index * 0.05 }}
      className="rounded-xl border border-line bg-surface p-6"
    >
      <h2 className="mb-4 text-xs font-medium uppercase tracking-wider text-muted-foreground">{title}</h2>
      {children}
    </motion.section>
  );
}

/** The report's sections in the order of architecture sec7, minus the order and the
 *  actions, which live in the sticky panel beside it. Sections that don't apply are
 *  `null` on the report and are skipped (M5-FR-1). */
export function ReportView({ report }: { report: Report }) {
  const facts = evidenceFacts(report.signals);
  const outcome = OUTCOME[report.outcome];
  let index = 0;
  const next = () => index++;

  return (
    <div className="space-y-4">
      <header>
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
          <h1 className="num text-5xl font-bold tracking-tight">{report.ticker}</h1>
          {report.company_name && <span className="text-lg text-muted-foreground">{report.company_name}</span>}
          <span className={cn("rounded-md border px-2.5 py-1 text-sm font-medium", outcome.style)}>
            {outcome.label}
          </span>
        </div>
        <p className="num mt-2 text-xs text-muted-foreground">
          Price data through {report.as_of} · {report.mode} mode · {dateTime(report.generated_at)} · {report.request_id}
        </p>
      </header>

      <Section title="Recommendation" index={next()}>
        {report.confidence != null && (
          <div className="mb-3 flex items-center gap-3">
            <span className="text-sm text-muted-foreground">Confidence</span>
            <div className="h-1.5 w-32 overflow-hidden rounded-full bg-surface-2" aria-hidden>
              <div className="h-full bg-amber" style={{ width: `${report.confidence * 100}%` }} />
            </div>
            <span className="num text-sm font-medium">{num(report.confidence)}</span>
          </div>
        )}
        {report.summary && (
          <p className="leading-relaxed">
            <EvidenceText text={report.summary} facts={facts} />
          </p>
        )}
        {report.reason && report.outcome !== "rejected" && (
          <p className="mt-3 text-sm text-muted-foreground">
            {report.reason}
            {report.reason_detail && <> &ldquo;{report.reason_detail}&rdquo;</>}
          </p>
        )}
        {report.outcome === "rejected" && report.reason && (
          <p className="text-sm text-bear">{report.reason}</p>
        )}
      </Section>

      {report.signals.length > 0 && (
        <Section title="What the analysts found" index={next()}>
          <AnalystSection report={report} facts={facts} />
        </Section>
      )}

      {report.debate && (
        <Section title="The debate" index={next()}>
          <DebateSection report={report} debate={report.debate} facts={facts} />
        </Section>
      )}

      {report.attempts.length > 0 && (
        <Section title="Risk manager" index={next()}>
          {report.loss_warning && (
            <p role="alert" className="mb-4 rounded-lg border border-bear/50 bg-bear/10 p-3 text-sm text-bear">
              Loss warning: the account fell more than the limit recently. Approving needs an extra confirmation.
            </p>
          )}
          {report.order && <Limits order={report.order} />}
          <ol className="mt-4 space-y-2 text-sm">
            {report.attempts.map((a) => (
              <li key={a.number} className="rounded-lg border border-line bg-surface-2 p-3">
                <span className="font-medium">
                  Attempt <span className="num">{a.number}</span>: {a.action === "buy" ? "Buy" : "No trade"}
                </span>
                <span className="text-muted-foreground">
                  {a.action === "buy" && ` · ${pct(Number(a.target_weight) * 100)} target · ${a.exit_style} exits`}
                  {` · confidence ${num(a.confidence)}`}
                </span>
                {a.blocked_reason && <p className="mt-1 text-bear">Blocked: {a.blocked_reason}</p>}
                {a.shares != null && !a.blocked_reason && (
                  <p className="mt-1 text-muted-foreground">Sized at <span className="num">{a.shares}</span> shares.</p>
                )}
                {a.review_decision && (
                  <p className="mt-1 text-muted-foreground">
                    Review: <span className="font-medium text-foreground">{a.review_decision}</span>
                    {a.review_clamped ? " (clamped)" : ""}
                    {a.review_reason && <> &ldquo;{a.review_reason}&rdquo;</>}
                  </p>
                )}
              </li>
            ))}
          </ol>
          {report.loss_warning == null && (
            <p className="mt-3 text-xs text-muted-foreground">Loss warning: not available (no equity history yet).</p>
          )}
        </Section>
      )}

      {report.would_change_view && (
        <Section title="What would change the view" index={next()}>
          <p>{report.would_change_view}</p>
        </Section>
      )}

      {report.market && (
        <Section title="Market context" index={next()}>
          <ul className="mb-2 space-y-1 text-sm">
            <li>
              <span className="text-muted-foreground">SPY: </span>
              {report.market.spy_above == null || report.market.spy_close == null || report.market.spy_sma_200 == null ? (
                "200-day average not available"
              ) : (
                <span className="num">
                  {money(report.market.spy_close)} is {report.market.spy_above ? "above" : "below"} its 200-day
                  average of {money(report.market.spy_sma_200)}
                </span>
              )}
            </li>
            <li>
              <span className="text-muted-foreground">VIX: </span>
              <span className="num">
                {report.market.vix_close == null ? "not available" : `${num(report.market.vix_close)}, ${report.market.vix_label}`}
              </span>
            </li>
          </ul>
          <p className="text-sm text-muted-foreground">{report.market.explanation}</p>
        </Section>
      )}

      <Section title="Data notes" index={next()}>
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
          {report.outcome !== "rejected" && (
            <>
              <dt className="text-muted-foreground">Models used</dt>
              <dd className="num">{report.data_notes.models.join(", ") || "none"}</dd>
              <dt className="text-muted-foreground">News headlines</dt>
              <dd className="num">{report.data_notes.news_headlines ?? "not available"}</dd>
              <dt className="text-muted-foreground">Latest filing</dt>
              <dd className="num">
                {report.data_notes.filing_form
                  ? `${report.data_notes.filing_form}, filed ${report.data_notes.filing_date}`
                  : "not available"}
              </dd>
              <dt className="text-muted-foreground">Price source</dt>
              <dd className="num">{report.data_notes.price_source ?? "not available"}</dd>
            </>
          )}
          <dt className="text-muted-foreground">Warnings</dt>
          <dd>
            {report.data_notes.warnings.length === 0 ? (
              "none"
            ) : (
              <ul className="list-disc pl-4 text-amber">
                {report.data_notes.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
          </dd>
        </dl>
      </Section>

      <p className="pt-2 text-center text-xs text-muted-foreground">
        Research, not financial advice. Paper trading only.
      </p>
    </div>
  );
}

/** The four share limits; the one that set the size is outlined (architecture Part 11). */
function Limits({ order }: { order: NonNullable<Report["order"]> }) {
  const shrunk = order.shares < order.limit_shares[order.limit];
  return (
    <div>
      <div className="grid grid-cols-4 gap-2">
        {(["target", "risk", "cap", "cash"] as const).map((name) => (
          <div
            key={name}
            className={cn(
              "rounded-lg border p-3 text-center",
              name === order.limit && !shrunk ? "border-amber" : "border-line",
            )}
          >
            <div className="text-xs capitalize text-muted-foreground">{name}</div>
            <div className="num text-lg font-semibold">{order.limit_shares[name]}</div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        The smallest limit sets the size: <span className="capitalize">{order.limit}</span>
        {shrunk && <>; the risk review then shrank it to <span className="num">{order.shares}</span> shares</>}.
      </p>
    </div>
  );
}
