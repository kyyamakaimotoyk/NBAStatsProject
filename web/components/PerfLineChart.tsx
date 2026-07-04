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
import { useLang } from "@/lib/i18n";

const COLORS: Record<string, string> = { rf: "#3b82f6", nn: "#22c55e", xgb: "#f59e0b" };

export default function PerfLineChart({
  data,
  models,
  xKey,
  xLabel,
  yLabel,
  numericX = false,
  diagonal = false,
}: {
  data: Record<string, number | string>[];
  models: string[];
  xKey: string;
  xLabel?: string;
  yLabel?: string;
  numericX?: boolean; // numeric x-axis (calibration) vs category (dates)
  diagonal?: boolean; // draw the y=x perfect-calibration reference
}) {
  const { t } = useLang();
  if (data.length === 0) return <p className="status">{t.charts.notEnoughData}</p>;

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
        <YAxis
          domain={[0, 100]}
          unit="%"
          tick={{ fontSize: 12, fill: "#9aa6c0" }}
          label={
            yLabel
              ? { value: yLabel, angle: -90, position: "insideLeft", fill: "#9aa6c0", fontSize: 12, style: { textAnchor: "middle" } }
              : undefined
          }
        />
        <Tooltip contentStyle={{ background: "#141a2e", border: "1px solid #243049" }} />
        {/* Legend on top so it can't collide with the x-axis title. */}
        <Legend verticalAlign="top" height={30} />
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
            type="linear"
            dataKey={m}
            name={t.models[m] ?? m}
            stroke={COLORS[m] ?? "#888"}
            dot={{ r: 2.5 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
