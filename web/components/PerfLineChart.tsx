"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { MODEL_LABELS } from "@/lib/perf";

const COLORS: Record<string, string> = { rf: "#3b82f6", nn: "#22c55e", xgb: "#f59e0b" };

export default function PerfLineChart({
  data,
  models,
  xKey,
  xLabel,
  numericX = false,
  diagonal = false,
}: {
  data: Record<string, number | string>[];
  models: string[];
  xKey: string;
  xLabel?: string;
  numericX?: boolean; // numeric x-axis (calibration) vs category (dates)
  diagonal?: boolean; // draw the y=x perfect-calibration reference
}) {
  if (data.length === 0) return <p className="status">Not enough data in this window yet.</p>;

  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 14, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis
          dataKey={xKey}
          type={numericX ? "number" : "category"}
          domain={numericX ? [0, 100] : undefined}
          tick={{ fontSize: 12, fill: "#9aa6c0" }}
          label={
            xLabel
              ? { value: xLabel, position: "insideBottom", offset: -4, fill: "#9aa6c0", fontSize: 12 }
              : undefined
          }
        />
        <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 12, fill: "#9aa6c0" }} />
        <Tooltip contentStyle={{ background: "#141a2e", border: "1px solid #243049" }} />
        <Legend />
        {diagonal && (
          <ReferenceLine
            segment={[
              { x: 0, y: 0 },
              { x: 100, y: 100 },
            ]}
            stroke="#555"
            strokeDasharray="4 4"
            ifOverflow="extendDomain"
          />
        )}
        {models.map((m) => (
          <Line
            key={m}
            type="monotone"
            dataKey={m}
            name={MODEL_LABELS[m] ?? m}
            stroke={COLORS[m] ?? "#888"}
            dot={numericX}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
