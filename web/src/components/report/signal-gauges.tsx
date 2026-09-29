"use client";

import { motion } from "motion/react";

import type { Report } from "@/api/client";
import { num } from "@/lib/format";

type Signal = Report["signals"][number];

const TONE = {
  bullish: { text: "text-bull", stroke: "var(--bull)", sign: 1 },
  bearish: { text: "text-bear", stroke: "var(--bear)", sign: -1 },
  neutral: { text: "text-neutral-signal", stroke: "var(--neutral-signal)", sign: 0 },
} as const;

const ANALYSTS = ["technical", "fundamentals", "sentiment"];
const CENTRE = 60;

/** Three half-dial gauges. The needle angle is direction x confidence, from -90 to +90
 *  degrees, in the direction's colour. With no signals yet they sit empty. */
export function SignalGauges({ signals }: { signals: Signal[] }) {
  return (
    <div className="grid grid-cols-3 gap-3">
      {ANALYSTS.map((name, index) => (
        <Gauge key={name} name={name} signal={signals.find((s) => s.analyst === name)} index={index} />
      ))}
    </div>
  );
}

function Gauge({ name, signal, index }: { name: string; signal?: Signal; index: number }) {
  const tone = signal ? TONE[signal.direction] : undefined;
  const angle = signal && tone ? tone.sign * signal.confidence * 90 : 0;
  return (
    <div className="rounded-lg border border-line bg-surface p-3 text-center">
      <svg viewBox="0 0 120 70" role="img" aria-label={gaugeLabel(name, signal)} className="mx-auto w-full max-w-40">
        <path d="M10 60 A50 50 0 0 1 110 60" fill="none" stroke="var(--line)" strokeWidth="6" strokeLinecap="round" />
        <line x1="60" y1="8" x2="60" y2="14" stroke="var(--muted)" strokeWidth="1.5" />
        {signal && tone && (
          <path
            d={arc(angle)}
            fill="none"
            stroke={tone.stroke}
            strokeWidth="6"
            strokeLinecap="round"
            opacity={0.35}
          />
        )}
        <motion.line
          x1={CENTRE}
          y1={CENTRE}
          x2={CENTRE}
          y2="16"
          stroke={tone?.stroke ?? "var(--muted)"}
          strokeWidth="2.5"
          strokeLinecap="round"
          style={{ transformOrigin: `${CENTRE}px ${CENTRE}px` }}
          initial={{ rotate: 0 }}
          animate={{ rotate: angle }}
          transition={{ duration: 0.25, delay: index * 0.12, ease: "easeOut" }}
        />
        <circle cx={CENTRE} cy={CENTRE} r="4" fill={tone?.stroke ?? "var(--muted)"} />
      </svg>
      <div className="mt-1 text-xs capitalize text-muted-foreground">{name}</div>
      <div className={`text-sm font-medium capitalize ${tone?.text ?? "text-muted-foreground"}`}>
        {signal ? signal.direction : "waiting"}
      </div>
      <div className="num text-xs text-muted-foreground">
        {signal ? num(signal.confidence) : "—"}
      </div>
    </div>
  );
}

function gaugeLabel(name: string, signal?: Signal): string {
  return signal
    ? `${name}: ${signal.direction}, confidence ${num(signal.confidence)}`
    : `${name}: not in yet`;
}

/** The arc from the top (neutral) to the needle, so the swing reads at a glance. */
function arc(angle: number): string {
  const radians = ((angle - 90) * Math.PI) / 180;
  const x = CENTRE + 50 * Math.cos(radians);
  const y = CENTRE + 50 * Math.sin(radians);
  const sweep = angle >= 0 ? 1 : 0;
  return `M60 10 A50 50 0 0 ${sweep} ${x.toFixed(2)} ${y.toFixed(2)}`;
}
