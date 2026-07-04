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
  yLabel,
}: {
  data: Record<string, number | string>[];
  teams: string[];
  yLabel?: string;
}) {
  if (teams.length === 0) return <p className="status">Pick at least one team.</p>;
  if (data.length === 0) return <p className="status">No games for these teams in range.</p>;

  return (
    <ResponsiveContainer width="100%" height={420}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 22, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          minTickGap={40}
          label={{ value: "Game date", position: "insideBottom", offset: -12, fill: "#9aa6c0", fontSize: 12 }}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          width={56}
          label={
            yLabel
              ? { value: yLabel, angle: -90, position: "insideLeft", fill: "#9aa6c0", fontSize: 12, style: { textAnchor: "middle" } }
              : undefined
          }
        />
        <Tooltip contentStyle={{ background: "#141a2e", border: "1px solid #243049" }} />
        {/* Legend on top so it can't collide with the x-axis title. */}
        <Legend verticalAlign="top" height={30} />
        {teams.map((t, i) => (
          <Line
            key={t}
            type="linear"
            dataKey={t}
            stroke={PALETTE[i % PALETTE.length]}
            dot={{ r: 2 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
