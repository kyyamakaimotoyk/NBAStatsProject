"use client";

import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { DistBin } from "@/lib/playerExplore";
import { useLang } from "@/lib/i18n";

// Share-of-games histogram on FIXED per-stat bins, so charts are directly
// comparable across players. The Y axis holds a fixed cap per stat family
// (yCap) and only expands when a bar would otherwise clip. For Poisson stats
// a dotted line overlays the model-implied frequencies.
export default function PlayerDistChart({
  bins,
  barName,
  poissonName,
  yCap = 0.4,
}: {
  bins: DistBin[];
  barName: string;
  poissonName?: string;
  yCap?: number;
}) {
  const { t } = useLang();
  if (bins.length === 0) return <p className="status">{t.charts.notEnoughData}</p>;
  const showPoisson = poissonName !== undefined && bins.some((b) => b.poisson !== undefined);
  const pct = (v: number) => `${Math.round(v * 100)}%`;

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={bins} margin={{ top: 8, right: 24, bottom: 12, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          tickMargin={6}
          interval={0}
        />
        <YAxis
          domain={[0, (dataMax: number) => Math.max(yCap, Math.ceil(dataMax * 10) / 10)]}
          tickFormatter={pct}
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          tickMargin={4}
          width={44}
          allowDecimals
        />
        <Tooltip
          contentStyle={{ background: "#141a2e", border: "1px solid #243049" }}
          formatter={(value) => pct(Number(value))}
        />
        <Legend verticalAlign="top" height={30} />
        <Bar dataKey="share" name={barName} fill="#3b82f6" fillOpacity={0.75} />
        {showPoisson && (
          <Line
            type="linear"
            dataKey="poisson"
            name={poissonName}
            stroke="#f59e0b"
            dot={{ r: 2.5 }}
            connectNulls
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
