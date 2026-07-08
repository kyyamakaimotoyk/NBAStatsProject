"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";

export type BucketSeries = { key: string; name: string; color: string };

/**
 * Grouped bars on an honest 0-100% scale with a coin-flip reference line.
 * A series key absent from a row draws no bar (used for under-sampled
 * buckets); the matching `<key>_n` count feeds the tooltip.
 */
export default function BucketBars({
  data,
  series,
  xKey,
  xLabel,
  yLabel,
  gamesLabel,
}: {
  data: Record<string, number | string>[];
  series: BucketSeries[];
  xKey: string;
  xLabel?: string;
  yLabel?: string;
  gamesLabel: (n: number) => string;
}) {
  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" vertical={false} />
        <XAxis
          dataKey={xKey}
          tick={{ fontSize: 12, fill: "#9aa6c0" }}
          label={
            xLabel
              ? { value: xLabel, position: "insideBottom", offset: -16, fill: "#9aa6c0", fontSize: 12 }
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
        <Tooltip
          contentStyle={{ background: "#141a2e", border: "1px solid #243049" }}
          formatter={(v: unknown, name: unknown, item: unknown) => {
            const { dataKey, payload } = (item ?? {}) as {
              dataKey?: string;
              payload?: Record<string, number>;
            };
            const n = dataKey ? payload?.[`${dataKey}_n`] : undefined;
            const pct = `${Number(v).toFixed(1)}%`;
            return [n ? `${pct} (${gamesLabel(n)})` : pct, String(name)];
          }}
        />
        <Legend verticalAlign="top" height={30} />
        <ReferenceLine y={50} stroke="#555" strokeDasharray="4 4" />
        {series.map((s) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.name}
            fill={s.color}
            fillOpacity={0.85}
            barSize={16}
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
