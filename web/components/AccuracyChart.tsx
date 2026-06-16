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
} from "recharts";
import type { RollingPoint } from "@/lib/api";

const COLORS: Record<string, string> = {
  rf: "#3b82f6",
  nn: "#22c55e",
  xgb: "#f59e0b",
};

export default function AccuracyChart({ points }: { points: RollingPoint[] }) {
  // The API returns one row per (date, model). Recharts wants one row per date
  // with a column per model, so we pivot: { game_date, rf: 62, nn: 58, ... }.
  const byDate = new Map<string, Record<string, number | string>>();
  const models = new Set<string>();
  for (const p of points) {
    models.add(p.model_type);
    const row = byDate.get(p.game_date) ?? { game_date: p.game_date };
    if (p.accuracy !== null) row[p.model_type] = Math.round(p.accuracy * 100);
    byDate.set(p.game_date, row);
  }
  const data = Array.from(byDate.values());

  if (data.length === 0)
    return <p className="status">No completed games in this window yet.</p>;

  return (
    <ResponsiveContainer width="100%" height={360}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis dataKey="game_date" tick={{ fontSize: 12, fill: "#9aa6c0" }} />
        <YAxis
          domain={[0, 100]}
          unit="%"
          tick={{ fontSize: 12, fill: "#9aa6c0" }}
        />
        <Tooltip
          contentStyle={{ background: "#141a2e", border: "1px solid #243049" }}
        />
        <Legend />
        {Array.from(models).map((m) => (
          <Line
            key={m}
            type="monotone"
            dataKey={m}
            name={m}
            stroke={COLORS[m] ?? "#888"}
            dot={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
