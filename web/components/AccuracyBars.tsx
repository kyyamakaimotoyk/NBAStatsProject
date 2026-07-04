"use client";

import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  LabelList,
  ResponsiveContainer,
} from "recharts";

export type AccuracyBar = {
  name: string; // localized display name (market / model)
  pct: number; // winner-classification accuracy, 0-100
  n: number; // games behind the bar
  color: string;
};

/** Market-vs-models winner classification, one bar each. Bars start at zero
 * (never truncated), the dashed line marks coin-flip, and each bar carries its
 * value label so small differences stay readable on the honest 0-100 scale. */
export default function AccuracyBars({
  data,
  yLabel,
}: {
  data: AccuracyBar[];
  yLabel?: string;
}) {
  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} margin={{ top: 20, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#9aa6c0" }} />
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
        <Tooltip
          contentStyle={{ background: "#141a2e", border: "1px solid #243049" }}
          formatter={(v, _name, item) => {
            const n = (item?.payload as AccuracyBar | undefined)?.n;
            return [`${Number(v).toFixed(1)}%${n ? ` (${n.toLocaleString()})` : ""}`, ""];
          }}
        />
        <ReferenceLine y={50} stroke="#555" strokeDasharray="4 4" />
        <Bar dataKey="pct" isAnimationActive={false} barSize={52} radius={[4, 4, 0, 0]}>
          {data.map((d) => (
            <Cell key={d.name} fill={d.color} fillOpacity={0.85} />
          ))}
          <LabelList
            dataKey="pct"
            position="top"
            formatter={(v: unknown) => `${Number(v).toFixed(1)}%`}
            fill="#e7ecf5"
            fontSize={12}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
