"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { ErrorHistBin } from "@/lib/perf";

export type HistPanel = { label: string; color: string; n: number; bins: ErrorHistBin[] };

/**
 * Small-multiple histograms, one panel per model, sharing the same x bins and
 * y scale so shapes compare honestly. The zero line marks an unbiased miss.
 */
export default function ErrorHistogram({
  panels,
  xLabel,
  gamesLabel,
}: {
  panels: HistPanel[];
  xLabel: string;
  gamesLabel: (n: number) => string;
}) {
  if (panels.length === 0) return null;
  const yMax = Math.max(
    5,
    Math.ceil(Math.max(...panels.flatMap((p) => p.bins.map((b) => b.pct))) / 5) * 5,
  );

  return (
    <div>
      <div className="hist-row">
        {panels.map((p) => (
          <div key={p.label} className="hist-cell">
            <div className="hist-title">
              {p.label} <span className="hist-n">({gamesLabel(p.n)})</span>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={p.bins} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#243049" vertical={false} />
                <XAxis
                  dataKey="x"
                  ticks={[-30, -20, -10, 0, 10, 20, 30]}
                  tick={{ fontSize: 10, fill: "#9aa6c0" }}
                />
                <YAxis
                  domain={[0, yMax]}
                  unit="%"
                  width={38}
                  tick={{ fontSize: 10, fill: "#9aa6c0" }}
                />
                <Tooltip
                  contentStyle={{ background: "#141a2e", border: "1px solid #243049" }}
                  labelFormatter={(x) => `${Number(x) >= 0 ? "+" : ""}${x} pts`}
                  formatter={(v: unknown, _name: unknown, item: unknown) => {
                    const n = ((item ?? {}) as { payload?: { n?: number } }).payload?.n ?? 0;
                    return [`${Number(v).toFixed(1)}% (${gamesLabel(n)})`, ""];
                  }}
                />
                <ReferenceLine x={0} stroke="#555" strokeDasharray="4 4" />
                <Bar
                  dataKey="pct"
                  fill={p.color}
                  fillOpacity={0.85}
                  barSize={10}
                  radius={[3, 3, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ))}
      </div>
      <div className="hist-xlabel">{xLabel}</div>
    </div>
  );
}
