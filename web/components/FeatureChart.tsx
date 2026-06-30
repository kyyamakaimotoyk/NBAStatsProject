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

const PALETTE = [
  "#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#14b8a6", "#eab308", "#ec4899",
];

export default function FeatureChart({
  data,
  teams,
}: {
  data: Record<string, number | string>[];
  teams: string[];
}) {
  if (teams.length === 0) return <p className="status">Pick at least one team.</p>;
  if (data.length === 0) return <p className="status">No games for these teams in range.</p>;

  return (
    <ResponsiveContainer width="100%" height={420}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#9aa6c0" }} minTickGap={40} />
        <YAxis tick={{ fontSize: 11, fill: "#9aa6c0" }} width={56} />
        <Tooltip contentStyle={{ background: "#141a2e", border: "1px solid #243049" }} />
        <Legend />
        {teams.map((t, i) => (
          <Line
            key={t}
            type="monotone"
            dataKey={t}
            stroke={PALETTE[i % PALETTE.length]}
            dot={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
