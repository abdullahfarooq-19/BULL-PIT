"use client";

import {
  AreaSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  LineStyle,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import type { Schemas, TradeOut } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { money } from "@/lib/format";

type Point = Schemas["EquityPoint"];

// The chart is a canvas, so it can't read CSS variables: the section 9.6 tokens as values.
const COLOURS = {
  bull: "#2bd4a4",
  bear: "#ff5c6c",
  muted: "#8a93a0",
  line: "#232830",
};

function markers(trades: TradeOut[], days: Set<string>): SeriesMarker<Time>[] {
  const found: SeriesMarker<Time>[] = [];
  for (const trade of trades) {
    if (trade.entry_date && days.has(trade.entry_date)) {
      found.push({
        time: trade.entry_date,
        position: "belowBar",
        shape: "arrowUp",
        color: COLOURS.bull,
        text: trade.ticker,
      });
    }
    if (trade.exit_date && days.has(trade.exit_date)) {
      found.push({
        time: trade.exit_date,
        position: "aboveBar",
        shape: "arrowDown",
        color: Number(trade.pnl ?? 0) >= 0 ? COLOURS.bull : COLOURS.bear,
        text: trade.pnl ? `${trade.ticker} ${money(trade.pnl)}` : trade.ticker,
      });
    }
  }
  return found.sort((a, b) => String(a.time).localeCompare(String(b.time)));
}

/** Live account equity (TradingView Lightweight Charts, M8 D-M8-22): pan, zoom, crosshair,
 *  and markers at trade entries and exits. A canvas is invisible to screen readers, so a
 *  one-line summary and a table view carry the same numbers (C11). */
export function EquityChart({ points, trades }: { points: Point[]; trades: TradeOut[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [legend, setLegend] = useState<string>();
  const [asTable, setAsTable] = useState(false);

  useEffect(() => {
    const element = container.current;
    if (!element || points.length === 0 || asTable) return;
    const chart = createChart(element, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: COLOURS.muted,
        fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
      },
      grid: {
        vertLines: { color: "rgba(35, 40, 48, 0.4)" },
        horzLines: { color: "rgba(35, 40, 48, 0.4)" },
      },
      rightPriceScale: { borderColor: COLOURS.line },
      timeScale: { borderColor: COLOURS.line },
      crosshair: { horzLine: { labelBackgroundColor: COLOURS.line }, vertLine: { labelBackgroundColor: COLOURS.line } },
    });
    const series = chart.addSeries(AreaSeries, {
      lineColor: COLOURS.bull,
      topColor: "rgba(43, 212, 164, 0.25)",
      bottomColor: "rgba(43, 212, 164, 0)",
      lineWidth: 2,
      priceLineVisible: false,
    });
    series.setData(points.map((p) => ({ time: p.date, value: Number(p.equity) })));
    series.createPriceLine({
      price: Number(points[0].equity),
      color: COLOURS.muted,
      lineStyle: LineStyle.Dotted,
      lineWidth: 1,
      axisLabelVisible: false,
    });
    createSeriesMarkers(series, markers(trades, new Set(points.map((p) => p.date))));
    chart.timeScale().fitContent();

    chart.subscribeCrosshairMove((param) => {
      const value = param.seriesData.get(series);
      if (param.time && value && "value" in value) setLegend(`${param.time}  ${money(value.value)}`);
      else setLegend(undefined);
    });
    return () => chart.remove();
  }, [points, trades, asTable]);

  if (points.length === 0) return null;
  const first = Number(points[0].equity);
  const last = Number(points[points.length - 1].equity);
  const change = last - first;

  return (
    <section aria-label="Live equity" className="rounded-xl border border-line bg-surface p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="num text-sm" aria-live="polite">
          {legend ?? `${money(first)} to ${money(last)}`}
          {!legend && (
            <span className={change >= 0 ? "ml-2 text-bull" : "ml-2 text-bear"}>
              {change >= 0 ? "+" : "-"}
              {money(Math.abs(change))}
            </span>
          )}
        </p>
        <Button variant="outline" size="sm" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
          {asTable ? "Show chart" : "Show as table"}
        </Button>
      </div>
      {asTable ? (
        <div className="max-h-72 overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead className="text-right">Equity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {points.map((p) => (
                <TableRow key={p.date}>
                  <TableCell className="num">{p.date}</TableCell>
                  <TableCell className="num text-right">{money(p.equity)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div ref={container} className="h-72 w-full" />
      )}
    </section>
  );
}
