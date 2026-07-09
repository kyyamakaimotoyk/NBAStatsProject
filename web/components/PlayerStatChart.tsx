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
import { useLang } from "@/lib/i18n";

export type PlayerChartRow = {
  label: string; // short date for the x-axis
  date: string; // full ISO date (tooltip)
  opp: string | null;
  is_home: number;
  actual: number | null;
  pred: number | null;
};

// Hover card: date, opponent (vs/@), predicted and actual — per the page spec.
function GameTooltip({
  active,
  payload,
  statLabel,
  t,
}: {
  active?: boolean;
  payload?: { payload: PlayerChartRow }[];
  statLabel: string;
  t: ReturnType<typeof useLang>["t"];
}) {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0].payload;
  return (
    <div
      style={{
        background: "#141a2e",
        border: "1px solid #243049",
        padding: "8px 10px",
        fontSize: 12,
      }}
    >
      <div>
        <strong>{row.date}</strong> · {row.is_home ? "vs." : "@"} {row.opp ?? "?"}
      </div>
      <div style={{ color: "#f59e0b" }}>
        {t.playersExplore.predicted} {statLabel}:{" "}
        {row.pred != null ? row.pred.toFixed(1) : "—"}
      </div>
      <div style={{ color: "#3b82f6" }}>
        {t.playersExplore.actual} {statLabel}: {row.actual != null ? row.actual : "—"}
      </div>
    </div>
  );
}

export default function PlayerStatChart({
  data,
  statLabel,
}: {
  data: PlayerChartRow[];
  statLabel: string;
}) {
  const { t } = useLang();
  if (data.length === 0) return <p className="status">{t.charts.notEnoughData}</p>;

  return (
    <ResponsiveContainer width="100%" height={330}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#9aa6c0" }} minTickGap={40} />
        <YAxis tick={{ fontSize: 12, fill: "#9aa6c0" }} />
        <Tooltip content={<GameTooltip statLabel={statLabel} t={t} />} />
        <Legend verticalAlign="top" height={30} />
        <Line
          type="linear"
          dataKey="actual"
          name={`${t.playersExplore.actual} ${statLabel}`}
          stroke="#3b82f6"
          dot={{ r: 2.5 }}
          connectNulls
        />
        <Line
          type="linear"
          dataKey="pred"
          name={`${t.playersExplore.predicted} ${statLabel}`}
          stroke="#f59e0b"
          strokeDasharray="6 4"
          dot={{ r: 2 }}
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
