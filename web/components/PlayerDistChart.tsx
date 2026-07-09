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

// Share-of-games histogram; for Poisson-modeled stats a dotted line overlays
// the model-implied frequencies so calibration is visible at a glance.
export default function PlayerDistChart({
  bins,
  barName,
  poissonName,
}: {
  bins: DistBin[];
  barName: string;
  poissonName?: string;
}) {
  const { t } = useLang();
  if (bins.length === 0) return <p className="status">{t.charts.notEnoughData}</p>;
  const showPoisson = poissonName !== undefined && bins.some((b) => b.poisson !== undefined);
  const pct = (v: number) => `${(v * 100).toFixed(0)}%`;

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={bins} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#9aa6c0" }} />
        <YAxis tickFormatter={pct} tick={{ fontSize: 12, fill: "#9aa6c0" }} />
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
