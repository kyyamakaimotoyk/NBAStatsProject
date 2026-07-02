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
}: {
  data: TrendRow[];
  series: TrendSeries[];
  yUnit?: string;
  yDomain?: [number, number];
  refY?: number; // horizontal reference (e.g. 50% = coin flip)
}) {
  if (data.length === 0) return <p className="status">Not enough data in this window yet.</p>;

  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis dataKey="date" tick={{ fontSize: 12, fill: "#9aa6c0" }} minTickGap={40} />
        <YAxis domain={yDomain} unit={yUnit} tick={{ fontSize: 12, fill: "#9aa6c0" }} />
        <Tooltip contentStyle={{ background: "#141a2e", border: "1px solid #243049" }} />
        <Legend />
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
