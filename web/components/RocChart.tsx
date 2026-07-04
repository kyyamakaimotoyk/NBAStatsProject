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
import type { RocPoint } from "@/lib/perf";
import { useLang } from "@/lib/i18n";

export type RocCurveData = {
  model: string;
  label: string;
  color: string;
  auc: number;
  points: RocPoint[];
};

export default function RocChart({ curves }: { curves: RocCurveData[] }) {
  const { t } = useLang();
  if (curves.length === 0)
    return <p className="status">{t.charts.rocNotEnough}</p>;

  return (
    <ResponsiveContainer width="100%" height={380}>
      {/* No shared data: each model's curve has its own (fpr, tpr) points. */}
      <LineChart margin={{ top: 8, right: 16, bottom: 20, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis
          type="number"
          dataKey="fpr"
          domain={[0, 100]}
          unit="%"
          tick={{ fontSize: 12, fill: "#9aa6c0" }}
          label={{
            value: t.charts.rocXLabel,
            position: "insideBottom",
            offset: -8,
            fill: "#9aa6c0",
            fontSize: 12,
          }}
        />
        <YAxis
          type="number"
          dataKey="tpr"
          domain={[0, 100]}
          unit="%"
          tick={{ fontSize: 12, fill: "#9aa6c0" }}
          label={{
            value: t.charts.rocYLabel,
            angle: -90,
            position: "insideLeft",
            fill: "#9aa6c0",
            fontSize: 12,
            style: { textAnchor: "middle" },
          }}
        />
        <Tooltip contentStyle={{ background: "#141a2e", border: "1px solid #243049" }} />
        {/* Legend on top so it can't collide with the x-axis title. */}
        <Legend verticalAlign="top" height={30} />
        <ReferenceLine
          segment={[
            { x: 0, y: 0 },
            { x: 100, y: 100 },
          ]}
          stroke="#555"
          strokeDasharray="4 4"
        />
        {curves.map((c) => (
          <Line
            key={c.model}
            data={c.points}
            type="linear"
            dataKey="tpr"
            name={`${c.label} (AUC ${c.auc.toFixed(2)})`}
            stroke={c.color}
            dot={false}
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
