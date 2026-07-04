"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { TrendRow } from "@/lib/perf";

export type TrendSeries = {
  key: string;
  name: string;
  color: string;
  dashed?: boolean; // benchmark lines (e.g. the market) render dashed
};

export default function TrendChart({
  data,
  series,
  yUnit,
  yDomain,
  refY,
  xLabel,
  yLabel,
  yTickStep,
}: {
  data: TrendRow[];
  series: TrendSeries[];
  yUnit?: string;
  yDomain?: [number, number];
  refY?: number; // horizontal reference (e.g. 50% = coin flip)
  xLabel?: string;
  yLabel?: string;
  yTickStep?: number; // fixed y demarcation interval (e.g. 5 pts)
}) {
  if (data.length === 0) return <p className="status">Not enough data in this window yet.</p>;

  // Explicit ticks when a step is requested: 0, step, 2*step ... up to the max.
  let yTicks: number[] | undefined;
  let domain = yDomain;
  if (yTickStep) {
    const vals = data.flatMap((d) =>
      series.map((s) => Number(d[s.key])).filter(Number.isFinite),
    );
    const top = Math.max(yTickStep, Math.ceil(Math.max(...vals, 0) / yTickStep) * yTickStep);
    yTicks = Array.from({ length: top / yTickStep + 1 }, (_, i) => i * yTickStep);
    domain = domain ?? [0, top];
  }

  return (
    <ResponsiveContainer width="100%" height={330}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 22, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12, fill: "#9aa6c0" }}
          minTickGap={40}
          label={
            xLabel
              ? { value: xLabel, position: "insideBottom", offset: -12, fill: "#9aa6c0", fontSize: 12 }
              : undefined
          }
        />
        <YAxis
          domain={domain}
          ticks={yTicks}
          unit={yUnit}
          tick={{ fontSize: 12, fill: "#9aa6c0" }}
          label={
            yLabel
              ? { value: yLabel, angle: -90, position: "insideLeft", fill: "#9aa6c0", fontSize: 12, style: { textAnchor: "middle" } }
              : undefined
          }
        />
        <Tooltip contentStyle={{ background: "#141a2e", border: "1px solid #243049" }} />
        {/* Legend on top: the x-axis title owns the bottom edge. */}
        <Legend verticalAlign="top" height={30} />
        {refY !== undefined && <ReferenceLine y={refY} stroke="#555" strokeDasharray="4 4" />}
        {series.map((s) => (
          <Line
            key={s.key}
            type="linear"
            dataKey={s.key}
            name={s.name}
            stroke={s.color}
            strokeDasharray={s.dashed ? "6 4" : undefined}
            dot={s.dashed ? false : { r: 2.5 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
